import io
import json
from pathlib import Path
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from local_bridge import (validate_headers, strict_json, dispatch,
    LocalTools, SCOPE, CONNECTOR, connection_values, dispatch_tool, SharedBridge, StateBusy)
from capella_groundwork.protocol import Protocol, serve, VERSION
from relay.store import Ledger


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.token = "a" * 43
        self.headers = [("Host", "127.0.0.1:4321"), ("Authorization", "Bearer " + self.token),
                        ("Content-Type", "application/json"), ("Content-Length", "2")]
        self.ledger = Ledger(sqlite3.connect(":memory:"))
        self.snapshot = {"model_id": "native-model", "revision": 0, "session_epoch": "local-epoch",
                         "elements": [{"alias": "logical-system", "type": "LogicalComponent"},
                                      {"alias": "root-function", "type": "LogicalFunction"}]}

    def tearDown(self):
        self.ledger.close()

    def test_literal_host_and_credential_required(self):
        self.assertEqual(2, validate_headers(self.headers, "127.0.0.1", 4321, self.token))
        for name, value in [("Host", "localhost:4321"), ("Host", "example.com:4321"),
                            ("Host", "127.0.0.1:4322"), ("Authorization", "Bearer wrong")]:
            changed = [(key, value if key == name else original) for key, original in self.headers]
            with self.assertRaises(PermissionError):
                validate_headers(changed, "127.0.0.1", 4321, self.token)
        with self.assertRaises(PermissionError):
            validate_headers(self.headers, "192.168.1.2", 4321, self.token)

    def test_browser_smuggling_and_duplicate_headers_denied(self):
        for extra in [("Origin", "null"), ("Transfer-Encoding", "chunked"), ("Expect", "100-continue"),
                      ("Content-Encoding", "gzip"), ("host", "127.0.0.1:4321")]:
            with self.assertRaises(ValueError):
                validate_headers(self.headers + [extra], "127.0.0.1", 4321, self.token)

    def test_bounded_lengths(self):
        for size in ("0", "-1", "262145", "99999999999999999999", "2,2", "", "NaN"):
            with self.assertRaises(ValueError):
                validate_headers([(key, size if key == "Content-Length" else value) for key, value in self.headers],
                                 "127.0.0.1", 4321, self.token)

    def test_strict_json(self):
        for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{}{}', b'\xff', b' ' * 262145):
            with self.assertRaises((ValueError, UnicodeDecodeError)):
                strict_json(payload)

    def test_native_job_flow_reuses_ledger_guards(self):
        self.assertEqual({"published": True}, dispatch(self.ledger, "/connector/snapshot", self.snapshot))
        self.assertEqual(self.snapshot, self.ledger.snapshot(SCOPE))
        self.assertEqual({"job": None}, dispatch(self.ledger, "/connector/claim", {}))
        for route, body in [("/mcp", {}), ("/connector/claim", {"scope": "other"}),
                            ("/connector/result", {"job_id": "a" * 32, "lease": "g" * 48, "status": "rejected", "result": {}})]:
            with self.assertRaises(ValueError):
                dispatch(self.ledger, route, body)

    def test_connection_tool_does_not_disclose_credentials(self):
        bridge = SimpleNamespace(ledger=self.ledger, profile=Path("connection.json"), token=self.token)
        tools = LocalTools(bridge)
        response = tools.call("capella_connection", {})
        self.assertFalse(response["structuredContent"]["connected"])
        self.assertNotIn(self.token, json.dumps(response))
        self.assertTrue(tools.call("capella_connection", {"token": "wrong"})["isError"])
        self.ledger.bind(SCOPE, CONNECTOR, self.snapshot)
        self.assertTrue(tools.call("capella_connection", {})["structuredContent"]["connected"])

    def test_live_protocol_injection_keeps_stdio_clean(self):
        tools = LocalTools(SimpleNamespace(ledger=self.ledger, profile=Path("connection.json")))
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        reader = io.BytesIO(("\n".join(json.dumps(message) for message in messages) + "\n").encode())
        writer = io.BytesIO()
        serve(reader, writer, Protocol(tools, tools.catalogue, server_info={"name": "local", "version": "test"}))
        replies = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual("local", replies[0]["result"]["serverInfo"]["name"])
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertEqual(6, len(names))
        self.assertIn("capella_submit", names)

    def test_follower_profile_cannot_route_outside_loopback(self):
        profile = {"format": "capella-local-bridge/1", "origin": "http://127.0.0.1:4321", "token": self.token}
        self.assertEqual((4321, self.token), connection_values(json.dumps(profile).encode()))
        for origin in ("https://127.0.0.1:4321", "http://localhost:4321", "http://192.168.1.2:4321",
                       "http://127.0.0.1:65536", "http://127.0.0.1:0", "http://127.0.0.1:4321/path",
                       "http://user@127.0.0.1:4321", "http://127.0.0.1:4321?query", None):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                connection_values(json.dumps(dict(profile, origin=origin)).encode())

    def test_internal_tool_route_rejects_arbitrary_names_and_fields(self):
        bridge = SimpleNamespace(ledger=self.ledger, profile=Path("connection.json"))
        for body in ({}, {"name": "eval", "arguments": {}}, {"name": [], "arguments": {}},
                     {"name": "capella_connection", "arguments": [], "extra": True}):
            with self.assertRaises(ValueError):
                dispatch_tool(bridge, body)
        self.assertFalse(dispatch_tool(bridge, {"name": "capella_connection", "arguments": {}})["isError"])

    def test_shared_broker_lock_contention_does_not_close_stdio(self):
        with patch("local_bridge.LocalBridge") as bridge_class:
            bridge_class.return_value.__enter__.side_effect = StateBusy("test contention")
            with SharedBridge(Path("not-accessed")) as shared:
                self.assertIsNone(shared.owner)
                self.assertEqual(6, len(shared.protocol().catalogue()))
            bridge_class.return_value.__exit__.assert_not_called()

    def test_shared_broker_owner_closes_once(self):
        with patch("local_bridge.LocalBridge") as bridge_class:
            with SharedBridge(Path("not-accessed")) as shared:
                self.assertIsNotNone(shared.owner)
                shared._elect()
            self.assertEqual(1, bridge_class.call_count)
            bridge_class.return_value.__exit__.assert_called_once()

    def test_follower_communication_error_returns_error_without_retry(self):
        with patch("local_bridge.LocalBridge") as bridge_class, patch("pathlib.Path.open", side_effect=OSError("test failure")):
            bridge_class.return_value.__enter__.side_effect = StateBusy("test contention")
            shared = SharedBridge(Path("not-accessed"))
            response = shared.call("capella_submit", {})
            self.assertTrue(response["isError"])
            self.assertIn("No automatic retry", response["content"][0]["text"])
            self.assertEqual(1, bridge_class.call_count)
