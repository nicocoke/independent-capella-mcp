import unittest

from capella_groundwork.core import PlanError
from relay.inspection import page
from relay.preflight import check_references


class TraceabilityTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"model_id": "native-model", "revision": 1, "session_epoch": "fixture", "limits": [],
                         "elements": [
                             {"alias": "oa", "type": "OperationalActivity", "architecture": "OperationalAnalysis"},
                             {"alias": "sa", "type": "SystemFunction", "architecture": "SystemAnalysis"},
                             {"alias": "la", "type": "LogicalFunction", "architecture": "LogicalArchitecture"},
                             {"alias": "component", "type": "LogicalComponent", "architecture": "LogicalArchitecture"},
                             {"alias": "unrelated", "type": "LogicalFunction", "architecture": "LogicalArchitecture"},
                         ]}

    def test_realization_direction(self):
        plan = {"operations": [{"op": "realize_function", "id": "relation", "source": "sa", "target": "oa"}]}
        check_references(plan, self.snapshot)
        plan["operations"][0].update(source="la", target="oa")
        with self.assertRaisesRegex(PlanError, "preceding architecture"):
            check_references(plan, self.snapshot)

    def test_trace_follows_realizations_and_allocations(self):
        rows = self.snapshot["elements"]
        for alias, typ, source, target in [
            ("r1", "FunctionRealization", "sa", "oa"), ("r2", "FunctionRealization", "la", "sa"),
            ("a1", "ComponentFunctionalAllocation", "component", "la"),
        ]:
            rows.append({"alias": alias, "type": typ, "links": {"sourceElement": [source], "targetElement": [target]}})
        result = page(self.snapshot, {"trace_from": "oa"})
        self.assertEqual({row["alias"] for row in result["elements"]}, {"oa", "sa", "la", "component", "r1", "r2", "a1"})
        with self.assertRaisesRegex(PlanError, "outside"):
            page(self.snapshot, {"trace_from": "external"})
