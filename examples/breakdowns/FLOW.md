# Extend an existing flow diagram

Find the diagram descriptor and the two function references in a fresh snapshot. Create the exchange between those function references, then insert its view. The plan below illustrates the operations for a Logical, System or Physical Data Flow Blank when both endpoint functions already have views.

```json
[
  {"op":"connect_functions","id":"statusExchange","name":"Status","source":"native_SOURCE","target":"native_TARGET"},
  {"op":"show_element","id":"statusView","diagram":"diagram_FLOW","element":"statusExchange"}
]
```

For an Operational Activity Interaction Blank, use two operational activity references and the `create_interaction` operation in place of `connect_functions`. To create a diagram first, use `create_diagram` with kind `LDFB`, `SDFB`, `PDFB` or `OAIB` and the corresponding function or activity as its target. Add missing endpoint views before adding the edge. Prepare the plan against the current revision and submit its exact preview digest. Inspect the returned job and confirm the views before saving.
