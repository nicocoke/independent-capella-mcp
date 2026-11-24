import json
import sqlite3
import time
import unittest
from relay.oauth import OAuthResource, Introspection
from relay.store import Ledger


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(sqlite3.connect(":memory:"))
        self.claims = {"active": True, "iss": "https://issuer.test", "aud": "https://relay.test/mcp",
                       "exp": time.time() + 1000, "scope": "capella:edit", "sub": "alice"}
        async def introspect(token): return dict(self.claims)
        self.app = OAuthResource(self.ledger, resource="https://relay.test/mcp", issuer="https://issuer.test",
            introspect=introspect, subjects={"alice": "p"}, connector_grants={}, origins=["https://client.test"])

    def tearDown(self): self.ledger.close()

    def call(self, path="/mcp", auth=True, method="POST"):
        events = []
        async def receive(): return {"type": "http.request", "body": b'{}'}
        async def send(event): events.append(event)
        headers = [(b"authorization", b"Bearer synthetic")] if auth else []
        coroutine = self.app({"type": "http", "scheme": "https", "path": path, "method": method, "headers": headers}, receive, send)
        try: coroutine.send(None)
        except StopIteration: pass
        else:
            coroutine.close()
            self.fail("Unexpected IO")
        return events[0]["status"], json.loads(events[1]["body"]) if events[1]["body"] else None

    def test_metadata(self):
        status, body = self.call("/.well-known/oauth-protected-resource", auth=False, method="GET")
        self.assertEqual(200, status)
        self.assertEqual(["https://issuer.test"], body["authorization_servers"])

    def test_missing_token(self): self.assertEqual(401, self.call(auth=False)[0])

    def test_inactive_wrong_issuer_audience_expiry_scope(self):
        original = dict(self.claims)
        for key, value in [("active", False), ("iss", "https://wrong.test"), ("aud", "https://wrong.test"),
                           ("exp", 1), ("exp", True), ("exp", float("inf")),
                           ("aud", {"https://relay.test/mcp": True}), ("scope", "unrelated")]:
            self.claims = dict(original, **{key: value})
            self.assertEqual(401, self.call()[0])

    def test_unknown_subject(self):
        self.claims["sub"] = "mallory"
        self.assertEqual(403, self.call()[0])

    def test_valid_token_reaches_mcp_transport(self):
        # Missing content type is rejected by MCP transport, after successful auth.
        self.assertEqual(415, self.call()[0])

    def test_introspection_rejects_plain_http(self):
        with self.assertRaises(ValueError): Introspection("http://issuer.test", "id", "secret")

    def test_metadata_rejects_post(self):
        self.assertEqual(405, self.call("/.well-known/oauth-protected-resource", auth=False)[0])
