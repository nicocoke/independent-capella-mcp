package org.example.capella.mcp;

/** Capella 7.1 diagram descriptions and the allowlisted breakdown mappings. */
enum DiagramKind {
    LAB("Logical Architecture Blank"),
    SAB("System Architecture Blank"),
    PAB("Physical Architecture Blank"),
    OEB("Operational Entity Breakdown"),
    CIBD("Configuration Items Breakdown"),
    LFBD("Logical Function Breakdown", "LogicalFunction", "LFB_LogicalFunction", "LFB_LogicalFunction_subFunctions"),
    SFBD("System Function Breakdown", "SystemFunction", "SFB_SystemFunction", "SFB_SystemFunction_subFunctions"),
    PFBD("Physical Function Breakdown", "PhysicalFunction", "PFB_PhysicalFunction", "PFB_PhysicalFunction_subFunctions"),
    OABD("Operational Activity Breakdown", "OperationalActivity", "OAB_OperationalActivity", "OAB_OperationalActivity_subFunctions"),
    LCBD("Logical Component Breakdown", "LogicalComponent", "LCB_LogicalComponent", "LCB_LogicalComponent_subComponents"),
    PCBD("Physical Component Breakdown", "PhysicalComponent", "PCB_PhysicalComponent", "PCB_PhysicalComponent_subComponents"),
    EAB("EPBS Architecture Blank"),
    LDFB("Logical Data Flow Blank", "LogicalFunction", "LDFB_Function", "LDFB_Exchange", "LDFB_Pin"),
    SDFB("System Data Flow Blank", "SystemFunction", "SDFB_Function", "SDFB_Exchange", "SDFB_Pin"),
    PDFB("Physical Data Flow Blank", "PhysicalFunction", "PDFB_Function", "PDFB_Exchange", "PDFB_Pin"),
    OAIB("Operational Activity Interaction Blank", "OperationalActivity", "OAIB Operational Activity", "OAIB Interaction", ""),
    OAB("Operational Entity Blank"),
    FCD("Functional Chain Description"),
    OPD("Operational Process Description"),
    FS("Functional Scenario"),
    AIS("Activity Interaction Scenario"),
    MSM("Mode State Machine");

    final String title;
    final String semanticType;
    final String nodeMapping;
    final String edgeMapping;
    final String pinMapping;

    DiagramKind(String title) { this(title, null, null, null); }
    DiagramKind(String title, String semanticType, String nodeMapping, String edgeMapping) {
        this(title, semanticType, nodeMapping, edgeMapping, null);
    }
    DiagramKind(String title, String semanticType, String nodeMapping, String edgeMapping, String pinMapping) {
        this.title = title;
        this.semanticType = semanticType;
        this.nodeMapping = nodeMapping;
        this.edgeMapping = edgeMapping;
        this.pinMapping = pinMapping;
    }

    boolean isBreakdown() { return nodeMapping != null && !isFlow(); }
    boolean isFlow() { return pinMapping != null; }

    static DiagramKind fromTitle(String title) {
        for (var kind : values()) if (kind.title.equals(title)) return kind;
        throw new IllegalArgumentException("Unsupported diagram description");
    }
}
