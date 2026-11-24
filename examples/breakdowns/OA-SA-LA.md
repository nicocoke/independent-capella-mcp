# Trace a capability across OA, SA and LA

Select System Engineering when pairing. Find the three capability package aliases with a fresh snapshot. In a revision-bound plan, create a capability in each layer and connect them in downstream-to-upstream order.

```json
[
  {"op":"create_operational_capability","id":"response","parent":"native_OA_PACKAGE","name":"Emergency response"},
  {"op":"create_system_capability","id":"coordinate","parent":"native_SA_PACKAGE","name":"Coordinate response"},
  {"op":"create_logical_capability","id":"dispatch","parent":"native_LA_PACKAGE","name":"Dispatch resources"},
  {"op":"realize_capability","id":"systemTrace","source":"coordinate","target":"response"},
  {"op":"realize_capability","id":"logicalTrace","source":"dispatch","target":"coordinate"}
]
```

Use `involve_operational_entity` with the operational capability as `parent` and the entity as `element`. Use `involve_capability_path` with the capability as `parent` and a same-layer process or chain as `element`. For existing models, substitute the exact aliases published by the snapshot.

After an unsaved-success receipt, query `capella_snapshot` with `trace_from` and the operational capability's stable reference. The same filter follows activity-to-function realization links and function-to-component allocations.
