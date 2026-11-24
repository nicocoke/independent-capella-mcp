import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from capella_groundwork.protocol import Protocol, serve, MAX_LINE, VERSION
from capella_groundwork.compiler import compile_plan


def request(method, params=None, identifier=1):
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or {}})


def initialize(protocol):
    result = protocol.receive(request("initialize", {"protocolVersion": VERSION, "capabilities": {},
                              "clientInfo": {"name": "memory-test", "version": "1"}}))
    protocol.receive('{"jsonrpc":"2.0","method":"notifications/initialized"}')
    return result


class ProtocolTests(unittest.TestCase):
    def test_initialization_and_list(self):
        protocol = Protocol()
        self.assertEqual(VERSION, initialize(protocol)["result"]["protocolVersion"])
        self.assertEqual(3, len(protocol.receive(request("tools/list"))["result"]["tools"]))

    def test_requires_initialization(self):
        self.assertIn("error", Protocol().receive(request("tools/list")))

    def test_reinitialization_rejected(self):
        protocol = Protocol()
        initialize(protocol)
        self.assertIn("error", initialize(protocol))

    def test_notifications_never_receive_responses(self):
        protocol = Protocol()
        for method in ("notifications/cancelled", "unknown", "tools/call"):
            self.assertIsNone(protocol.receive(json.dumps({"jsonrpc": "2.0", "method": method})))

    def test_invalid_json_and_duplicate_members(self):
        for raw in ('{', '{"a":1,"a":2}', '{"a":NaN}', '[' * 2000):
            self.assertEqual(-32700, Protocol().receive(raw)["error"]["code"])

    def test_invalid_requests(self):
        for value in ([], None, 1, {"jsonrpc": "2.0", "id": True, "method": "ping"}):
            self.assertEqual(-32600, Protocol().receive(json.dumps(value))["error"]["code"])

    def test_unknown_method_and_tool(self):
        protocol = Protocol()
        initialize(protocol)
        self.assertEqual(-32601, protocol.receive(request("unknown"))["error"]["code"])
        self.assertEqual(-32602, protocol.receive(request("tools/call", {"name": "connect_live"}))["error"]["code"])

    def test_tool_error_is_not_protocol_error(self):
        protocol = Protocol()
        initialize(protocol)
        result = protocol.receive(request("tools/call", {"name": "capella_preview_plan", "arguments": {"plan": {}}}))
        self.assertTrue(result["result"]["isError"])

    def test_streams_without_network_or_subprocess(self):
        reader = io.BytesIO((request("ping") + "\n").encode())
        writer = io.BytesIO()
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")), \
             patch("subprocess.Popen", side_effect=AssertionError("Process forbidden")):
            serve(reader, writer)
        self.assertEqual({}, json.loads(writer.getvalue())["result"])

    def test_oversized_frame_stops_before_next_request(self):
        reader = io.BytesIO(b"x" * (MAX_LINE + 1) + b"\n" + request("ping").encode())
        writer = io.BytesIO()
        serve(reader, writer)
        self.assertEqual(1, len(writer.getvalue().splitlines()))
        self.assertEqual(-32600, json.loads(writer.getvalue())["error"]["code"])

    def test_invalid_utf8(self):
        writer = io.BytesIO()
        serve(io.BytesIO(b"\xff\n"), writer)
        self.assertEqual(-32700, json.loads(writer.getvalue())["error"]["code"])

    def test_sessions_have_independent_models(self):
        first, second = Protocol(), Protocol()
        first.tools.engine._state["revision"] = 4
        self.assertEqual(0, second.tools.engine.snapshot()["revision"])

    def test_compiler_explicit_native_recipes(self):
        plan = json.loads((Path(__file__).resolve().parents[1] / "examples/logical-monitoring.json").read_text())
        compiled = compile_plan(plan)
        self.assertFalse(compiled["save"])
        self.assertEqual(13, len(compiled["commands"]))
        self.assertEqual("functional_exchange_with_ports", compiled["commands"][6]["recipe"])
        self.assertEqual("connect_functions", plan["operations"][6]["op"])
