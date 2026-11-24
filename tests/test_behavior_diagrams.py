import unittest

from capella_groundwork.compiler import compile_plan
from capella_groundwork.core import PlanError
from relay.preflight import check_references


class BehaviorDiagramTests(unittest.TestCase):
    def test_transition_checks_region_for_new_and_existing_states(self):
        layer = {"architecture": "LogicalArchitecture"}
        snapshot = {"model_id": "native-model", "revision": 1, "session_epoch": "fixture", "limits": [],
                    "elements": [dict(layer, alias="main", type="Region"),
                                 dict(layer, alias="active", type="State", owner="main"),
                                 dict(layer, alias="other", type="Mode", owner="elsewhere")]}
        plan = {"version": 1, "model_id": "native-model", "base_revision": 1, "operations": [
            {"op": "create_mode", "id": "idle", "name": "Idle", "parent": "main"},
            {"op": "create_transition", "id": "start", "name": "Start", "source": "idle", "target": "active"},
        ]}
        check_references(plan, snapshot)
        self.assertEqual("create_transition", compile_plan(plan)["commands"][1]["recipe"])
        plan["operations"][1]["target"] = "other"
        with self.assertRaisesRegex(PlanError, "share a region"):
            check_references(plan, snapshot)
