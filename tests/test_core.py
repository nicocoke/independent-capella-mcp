import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import unittest

from capella_groundwork.core import MockEngine, PlanError, create_live_backend
from capella_groundwork.tools import OfflineTools, catalogue


ROOT = Path(__file__).resolve().parents[1]


class GroundworkTests(unittest.TestCase):
    def setUp(self):
        self.engine = MockEngine()
        self.plan = json.loads((ROOT / "examples/logical-monitoring.json").read_text(encoding="utf-8"))

    def commit(self, plan=None, request_id="request-one"):
        plan = self.plan if plan is None else plan
        return self.engine.commit_mock(plan, self.engine.preview(plan)["digest"], request_id)

    def test_preview_has_no_side_effects(self):
        before = self.engine.snapshot()
        preview = self.engine.preview(self.plan)
        self.assertEqual(before, self.engine.snapshot())
        self.assertEqual(13, preview["operation_count"])
        self.assertEqual(5, len(preview["candidate"]["views"]))

    def test_commit_creates_model_and_separate_views(self):
        receipt = self.commit()
        state = self.engine.snapshot()
        self.assertEqual(1, receipt["revision"])
        self.assertEqual("functional_exchange", state["elements"]["temperature"]["kind"])
        self.assertEqual(2, len(state["allocations"]))
        self.assertEqual("temperature", state["views"]["view-temperature"]["element"])

    def test_semantic_creation_does_not_imply_view(self):
        self.plan["operations"] = self.plan["operations"][:1]
        self.commit()
        self.assertIn("sensor", self.engine.snapshot()["elements"])
        self.assertEqual({}, self.engine.snapshot()["views"])

    def test_bad_late_operation_rolls_back_mock(self):
        before = self.engine.snapshot()
        self.plan["operations"][-1]["element"] = "missing"
        with self.assertRaises(PlanError):
            self.engine.commit_mock(self.plan, self._digest(), "request-one")
        self.assertEqual(before, self.engine.snapshot())

    def _digest(self):
        from capella_groundwork.core import _digest
        return _digest(self.plan)

    def test_tampering_after_preview_rejected(self):
        digest = self.engine.preview(self.plan)["digest"]
        self.plan["operations"][0]["name"] = "Changed"
        with self.assertRaises(PlanError):
            self.engine.commit_mock(self.plan, digest, "request-one")

    def test_stale_revision_rejected(self):
        digest = self.engine.preview(self.plan)["digest"]
        self.commit()
        with self.assertRaisesRegex(PlanError, "Stale"):
            self.engine.commit_mock(self.plan, digest, "request-two")

    def test_retry_returns_same_receipt_without_duplicates(self):
        digest = self.engine.preview(self.plan)["digest"]
        receipt = self.engine.commit_mock(self.plan, digest, "request-one")
        state = self.engine.snapshot()
        self.assertEqual(receipt, self.engine.commit_mock(self.plan, digest, "request-one"))
        self.assertEqual(state, self.engine.snapshot())

    def test_request_id_cannot_be_reused_for_other_plan(self):
        self.commit()
        self.plan["base_revision"] = 1
        self.plan["operations"] = [{"op": "create_component", "id": "extra", "name": "Extra",
                                    "parent": "logical-system"}]
        with self.assertRaisesRegex(PlanError, "reused"):
            self.commit()

    def test_concurrent_duplicate_request_commits_once(self):
        digest = self.engine.preview(self.plan)["digest"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: self.engine.commit_mock(
                self.plan, digest, "request-one"), range(8)))
        self.assertTrue(all(r == receipts[0] for r in receipts))
        self.assertEqual(1, self.engine.snapshot()["revision"])

    def test_wrong_model_rejected(self):
        self.plan["model_id"] = "another-model"
        with self.assertRaisesRegex(PlanError, "Wrong model"):
            self.engine.preview(self.plan)

    def test_wrong_reference_kind_rejected(self):
        self.plan["operations"][2]["parent"] = "sensor"
        with self.assertRaisesRegex(PlanError, "wrong-kind"):
            self.engine.preview(self.plan)

    def test_exchange_view_requires_endpoint_views(self):
        self.plan["operations"] = self.plan["operations"][:8] + self.plan["operations"][-1:]
        with self.assertRaisesRegex(PlanError, "endpoints"):
            self.engine.preview(self.plan)

    def test_duplicate_allocation_rejected(self):
        self.plan["operations"].append({"op": "allocate_function", "id": "duplicate-allocation",
                                        "function": "measure", "component": "controller"})
        with self.assertRaisesRegex(PlanError, "already allocated"):
            self.engine.preview(self.plan)

    def test_unknown_fields_and_execution_operations_rejected(self):
        for operation in [{"op": "execute_python", "id": "code", "code": "anything"},
                          dict(self.plan["operations"][0], filename="model.capella")]:
            plan = deepcopy(self.plan)
            plan["operations"] = [operation]
            with self.assertRaises(PlanError):
                self.engine.preview(plan)

    def test_malformed_values_rejected(self):
        for key, value in [("version", True), ("base_revision", True),
                           ("operations", []), ("operations", [None]), ("model_id", "../private")]:
            plan = deepcopy(self.plan)
            plan[key] = value
            with self.assertRaises(PlanError):
                self.engine.preview(plan)

    def test_duplicate_ids_and_unsupported_diagrams_rejected(self):
        plan = deepcopy(self.plan)
        plan["operations"][1]["id"] = "sensor"
        with self.assertRaisesRegex(PlanError, "Duplicate"):
            self.engine.preview(plan)
        self.plan["operations"][7]["kind"] = "scenario"
        with self.assertRaisesRegex(PlanError, "LAB"):
            self.engine.preview(self.plan)

    def test_snapshots_and_previews_do_not_leak_mutable_state(self):
        state = self.engine.snapshot()
        state["elements"].clear()
        preview = self.engine.preview(self.plan)
        preview["candidate"]["elements"].clear()
        self.assertEqual(2, len(self.engine.snapshot()["elements"]))

    def test_live_backend_always_refuses(self):
        with self.assertRaisesRegex(PlanError, "not implemented or authorized"):
            create_live_backend()

    def test_tool_dispatch_preview_and_commit(self):
        tools = OfflineTools()
        preview = tools.call("capella_preview_plan", {"plan": self.plan})
        self.assertFalse(preview["isError"])
        commit = tools.call("capella_commit_mock", {
            "plan": self.plan, "preview_digest": preview["structuredContent"]["digest"],
            "request_id": "request-one"})
        self.assertFalse(commit["isError"])
        self.assertEqual(1, tools.call("capella_mock_snapshot", {})["structuredContent"]["revision"])

    def test_unknown_tools_and_arguments_return_tool_errors(self):
        tools = OfflineTools()
        for name, arguments in [("capella_connect", {}), ("capella_mock_snapshot", {"path": "x"}),
                                ("capella_preview_plan", {}), ("capella_preview_plan", {"plan": None})]:
            self.assertTrue(tools.call(name, arguments)["isError"])

    def test_catalogue_serializes_and_labels_mock_write(self):
        tools = catalogue()
        json.dumps(tools)
        self.assertEqual(3, len(tools))
        self.assertFalse(tools[-1]["annotations"]["readOnlyHint"])
        self.assertTrue(all(not t["annotations"]["openWorldHint"] for t in tools))

    def test_implementation_has_no_network_process_or_file_access(self):
        allowed = {"copy", "hashlib", "json", "re", "threading", "core", "tools", "architecture"}
        for path in (ROOT / "capella_groundwork").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(n.name in allowed for n in node.names))
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"open", "exec", "eval", "__import__", "compile"})


if __name__ == "__main__":
    unittest.main()
