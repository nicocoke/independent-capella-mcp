"""Exercise the Python boundary with a publication exported by disposable Capella 7.1.0."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import unittest
from relay.preflight import validate_snapshot
from relay.service import NativeTools
from relay.store import Ledger

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/incremental"


class NativePublicationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((EXAMPLES / "inventory.json").read_text())
        validate_snapshot(self.snapshot)
        self.store = Ledger(sqlite3.connect(":memory:", check_same_thread=False))
        self.addCleanup(self.store.close)
        self.store.bind("fixture", "synthetic", self.snapshot)
        self.client = NativeTools(self.store, "fixture")

    def call(self, name, arguments):
        result = self.client.call(name, arguments)
        self.assertFalse(result["isError"], result)
        return result["structuredContent"]

    def test_replay_read_pages_without_duplicates_or_omissions(self):
        found = []
        args = {"limit":7}
        while True:
            page = self.call("capella_snapshot", args)
            found.extend(r["alias"] for r in page["elements"])
            if page["next_offset"] is None:
                break
            args.update(offset=page["next_offset"], revision=page["revision"], session_epoch=page["session_epoch"])
        self.assertEqual(sorted(r["alias"] for r in self.snapshot["elements"]), found)
        self.assertEqual(len(found), len(set(found)))

    def test_cross_layer_realization_and_reverse_query(self):
        inventory = {r["alias"]:r for r in self.snapshot["elements"]}
        trace = self.call("capella_snapshot", {"type":"PhysicalArtifactRealization"})["elements"][0]
        source = trace["links"]["sourceElement"][0]
        target = trace["links"]["targetElement"][0]
        self.assertEqual("EPBSArchitecture", inventory[source]["architecture"])
        self.assertEqual("PhysicalArchitecture", inventory[target]["architecture"])
        reverse = self.call("capella_snapshot", {"links_to":target, "type":"PhysicalArtifactRealization"})
        self.assertIn(trace, reverse["elements"])

    def test_every_incremental_example_prepares_against_native_publication(self):
        plans = list(EXAMPLES.glob("*-*.json"))
        self.assertEqual(5, len(plans))
        for path in plans:
            with self.subTest(path=path.name):
                plan = json.loads(path.read_text())
                prepared = self.call("capella_prepare", {"plan":plan})
                self.assertFalse(prepared["payload"]["save"])
                self.assertEqual(self.snapshot["session_epoch"], prepared["payload"]["session_epoch"])

    def test_concurrent_incremental_submission_has_single_job_and_claim(self):
        plan = json.loads((EXAMPLES / "PA-add-node-and-port.json").read_text())
        prepared = self.call("capella_prepare", {"plan":plan})
        args = {"plan":plan, "preview_digest":prepared["preview_digest"], "request_id":"two-clients"}
        clients = [NativeTools(self.store,"fixture") for _ in range(2)]
        with ThreadPoolExecutor(2) as threads:
            results = list(threads.map(lambda c: c.call("capella_submit", args), clients))
        self.assertTrue(all(not result["isError"] for result in results))
        self.assertEqual(results[0]["structuredContent"], results[1]["structuredContent"])
        job = self.store.claim("fixture", "synthetic")
        self.assertIsNotNone(job)
        self.assertIsNone(self.store.claim("fixture", "synthetic"))
        self.store.finish("fixture","synthetic",job["job_id"],job["lease"],"unknown_outcome",{})
        self.assertEqual("unknown_outcome", self.call("capella_submit", args)["status"])
        self.assertIsNone(self.store.claim("fixture", "synthetic"))

