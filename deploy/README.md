# Deployment files — for a later isolated host

Nothing in this directory was deployed. Do not point the native plug-in at a real work session for its first test.

The Python code has no mandatory third-party dependencies. An ASGI server such as Uvicorn is needed only when deliberately hosting it. Use one worker for the first pilot; SQLite persists jobs, while MCP session state is held in that worker. A process restart requires clients to reconnect. Do not expose the development app directly on the public internet.

Copy `config.example.json` to a private configuration file on the chosen host. Configure a dedicated absolute `.sqlite3` path, approved browser origins and credentials. Empty `grants` and `subjects` deny everyone.

Each connector gets a separately generated high-entropy token with this grant shape:

```json
{"role":"connector","scope":"chosen-project","connector":"chosen-connector"}
```

The token is the key inside `grants`. Do not reuse it as a client credential. For an internal development test without OAuth, omit `oauth` and add a distinct client token mapped to `{"role":"client","scope":"chosen-project"}`. Generate tokens with at least 32 random bytes and protect the configuration file with host access controls.

For OAuth, use an existing authorization server. Configure an HTTPS introspection endpoint, its client credentials, exact issuer/resource URLs and the `capella:edit` scope. Map trusted subject identifiers to project scopes in `subjects`; no project scope is accepted from token-controlled custom claims. The authorization server must return `active`, `iss`, `aud`, `exp`, `scope` and `sub`. Client registration, consent and login belong to that authorization server. This implementation provides resource metadata, token validation and access control, not an authorization server.

Startup is deliberately gated. Set `CAPELLA_RELAY_ENABLE=explicit-development-host`, `CAPELLA_RELAY_CONFIG` to the private config path, and the configured introspection secret environment variable. Then use an ASGI server's factory mode with `relay.server:from_environment`, one worker, HTTPS and no automatic reload. Disable ASGI lifespan handling (for Uvicorn: `--lifespan off`); this application handles HTTP only. The source does not start a listener on import. No ASGI server dependency has been installed or launched here.

Terminate TLS in the ASGI server for the simplest pilot. If using a reverse proxy, only trust forwarded headers from that proxy and preserve HTTPS scope. Configure bounded request-body timeouts and a 256 KiB body limit at the proxy. Do not disable certificate checks in the connector.

Endpoints: `/mcp` for clients; `/connector/snapshot`, `/connector/claim`, `/connector/result` for the explicitly paired native connector; `/.well-known/oauth-protected-resource` when OAuth is configured. The connector uses outbound HTTPS only and never follows redirects.

After an expired execution lease, the ledger marks the job `unknown_outcome` and blocks further claims for that scope. A matching late receipt can reconcile it. If the native process restarted before producing a receipt, inspect the synthetic model manually before any operator-led recovery. There is intentionally no automatic retry or remotely callable “clear uncertainty” operation.
