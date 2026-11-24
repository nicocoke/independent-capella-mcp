# Capability matrix for 0.9.1

| New operation | Scope |
|---|---|
| Create operational, system and logical capabilities | Select the matching capability package. |
| Involve an entity or path | Link an OA entity to an operational capability, or link an operational process or functional chain to a same-layer capability. |
| Realize capabilities and functions | OA activity or capability → SA function or capability → LA function or capability realization. In each edit, `source` is the downstream realizing element. |
| Realize a system component | Use a logical component and a system component with matching actor status. |
| Trace across layers | Pair System Engineering, then use `capella_snapshot` with `trace_from` and an exact alias. The bounded query returns explicit downstream realizations and function allocations, with their relationship rows. |
| Connect SA or LA components | Create an oriented FLOW exchange with fresh input and output ports in singleton-component mode. With both component Parts visible, show the exchange in an existing SAB or LAB. |

Published trace results are bounded by the paired inventory. Use the returned relationship endpoints and inventory limits when identifying gaps. Interface and exchanged-item authoring, missions and ordered scenario message editing are outside these additions.

| Added in 0.8.0 | Creation target | Available edit operations |
|---|---|---|
| Operational Entity Blank (OAB) | Entity or entity package | Show entities and actors, uniquely allocated activities, and direct interactions |
| Functional Chain Description (FCD) | Existing Capella functional chain accepted by the viewpoint | Add function and exchange involvements and show their nodes and links |
| Operational Process Description (OPD) | Existing operational process | Add activity and interaction involvements and show their nodes and links |
| Mode State Machine (MSM) | Existing state-machine region | Add and show states, modes and transitions within the region |
| Functional Scenario (FS) | Existing functional scenario accepted by the viewpoint | Native diagram creation |
| Activity Interaction Scenario (AIS) | Existing operational activity scenario accepted by the viewpoint | Native diagram creation |

For a chain or process, add endpoint involvements before its exchange involvement. Show both endpoint nodes before showing the link. State transitions require endpoints in the same region. Trigger and guard editing, chain control-flow editing, and scenario lifeline and message editing remain outside the implemented recipes. See the verification record for the tested subset.

A manually paired architecture is a supported unit of editing. Selecting System Engineering also permits inspection across layers in the selected model. All writes require a revision-bound preview and run through native validation. Diagram view insertion is an explicit plan operation.

| Architecture | Read | Semantic edits | Create and extend loaded diagrams |
|---|---|---|---|
| Logical Architecture | Components, Parts, function containment, allocation objects, ports and exchange endpoints | Child logical component with native Part, child function, allocate or reassign, connect two existing functions with fresh ports | Logical Architecture Blank (LAB), Logical Function Breakdown (LFBD), Logical Component Breakdown (LCBD) |
| System Analysis | System and actor components, functions, allocations and exchanges | Create an actor under a system component package, child system function, allocate or reassign, connect functions | System Architecture Blank (SAB), System Function Breakdown (SFBD) |
| Physical Architecture | Component nature and kind, Parts, deployment location and deployed Part, physical ports, link ends, functions and allocations | Create NODE or BEHAVIOR components and physical functions. Allocate functions to behavior, deploy a sibling behavior Part on a node Part, add physical ports on nodes, connect two ports on distinct sibling nodes, connect physical functions | Physical Architecture Blank (PAB), Physical Function Breakdown (PFBD) |
| Operational Analysis | Operational entities and actors, activities, interaction endpoints and allocations | Create entities or operational actors in an entity package or under a non-actor entity, child activities, direct activity interactions and entity/activity allocations | Operational Entity Breakdown (OEB), Operational Activity Breakdown (OABD) |
| EPBS | Configuration item containment, kind, item identifier and physical artifact realization endpoints when in scope | Create a typed configuration item under an item or item package | Configuration Items Breakdown (CIBD), with configuration item nodes |

Use the short code in `create_diagram.kind`. For LFBD, SFBD, PFBD and OABD, select a function or activity of the corresponding layer. For LCBD, select a logical component in a project with singleton components. Native creation displays eligible descendants. On a loaded diagram, `show_element` adds or reuses the node and its native containment edge to an already visible parent. Add ancestors first when needed. Capella hides the architecture's artificial root, so its direct children need no parent view there. Breakdown views follow containment. Function allocations and exchanges belong to the architecture blank diagrams, and operational interaction views need a different diagram type. LCBD extension supports direct component ownership and unambiguous Parts.

LAB and SAB show component Parts, allocated functions and functional exchanges. PAB also shows singly deployed behavior under its visible host and single-Part physical links.

| Added in 0.7.0 | Creation target | Supported view edits |
|---|---|---|
| Logical Data Flow Blank (LDFB) | Logical function | Add functions and port-based functional exchanges |
| System Data Flow Blank (SDFB) | System function | Add functions and port-based functional exchanges |
| Physical Data Flow Blank (PDFB) | Physical function | Add functions and port-based functional exchanges |
| Operational Activity Interaction Blank (OAIB) | Operational activity | Add activities and direct activity interactions |
| Physical Component Breakdown (PCBD) | Physical component | Add owned physical components and single-Part containment edges |
| EPBS Architecture Blank (EAB) | Configuration item or item package | Add in-scope configuration item Part views |

Show both endpoints before an exchange or interaction. The three Data Flow Blank mappings add the native input and output pin views when needed. Function allocation is independent of flow view insertion. These four flow types currently target function- or activity-owned diagrams. PCBD uses the same parent-first containment rules as LCBD. EAB inserts configuration item views under the selected owner or its already-visible nested configuration item.

**Stable references.** Query by exact `alias`, `native_id`, `type`, `architecture` or `owner`. Use `search` for case-insensitive name/description substring matching, `links_to` for relationship rows with a matching stored endpoint and `diagrams: true` for descriptor rows. Each diagram includes its native description name, semantic target in `owner`, load status and bounded `represented` references for loaded diagrams. Part views report the represented component. Different diagrams can share a name. Use the descriptor alias for the requested diagram. Names alone never identify edit targets.

**Read limits.** Each paired root contributes at most 1,500 descendants. Publication has a conservative 216,000-unit JSON size budget, scans up to 512 descriptors in the main analysis, and inspects up to 2,048 contained objects or 96 unique represented references per diagram. A row exposes up to 16 values per supported relationship, 160 characters of label and 512 of description. The default page is 24 rows, maximum 50, with an additional response-size limit. Later pages require `session_epoch` and `revision`. Pagination covers the bounded publication. Proxy targets, external resources, secondary analysis files, unsupported metamodel features and unloaded diagram contents can be absent. Read `limits` alongside results. The native Capella and EMF validation remains authoritative.

**Edit prerequisites.** Select a functional parent separately from an allocating component. Allocation reassignment identifies the actual allocation and requires one in-scope source, function and compatible new owner. Operational interactions directly connect activities. LA, SA and PA functional exchanges create input/output ports on distinct same-layer functions with a common functional ancestor. A PA deployment requires existing Part references, a node host and an undeployed behavior Part with the same container. Physical links use two physical ports on distinct sibling node components in single-Part mode. Multipart links, multi-host view selection, and node deployment are outside this release.

**Diagram boundaries.** The requested Capella viewpoint must already be enabled. Show component views before functions, and endpoint functions or nodes before connections. An existing diagram must be loaded, match the supported description and belong to the element's architecture. Ambiguous Part or view choices are rejected. Existing diagrams receive targeted view operations. Open and arrange diagrams manually in Capella after the connector job finishes. Native Sirius synchronization can generate mandatory views on its own. Other representations may be discoverable without supporting edits. OA and EPBS support the specific breakdown diagrams in the matrix. Destructive operations, generic feature writes, rename, auto-save, unrelated file discovery and arbitrary scripts have no tool.

See [verification](VERIFICATION.md) for which matrix entries received runtime checks and which still require further coverage.
