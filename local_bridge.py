"""Stdio MCP plus an authenticated IPv4 loopback connector endpoint.

No Capella discovery, process launches, project access or listeners on import.
Only the explicitly enabled native connector can publish a selected session.
"""
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
from socketserver import ThreadingMixIn
import sqlite3
import threading

from capella_groundwork.protocol import Protocol, MAX_LINE, _pairs, _constant
from relay.preflight import validate_snapshot
from relay.service import NativeTools, native_catalogue
from relay.store import Ledger, Conflict

SCOPE = "local-session"
CONNECTOR = "local-capella"
FORMAT = "capella-local-bridge/1"
INSTRUCTIONS = "Call capella_connection first. Only the explicitly paired Capella session is editable. Read capella_snapshot before preparing a plan; use its model_id and revision and advertised aliases. Prepare then submit with the exact preview_digest and a unique request_id. A queued job is not success: poll capella_job until terminal. succeeded_unsaved means Capella has changed but the user must save. If an edit blocker has unknown_outcome, report the blocking job ID and stop submitting edits. Never automatically resubmit an unknown_outcome with a new request_id."


def strict_json(data):
    if len(data) > MAX_LINE:
        raise ValueError("Payload limit exceeded")
    result = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(result, dict):
        raise ValueError("Object required")
    return result


def validate_headers(headers, peer, port, token):
    names = [name.lower() for name, value in headers]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate headers")
    values = dict((name.lower(), value) for name, value in headers)
    if peer != "127.0.0.1" or values.get("host") != "127.0.0.1:" + str(port):
        raise PermissionError("Loopback host required")
    if any(name in values for name in ("origin", "transfer-encoding", "expect", "content-encoding")):
        raise ValueError("Unsupported request headers")
    authorization = values.get("authorization", "")
    if not hmac.compare_digest(authorization.encode("utf-8"), ("Bearer " + token).encode("ascii")):
        raise PermissionError("Authentication required")
    if values.get("content-type", "").split(";")[0] != "application/json":
        raise ValueError("JSON required")
    length = values.get("content-length", "")
    if not re.fullmatch(r"[0-9]{1,6}", length) or not 1 <= int(length) <= MAX_LINE:
        raise ValueError("Invalid payload size")
    return int(length)


def dispatch(ledger, route, body):
    if route == "/connector/snapshot":
        validate_snapshot(body)
        ledger.bind(SCOPE, CONNECTOR, body)
        return {"published": True}
    if route == "/connector/claim":
        if body:
            raise ValueError("Claim takes no parameters")
        return {"job": ledger.claim(SCOPE, CONNECTOR)}
    if route == "/connector/result":
        if set(body) != {"job_id", "lease", "status", "result"}:
            raise ValueError("Invalid receipt fields")
        NativeTools._job_id(body["job_id"])
        if (not isinstance(body["lease"], str) or not re.fullmatch(r"[a-f0-9]{48}", body["lease"])
                or not isinstance(body["status"], str) or not isinstance(body["result"], dict)):
            raise ValueError("Invalid receipt values")
        return ledger.finish(SCOPE, CONNECTOR, body["job_id"], body["lease"], body["status"], body["result"])
    raise ValueError("Unknown connector route")


class StateBusy(RuntimeError):
    pass


class StateLock:
    def __init__(self, folder):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (folder / "server.lock").open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise StateBusy("Another Capella local server owns this state folder") from None

    def close(self):
        if not self.file.closed:
            self.file.close()


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def __init__(self, bridge):
        self.bridge = bridge
        self.capacity = threading.BoundedSemaphore(8)
        super().__init__(("127.0.0.1", 0), _Handler)

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def process_request(self, request, address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.capacity.release()

    def handle_error(self, request, client_address):
        pass


class _Handler(BaseHTTPRequestHandler):
    server_version = "CapellaLocal/0.4"
    sys_version = ""

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, format, *arguments):
        pass

    def do_POST(self):
        bridge = self.server.bridge
        try:
            if self.path not in {"/connector/snapshot", "/connector/claim", "/connector/result", "/local/tool"}:
                self.respond(404, {"error": "Unknown connector route"})
                return
            length = validate_headers(list(self.headers.items()), self.client_address[0],
                                      self.server.server_port, bridge.token)
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Incomplete payload")
            body = strict_json(data)
            if self.path == "/local/tool":
                result = dispatch_tool(bridge, body)
                self.respond(200, result)
                return
            with bridge.ledger.lock:
                if self.path == "/connector/snapshot":
                    epoch = body.get("session_epoch")
                    if bridge.active_epoch is not None and epoch != bridge.active_epoch:
                        raise Conflict("Another native session is already paired; stop it before restarting the local MCP")
                result = dispatch(bridge.ledger, self.path, body)
                if self.path == "/connector/snapshot":
                    bridge.active_epoch = body["session_epoch"]
            self.respond(200, result)
        except PermissionError:
            self.respond(403, {"error": "Local connector authentication or host denied"})
        except (ValueError, TypeError, KeyError, RecursionError) as failure:
            self.respond(409 if isinstance(failure, Conflict) else 400, {"error": str(failure)})
        except (OSError, sqlite3.Error):
            self.close_connection = True

    def respond(self, status, body):
        encoded = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("ascii")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True


class LocalTools:
    def __init__(self, bridge):
        self.bridge = bridge
        self.native = NativeTools(bridge.ledger, SCOPE)

    @staticmethod
    def catalogue():
        return [{"name": "capella_connection", "description": "Show local pairing status, connection file path and any job blocking edits. Contains no credential.",
                 "inputSchema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}] + native_catalogue()

    def call(self, name, arguments):
        if name != "capella_connection":
            return self.native.call(name, arguments)
        if not isinstance(arguments, dict) or arguments:
            return {"content": [{"type": "text", "text": "This tool takes no arguments"}], "isError": True}
        with self.bridge.ledger.lock:
            try:
                snapshot = self.bridge.ledger.snapshot(SCOPE)
                connected = True
            except Conflict:
                snapshot, connected = None, False
            blocker = self.bridge.ledger.edit_blocker(SCOPE)
        result = {"connected": connected, "connection_file": str(self.bridge.profile),
                  "transport": "local stdio with authenticated IPv4 loopback connector",
                  "instructions": "In Capella select an architecture root or a logical component in the semantic tree, run Start / Stop Independent MCP (Development), and select this connection file. Use a disposable model for initial acceptance. Changes remain unsaved.",
                  "session_epoch": snapshot["session_epoch"] if snapshot else None,
                  "edit_blocker": blocker}
        return {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result, "isError": False}


def dispatch_tool(bridge, body):
    if (set(body) != {"name", "arguments"} or not isinstance(body["name"], str)
            or body["name"] not in {item["name"] for item in LocalTools.catalogue()}
            or not isinstance(body["arguments"], dict)):
        raise ValueError("Invalid local tool request")
    return LocalTools(bridge).call(body["name"], body["arguments"])


def connection_values(data):
    profile = strict_json(data)
    if set(profile) != {"format", "origin", "token"} or profile["format"] != FORMAT:
        raise ValueError("Unsupported local connection profile")
    origin, token = profile["origin"], profile["token"]
    match = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})/?", origin) if isinstance(origin, str) else None
    if (match is None or int(match[1]) > 65535 or not isinstance(token, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token) is None):
        raise ValueError("Literal authenticated IPv4 loopback required")
    return int(match[1]), token


class LocalBridge:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.profile = self.folder / "connection.json"
        self.lock = None
        self.ledger = None
        self.server = None
        self.thread = None
        self.active_epoch = None
        self.token = None

    def __enter__(self):
        self.lock = StateLock(self.folder)
        try:
            secret = self.folder / "connector.key"
            if secret.exists():
                token = secret.read_text(encoding="ascii").strip()
                if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
                    raise ValueError("Invalid existing connector credential")
            else:
                token = secrets.token_urlsafe(32)
                descriptor = os.open(secret, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                    stream.write(token)
            self.token = token
            self.ledger = Ledger(sqlite3.connect(self.folder / "jobs.sqlite3", check_same_thread=False))
            with self.ledger.lock, self.ledger.db:
                self.ledger.db.execute("UPDATE models SET updated=? WHERE scope=?", (self.ledger.clock() - 121, SCOPE))
            self.server = _Server(self)
            self.thread = threading.Thread(target=self.server.serve_forever, name="Capella local connector", daemon=True)
            self.thread.start()
            profile = {"format": FORMAT, "origin": "http://127.0.0.1:" + str(self.server.server_port), "token": self.token}
            temporary = self.folder / ("connection-" + secrets.token_hex(8) + ".tmp")
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(profile, stream)
            os.replace(temporary, self.profile)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def protocol(self):
        return Protocol(LocalTools(self), LocalTools.catalogue,
                        server_info={"name": "independent-capella-local", "version": "0.9.2"},
                        instructions=INSTRUCTIONS)

    def __exit__(self, *arguments):
        if self.server is not None:
            if self.thread is not None and self.thread.is_alive():
                self.server.shutdown()
                self.thread.join(timeout=10)
            self.server.server_close()
        if self.ledger is not None:
            with self.ledger.lock, self.ledger.db:
                self.ledger.db.execute("UPDATE models SET updated=? WHERE scope=?", (self.ledger.clock() - 121, SCOPE))
            self.ledger.close()
        if self.lock is not None:
            try:
                self.profile.unlink(missing_ok=True)
            finally:
                self.lock.close()


class SharedBridge:
    """Independent MCP sessions share one locked broker; no edit is replayed on transport failure."""
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.owner = None

    def _elect(self):
        if self.owner is None:
            candidate = LocalBridge(self.folder)
            try:
                candidate.__enter__()
            except StateBusy:
                return
            self.owner = candidate

    def __enter__(self):
        self._elect()
        return self

    def __exit__(self, *arguments):
        if self.owner is not None:
            self.owner.__exit__(*arguments)
            self.owner = None

    def protocol(self):
        return Protocol(self, LocalTools.catalogue,
                        server_info={"name": "independent-capella-local", "version": "0.9.2"},
                        instructions=INSTRUCTIONS)

    def call(self, name, arguments):
        try:
            self._elect()
            body = {"name": name, "arguments": arguments}
            if self.owner is not None:
                return dispatch_tool(self.owner, body)
            with (self.folder / "connection.json").open("rb") as stream:
                data = stream.read(65537)
            if len(data) > 65536:
                raise ValueError("Connection file too large")
            port, token = connection_values(data)
            encoded = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("ascii")
            if len(encoded) > MAX_LINE:
                raise ValueError("Tool request too large")
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                connection.request("POST", "/local/tool", encoded,
                                   {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                response = connection.getresponse()
                payload = response.read(1048577)
                if response.status != 200 or len(payload) > 1048576:
                    raise RuntimeError("Shared broker unavailable or incompatible")
                result = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
                if not isinstance(result, dict) or not isinstance(result.get("isError"), bool) or not isinstance(result.get("content"), list):
                    raise ValueError("Invalid broker result")
                return result
            finally:
                connection.close()
        except (OSError, ValueError, TypeError, RuntimeError, http.client.HTTPException, RecursionError):
            return {"content": [{"type": "text", "text": "The shared local broker could not complete this request. No automatic retry was made. If updating from 0.4.0, fully quit Claude and reopen it after installing the current extension. Otherwise retry a read-only connection/job check. For a submitted edit, keep the same request_id and inspect its job; do not submit it under a new identity."}], "isError": True}
