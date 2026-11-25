"""Durable job ledger. The caller supplies the SQLite connection/location.

An expired lease becomes unknown_outcome, NEVER an automatic retry. Native edits
and this database cannot participate in one transaction.
"""
import hashlib
import json
import secrets
import sqlite3
import threading
import time


class Conflict(ValueError):
    pass


_EDIT_BLOCKING = """scope=? AND (status='executing' OR (status='unknown_outcome' AND NOT EXISTS
    (SELECT 1 FROM job_reviews WHERE job_id=jobs.id AND receipt=COALESCE(jobs.result,''))))"""


class Ledger:
    def __init__(self, connection, clock=time.time):
        self.db, self.clock, self.lock = connection, clock, threading.RLock()
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS models (
          scope TEXT PRIMARY KEY, connector TEXT NOT NULL, snapshot TEXT NOT NULL,
          updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, scope TEXT NOT NULL, request_key TEXT NOT NULL,
          digest TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
          lease TEXT, deadline REAL, result TEXT, created REAL NOT NULL,
          UNIQUE(scope, request_key));
        CREATE INDEX IF NOT EXISTS pending_jobs ON jobs(scope,status,created);
        CREATE TABLE IF NOT EXISTS job_reviews (
          job_id TEXT NOT NULL REFERENCES jobs(id), receipt TEXT NOT NULL,
          reviewed_at REAL NOT NULL, PRIMARY KEY(job_id,receipt));
        ''')

    def close(self):
        self.db.close()

    def bind(self, scope, connector, snapshot):
        encoded = json.dumps(snapshot, allow_nan=False)
        if len(encoded) > 500000:
            raise ValueError("Snapshot too large")
        with self.lock, self.db:
            old = self.db.execute("SELECT connector FROM models WHERE scope=?", (scope,)).fetchone()
            if old and old[0] != connector:
                raise Conflict("Scope already bound to another connector")
            self.db.execute("INSERT INTO models VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET snapshot=excluded.snapshot,updated=excluded.updated",
                            (scope, connector, encoded, self.clock()))

    def snapshot(self, scope):
        with self.lock:
            row = self.db.execute("SELECT snapshot,updated FROM models WHERE scope=?", (scope,)).fetchone()
            if not row:
                raise Conflict("No explicitly paired native session")
            if self.clock() - row[1] > 120:
                raise Conflict("Native snapshot expired; connector must publish again")
            return json.loads(row[0])

    def submit(self, scope, request_key, payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        if len(encoded) > 262144:
            raise ValueError("Plan too large")
        with self.lock:
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND request_key=?", (scope, request_key)).fetchone()
            if row:
                if row["digest"] != digest:
                    raise Conflict("Idempotency key reused for another payload")
                return self.get(scope, row["id"])
            self.snapshot(scope)
            blocker = self.edit_blocker(scope)
            if blocker and blocker["status"] == "unknown_outcome":
                raise Conflict(f"Edits blocked by job {blocker['job_id']} (unknown_outcome). "
                               "Check that job and reconcile its outcome before submitting new edits.")
            if self.db.execute("SELECT COUNT(*) FROM jobs WHERE scope=? AND status='queued'", (scope,)).fetchone()[0] >= 32:
                raise Conflict("Pending job capacity reached")
            identifier = secrets.token_hex(16)
            with self.db:
                self.db.execute("INSERT INTO jobs(id,scope,request_key,digest,payload,status,created) VALUES(?,?,?,?,?,'queued',?)",
                                (identifier, scope, request_key, digest, encoded, self.clock()))
            return self.get(scope, identifier)

    def retry(self, scope, request_key, plan_digest, preview_digest):
        with self.lock, self.db:
            self._expire(scope)
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND request_key=?", (scope, request_key)).fetchone()
            if not row:
                return None
            payload = json.loads(row["payload"])
            expected_preview = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if payload["plan_digest"] != plan_digest or expected_preview != preview_digest:
                raise Conflict("Idempotency key reused with a different plan or preview")
            return self._public(row)

    def _public(self, row):
        result = {"job_id": row["id"], "status": row["status"],
                  "result": json.loads(row["result"]) if row["result"] else None}
        if row["status"] == "queued":
            blocker = self._edit_blocker(row["scope"])
            if blocker:
                result["blocked_by"] = blocker
        if row["status"] == "unknown_outcome":
            review = self.db.execute("SELECT reviewed_at FROM job_reviews WHERE job_id=? AND receipt=?",
                                     (row["id"], row["result"] or "")).fetchone()
            if review:
                result["operator_reviewed_at"] = review["reviewed_at"]
        return result

    def get(self, scope, identifier):
        with self.lock, self.db:
            self._expire(scope)
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND id=?", (scope, identifier)).fetchone()
            if not row:
                raise Conflict("Unknown job in this scope")
            return self._public(row)

    def _expire(self, scope):
        self.db.execute("UPDATE jobs SET status='unknown_outcome' WHERE scope=? AND status='executing' AND deadline<?",
                        (scope, self.clock()))

    def _edit_blocker(self, scope):
        row = self.db.execute(f"SELECT id, status FROM jobs WHERE {_EDIT_BLOCKING} "
                              "ORDER BY CASE status WHEN 'unknown_outcome' THEN 0 ELSE 1 END, created, id LIMIT 1",
                              (scope,)).fetchone()
        return {"job_id": row["id"], "status": row["status"]} if row else None

    def edit_blocker(self, scope):
        with self.lock, self.db:
            self._expire(scope)
            return self._edit_blocker(scope)

    def record_operator_review(self, scope, identifier):
        """Record a local operator's review without modifying the native receipt or replaying a job."""
        with self.lock, self.db:
            row = self.db.execute("SELECT status,result FROM jobs WHERE scope=? AND id=?", (scope, identifier)).fetchone()
            if not row or row["status"] != "unknown_outcome":
                raise Conflict("Only a job with unknown_outcome can be reviewed")
            if self.db.execute("SELECT 1 FROM jobs WHERE scope=? AND status IN ('executing','queued')", (scope,)).fetchone():
                raise Conflict("An edit is executing or queued. Resolve it before recording this review.")
            self.db.execute("INSERT OR IGNORE INTO job_reviews VALUES (?, ?, ?)",
                            (identifier, row["result"] or "", self.clock()))

    def claim(self, scope, connector):
        with self.lock, self.db:
            model = self.db.execute("SELECT connector FROM models WHERE scope=?", (scope,)).fetchone()
            if not model or model[0] != connector:
                raise Conflict("Connector is not paired to this scope")
            self._expire(scope)
            # A session cannot accept more edits until every unknown outcome is reconciled.
            if self._edit_blocker(scope):
                return None
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND status='queued' ORDER BY created,id LIMIT 1", (scope,)).fetchone()
            if not row:
                return None
            lease = secrets.token_hex(24)
            updated = self.db.execute("UPDATE jobs SET status='executing',lease=?,deadline=? WHERE id=? AND status='queued' "
                                      f"AND NOT EXISTS (SELECT 1 FROM jobs WHERE {_EDIT_BLOCKING})",
                            (lease, self.clock() + 120, row["id"], scope))
            if updated.rowcount != 1:
                return None
            return {"job_id": row["id"], "lease": lease, "payload": json.loads(row["payload"])}

    def finish(self, scope, connector, identifier, lease, status, result):
        if status not in {"succeeded_unsaved", "rejected", "unknown_outcome"}:
            raise ValueError("Invalid terminal status")
        encoded = json.dumps(result, allow_nan=False)
        if len(encoded) > 500000:
            raise ValueError("Result too large")
        with self.lock, self.db:
            model = self.db.execute("SELECT connector FROM models WHERE scope=?", (scope,)).fetchone()
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND id=?", (scope, identifier)).fetchone()
            if not model or model[0] != connector or not row or not lease or row["lease"] != lease:
                raise Conflict("Invalid connector or lease")
            if row["status"] not in {"executing", "unknown_outcome"}:
                if row["status"] == status and row["result"] == encoded:
                    return self._public(row)
                raise Conflict("Receipt conflicts with terminal result")
            self.db.execute("UPDATE jobs SET status=?,result=? WHERE id=?", (status, encoded, identifier))
            return self.get(scope, identifier)

    def cancel(self, scope, identifier):
        with self.lock, self.db:
            row = self.get(scope, identifier)
            if row["status"] != "queued":
                raise Conflict("Only unclaimed jobs can be cancelled")
            changed = self.db.execute("UPDATE jobs SET status='cancelled' WHERE scope=? AND id=? AND status='queued'", (scope, identifier))
            if changed.rowcount != 1:
                raise Conflict("Job was claimed before cancellation")
            return self.get(scope, identifier)
