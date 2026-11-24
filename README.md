# Independent Capella MCP

A local integration that lets Claude Desktop read, edit and create native diagrams in an explicitly paired Eclipse Capella model.

**Preview · Windows x64 · Capella 7.1.0**  
Claude Desktop starts the MCP process locally. In Capella, you choose the model and start the connector. Claude can prepare and submit changes through the MCP tools, and you choose whether to save in Capella.

## What it supports

- Read model elements, relationships and diagrams by stable reference.
- Create capabilities and follow explicit realization and allocation links across Operational Analysis, System Analysis and Logical Architecture.
- Edit supported entities, activities, components, functions, allocations and exchanges.
- Create and extend 20 diagram types, including architecture blanks, breakdowns, data-flow diagrams, operational process descriptions, and mode/state machines. Two scenario types have experimental creation-only recipes.
- Create native diagram content while leaving editor opening and arrangement to you.

See the [capability matrix](docs/CAPABILITIES.md) for supported operations and prerequisites.

## Try it

1. From the release assets, get the Windows `.mcpb`, the matching Capella update-site ZIP and the optional synthetic project.
2. Install the Capella feature and Claude extension using the [installation guide](docs/CLAUDE-DESKTOP.md).
3. Open a disposable model. Select **System Engineering** to pair across architecture levels, or select one architecture to limit the scope.
4. In Claude, ask “Read a snapshot of the paired Capella model and list the diagrams with their names and aliases.”

On success the edit tools return `succeeded_unsaved`. A fresh snapshot may take a few seconds to reach the receipt revision. Before another edit, use a snapshot at the receipt revision or later, with the same session. See the [diagram and trace examples](examples/breakdowns/README.md).

## Develop

Run the dependency-free Python tests from the repo root.

```text
python -B tools/verify_offline.py
```

The [native build notes](native/BUILD.md) explain the prepared Capella target. The [disposable test procedure](docs/ISOLATED-TRIAL.md) covers the Windows native run. See [verification](docs/VERIFICATION.md) for the tested scope.

## Licensing and project status

Project source is licensed under the MIT License. See [Third-party notices](THIRD-PARTY-NOTICES.md) for the bundled dependencies. This is an independent integration for Eclipse Capella. Capella is a trademark of the Eclipse Foundation.
