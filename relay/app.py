"""Authenticated outbound-connector relay. No listeners are started on import."""
import hmac
import json
from development_http import DevelopmentApp
from capella_groundwork.protocol import Protocol, MAX_LINE, _pairs, _constant
from capella_groundwork.core import _identifier
from .service import NativeTools, native_catalogue
from .store import Conflict
from .preflight import validate_snapshot


class RelayApp:
    def __init__(self, ledger, grants, origins):
        """grants: explicit token -> {role, scope, connector} mapping supplied by operator."""
        self.ledger = ledger
        self.grants = dict(grants)
        self.apps = {}
        for token, grant in grants.items():
            if not isinstance(token, str) or len(token) < 32 or not token.isascii() or not isinstance(grant, dict) or grant.get("role") not in {"client", "connector"}:
                raise ValueError("Invalid explicit credential grant")
            expected = {"role", "scope", "connector"} if grant["role"] == "connector" else {"role", "scope"}
            if set(grant) != expected:
                raise ValueError("Invalid credential grant fields")
            _identifier(grant["scope"])
            if grant["role"] == "connector":
                _identifier(grant["connector"])
            if grant["role"] == "client":
                scope = grant["scope"]
                self.apps[token] = DevelopmentApp(token=token, origins=origins,
                    protocol_factory=lambda scope=scope: Protocol(NativeTools(ledger, scope), native_catalogue))

    async def __call__(self, scope, receive, send):
        async def respond(status, result):
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": json.dumps(result).encode()})
        if scope.get("type") != "http":
            raise ValueError("HTTP only")
        raw_headers = scope.get("headers", [])
        if len({k.lower() for k, _ in raw_headers}) != len(raw_headers):
            return await respond(400, {"error": "Duplicate headers"})
        headers = {k.lower(): v for k, v in raw_headers}
        authorization = headers.get(b"authorization", b"")
        token = next((key for key in self.grants if hmac.compare_digest(
            authorization, ("Bearer " + key).encode())), None)
        if token is None:
            return await respond(401, {"error": "Authentication required"})
        grant = self.grants[token]
        if scope.get("path") == "/mcp" and grant["role"] == "client":
            return await self.apps[token](scope, receive, send)
        if grant["role"] != "connector" or scope.get("scheme") != "https":
            return await respond(403, {"error": "Role or transport denied"})
        if scope.get("method") != "POST" or scope.get("path") not in {"/connector/snapshot", "/connector/claim", "/connector/result"}:
            return await respond(404, {"error": "Unknown connector route"})
        if b"origin" in headers:
            return await respond(403, {"error": "Connector route is not a browser endpoint"})
        if headers.get(b"content-type", b"").split(b";")[0] != b"application/json":
            return await respond(415, {"error": "JSON required"})
        data = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            data.extend(event.get("body", b""))
            if len(data) > MAX_LINE:
                return await respond(413, {"error": "Payload limit exceeded"})
            if not event.get("more_body", False):
                break
        try:
            body = json.loads(data.decode(), object_pairs_hook=_pairs, parse_constant=_constant)
            if not isinstance(body, dict):
                raise ValueError("Object required")
            project, connector = grant["scope"], grant["connector"]
            if scope["path"] == "/connector/snapshot":
                validate_snapshot(body)
                self.ledger.bind(project, connector, body)
                result = {"published": True}
            elif scope["path"] == "/connector/claim":
                if body:
                    raise ValueError("Claim takes no parameters")
                result = {"job": self.ledger.claim(project, connector)}
            else:
                if set(body) != {"job_id", "lease", "status", "result"}:
                    raise ValueError("Invalid receipt fields")
                NativeTools._job_id(body["job_id"])
                if not isinstance(body["lease"], str) or len(body["lease"]) != 48 or not isinstance(body["status"], str) or not isinstance(body["result"], dict):
                    raise ValueError("Invalid receipt values")
                result = self.ledger.finish(project, connector, body["job_id"], body["lease"], body["status"], body["result"])
            return await respond(200, result)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            return await respond(409 if isinstance(exc, Conflict) else 400, {"error": str(exc)})
