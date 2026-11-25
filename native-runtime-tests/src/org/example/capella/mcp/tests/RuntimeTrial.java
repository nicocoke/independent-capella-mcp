package org.example.capella.mcp.tests;

import java.nio.file.Files;
import java.nio.file.Path;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.*;
import com.google.gson.*;
import org.eclipse.core.resources.ResourcesPlugin;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.transaction.RecordingCommand;
import org.eclipse.sirius.business.api.session.Session;
import org.eclipse.sirius.business.api.session.SessionManager;
import org.eclipse.sirius.business.api.dialect.DialectManager;
import org.eclipse.sirius.ui.business.api.viewpoint.ViewpointSelection;
import org.eclipse.sirius.ui.business.api.dialect.DialectUIManager;
import org.eclipse.sirius.ui.business.api.dialect.ExportFormat;
import org.eclipse.sirius.common.tools.api.resource.ImageFileFormat;
import org.eclipse.sirius.diagram.DDiagram;
import org.eclipse.sirius.diagram.DEdge;
import org.eclipse.ui.IStartup;
import org.eclipse.ui.PlatformUI;
import org.polarsys.capella.core.platform.sirius.ui.project.operations.ProjectSessionCreationHelper;
import org.polarsys.capella.core.data.la.*;
import org.polarsys.capella.core.data.fa.FunctionalExchange;
import org.polarsys.capella.core.data.cs.Part;
import org.example.capella.mcp.*;

/** Test-only startup extension, excluded from the shipping plugin and feature.
 * Runs only with an explicit test root and a matching dedicated workspace.
 */
public final class RuntimeTrial implements IStartup {
    private Path root;
    private final JsonArray checks = new JsonArray();
    private Session session;
    private NativeGuard guard;
    private final NullProgressMonitor monitor = new NullProgressMonitor();
    @Override public void earlyStartup() {
        if (!"native".equals(System.getProperty("capella.mcp.test.mode", "native"))) return;
        String configured = System.getProperty("capella.mcp.disposable.test");
        if (configured == null) return;
        root = Path.of(configured).toAbsolutePath().normalize();
        Path workspace = ResourcesPlugin.getWorkspace().getRoot().getLocation().toFile().toPath().toAbsolutePath().normalize();
        if (!workspace.equals(root.resolve("workspace")) || !Files.isRegularFile(root.resolve("AUTHORIZED-SYNTHETIC-ONLY")))
            throw new IllegalStateException("Refusing non-disposable workspace");
        PlatformUI.getWorkbench().getDisplay().asyncExec(this::run);
    }
    private void record(String name, boolean success) {
        JsonObject entry = new JsonObject(); entry.addProperty("check", name); entry.addProperty("passed", success); checks.add(entry);
        if (!success) throw new AssertionError(name);
    }
    private void stage(String value) {
        try { Files.writeString(root.resolve("stage.txt"), value); } catch (Exception e) { throw new RuntimeException(e); }
    }
    private void run() {
        JsonObject report = new JsonObject();
        try {
            String capellaVersion = org.eclipse.core.runtime.Platform.getBundle("org.polarsys.capella.core.data.gen").getVersion().toString();
            report.addProperty("capella_version", capellaVersion);
            report.addProperty("mcp_bundle_version", org.eclipse.core.runtime.Platform.getBundle("org.example.capella.mcp").getVersion().toString());
            record("runtime matches requested Capella version", capellaVersion.startsWith(System.getProperty("capella.mcp.expected.version", "7.0.1") + "."));
            stage("Creating synthetic model with native Capella project services");
            record("workspace starts empty", ResourcesPlugin.getWorkspace().getRoot().getProjects().length == 0);
            session = new ProjectSessionCreationHelper(true, true).createFullProject(
                "McpSyntheticTrial", null, List.of(), ViewpointSelection.getViewpoints("capella"), monitor);
            record("new native session opens", session != null && session.isOpen());
            LogicalArchitecture architecture = null;
            for (var resource : session.getSemanticResources()) {
                var iterator = resource.getAllContents();
                while (iterator.hasNext()) if (iterator.next() instanceof LogicalArchitecture la) architecture = la;
            }
            record("native logical architecture exists", architecture != null);
            LogicalComponent system = (LogicalComponent) architecture.getSystem();
            LogicalFunction function = architecture.getContainedLogicalFunctionPkg().getOwnedLogicalFunctions().get(0);
            Map<String, EObject> bindings = new HashMap<>();
            bindings.put("logical-system", system); bindings.put("root-function", function);
            JsonObject payload = JsonParser.parseString(Files.readString(root.resolve("intent.json"))).getAsJsonObject();
            var commands = new ArrayList<NativeCommand>();
            for (var item : payload.getAsJsonArray("commands")) {
                var object = item.getAsJsonObject(); var values = new HashMap<String, String>();
                for (var entry : object.entrySet()) if (!entry.getKey().equals("recipe")) values.put(entry.getKey(), entry.getValue().getAsString());
                commands.add(new NativeCommand(object.get("recipe").getAsString(), values));
            }
            guard = new NativeGuard(session);
            SessionExecutor executor = new SessionExecutor(session, guard, new LabDiagramAdapter());
            stage("Applying native monitoring plan");
            var created = executor.apply(commands, bindings, Long.toString(guard.revision()));
            record("all thirteen aliases created", created.size() == 13);
            bindings.putAll(created);
            var sensor = (LogicalComponent) created.get("sensor");
            var controller = (LogicalComponent) created.get("controller");
            var measure = (LogicalFunction) created.get("measure");
            var watch = (LogicalFunction) created.get("monitor");
            var exchange = (FunctionalExchange) created.get("temperature");
            record("components contained by logical system", sensor.eContainer() == system && controller.eContainer() == system);
            record("functions contained by root function", measure.eContainer() == function && watch.eContainer() == function);
            record("both allocations point to functions", sensor.getOwnedFunctionalAllocation().stream().anyMatch(a -> a.getTargetElement() == measure) && controller.getOwnedFunctionalAllocation().stream().anyMatch(a -> a.getTargetElement() == watch));
            record("exchange connects owned native ports", measure.getOutputs().contains(exchange.getSource()) && watch.getInputs().contains(exchange.getTarget()));
            DDiagram diagram = (DDiagram) created.get("monitoring-lab");
            record("diagram contains exchange edge", diagram.getDiagramElements().stream().anyMatch(v -> v instanceof DEdge && v.getTarget() == exchange));
            record("diagram contains both component Parts", diagram.getDiagramElements().stream().filter(v -> v.getTarget() instanceof Part p && (p.getAbstractType() == sensor || p.getAbstractType() == controller)).count() == 2);
            stage("Opening the synthetic native diagram for export");
            DialectUIManager.INSTANCE.openEditor(session, diagram, monitor);
            DialectUIManager.INSTANCE.export(diagram, session, new org.eclipse.core.runtime.Path(root.resolve("monitoring.png").toString()),
                new ExportFormat(ExportFormat.ExportDocumentFormat.NONE, ImageFileFormat.PNG), monitor);
            record("native diagram exported", Files.size(root.resolve("monitoring.png")) > 1000);

            stage("Checking stale revisions and atomic rollback");
            long stale = guard.revision();
            session.getTransactionalEditingDomain().getCommandStack().execute(new RecordingCommand(session.getTransactionalEditingDomain()) {
                @Override protected void doExecute() { sensor.setName("Sensor manually edited"); }
            });
            record("unsaved manual edit increments revision", guard.revision() > stale);
            boolean staleDenied = false;
            try { guard.checkSessionRevision(Long.toString(stale)); } catch (IllegalStateException expected) { staleDenied = true; }
            record("stale revision rejected", staleDenied);
            int before = system.getOwnedLogicalComponents().size();
            var broken = List.of(
                new NativeCommand("logical_component_with_part", Map.of("id", "rollback-child", "parent", "logical-system", "name", "Must roll back")),
                new NativeCommand("logical_function", Map.of("id", "invalid-child", "parent", "logical-system", "name", "Invalid parent type")));
            boolean failed = false;
            try { executor.apply(broken, bindings, Long.toString(guard.revision())); } catch (Exception expected) { failed = true; }
            record("late native operation fails", failed);
            record("late failure rolls back created component", system.getOwnedLogicalComponents().size() == before);
            stage("Checking native JSON receipts and duplicate suppression");
            try (var controllerBoundary = new NativeController(session, system, function)) {
                JsonObject snapshot = controllerBoundary.snapshot();
                JsonObject nativePayload = payload.deepCopy();
                nativePayload.addProperty("session_epoch", snapshot.get("session_epoch").getAsString());
                nativePayload.addProperty("expected_revision", snapshot.get("revision").getAsLong());
                JsonArray jsonCommands = new JsonArray();
                JsonObject createCommand = new JsonObject();
                createCommand.addProperty("recipe", "logical_component_with_part");
                createCommand.addProperty("id", "json-sensor");
                createCommand.addProperty("parent", "logical-system");
                createCommand.addProperty("name", "JSON Boundary Sensor");
                jsonCommands.add(createCommand);
                nativePayload.add("commands", jsonCommands);
                JsonObject nativeJob = new JsonObject();
                nativeJob.addProperty("job_id", "native-json-test");
                nativeJob.addProperty("lease", "synthetic-lease");
                nativeJob.add("payload", nativePayload);
                int jsonBefore = system.getOwnedLogicalComponents().size();
                JsonObject receipt = controllerBoundary.execute(nativeJob);
                record("JSON boundary reports unsaved native success", "succeeded_unsaved".equals(receipt.get("status").getAsString()) && !receipt.getAsJsonObject("result").get("saved").getAsBoolean());
                record("JSON boundary creates exactly one component", system.getOwnedLogicalComponents().size() == jsonBefore + 1);
                record("identical native retry returns same receipt", receipt.equals(controllerBoundary.execute(nativeJob)));
                record("native retry does not duplicate component", system.getOwnedLogicalComponents().size() == jsonBefore + 1);
                JsonObject wrongEpoch = nativeJob.deepCopy();
                wrongEpoch.addProperty("job_id", "wrong-epoch");
                wrongEpoch.getAsJsonObject("payload").addProperty("session_epoch", "stale-epoch");
                record("wrong native epoch rejected", "rejected".equals(controllerBoundary.execute(wrongEpoch).get("status").getAsString()));
            }
            new ArchitectureTrial(session,checks).logical(system,function,diagram,measure,watch,sensor);
            new ArchitectureTrial(session,checks).scope(sensor,controller,function);
            List<org.polarsys.capella.core.data.cs.BlockArchitecture> layers = new ArrayList<>();
            for (var r:session.getSemanticResources()) {
                var it=r.getAllContents();
                while (it.hasNext()) if (it.next() instanceof org.polarsys.capella.core.data.cs.BlockArchitecture l && !(l instanceof LogicalArchitecture)) layers.add(l);
            }
            record("Four additional architecture roots in fixture", layers.size()==4);
            var errors=new ArrayList<String>();
            for (var l : layers) {
                stage("Testing "+l.eClass().getName());
                try { new ArchitectureTrial(session,checks).run(l); }
                catch (Throwable failure) {
                    failure.printStackTrace();
                    errors.add(l.eClass().getName()+" "+failure);
                }
            }
            if (!errors.isEmpty()) throw new AssertionError(errors);
            var breakdowns = new ArchitectureTrial(session, checks);
            stage("Testing five additional native breakdown diagram types");
            breakdowns.breakdown(architecture, "LFBD", "logical_function", function);
            breakdowns.breakdown(architecture, "LCBD", "logical_component_with_part", system);
            for (var layer : layers) {
                if (layer instanceof org.polarsys.capella.core.data.ctx.SystemAnalysis sa)
                    breakdowns.breakdown(sa, "SFBD", "create_system_function",
                        sa.getContainedSystemFunctionPkg().getOwnedSystemFunctions().get(0));
                if (layer instanceof org.polarsys.capella.core.data.pa.PhysicalArchitecture pa)
                    breakdowns.breakdown(pa, "PFBD", "create_physical_function",
                        pa.getContainedPhysicalFunctionPkg().getOwnedPhysicalFunctions().get(0));
                if (layer instanceof org.polarsys.capella.core.data.oa.OperationalAnalysis oa)
                    breakdowns.breakdown(oa, "OABD", "create_activity",
                        oa.getContainedOperationalActivityPkg().getOwnedOperationalActivities().get(0));
            }
            stage("Testing data flows and structural diagrams");
            breakdowns.flow(architecture, "LDFB", "logical_function", function);
            breakdowns.stateMachine(architecture);
            breakdowns.chain(architecture, function, "FCD");
            for (var layer : layers) {
                if (layer instanceof org.polarsys.capella.core.data.ctx.SystemAnalysis sa)
                    breakdowns.flow(sa, "SDFB", "create_system_function",
                        sa.getContainedSystemFunctionPkg().getOwnedSystemFunctions().get(0));
                if (layer instanceof org.polarsys.capella.core.data.pa.PhysicalArchitecture pa) {
                    breakdowns.flow(pa, "PDFB", "create_physical_function",
                        pa.getContainedPhysicalFunctionPkg().getOwnedPhysicalFunctions().get(0));
                    breakdowns.breakdown(pa, "PCBD", "create_node_component", pa.getSystem());
                }
                if (layer instanceof org.polarsys.capella.core.data.oa.OperationalAnalysis oa)
                    breakdowns.flow(oa, "OAIB", "create_activity",
                        oa.getContainedOperationalActivityPkg().getOwnedOperationalActivities().get(0));
                if (layer instanceof org.polarsys.capella.core.data.oa.OperationalAnalysis oa)
                    breakdowns.operationalEntityBlank(oa);
                if (layer instanceof org.polarsys.capella.core.data.oa.OperationalAnalysis oa)
                    breakdowns.chain(oa, oa.getContainedOperationalActivityPkg().getOwnedOperationalActivities().get(0), "OPD");
                if (layer instanceof org.polarsys.capella.core.data.oa.OperationalAnalysis oa)
                    breakdowns.synchronizedStateMachine(oa);
                if (layer instanceof org.polarsys.capella.core.data.epbs.EPBSArchitecture epbs)
                    breakdowns.epbsBlank(epbs);
            }
            var engineering = (org.polarsys.capella.core.data.capellamodeller.SystemEngineering) architecture.eContainer();
            stage("Testing cross-layer capability and function traces");
            breakdowns.trace(engineering);
            try (var inventory = new NativeController(session,engineering)) {
                Files.writeString(root.resolve("synthetic-inventory.json"),inventory.snapshot().toString());
            }
            stage("Saving only the synthetic fixture for later reopen checks");
            session.save(monitor);
            record("fixture saved by explicit test harness", Files.isRegularFile(root.resolve("workspace/McpSyntheticTrial/McpSyntheticTrial.capella")));
            stage("Reopening only the saved synthetic session");
            var savedUri = session.getSessionResource().getURI();
            guard.close(); guard = null;
            for (var window : PlatformUI.getWorkbench().getWorkbenchWindows())
                for (var page : window.getPages()) page.closeAllEditors(false);
            var display = PlatformUI.getWorkbench().getDisplay();
            for (int pending = 0; pending < 200 && display.readAndDispatch(); pending++) { }
            session.close(monitor);
            session = SessionManager.INSTANCE.getSession(savedUri, monitor);
            session.open(monitor);
            record("saved synthetic session reopens", session.isOpen());
            record("native LAB survives save and reopen", DialectManager.INSTANCE.getAllRepresentations(session).stream().anyMatch(representation -> representation instanceof DDiagram reopened && reopened.getName().equals("Synthetic Monitoring LAB") && reopened.getDiagramElements().stream().anyMatch(element -> element instanceof DEdge && element.getTarget() instanceof FunctionalExchange)));
            for (String code : List.of("LFBD", "LCBD", "SFBD", "PFBD", "OABD")) {
                record(code + " hierarchy survives save and reopen",
                    DialectManager.INSTANCE.getAllRepresentations(session).stream().anyMatch(rep ->
                        rep instanceof DDiagram reopened && rep.getName().equals("Synthetic " + code) &&
                            reopened.getEdges().size() >= 2));
            }
            report.addProperty("status", "passed");
        } catch (Throwable failure) {
            report.addProperty("status", "failed");
            StringWriter trace = new StringWriter(); failure.printStackTrace(new PrintWriter(trace));
            report.addProperty("error", trace.toString());
        } finally {
            report.add("checks", checks);
            try { Files.writeString(root.resolve("native-result.json"), new GsonBuilder().setPrettyPrinting().create().toJson(report)); }
            catch (Exception error) { error.printStackTrace(); }
            if (guard != null) guard.close();
            stage("Finished: " + report.get("status").getAsString());
            if (!Boolean.getBoolean("capella.mcp.test.hold")) {
                try {
                    for (var window : PlatformUI.getWorkbench().getWorkbenchWindows())
                        for (var page : window.getPages()) page.closeAllEditors(false);
                    if (session != null && session.isOpen()) session.close(monitor);
                } finally { PlatformUI.getWorkbench().getDisplay().asyncExec(() -> PlatformUI.getWorkbench().close()); }
            }
        }
    }
}
