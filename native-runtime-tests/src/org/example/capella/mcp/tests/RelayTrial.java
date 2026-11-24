package org.example.capella.mcp.tests;

import java.nio.file.Files;
import java.nio.file.Path;
import java.net.URI;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.List;
import com.google.gson.*;
import org.eclipse.core.resources.ResourcesPlugin;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.sirius.business.api.session.Session;
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
import org.example.capella.mcp.*;

public final class RelayTrial implements IStartup {
    private Path root;
    private Session session;
    private LogicalComponent system;
    private OutboundConnector connector;
    private final JsonArray checks = new JsonArray();
    private final NullProgressMonitor monitor = new NullProgressMonitor();
    private long deadline;

    @Override public void earlyStartup() {
        if (!List.of("relay", "local").contains(System.getProperty("capella.mcp.test.mode", ""))) return;
        String configured = System.getProperty("capella.mcp.disposable.test");
        if (configured == null) return;
        root = Path.of(configured).toAbsolutePath().normalize();
        Path workspace = ResourcesPlugin.getWorkspace().getRoot().getLocation().toFile().toPath().toAbsolutePath().normalize();
        if (!workspace.equals(root.resolve("workspace")) || !Files.isRegularFile(root.resolve("AUTHORIZED-SYNTHETIC-ONLY")))
            throw new IllegalStateException("Refusing non-disposable relay workspace");
        PlatformUI.getWorkbench().getDisplay().asyncExec(this::start);
    }

    private void check(String name, boolean passed) {
        JsonObject entry = new JsonObject(); entry.addProperty("check", name); entry.addProperty("passed", passed); checks.add(entry);
        if (!passed) throw new AssertionError(name);
    }

    private void stage(String name) throws Exception { Files.writeString(root.resolve("stage.txt"), name); }

    private void start() {
        try {
            String capellaVersion = org.eclipse.core.runtime.Platform.getBundle("org.polarsys.capella.core.data.gen").getVersion().toString();
            check("relay runtime matches requested Capella version", capellaVersion.startsWith(System.getProperty("capella.mcp.expected.version", "7.0.1") + "."));
            var commandService = PlatformUI.getWorkbench().getService(org.eclipse.ui.commands.ICommandService.class);
            check("installed MCP command registered in workbench", commandService.getCommand("org.example.capella.mcp.toggle").isDefined());
            check("relay workspace starts empty", ResourcesPlugin.getWorkspace().getRoot().getProjects().length == 0);
            stage("Creating synthetic session for real connector");
            session = new ProjectSessionCreationHelper(false, false).createFullProject(
                "McpSyntheticTrial", null, List.of(), ViewpointSelection.getViewpoints("capella"), monitor);
            LogicalArchitecture architecture = null;
            for (var resource : session.getSemanticResources()) {
                var contents = resource.getAllContents();
                while (contents.hasNext()) if (contents.next() instanceof LogicalArchitecture logical) architecture = logical;
            }
            check("relay session has native logical architecture", architecture != null);
            system = (LogicalComponent) architecture.getSystem();
            LogicalFunction rootFunction = architecture.getContainedLogicalFunctionPkg().getOwnedLogicalFunctions().get(0);
            NativeController controller = new NativeController(session, system, rootFunction);
            if ("local".equals(System.getProperty("capella.mcp.test.mode"))) {
                Path profile = root.resolve("local-state/connection.json");
                LocalConnection connection = LocalConnection.read(profile);
                check("test local connector is literal IPv4 loopback only", "http".equals(connection.origin().getScheme()) && "127.0.0.1".equals(connection.origin().getHost()));
                connector = OutboundConnector.local(controller, profile, PlatformUI.getWorkbench().getDisplay());
            } else {
                JsonObject connection = JsonParser.parseString(Files.readString(root.resolve("relay.json"))).getAsJsonObject();
                URI origin = URI.create(connection.get("origin").getAsString());
                check("test relay is loopback HTTPS only", "https".equals(origin.getScheme()) && "127.0.0.1".equals(origin.getHost()));
                connector = new OutboundConnector(controller, origin,
                    connection.get("connector_token").getAsString(), PlatformUI.getWorkbench().getDisplay());
            }
            connector.start();
            deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(150);
            stage("Awaiting real MCP request and native connector receipt");
            PlatformUI.getWorkbench().getDisplay().timerExec(500, this::poll);
        } catch (Throwable failure) { finish(failure); }
    }

    private void poll() {
        try {
            Path clientResult = root.resolve("relay-client-result.json");
            if (!Files.exists(clientResult)) {
                if (System.nanoTime() > deadline) throw new IllegalStateException("Client/connector timeout: " + connector.status());
                PlatformUI.getWorkbench().getDisplay().timerExec(500, this::poll);
                return;
            }
            JsonObject result = JsonParser.parseString(Files.readString(clientResult)).getAsJsonObject();
            check("external MCP client completed actual connector flow", "passed".equals(result.get("status").getAsString()));
            check("network retry leaves exactly two native components", system.getOwnedLogicalComponents().size() == 2);
            DDiagram diagram = null;
            for (var representation : DialectManager.INSTANCE.getAllRepresentations(session))
                if (representation instanceof DDiagram candidate && "Synthetic Monitoring LAB".equals(candidate.getName())) diagram = candidate;
            check("network job creates native LAB", diagram != null);
            check("network job creates connected functional exchange view", diagram.getDiagramElements().stream().anyMatch(view -> view instanceof DEdge && view.getTarget() instanceof FunctionalExchange));
            stage("Exporting diagram produced by real MCP job");
            DialectUIManager.INSTANCE.export(diagram, session, new org.eclipse.core.runtime.Path(root.resolve("monitoring.png").toString()),
                new ExportFormat(ExportFormat.ExportDocumentFormat.NONE, ImageFileFormat.PNG), monitor);
            check("MCP-created native diagram exports", Files.size(root.resolve("monitoring.png")) > 1000);
            connector.close(); connector = null;
            session.save(monitor);
            check("only synthetic network fixture saved", Files.isRegularFile(root.resolve("workspace/McpSyntheticTrial/McpSyntheticTrial.capella")));
            finish(null);
        } catch (Throwable failure) { finish(failure); }
    }

    private void finish(Throwable failure) {
        JsonObject report = new JsonObject();
        report.addProperty("transport", System.getProperty("capella.mcp.test.mode"));
        report.addProperty("capella_version", org.eclipse.core.runtime.Platform.getBundle("org.polarsys.capella.core.data.gen").getVersion().toString());
        report.addProperty("mcp_bundle_version", org.eclipse.core.runtime.Platform.getBundle("org.example.capella.mcp").getVersion().toString());
        report.addProperty("status", failure == null ? "passed" : "failed");
        report.add("checks", checks);
        if (failure != null) {
            StringWriter trace = new StringWriter(); failure.printStackTrace(new PrintWriter(trace));
            report.addProperty("error", trace.toString());
            if (connector != null) report.addProperty("connector_status", connector.status());
        }
        try {
            if (connector != null) connector.close();
            Files.writeString(root.resolve("native-result.json"), new GsonBuilder().setPrettyPrinting().create().toJson(report));
            stage("Finished: " + report.get("status").getAsString());
            for (var window : PlatformUI.getWorkbench().getWorkbenchWindows())
                for (var page : window.getPages()) page.closeAllEditors(false);
            if (session != null && session.isOpen()) session.close(monitor);
        } catch (Exception cleanupFailure) { cleanupFailure.printStackTrace(); }
        finally { PlatformUI.getWorkbench().getDisplay().asyncExec(() -> PlatformUI.getWorkbench().close()); }
    }
}
