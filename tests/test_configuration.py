import os
import sqlite3
import unittest
from unittest.mock import patch
from relay.app import RelayApp
from relay.server import from_environment
from relay.store import Ledger


class ConfigurationTests(unittest.TestCase):
    def test_factory_disabled_before_file_access(self):
        with patch.dict(os.environ, {}, clear=True), patch("builtins.open", side_effect=AssertionError("No config access")):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                from_environment()

    def test_malformed_grants_refused(self):
        store = Ledger(sqlite3.connect(":memory:"))
        self.addCleanup(store.close)
        for grant in ({}, {"role": "admin", "scope": "p"}, {"role": "connector", "scope": "p"},
                      {"role": "client", "scope": []}, {"role": "client", "scope": "p", "wildcard": True}):
            with self.assertRaises(ValueError):
                RelayApp(store, {"x" * 32: grant}, ["https://example.test"])

    def test_empty_grants_create_no_clients(self):
        store = Ledger(sqlite3.connect(":memory:"))
        self.addCleanup(store.close)
        self.assertEqual({}, RelayApp(store, {}, ["https://example.test"]).apps)
