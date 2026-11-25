# Resume editing after an uncertain job

An `unknown_outcome` receipt means the connector could not establish whether the edit committed. Snapshots remain available while the broker holds the edit queue. Cancelling a later job does not establish the original job’s outcome.

1. In Claude, ask for `capella_connection` and `capella_job` for the reported blocking ID. Record the connection file’s containing directory and keep the file contents private. An `executing` job may still finish. Let it settle before proceeding.
2. Review the original plan and check the affected objects, relationships and diagram views directly in Capella. Settle any changes that the original edit may have made before proceeding. The snapshot is bounded, so a missing search result alone cannot establish that something was never created. Leave the hold in place if you cannot settle the batch’s effects.
3. Check that later submitted jobs are terminal. Cancel still-queued jobs by their existing IDs if they should be discarded. Stop the MCP connector from Capella’s menu and fully quit Claude Desktop. Capella can stay open. The review command refuses to write if the broker still owns the journal or if a job is queued or executing.
4. Extract a copy of `independent-capella-local-0.9.2-win-x64.mcpb` as a ZIP to a fresh folder. From that folder, open PowerShell. Set `$stateDir` to the directory that contains the `connection.json` path reported in step 1. Use the actual path reported by Claude, even if `connection.json` was removed on shutdown. Set `$jobId` to the blocking job ID.

   ```powershell
   $stateDir = 'C:\path\to\IndependentCapellaMCP'
   $jobId = 'paste-the-blocking-job-id-here'
   & .\runtime\python.exe -I -B .\server\local_reconcile.py --state-dir $stateDir --job-id $jobId
   ```

5. If you have settled the original batch’s effects, type `REVIEWED ` followed by the exact job ID when the terminal prompts. The command records the review in the existing journal. `capella_job` will still show the original `unknown_outcome` receipt and add `operator_reviewed_at`.
6. Start Claude with extension 0.9.2, then manually pair Capella. `capella_connection` reports any remaining blocker. Verify the affected model content again before preparing a new edit, and use a fresh snapshot and preview for that edit. The review never queues or replays work.
