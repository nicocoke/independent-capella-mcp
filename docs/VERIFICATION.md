# Verification

## Claude Desktop extension 0.9.2 and Capella plug-in 0.7.2

| Check | Result |
|---|---|
| Offline suite | 118 tests passed. The baseline on 0.9.1 was 113 tests. |
| Extension 0.9.2 packaged Windows clients | 25 synthetic multi-process checks and 11 packaged stdio lifecycle checks passed. |
| Plug-in 0.7.2 with Capella 7.1.0 | 273 checks passed using build `0.7.2.202611251139` in a disposable Capella product. |
| Actual Claude Desktop | The maintainer reported that 0.9.2 exposed an existing edit blocker. The 0.7.2 fix was exercised through the native harness. Acceptance through the full installed Claude Desktop and Capella workflow remains open. |

The 0.9.2 tests cover continued reads during a hold, identification of the blocking job by independent clients, journal persistence, and the operator review path. The original receipt is retained and the review queues no work.

On plug-in 0.7.1, a synthetic synchronized Operational Analysis Mode State Machine diagram already displayed ten nested states and five transitions. A batch of 15 `show_element` operations failed on the diagram-region check. On 0.7.2 the same batch succeeded unsaved without advancing the revision, opening an editor, or replacing a view. A state outside the diagram’s Region subtree was still rejected.

- [0.9.2 multi-process checks](evidence/processes-0.9.2.json)
- [0.9.2 packaged stdio checks](evidence/packaged-stdio-0.9.2.json)
- [0.7.1 reproduction](evidence/msm-0.7.1-regression.json)
- [0.7.2 native assertions](evidence/native-0.7.2.json)

## 0.9.1 preview

| Check | Status |
|---|---|
| Offline Python suite | 113 tests passed. The runner blocks sockets and subprocesses. |
| Native Capella 7.1.0 | 263 checks passed with the published connector JAR, build `0.7.1.202611241414`, loaded in a fresh disposable Capella product. |
| Packaged Windows stdio | 11 checks passed with three independent processes from the extracted MCPB, including broker ownership transfer. |
| Actual Claude Desktop | The maintainer reported successful capability, function and component traces and a port-based SAB edit on 0.9.0. They subsequently reported opening a created demo diagram successfully after the move to manual editor opening. |
| Clean external installation | The full 0.9.1 installation and authenticated edit workflow still need a recorded run on a second clean setup. The native harness registered the shipping JAR directly. |
| Scenario diagrams | Functional Scenario and Activity Interaction Scenario have experimental creation-only recipes. Native acceptance evidence is pending. |

The native test checked that 19 creation paths left the workbench editor count unchanged. It also verified port-based view insertion into SAB and LAB. The patch removes automatic editor opening and layout from MCP jobs. The original repeating refresh popup was reported during a 0.9.0 live test.

The GitHub starter was tested before handoff. Its offline command passed all 113 tests and its portable native runner reproduced all 263 native checks in a new disposable product. The workflow file is included for GitHub CI. The run above was local.

- [Native assertions](evidence/native-0.9.1.json)
- [Packaged stdio assertions](evidence/packaged-stdio-0.9.1.json)
