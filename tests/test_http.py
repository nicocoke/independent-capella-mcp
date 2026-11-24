import asyncio
import json
import unittest
from unittest.mock import patch
from development_http import DevelopmentApp
from capella_groundwork.protocol import VERSION


TOKEN = "synthetic-test-token-never-use-outside-tests"


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.app = DevelopmentApp(token=TOKEN, origins=["https://example.test"])

    def call(self, message, *, session=None, token=TOKEN, origin="https://example.test", method="POST"):
        events = []
        headers = [(b"authorization", ("Bearer " + token).encode()),
                   (b"origin", origin.encode()), (b"content-type", b"application/json"),
                   (b"accept", b"application/json, text/event-stream")]
        if session:
            headers += [(b"mcp-session-id", session.encode()), (b"mcp-protocol-version", VERSION.encode())]
        async def receive():
            return {"type": "http.request", "body": json.dumps(message).encode()}
        async def send(event):
            events.append(event)
        with patch("socket.socket", side_effect=AssertionError("No sockets")), \
             patch("subprocess.Popen", side_effect=AssertionError("No processes")):
            # asyncio.run may itself create a wakeup socket on some platforms.
            # The coroutine has no suspending IO; drive it directly instead.
            coroutine = self.app({"type": "http", "scheme": "https", "path": "/mcp",
                                  "method": method, "headers": headers}, receive, send)
            try:
                coroutine.send(None)
            except StopIteration:
                pass
            else:
                coroutine.close()
                self.fail("Unexpected external await")
        return events

    def initialize(self):
        events = self.call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        self.assertEqual(200, events[0]["status"])
        return dict(events[0]["headers"])[b"mcp-session-id"].decode()

    def test_initialize_notify_and_list(self):
        session = self.initialize()
        events = self.call({"jsonrpc": "2.0", "method": "notifications/initialized"}, session=session)
        self.assertEqual(202, events[0]["status"])
        events = self.call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session=session)
        self.assertEqual(3, len(json.loads(events[1]["body"])["result"]["tools"]))

    def test_denies_wrong_token_and_origin(self):
        self.assertEqual(401, self.call({}, token="wrong")[0]["status"])
        self.assertEqual(403, self.call({}, origin="https://evil.test")[0]["status"])

    def test_unknown_session(self):
        self.assertEqual(404, self.call({}, session="missing")[0]["status"])

    def test_delete_session(self):
        session = self.initialize()
        self.assertEqual(204, self.call({}, session=session, method="DELETE")[0]["status"])
        self.assertEqual(404, self.call({}, session=session)[0]["status"])

    def test_bounded_sessions(self):
        self.app = DevelopmentApp(token=TOKEN, origins=["https://example.test"], max_sessions=1)
        self.initialize()
        events = self.call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        self.assertEqual(503, events[0]["status"])

    def test_expired_session(self):
        session = self.initialize()
        with patch("development_http.time.monotonic", return_value=10**15):
            self.assertEqual(404, self.call({}, session=session)[0]["status"])
