"""Small offline MCP stdio implementation, explicitly targeting 2025-06-18.

No network, filesystem, runtime discovery or native adapter imports. Not a claim
of 2026 protocol support. Each instance owns one isolated synthetic model.
"""
import json
from .tools import OfflineTools, catalogue

VERSION = "2025-06-18"
MAX_LINE = 262144


def error(identifier, code, message):
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


class Protocol:
    def __init__(self, tools=None, tool_catalogue=None, server_info=None, instructions=None):
        self.phase = "new"
        self.tools = OfflineTools() if tools is None else tools
        self.catalogue = catalogue if tool_catalogue is None else tool_catalogue
        self.server_info = server_info or {"name": "capella-offline-development", "version": "0.2.0"}
        self.instructions = instructions or "Use the advertised tools. Queued jobs are not completed edits. Check their outcomes."

    def receive(self, raw):
        if len(raw.encode("utf-8")) > MAX_LINE:
            return error(None, -32600, "Message too large")
        try:
            message = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        except (ValueError, RecursionError):
            return error(None, -32700, "Invalid JSON")
        if not isinstance(message, dict):
            return error(None, -32600, "Expected JSON-RPC object; batches unsupported")
        identifier = message.get("id")
        notification = "id" not in message
        if (message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str)
                or (not notification and type(identifier) not in (str, int))):
            return error(None, -32600, "Invalid request")
        method = message["method"]
        params = message.get("params", {})
        if not isinstance(params, dict):
            return None if notification else error(identifier, -32602, "Expected object parameters")
        if notification:
            if method == "notifications/initialized" and self.phase == "initializing":
                self.phase = "ready"
            return None
        if method == "ping":
            result = {}
        elif method == "initialize":
            info = params.get("clientInfo")
            if self.phase != "new":
                return error(identifier, -32600, "Already initialized")
            if (not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(info, dict)
                    or not all(isinstance(info.get(k), str) for k in ("name", "version"))):
                return error(identifier, -32602, "Invalid initialization parameters")
            self.phase = "initializing"
            result = {"protocolVersion": VERSION, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": self.server_info,
                      "instructions": self.instructions}
        elif self.phase != "ready":
            return error(identifier, -32000, "Initialization not completed")
        elif method == "tools/list":
            if params.get("cursor") is not None:
                return error(identifier, -32602, "No pagination cursor supported")
            result = {"tools": self.catalogue()}
        elif method == "tools/call":
            name = params.get("name")
            if name not in [item["name"] for item in self.catalogue()]:
                return error(identifier, -32602, "Unknown tool")
            result = self.tools.call(name, params.get("arguments", {}))
        else:
            return error(identifier, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": identifier, "result": result}


def serve(reader, writer, protocol=None):
    """Operate on supplied binary streams; tests supply BytesIO, never processes."""
    protocol = Protocol() if protocol is None else protocol
    while True:
        line = reader.readline(MAX_LINE + 1)
        if not line:
            return
        if len(line) > MAX_LINE:
            # Terminate rather than interpreting a truncated tail as another request.
            writer.write((json.dumps(error(None, -32600, "Message too large")) + "\n").encode())
            writer.flush()
            return
        try:
            response = protocol.receive(line.decode("utf-8"))
        except UnicodeDecodeError:
            response = error(None, -32700, "Invalid UTF-8")
        if response is not None:
            writer.write((json.dumps(response, ensure_ascii=True) + "\n").encode("utf-8"))
            writer.flush()
