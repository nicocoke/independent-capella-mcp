"""Read-only bounded pages of the paired connector publication."""
import json
from collections import defaultdict, deque
from capella_groundwork.core import PlanError

QUERY = {key: {"type": "string", "minLength": 1, "maxLength": 160}
         for key in ("alias", "type", "owner", "architecture", "search", "session_epoch", "links_to", "native_id", "trace_from")}
QUERY.update(limit={"type":"integer","minimum":1,"maximum":50},
             offset={"type":"integer","minimum":0,"maximum":5000},
             revision={"type":"integer","minimum":0}, diagrams={"type":"boolean"})

def _trace(rows, start):
    indexed = {row["alias"] for row in rows}
    if start not in indexed:
        raise PlanError("Trace start is outside the published inventory")
    neighbors = defaultdict(list)
    for row in rows:
        if not (row["type"].endswith("Realization") or row["type"] == "ComponentFunctionalAllocation"):
            continue
        links = row.get("links", {})
        source, target = links.get("sourceElement", []), links.get("targetElement", [])
        if len(source) == len(target) == 1 and source[0] in indexed and target[0] in indexed:
            neighbors[target[0]].append((row["alias"], source[0]))
    reached = {start}
    pending = deque([start])
    while pending:
        for link, dest in neighbors[pending.popleft()]:
            if dest not in reached:
                pending.append(dest)
            reached.update((link, dest))
    return reached


def page(snapshot, query):
    if not query and "limits" not in snapshot:
        return snapshot  # 0.4.1 connector response
    for key, value in query.items():
        rule = QUERY[key]
        if rule["type"] == "string" and (type(value) is not str or not 1 <= len(value) <= 160):
            raise PlanError("Invalid query text")
        if rule["type"] == "integer" and (type(value) is not int or not rule["minimum"] <= value <= rule.get("maximum", 2**63-1)):
            raise PlanError("Invalid query range")
        if rule["type"] == "boolean" and type(value) is not bool:
            raise PlanError("Invalid diagram filter")
    if query.get("offset") and not {"revision","session_epoch"} <= query.keys():
        raise PlanError("Later pages require the revision and session_epoch from the first page")
    if any(query[k] != snapshot[k] for k in ("revision","session_epoch") if k in query):
        raise PlanError("Stale inspection page")
    trace = _trace(snapshot["elements"], query["trace_from"]) if "trace_from" in query else None
    rows = [r for r in snapshot["elements"] if
            (trace is None or r["alias"] in trace) and
            all(r.get(k) == query[k] for k in ("alias","owner","type","architecture","native_id") if k in query)
            and ("links_to" not in query or any(query["links_to"] in ids for ids in r.get("links",{}).values()))
            and ("diagrams" not in query or ("diagram_kind" in r) == query["diagrams"])
            and query.get("search","").casefold() in ((r.get("name") or "")+" "+r.get("description","")).casefold()]
    rows.sort(key=lambda r:r["alias"])
    offset, limit = query.get("offset",0), query.get("limit",24)
    # Tool results carry both structured content and its JSON text. Fit follower transport too.
    chunk=[]
    budget=64000
    for row in rows[offset:offset+limit]:
        size=len(json.dumps(row,ensure_ascii=True))
        if chunk and size>budget: break
        chunk.append(row)
        budget-=size
    limit=len(chunk)
    return {**snapshot,"elements":chunk,"matched":len(rows),
            "next_offset":offset+limit if offset+limit < len(rows) else None,
            "limits":snapshot.get("limits",["Legacy inventory has no completeness metadata"])}

