# Create and extend a breakdown diagram

Pair Logical Architecture or the logical system with its root function tree, then use `capella_snapshot` to find the parent function and its stable reference. To create a Logical Function Breakdown on that function, use this operation in a revision-bound plan.

```json
{"op":"create_diagram","id":"breakdown","kind":"LFBD","name":"Monitoring breakdown","target":"native_PARENT"}
```

Use a fresh snapshot to get the created diagram's descriptor alias and confirm its semantic owner. To add one child to the existing diagram, use these two operations together. Substitute the actual parent and diagram aliases. The parent should be visible, or be the architecture root that Capella omits from the view.

```json
[
  {"op":"create_function","id":"checkSample","name":"Check sample","parent":"native_PARENT"},
  {"op":"show_element","id":"checkView","diagram":"diagram_DESCRIPTOR","element":"checkSample"}
]
```

The same pattern applies to the other new breakdowns.

The [concrete LFBD plan](LFBD-add-child-to-existing.json) uses IDs from the saved 0.6.0 synthetic project. Open that project yourself in a disposable workspace and pair Logical Architecture. Confirm its revision and references before preparing the plan.

| Kind | Selected diagram target | Create a child |
|---|---|---|
| LFBD | Logical function | `create_function` |
| LCBD | Logical component in a singleton-component project | `create_component` |
| SFBD | System function | `create_system_function` |
| PFBD | Physical function | `create_physical_function` |
| OABD | Operational activity | `create_activity` |

Pair the architecture owning the target. Use `capella_prepare`, submit the exact preview digest with a unique request ID, then check the outcome with `capella_job`. Confirm the represented child in a fresh diagram snapshot before deciding whether to save in Capella.
