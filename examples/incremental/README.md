# Incremental examples

These five plans use real object IDs from the accompanying synthetic fixture. `inventory.json` is the native controller's whole-model publication after the disposable trial. The Python suite prepares each plan against that exact publication. The trial executed its own recipes, recorded separately in the verification report.

| File prefix | Change |
|---|---|
| LA | Add one logical function to an existing function tree, then allocate it to the existing sensor |
| SA | Create one actor and insert its Part view into the existing SAB |
| PA | Add one physical node with a physical port |
| OA | Add one activity and allocate it to an existing entity |
| EPBS | Add a hardware configuration item and show it on the existing breakdown diagram |

To try a plan manually, use a fresh copy of `capella-mcp-synthetic-0.9.1.zip` in a disposable workspace. Open the project yourself and pair the intended scope. Use the live snapshot to resolve the parent, endpoints and diagram references, update the model ID and revision, then prepare. A new pairing has its own epoch. In a different project, substitute every input reference from that project's inventory.

To inspect an existing connection, search for its name and type, follow its stored endpoints and then their owner references. For example, a logical functional exchange points to its function ports, and each port's owner identifies the function. An operational interaction points directly to activities. For allocations or realizations involving one element, use `links_to` with its alias. For a diagram, query `diagrams: true`, then use its descriptor alias to read represented elements.

A useful first request in Claude is “List the logical components named Sensor, include their owners and stable references, and show which detected diagrams represent each one.” For an edit, specify the chosen reference and ask for a preview of only that change. A semantic creation and its view insertion may be separate plans or two ordered operations in a single plan.

