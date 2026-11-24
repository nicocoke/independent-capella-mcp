# Disposable native runtime harness

This test-only bundle is deliberately outside the shipping native feature and update-site build. Its startup extension runs only when an explicit `capella.mcp.disposable.test` system property identifies a folder containing `AUTHORIZED-SYNTHETIC-ONLY`, and the active workspace exactly matches that folder's `workspace` child. It rejects a nonempty workspace before creating a model.

The harness uses Capella's project-creation services to create a synthetic model, executes the monitoring intent through `SessionExecutor`, checks native ownership/allocation/exchange/view references, opens and exports the new diagram, checks unsaved revision tracking and a late transaction failure, and explicitly saves only the synthetic fixture. It records checks and failures as JSON and closes its own workbench.

The direct trial additionally checks native JSON receipts, duplicate prevention and save/reopen. `RelayTrial` runs only in the explicit relay test mode; it uses the actual `OutboundConnector` against the private HTTPS relay while an external synthetic MCP client prepares/submits/polls the job. The final installed-plug-in run also checks command registration. Both trials passed independently on Capella 7.1.0 on 23 November 2026, after the earlier 7.0.1 baseline. The new reports assert the requested runtime version and record the installed Capella and MCP bundle versions. Reports are in `docs/evidence/`.

The normal connector still does not save automatically and has no startup extension. Do not add this bundle to the shipping feature. Runtime evidence must identify whether the bundle was loaded through a development configuration or installed through p2; these establish different things.

Build/run orchestration currently lives under the chat's `work/` folder. Each run uses a fresh trial folder, dedicated user/settings directories, a new workspace, a bounded JVM heap and a process timeout. Only the exact child process started by the launcher is terminated on timeout.
