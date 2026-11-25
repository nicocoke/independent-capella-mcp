from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import local_reconcile
from local_bridge import CONNECTOR, SCOPE, StateBusy, StateLock
from relay.store import Ledger


class LocalReconcileTests(unittest.TestCase):
    def test_review_existing_journal_requires_offline_broker_lock(self):
        with tempfile.TemporaryDirectory(prefix="capella-local-review-") as directory:
            folder = Path(directory)
            with self.assertRaisesRegex(ValueError, "No existing journal"):
                local_reconcile.record_review(folder, "a" * 32)
            lock = StateLock(folder)
            try:
                ledger = Ledger(sqlite3.connect(folder / "jobs.sqlite3"))
                ledger.bind(SCOPE, CONNECTOR, {"session_epoch": "synthetic"})
                job_id = ledger.submit(SCOPE, "request-test", {})["job_id"]
                claim = ledger.claim(SCOPE, CONNECTOR)
                ledger.finish(SCOPE, CONNECTOR, job_id, claim["lease"], "unknown_outcome", {})
                ledger.db.execute("DROP TABLE job_reviews")  # The previous version had no review table.
                ledger.close()
                with self.assertRaises(StateBusy):
                    local_reconcile.record_review(folder, job_id)
            finally:
                lock.close()
            local_reconcile.record_review(folder, job_id)
            ledger = Ledger(sqlite3.connect(folder / "jobs.sqlite3"))
            try:
                self.assertIsNone(ledger.edit_blocker(SCOPE))
                self.assertEqual("unknown_outcome", ledger.get(SCOPE, job_id)["status"])
            finally:
                ledger.close()

    def test_command_requires_interactive_exact_confirmation(self):
        job_id = "a" * 32
        args = ["local_reconcile", "--state-dir", "unused", "--job-id", job_id]
        with patch("sys.argv", args), patch("sys.stdin.isatty", return_value=False), \
             patch("sys.stderr"), patch("local_reconcile.record_review") as write:
            self.assertEqual(1, local_reconcile.main())
            write.assert_not_called()
        with patch("sys.argv", args), patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stderr"), patch("sys.stdout"), patch("builtins.input", return_value="yes"), \
             patch("local_reconcile.record_review") as write:
            self.assertEqual(1, local_reconcile.main())
            write.assert_not_called()
        with patch("sys.argv", args), patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout"), patch("builtins.input", return_value="REVIEWED " + job_id), \
             patch("local_reconcile.record_review") as write:
            self.assertEqual(0, local_reconcile.main())
            write.assert_called_once_with(Path("unused"), job_id)
