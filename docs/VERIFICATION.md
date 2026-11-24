# Verification for 0.9.1

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
