"""Validate the published subset and type-check a native plan in operation order."""
from capella_groundwork.core import PlanError, _identifier
from capella_groundwork.architecture import OPERATIONS, FUNCTIONS, DIAGRAMS, BREAKDOWNS, FLOWS

LAYERS = {"SystemEngineering","LogicalArchitecture","PhysicalArchitecture","OperationalAnalysis","EPBSArchitecture","SystemAnalysis"}
LINKS = {"source","target","sourceElement","targetElement","abstractType","linkEnds","port","part","deployedElement","location"}
LINKS.add("involved")
PROPERTIES = {"kind","nature","actor","human","itemIdentifier","summary"}
VIEW_TYPES = {"LAB":{"LogicalComponent","LogicalFunction","FunctionalExchange","ComponentExchange"},
              "SAB":{"SystemComponent","SystemFunction","FunctionalExchange","ComponentExchange"},
              "PAB":{"PhysicalComponent","PhysicalFunction","FunctionalExchange","PhysicalLink"},
              "OEB":{"Entity"}, "CIBD":{"ConfigurationItem"},
              "EAB": {"ConfigurationItem"},
              "OAB": {"Entity", "OperationalActivity", "FunctionalExchange"},
              "MSM": {"State", "Mode", "StateTransition"},
              "FCD": {"FunctionalChainInvolvementFunction", "FunctionalChainInvolvementLink"},
              "OPD": {"FunctionalChainInvolvementFunction", "FunctionalChainInvolvementLink"},
              **{code: {target} for code, (_, target) in BREAKDOWNS.items()},
              **{code: {target, "FunctionalExchange"} for code, (_, target) in FLOWS.items()}}


def _within(rows, element, root):
    # An omitted intermediate owner cannot establish authority over this subtree.
    visited = set()
    while element and element not in visited:
        if element == root:
            return True
        visited.add(element)
        element = rows.get(element, {}).get("owner")
    return False


def _text(value, limit):
    if not isinstance(value,str) or len(value)>limit:
        raise PlanError("Invalid publication text")


def validate_snapshot(snapshot):
    required = {"model_id","revision","session_epoch","elements"}
    if not isinstance(snapshot,dict) or not required <= snapshot.keys() <= required | {"limits"}:
        raise PlanError("Invalid snapshot fields")
    _identifier(snapshot["model_id"])
    if type(snapshot["revision"]) is not int or snapshot["revision"]<0:
        raise PlanError("Invalid snapshot revision")
    _text(snapshot["session_epoch"],160)
    if not snapshot["session_epoch"]: raise PlanError("Missing epoch")
    limits = snapshot.get("limits",[])
    if not isinstance(limits,list) or len(limits)>32: raise PlanError("Invalid limits")
    for message in limits: _text(message,160)
    if not isinstance(snapshot["elements"],list) or len(snapshot["elements"])>5000:
        raise PlanError("Invalid inventory size")
    seen=set()
    for row in snapshot["elements"]:
        if not isinstance(row,dict) or not {"alias","type"} <= row.keys() <= {
            "alias","type","name","architecture","owner","containment","description","native_id",
            "properties","links","diagram_kind","represented","loaded"}:
            raise PlanError("Invalid inventory element")
        alias=row["alias"]
        _identifier(alias)
        if alias in seen: raise PlanError("Duplicate inventory alias")
        seen.add(alias)
        _text(row["type"],160)
        if not row["type"]: raise PlanError("Empty type")
        for key in ("name","description","native_id","containment","diagram_kind"):
            if key in row and not (key=="name" and row[key] is None): _text(row[key],4096)
        if "architecture" in row and row["architecture"] not in LAYERS: raise PlanError("Unknown architecture")
        if "owner" in row: _identifier(row["owner"])
        if "loaded" in row and type(row["loaded"]) is not bool: raise PlanError("Invalid diagram state")
        members=row.get("represented",[])
        if not isinstance(members,list) or len(members)>96: raise PlanError("Invalid members")
        for member in members: _identifier(member)
        props=row.get("properties",{})
        if not isinstance(props,dict) or not props.keys()<=PROPERTIES: raise PlanError("Invalid properties")
        for value in props.values(): _text(value,160)
        links=row.get("links",{})
        if not isinstance(links,dict) or not links.keys()<=LINKS: raise PlanError("Invalid links")
        for ids in links.values():
            if not isinstance(ids,list) or len(ids)>16: raise PlanError("Invalid reference list")
            for ref in ids:
                if ref is not None: _identifier(ref)


def check_references(plan,snapshot):
    validate_snapshot(snapshot)
    rows={r["alias"]:r for r in snapshot["elements"]}
    allocations={}
    projected={}
    def one(row,key):
        values=row.get("links",{}).get(key,[])
        return values[0] if len(values)==1 else None
    for r in rows.values():
        if r["type"]=="ComponentFunctionalAllocation":
            allocations.setdefault(one(r,"targetElement"),set()).add(one(r,"sourceElement"))
    def require(ref,types):
        row=rows.get(ref)
        if row is None or row["type"] not in types:
            raise PlanError("Missing or wrong-type reference: "+str(ref))
        return row
    def need_nature(row,nature):
        if row.get("properties",{}).get("nature")!=nature: raise PlanError("Physical component must be "+nature)
    existing=set(rows)
    for op in plan["operations"]:
        kind,alias=op["op"],op["id"]
        if alias in rows: raise PlanError("Alias already exists: "+alias)
        result={"alias":alias}
        if kind in OPERATIONS:
            specs,result["type"]=OPERATIONS[kind]
            inputs={k:require(op[k],types) for k,types in specs.items()}
            if kind in {"realize_capability", "realize_function", "realize_system_component"}:
                pair = (inputs["source"]["type"], inputs["target"]["type"])
                if pair not in {("Capability", "OperationalCapability"), ("CapabilityRealization", "Capability"),
                                ("SystemFunction", "OperationalActivity"), ("LogicalFunction", "SystemFunction"),
                                ("LogicalComponent", "SystemComponent")}:
                    raise PlanError("Expected a supported realization to the preceding architecture")
            elif len({r.get("architecture") for r in inputs.values()})!=1:
                raise PlanError("Architecture mismatch")
            if "limits" not in snapshot: raise PlanError("This operation requires the updated native connector")
            if kind in {"create_node_component","create_behavior_component"}:
                result["properties"]={"nature":"NODE" if kind=="create_node_component" else "BEHAVIOR"}
                if kind=="create_node_component" and inputs["parent"].get("properties",{}).get("nature")=="BEHAVIOR":
                    raise PlanError("Behavior cannot own a node")
            if kind=="create_physical_port": need_nature(inputs["parent"],"NODE")
            if kind=="deploy_behavior":
                for field,nature in (("host","NODE"),("deployed","BEHAVIOR")):
                    need_nature(require(one(inputs[field],"abstractType"),{"PhysicalComponent"}),nature)
                if inputs["host"].get("owner")!=inputs["deployed"].get("owner"): raise PlanError("Sibling Parts required")
            if kind=="connect_physical_ports":
                a,b=(require(inputs[k].get("owner"),{"PhysicalComponent"}) for k in ("source","target"))
                for r in (a,b): need_nature(r,"NODE")
                if a==b or a.get("owner")!=b.get("owner"): raise PlanError("Distinct sibling nodes required")
            if kind=="create_interaction" and op["source"]==op["target"]: raise PlanError("Distinct activities required")
            if kind == "create_interaction":
                projected[alias] = {op["source"], op["target"]}
            if kind == "connect_components":
                if op["source"] == op["target"] or inputs["source"]["type"] != inputs["target"]["type"]:
                    raise PlanError("Expected distinct components in the same architecture")
                projected[alias] = {op["source"], op["target"]}
            if kind == "create_transition":
                if not inputs["source"].get("owner") or inputs["source"]["owner"] != inputs["target"].get("owner"):
                    raise PlanError("Transition endpoints must share a region")
                projected[alias] = {op["source"], op["target"]}
            if kind=="reassign_allocation":
                old=inputs["allocation"]
                fn=one(old,"targetElement")
                require(fn,{FUNCTIONS[inputs["component"]["type"]]})
                if allocations.get(fn)!= {one(old,"sourceElement")} or op["component"] in allocations[fn]:
                    raise PlanError("Expected a unique allocation to a different owner")
                if inputs["component"]["type"]=="PhysicalComponent": need_nature(inputs["component"],"BEHAVIOR")
                allocations[fn]={op["component"]}
                result["links"]={"sourceElement":[op["component"]],"targetElement":[fn]}
            result["architecture"]=next(iter(inputs.values())).get("architecture")
        elif kind in ("create_component","create_function"):
            t="LogicalComponent" if kind=="create_component" else "LogicalFunction"
            parent=require(op["parent"],{t})
            result.update(type=t,architecture=parent.get("architecture"))
        elif kind=="allocate_function":
            component=require(op["component"],FUNCTIONS)
            func=require(op["function"],{FUNCTIONS[component["type"]]})
            if component.get("architecture")!=func.get("architecture"): raise PlanError("Architecture mismatch")
            if component["type"]=="PhysicalComponent": need_nature(component,"BEHAVIOR")
            if allocations.get(op["function"]): raise PlanError("Function already allocated")
            allocations[op["function"]]={op["component"]}
            result.update(type="ComponentFunctionalAllocation",architecture=component.get("architecture"),
                          links={"sourceElement":[op["component"]],"targetElement":[op["function"]]})
        elif kind=="connect_functions":
            src=require(op["source"],{"LogicalFunction","PhysicalFunction","SystemFunction"})
            dst=require(op["target"],{src["type"]})
            if src==dst or src.get("architecture")!=dst.get("architecture"): raise PlanError("Invalid exchange endpoints")
            projected[alias]={op["source"],op["target"]}
            result.update(type="FunctionalExchange",architecture=src.get("architecture"))
        elif kind=="create_diagram":
            title,types=DIAGRAMS[op["kind"]]
            target=require(op["target"],types)
            result.update(type="DSemanticDiagram", diagram_kind=title, represented=[],
                          architecture=target.get("architecture"), owner=op["target"])
        else:
            diagram=require(op["diagram"],{"DSemanticDiagram","DDiagram"})
            title=diagram.get("diagram_kind","Logical Architecture Blank")
            code=next((k for k,(name,_) in DIAGRAMS.items() if name==title),None)
            obj=require(op["element"],VIEW_TYPES.get(code,set()))
            if obj.get("architecture")!=diagram.get("architecture"): raise PlanError("Diagram architecture mismatch")
            if code in BREAKDOWNS and not _within(rows, op["element"], diagram.get("owner")):
                raise PlanError("Breakdown element must belong to the selected diagram's root subtree")
            if code == "EAB" and not _within(rows, op["element"], diagram.get("owner")):
                raise PlanError("Configuration item must belong to the selected diagram's root subtree")
            # Native views can already exist. Apply visibility rules to diagrams built by this plan.
            if op["diagram"] not in existing:
                visible=diagram["represented"]
                prerequisites = projected.get(op["element"], set())
                if code not in BREAKDOWNS and code not in FLOWS:
                    prerequisites = prerequisites | allocations.get(op["element"], set())
                if not prerequisites<=set(visible) or op["element"] in visible: raise PlanError("Invalid view ordering")
                visible.append(op["element"])
            result["type"]="DDiagramElement"
        if "parent" in op: result["owner"]=op["parent"]
        rows[alias]=result

