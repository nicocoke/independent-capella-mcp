"""Bounded ASGI transport. Importing this module never starts a listener.

Single-operator development only. Requires an explicitly supplied bearer token
and origin allowlist. Defaults to mock tools; relay injects scoped native tools
and optionally wraps this transport with an external OAuth integration.
"""
import hmac
import json
import secrets
import time
from capella_groundwork.protocol import Protocol, MAX_LINE, VERSION


class DevelopmentApp:
    def __init__(self, *, token, origins, max_sessions=8, ttl_seconds=900, protocol_factory=Protocol):
        if not isinstance(token, str) or len(token) < 32 or not token.isascii():
            raise ValueError("Explicit ASCII development token of at least 32 characters required")
        if not origins or max_sessions < 1 or ttl_seconds < 1:
            raise ValueError("Origins and positive session limits required")
        self._token = token
        self._origins = frozenset(origins)
        self._max_sessions = max_sessions
        self._ttl = ttl_seconds
        self._sessions = {}
        self._protocol_factory = protocol_factory

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            raise ValueError("HTTP only; no background lifecycle")

        async def respond(status, body=None, headers=()):
            raw = b"" if body is None else json.dumps(body).encode()
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"), *headers]})
            await send({"type": "http.response.body", "body": raw})

        pairs = scope.get("headers", [])
        headers = {}
        for key, value in pairs:
            key = key.lower()
            if key in headers:
                return await respond(400, {"error": "Duplicate header"})
            headers[key] = value.decode("latin-1")
        if scope.get("scheme") != "https":
            return await respond(403, {"error": "HTTPS required"})
        if scope.get("path") != "/mcp":
            return await respond(404)
        auth = headers.get(b"authorization", "")
        if not hmac.compare_digest(auth.encode("latin-1"), ("Bearer " + self._token).encode()):
            return await respond(401, headers=[(b"www-authenticate", b"Bearer")])
        origin = headers.get(b"origin")
        if origin is not None and origin not in self._origins:
            return await respond(403, {"error": "Origin denied"})
        now = time.monotonic()
        self._sessions = {key: entry for key, entry in self._sessions.items() if entry[1] > now}
        session_id = headers.get(b"mcp-session-id")
        method = scope.get("method")
        if method == "DELETE":
            if session_id not in self._sessions:
                return await respond(404)
            del self._sessions[session_id]
            return await respond(204)
        if method != "POST":
            return await respond(405, headers=[(b"allow", b"POST, DELETE")])
        if headers.get(b"content-type", "").split(";")[0].strip() != "application/json":
            return await respond(415)
        accept = headers.get(b"accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return await respond(406)
        payload = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            if event["type"] != "http.request":
                return await respond(400)
            payload.extend(event.get("body", b""))
            if len(payload) > MAX_LINE:
                return await respond(413)
            if not event.get("more_body", False):
                break
        try:
            raw = payload.decode("utf-8")
        except UnicodeDecodeError:
            return await respond(400)
        fresh = session_id is None
        if fresh:
            protocol = self._protocol_factory()
        else:
            if session_id not in self._sessions:
                return await respond(404)
            if headers.get(b"mcp-protocol-version") != VERSION:
                return await respond(400, {"error": "Unsupported protocol version"})
            protocol = self._sessions[session_id][0]
        response = protocol.receive(raw)
        response_headers = []
        if fresh:
            if protocol.phase != "initializing":
                return await respond(400, response or {"error": "Initialize first"})
            if len(self._sessions) >= self._max_sessions:
                return await respond(503, {"error": "Session capacity reached"})
            session_id = secrets.token_urlsafe(32)
            response_headers = [(b"mcp-session-id", session_id.encode())]
        self._sessions[session_id] = (protocol, now + self._ttl)
        return await respond(202 if response is None else 200, response, response_headers)
