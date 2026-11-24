from copy import deepcopy
import test_relay


import unittest
class InventoryChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = test_relay.RelayTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_missing_and_wrong_type_reference(self):
        for parent in ("absent", "root-function"):
            plan = deepcopy(self.fixture.plan)
            plan["operations"][0]["parent"] = parent
            self.assertTrue(self.fixture.service.call("capella_prepare", {"plan": plan})["isError"])

    def test_existing_alias_cannot_be_reused(self):
        plan = deepcopy(self.fixture.plan)
        plan["operations"][0]["id"] = "logical-system"
        self.assertTrue(self.fixture.service.call("capella_prepare", {"plan": plan})["isError"])

    def test_view_order_is_checked(self):
        plan = deepcopy(self.fixture.plan)
        plan["operations"][-1], plan["operations"][-2] = plan["operations"][-2], plan["operations"][-1]
        self.assertTrue(self.fixture.service.call("capella_prepare", {"plan": plan})["isError"])

    def test_malformed_job_id_is_tool_error(self):
        for value in ([], {}, None, 1):
            self.assertTrue(self.fixture.service.call("capella_job", {"job_id": value})["isError"])

    def test_duplicate_inventory_alias_is_rejected(self):
        snapshot = deepcopy(self.fixture.snapshot)
        snapshot["elements"].append(snapshot["elements"][0])
        self.assertEqual(400, self.fixture.call_http("/connector/snapshot", snapshot, test_relay.CONNECTOR)[0]["status"])

    def test_malformed_receipt_is_rejected(self):
        self.assertEqual(400, self.fixture.call_http("/connector/result", {
            "job_id": [], "lease": {}, "status": [], "result": {}}, test_relay.CONNECTOR)[0]["status"])
