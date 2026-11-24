from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from capella_groundwork.core import PlanError
from capella_groundwork.compiler import compile_plan
from relay.preflight import check_references, validate_snapshot
from relay.service import NativeTools
from relay.store import Ledger


def row(alias, typ, arch, **data):
    return {"alias":alias,"type":typ,"architecture":arch,**data}


def plan(*ops):
    return {"version":1,"model_id":"model","base_revision":9,"operations":list(ops)}


def op(operation, alias, **fields):
    return {"op":operation,"id":alias,**fields}


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        la,sa,pa,oa,ep="LogicalArchitecture","SystemAnalysis","PhysicalArchitecture","OperationalAnalysis","EPBSArchitecture"
        records=[
            row("c1","LogicalComponent",la,name="Duplicate"),row("c2","LogicalComponent",la,name="Duplicate"),
            row("f1","LogicalFunction",la),row("f2","LogicalFunction",la),
            row("la_alloc","ComponentFunctionalAllocation",la,owner="c1",links={"sourceElement":["c1"],"targetElement":["f1"]}),
            row("lab","DSemanticDiagram",la,diagram_kind="Logical Architecture Blank",loaded=True,represented=["c1","f1"]),
            row("sp","SystemComponentPkg",sa),row("sf","SystemFunction",sa),
            row("sys","PhysicalComponent",pa,properties={"nature":"UNSET"}),
            row("pf","PhysicalFunction",pa),row("entities","EntityPkg",oa),row("activities","OperationalActivity",oa),
            row("items","ConfigurationItemPkg",ep)]
        self.snapshot={"model_id":"model","session_epoch":"fixture","revision":9,"elements":records,"limits":[]}
        self.store=Ledger(sqlite3.connect(":memory:"));self.addCleanup(self.store.close)
        self.store.bind("scope","connector",self.snapshot)
        self.tools=NativeTools(self.store,"scope")

    def prepare(self,*ops):
        result=self.tools.call("capella_prepare",{"plan":plan(*ops)})
        self.assertFalse(result["isError"],result)
        return result["structuredContent"]

    def query(self,**args):
        result=self.tools.call("capella_snapshot",args)
        self.assertFalse(result["isError"],result)
        return result["structuredContent"]

    def test_duplicate_names_have_distinct_refs_and_page_guards(self):
        first=self.query(search="dupLIC",limit=1)
        self.assertEqual((2,"c1"),(first["matched"],first["elements"][0]["alias"]))
        args=dict(search="duplicate",limit=1,offset=first["next_offset"],revision=9,session_epoch="fixture")
        self.assertEqual("c2",self.query(**args)["elements"][0]["alias"])
        for change in ({"revision":10},{"session_epoch":"new"},{"limit":True},{"offset":-1}):
            self.assertTrue(self.tools.call("capella_snapshot",{**args,**change})["isError"])
        self.assertTrue(self.tools.call("capella_snapshot",{"offset":1})["isError"])
        self.assertTrue(self.tools.call("capella_snapshot",{"file":"x"})["isError"])

    def test_existing_diagram_and_ownership_filter(self):
        self.assertEqual(["c1","f1"],self.query(diagrams=True)["elements"][0]["represented"])
        self.assertEqual("la_alloc",self.query(owner="c1",type="ComponentFunctionalAllocation")["elements"][0]["alias"])
        self.assertEqual(0,self.query(alias="Duplicate")["matched"])
        prepared=self.prepare(op("create_function","extra",name="Duplicate",parent="f2"),
                op("allocate_function","alloc",function="extra",component="c2"),
                op("show_element","view",diagram="lab",element="extra"))
        self.assertEqual(3,len(prepared["payload"]["commands"]))
        self.assertEqual(self.snapshot,self.store.snapshot("scope"))

    def test_existing_allocation_vs_adjustment(self):
        self.assertTrue(self.tools.call("capella_prepare",{"plan":plan(op("allocate_function","new",function="f1",component="c2"))})["isError"])
        self.prepare(op("reassign_allocation","move",allocation="la_alloc",component="c2"))
        for component in ("c1","sys","gone"):
            self.assertTrue(self.tools.call("capella_prepare",{"plan":plan(op("reassign_allocation","move",allocation="la_alloc",component=component))})["isError"])

    def test_system_actor_function_and_diagram(self):
        self.prepare(op("create_system_actor","operator",parent="sp",name="Operator"),
                     op("create_system_function","action",parent="sf",name="Operate"),
                     op("allocate_function","alloc",function="action",component="operator"),
                     op("create_diagram","sab",kind="SAB",target="sp",name="Context"),
                     op("show_element","av",diagram="sab",element="operator"))

    def test_physical_connections_and_behavior_allocation(self):
        self.prepare(op("create_node_component","n",parent="sys",name="A"),
                     op("create_node_component","m",parent="sys",name="B"),
                     op("create_behavior_component","sw",parent="sys",name="Logic"),
                     op("create_physical_function","f",parent="pf",name="Act"),
                     op("allocate_function","allocation",component="sw",function="f"),
                     op("create_physical_port","a",parent="n",name="P"),
                     op("create_physical_port","b",parent="m",name="P"),
                     op("connect_physical_ports","wire",source="a",target="b",name="Cable"))

    def test_deployment_requires_part_types_and_nature(self):
        arch="PhysicalArchitecture"
        self.snapshot["elements"]+= [row("host","Part",arch,owner="sys",links={"abstractType":["node"]}),
            row("impl","Part",arch,owner="sys",links={"abstractType":["logic"]}),
            row("node","PhysicalComponent",arch,properties={"nature":"NODE"}),
            row("logic","PhysicalComponent",arch,properties={"nature":"BEHAVIOR"})]
        check_references(plan(op("deploy_behavior","d",host="host",deployed="impl")),self.snapshot)
        for host,deployed in [("impl","host"),("node","logic")]:
            with self.assertRaises(PlanError): check_references(plan(op("deploy_behavior","d",host=host,deployed=deployed)),self.snapshot)

    def test_oa_activity_and_epbs_item_constraints(self):
        self.prepare(op("create_operational_actor","actor",parent="entities",name="Operator"),
                     op("create_activity","read",name="Read",parent="activities"),
                     op("create_activity","act",name="Act",parent="activities"),
                     op("create_interaction","signal",source="read",target="act",name="Notify"),
                     op("allocate_function","assigned",component="actor",function="act"))
        self.prepare(op("create_configuration_item","ci",parent="items",kind="HWCI",name="Unit"),
                     op("create_diagram","breakdown",kind="CIBD",target="items",name="Breakdown"))
        for kind in ("UNSET","LogicalComponent",[]):
            self.assertTrue(self.tools.call("capella_prepare",{"plan":plan(op("create_configuration_item","ci",parent="items",kind=kind,name="Unit"))})["isError"])

    def test_reject_layer_mismatch_unloaded_or_unsupported_diagram(self):
        invalid=[op("connect_functions","bad",source="sf",target="pf",name="x"),
                 op("create_diagram","bad",kind="OEB",target="c1",name="x"),
                 op("show_element","bad",diagram="lab",element="pf"),
                 op("create_component","c",parent="Duplicate",name="x")]
        for operation in invalid:
            with self.assertRaises(PlanError): check_references(plan(operation),self.snapshot)
        diagram=self.snapshot["elements"][5]
        for typ,title in [("DRepresentationDescriptor","Logical Architecture Blank"),("DSemanticDiagram","Sequence")]:
            diagram.update(type=typ,diagram_kind=title)
            with self.assertRaises(PlanError): check_references(plan(op("show_element","v",diagram="lab",element="c1")),self.snapshot)

    def test_snapshot_bounds_and_unknown_refs(self):
        for changes in ({"links":{"target":[None]*17}},{"represented":["x"]*97},{"properties":{"script":"x"}}):
            snap=deepcopy(self.snapshot);snap["elements"][0].update(changes)
            with self.assertRaises(PlanError):validate_snapshot(snap)
        self.snapshot["elements"][4]["links"]["targetElement"]=[None]
        validate_snapshot(self.snapshot)

    def test_stale_preview_and_submission_under_new_epoch(self):
        request=plan(op("create_system_actor","a",parent="sp",name="Actor"))
        preview=self.prepare(*request["operations"])["preview_digest"]
        for change in ({"revision":10},{"session_epoch":"replacement"}):
            self.store.bind("scope","connector",{**self.snapshot,**change})
            self.assertTrue(self.tools.call("capella_submit",{"plan":request,"preview_digest":preview,"request_id":"retry"})["isError"])

