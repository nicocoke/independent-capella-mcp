import unittest

from capella_groundwork.architecture import BREAKDOWNS, FLOWS
from capella_groundwork.compiler import compile_plan
from capella_groundwork.core import PlanError
from capella_groundwork.tools import plan_schema
from relay.preflight import check_references


class BreakdownTests(unittest.TestCase):
    def fixture(self, title, semantic_type, layer):
        def row(alias, **fields):
            return {"alias": alias, "type": semantic_type, "architecture": layer, **fields}

        return {"model_id": "native-model", "revision": 1, "session_epoch": "test",
                "limits": [],
                "elements": [row("root"), row("child", owner="root"),
                             row("grandchild", owner="child"),
                             row("elsewhere"), row("old", type="DSemanticDiagram",
                                                   owner="root", diagram_kind=title, loaded=True)]}

    def plan(self, *operations):
        return {"version": 1, "model_id": "native-model", "base_revision": 1,
                "operations": list(operations)}

    def show(self, diagram, element):
        return {"op": "show_element", "id": "view", "diagram": diagram, "element": element}

    def test_all_five_breakdowns_accept_creation_and_existing_subtree_view(self):
        layers = {"LFBD": "LogicalArchitecture", "LCBD": "LogicalArchitecture",
                  "SFBD": "SystemAnalysis", "PFBD": "PhysicalArchitecture",
                  "OABD": "OperationalAnalysis", "PCBD": "PhysicalArchitecture"}
        for code, (title, semantic_type) in BREAKDOWNS.items():
            with self.subTest(code=code):
                data = self.fixture(title, semantic_type, layers[code])
                create = {"op": "create_diagram", "id": "new", "name": title,
                          "target": "root", "kind": code}
                plan = self.plan(create, self.show("new", "grandchild"))
                check_references(plan, data)
                self.assertEqual(code, compile_plan(plan)["commands"][0]["kind"])
                check_references(self.plan(self.show("old", "grandchild")), data)
                with self.assertRaisesRegex(PlanError, "root subtree"):
                    check_references(self.plan(self.show("old", "elsewhere")), data)

    def test_new_function_can_be_shown_without_allocation(self):
        title, semantic_type = BREAKDOWNS["LFBD"]
        data = self.fixture(title, semantic_type, "LogicalArchitecture")
        plan = self.plan({"op": "create_function", "id": "new", "parent": "grandchild",
                          "name": "Observe"}, self.show("old", "new"))
        check_references(plan, data)

    def test_reject_wrong_type_and_unloaded_representation(self):
        title, semantic_type = BREAKDOWNS["LCBD"]
        data = self.fixture(title, semantic_type, "LogicalArchitecture")
        data["elements"][1]["type"] = "LogicalFunction"
        with self.assertRaises(PlanError):
            check_references(self.plan(self.show("old", "child")), data)
        data["elements"][-1]["type"] = "DRepresentationDescriptor"
        with self.assertRaises(PlanError):
            check_references(self.plan(self.show("old", "root")), data)

    def test_advertises_exactly_twenty_two_native_diagram_kinds(self):
        variants = plan_schema(native=True)["properties"]["operations"]["items"]["oneOf"]
        diagram = next(v for v in variants if v["properties"]["op"]["const"] == "create_diagram")
        self.assertEqual(set(diagram["properties"]["kind"]["enum"]),
                         {"LAB", "SAB", "PAB", "OEB", "CIBD", "LFBD", "LCBD", "SFBD", "PFBD", "OABD", "PCBD", "LDFB", "SDFB", "PDFB", "OAIB", "EAB", "OAB", "FCD", "OPD", "FS", "AIS", "MSM"})

    def test_flow_connection_requires_both_endpoint_views_in_new_diagram(self):
        for code, (title, semantic_type) in FLOWS.items():
            with self.subTest(code=code):
                data = self.fixture(title, semantic_type, "LogicalArchitecture")
                create = {"op": "create_diagram", "id": "flow", "kind": code,
                          "name": title, "target": "root"}
                connect = {"op": "create_interaction" if code == "OAIB" else "connect_functions",
                           "id": "signal", "source": "child", "target": "grandchild", "name": "Check"}
                show_source = dict(self.show("flow", "child"), id="sourceView")
                show_target = dict(self.show("flow", "grandchild"), id="targetView")
                show_edge = self.show("flow", "signal")
                check_references(self.plan(create, connect, show_source, show_target, show_edge), data)
                with self.assertRaisesRegex(PlanError, "view ordering"):
                    check_references(self.plan(create, connect, show_source, show_edge), data)
