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
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND request_key=?", (scope, request_key)).fetchone()
            if row:
                if row["digest"] != digest:
                    raise Conflict("Idempotency key reused for another payload")
                return self._public(row)
            self.snapshot(scope)
            if self.db.execute("SELECT COUNT(*) FROM jobs WHERE scope=? AND status='queued'", (scope,)).fetchone()[0] >= 32:
                raise Conflict("Pending job capacity reached")
            identifier = secrets.token_hex(16)
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
        return {"job_id": row["id"], "status": row["status"],
                "result": json.loads(row["result"]) if row["result"] else None}

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

    def claim(self, scope, connector):
        with self.lock, self.db:
            model = self.db.execute("SELECT connector FROM models WHERE scope=?", (scope,)).fetchone()
            if not model or model[0] != connector:
                raise Conflict("Connector is not paired to this scope")
            self._expire(scope)
            # A session cannot accept more edits until every unknown outcome is reconciled.
            if self.db.execute("SELECT 1 FROM jobs WHERE scope=? AND status IN ('executing','unknown_outcome')", (scope,)).fetchone():
                return None
            row = self.db.execute("SELECT * FROM jobs WHERE scope=? AND status='queued' ORDER BY created,id LIMIT 1", (scope,)).fetchone()
            if not row:
                return None
            lease = secrets.token_hex(24)
            updated = self.db.execute("UPDATE jobs SET status='executing',lease=?,deadline=? WHERE id=? AND status='queued' AND NOT EXISTS (SELECT 1 FROM jobs WHERE scope=? AND status IN ('executing','unknown_outcome'))",
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
