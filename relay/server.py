"""Explicit ASGI factory for a future isolated host; no automatic startup."""
def from_environment():
    import json
    import os
    import sqlite3
    from pathlib import Path
    from .app import RelayApp
    from .store import Ledger
    if os.environ.get("CAPELLA_RELAY_ENABLE") != "explicit-development-host":
        raise RuntimeError("Relay is disabled")
    config_path = Path(os.environ["CAPELLA_RELAY_CONFIG"]).resolve(strict=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_path = Path(config["database"]).resolve()
    if db_path.suffix != ".sqlite3":
        raise ValueError("Dedicated relay database required")
    ledger = Ledger(sqlite3.connect(db_path))
    if "oauth" in config:
        from .oauth import OAuthResource, Introspection
        oauth = config["oauth"]
        return OAuthResource(ledger, resource=oauth["resource"], issuer=oauth["issuer"],
            introspect=Introspection(oauth["introspection_endpoint"], oauth["client_id"],
                                    os.environ[oauth["client_secret_env"]]),
            subjects=oauth["subjects"], connector_grants=config["grants"], origins=config["origins"])
    return RelayApp(ledger, config["grants"], config["origins"])
