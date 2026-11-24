"""Optional OAuth resource-server integration with an external authorization server.

No authorization server is implemented here. Operator supplies an HTTPS token
introspection endpoint and an explicit subject-to-project ACL. No discovery or
network calls occur during construction. Tests inject a pure in-memory validator.
"""
import asyncio
import base64
import json
import math
import secrets
import time
import urllib.parse
import urllib.request
from .app import RelayApp


class Introspection:
    def __init__(self, endpoint, client_id, client_secret):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.fragment:
            raise ValueError("Explicit HTTPS introspection endpoint required")
        self.endpoint, self.client_id, self.client_secret = endpoint, client_id, client_secret

    async def __call__(self, token):
        return await asyncio.to_thread(self._request, token)

    def _request(self, token):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError("Introspection redirects denied")
        credentials = base64.b64encode((urllib.parse.quote(self.client_id, safe="") + ":" +
                                       urllib.parse.quote(self.client_secret, safe="")).encode()).decode()
        request = urllib.request.Request(self.endpoint,
            data=urllib.parse.urlencode({"token": token, "token_type_hint": "access_token"}).encode(),
            headers={"Authorization": "Basic " + credentials, "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            data = response.read(65537)
            if len(data) > 65536: raise ValueError("Introspection response too large")
            return json.loads(data)


class OAuthResource:
    def __init__(self, ledger, *, resource, issuer, introspect, subjects, connector_grants, origins):
        for url in (resource, issuer):
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
                raise ValueError("HTTPS metadata URLs required")
        if urllib.parse.urlsplit(resource).path != "/mcp":
            raise ValueError("Resource must match this server's /mcp route")
        self.resource, self.issuer, self.introspect = resource, issuer, introspect
        self.metadata_url = resource.rstrip("/").removesuffix("/mcp") + "/.well-known/oauth-protected-resource"
        self.subjects = {}
        self.apps = {}
        for subject, project in subjects.items():
            internal = secrets.token_urlsafe(48)
            self.subjects[subject] = internal
            self.apps[subject] = RelayApp(ledger, {internal: {"role": "client", "scope": project}}, origins)
        self.connectors = RelayApp(ledger, connector_grants, origins)

    async def __call__(self, scope, receive, send):
        async def respond(code, body):
            await send({"type": "http.response.start", "status": code, "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", ('Bearer resource_metadata="' + self.metadata_url + '"').encode())]})
            await send({"type": "http.response.body", "body": json.dumps(body).encode()})
        if scope.get("scheme") != "https": return await respond(403, {"error": "HTTPS required"})
        path = scope.get("path", "")
        if path == "/.well-known/oauth-protected-resource":
            if scope.get("method") != "GET": return await respond(405, {"error": "GET required"})
            return await respond(200, {"resource": self.resource, "authorization_servers": [self.issuer],
                                      "scopes_supported": ["capella:edit"], "bearer_methods_supported": ["header"]})
        if path.startswith("/connector/"):
            return await self.connectors(scope, receive, send)
        pairs = scope.get("headers", [])
        auth = [value for key, value in pairs if key.lower() == b"authorization"]
        if len(auth) != 1 or not auth[0].startswith(b"Bearer ") or len(auth[0]) > 8192:
            return await respond(401, {"error": "Access token required"})
        try:
            claims = await self.introspect(auth[0][7:].decode("ascii"))
            audience = claims.get("aud", [])
            if isinstance(audience, str): audience = [audience]
            expiry = claims.get("exp")
            if (claims.get("active") is not True or claims.get("iss") != self.issuer or
                not isinstance(audience, list) or self.resource not in audience or type(expiry) not in (int, float) or
                not math.isfinite(expiry) or not expiry > time.time() or "capella:edit" not in claims.get("scope", "").split()):
                raise ValueError("Invalid token claims")
            subject = claims.get("sub")
            if subject not in self.subjects: return await respond(403, {"error": "Subject has no project grant"})
        except Exception:
            return await respond(401, {"error": "Token validation failed"})
        forwarded = dict(scope)
        forwarded["headers"] = [(k, v) for k, v in pairs if k.lower() != b"authorization"] + [
            (b"authorization", ("Bearer " + self.subjects[subject]).encode())]
        return await self.apps[subject](forwarded, receive, send)
