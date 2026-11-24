import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from relay.store import Ledger, Conflict
from relay.service import NativeTools
from relay.app import RelayApp
from capella_groundwork.protocol import VERSION

CLIENT = "test-client-credential-0000000000000000"
CONNECTOR = "test-connector-credential-00000000000000"


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.store = Ledger(sqlite3.connect(":memory:"), clock=lambda: self.now)
        self.snapshot = {"model_id": "native-model", "revision": 0, "session_epoch": "test-epoch", "elements": [
            {"alias": "logical-system", "type": "LogicalComponent"},
            {"alias": "root-function", "type": "LogicalFunction"}]}
        self.store.bind("project-A", "connector-A", self.snapshot)
        self.service = NativeTools(self.store, "project-A")
        self.plan = json.loads((Path(__file__).resolve().parents[1] / "examples/logical-monitoring.json").read_text())
        self.plan["model_id"] = "native-model"
        self.app = RelayApp(self.store, {
            CLIENT: {"role": "client", "scope": "project-A"},
            CONNECTOR: {"role": "connector", "scope": "project-A", "connector": "connector-A"}}, ["https://example.test"])

    def tearDown(self):
        self.store.close()

    def submit(self, key="request-A"):
        prepared = self.service.call("capella_prepare", {"plan": self.plan})["structuredContent"]
        args = {"plan": self.plan, "preview_digest": prepared["preview_digest"], "request_id": key}
        return self.service.call("capella_submit", args)["structuredContent"], args

    def test_complete_job_and_retry_after_revision_changed(self):
        job, args = self.submit()
        claimed = self.store.claim("project-A", "connector-A")
        result = self.store.finish("project-A", "connector-A", job["job_id"], claimed["lease"], "succeeded_unsaved", {"saved": False})
        self.store.bind("project-A", "connector-A", dict(self.snapshot, revision=1))
        retry = self.service.call("capella_submit", args)
        self.assertFalse(retry["isError"])
        self.assertEqual(result, retry["structuredContent"])

    def test_unknown_outcome_blocks_new_edits(self):
        job, _ = self.submit()
        self.store.claim("project-A", "connector-A")
        self.submit("request-B")
        self.now += 121
        self.assertIsNone(self.store.claim("project-A", "connector-A"))
        self.assertEqual("unknown_outcome", self.store.get("project-A", job["job_id"])["status"])

    def test_late_receipt_reconciles_expired_lease(self):
        job, _ = self.submit()
        claimed = self.store.claim("project-A", "connector-A")
        self.now += 121
        self.store.claim("project-A", "connector-A")
        self.assertEqual("succeeded_unsaved", self.store.finish("project-A", "connector-A", job["job_id"], claimed["lease"], "succeeded_unsaved", {})["status"])

    def test_scope_and_connector_isolation(self):
        job, _ = self.submit()
        for call in (lambda: self.store.get("project-B", job["job_id"]),
                     lambda: self.store.claim("project-A", "connector-B"),
                     lambda: self.store.bind("project-A", "connector-B", self.snapshot)):
            with self.assertRaises(Conflict): call()

    def test_bad_lease_and_conflicting_receipt(self):
        job, _ = self.submit()
        claimed = self.store.claim("project-A", "connector-A")
        with self.assertRaises(Conflict):
            self.store.finish("project-A", "connector-A", job["job_id"], "wrong", "rejected", {})
        self.store.finish("project-A", "connector-A", job["job_id"], claimed["lease"], "rejected", {})
        with self.assertRaises(Conflict):
            self.store.finish("project-A", "connector-A", job["job_id"], claimed["lease"], "succeeded_unsaved", {})

    def test_cancel_only_before_claim(self):
        job, _ = self.submit()
        self.assertEqual("cancelled", self.store.cancel("project-A", job["job_id"])["status"])
        job, _ = self.submit("request-B")
        self.store.claim("project-A", "connector-A")
        with self.assertRaises(Conflict): self.store.cancel("project-A", job["job_id"])

    def test_epoch_invalidates_preview(self):
        _, args = self.submit()
        args["request_id"] = "new-request"
        self.store.bind("project-A", "connector-A", dict(self.snapshot, session_epoch="new-epoch"))
        self.assertTrue(self.service.call("capella_submit", args)["isError"])

    def test_snapshot_expiry(self):
        self.now += 121
        self.assertTrue(self.service.call("capella_prepare", {"plan": self.plan})["isError"])

    def test_client_sees_expired_execution_without_connector_poll(self):
        job, _ = self.submit()
        self.store.claim("project-A", "connector-A")
        self.now += 121
        self.assertEqual("unknown_outcome", self.store.get("project-A", job["job_id"])["status"])

    def test_pending_queue_is_bounded(self):
        for index in range(32):
            self.submit("queued-" + str(index))
        prepared = self.service.call("capella_prepare", {"plan": self.plan})["structuredContent"]
        response = self.service.call("capella_submit", {"plan": self.plan,
            "preview_digest": prepared["preview_digest"], "request_id": "overflow"})
        self.assertTrue(response["isError"])

    def test_disk_restart_preserves_uncertain_job(self):
        # Only an explicitly created package-owned temporary folder is used.
        scratch = Path(__file__).resolve().parents[3] / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ledger-test-", dir=scratch) as directory:
            path = Path(directory) / "test.sqlite3"
            first = Ledger(sqlite3.connect(path), clock=lambda: self.now)
            first.bind("p", "c", self.snapshot)
            job = first.submit("p", "r", {"plan_digest": "x"})
            first.claim("p", "c")
            first.close()
            self.now += 121
            second = Ledger(sqlite3.connect(path), clock=lambda: self.now)
            self.assertIsNone(second.claim("p", "c"))
            self.assertEqual("unknown_outcome", second.get("p", job["job_id"])["status"])
            second.close()

    def call_http(self, path, body, token, session=None):
        events = []
        headers = [(b"authorization", ("Bearer " + token).encode()), (b"content-type", b"application/json"),
                   (b"accept", b"application/json, text/event-stream")]
        if session: headers += [(b"mcp-session-id", session.encode()), (b"mcp-protocol-version", VERSION.encode())]
        async def receive(): return {"type": "http.request", "body": json.dumps(body).encode()}
        async def send(event): events.append(event)
        coroutine = self.app({"type": "http", "scheme": "https", "path": path, "method": "POST", "headers": headers}, receive, send)
        with patch("socket.socket", side_effect=AssertionError("No sockets")), patch("subprocess.Popen", side_effect=AssertionError("No processes")):
            try: coroutine.send(None)
            except StopIteration: pass
            else:
                coroutine.close()
                self.fail("Unexpected network await")
        return events[0], json.loads(events[1]["body"]) if events[1]["body"] else None

    def test_connector_http_routes(self):
        self.assertEqual(200, self.call_http("/connector/snapshot", self.snapshot, CONNECTOR)[0]["status"])
        job, _ = self.submit()
        head, claimed = self.call_http("/connector/claim", {}, CONNECTOR)
        self.assertEqual(job["job_id"], claimed["job"]["job_id"])
        receipt = {"job_id": job["job_id"], "lease": claimed["job"]["lease"], "status": "succeeded_unsaved", "result": {}}
        self.assertEqual(200, self.call_http("/connector/result", receipt, CONNECTOR)[0]["status"])

    def test_client_cannot_claim_and_connector_cannot_call_mcp(self):
        self.assertEqual(403, self.call_http("/connector/claim", {}, CLIENT)[0]["status"])
        self.assertEqual(404, self.call_http("/mcp", {}, CONNECTOR)[0]["status"])

    def test_native_tools_are_advertised_over_mcp(self):
        head, body = self.call_http("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}, CLIENT)
        session = dict(head["headers"])[b"mcp-session-id"].decode()
        self.call_http("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, CLIENT, session)
        _, body = self.call_http("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, CLIENT, session)
        self.assertEqual(5, len(body["result"]["tools"]))

    def test_duplicate_request_returns_existing_job(self):
        first, args = self.submit()
        self.assertEqual(first, self.service.call("capella_submit", args)["structuredContent"])

    def test_invalid_receipt_and_snapshot_rejected(self):
        self.assertEqual(400, self.call_http("/connector/result", {}, CONNECTOR)[0]["status"])
        self.assertEqual(400, self.call_http("/connector/snapshot", dict(self.snapshot, revision=True), CONNECTOR)[0]["status"])

    def test_no_automatic_claim_retry(self):
        self.submit()
        self.assertIsNotNone(self.store.claim("project-A", "connector-A"))
        self.assertIsNone(self.store.claim("project-A", "connector-A"))

    def test_full_mcp_to_connector_contract(self):
        head, _ = self.call_http("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}, CLIENT)
        session = dict(head["headers"])[b"mcp-session-id"].decode()
        self.call_http("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, CLIENT, session)
        def tool(name, args):
            _, body = self.call_http("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": name, "arguments": args}}, CLIENT, session)
            self.assertFalse(body["result"]["isError"])
            return body["result"]["structuredContent"]
        prepared = tool("capella_prepare", {"plan": self.plan})
        job = tool("capella_submit", {"plan": self.plan, "preview_digest": prepared["preview_digest"], "request_id": "full-flow"})
        _, response = self.call_http("/connector/claim", {}, CONNECTOR)
        claimed = response["job"]
        self.assertEqual(13, len(claimed["payload"]["commands"]))
        self.assertEqual("test-epoch", claimed["payload"]["session_epoch"])
        # Emulate the native receipt, explicitly not a test of native Capella behavior.
        self.call_http("/connector/result", {"job_id": job["job_id"], "lease": claimed["lease"],
            "status": "succeeded_unsaved", "result": {"created_aliases": 13, "saved": False}}, CONNECTOR)
        outcome = tool("capella_job", {"job_id": job["job_id"]})
        self.assertEqual("succeeded_unsaved", outcome["status"])
        self.assertFalse(outcome["result"]["saved"])
