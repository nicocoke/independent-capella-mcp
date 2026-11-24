package org.example.capella.mcp;
import java.nio.file.Path;
import org.eclipse.core.commands.*;
import org.eclipse.jface.dialogs.*;
import org.eclipse.jface.viewers.IStructuredSelection;
import org.eclipse.jface.window.Window;
import org.eclipse.swt.SWT;
import org.eclipse.swt.layout.*;
import org.eclipse.swt.widgets.*;
import org.eclipse.ui.handlers.HandlerUtil;
import org.eclipse.sirius.business.api.session.SessionManager;
import org.polarsys.capella.core.data.la.*;
import org.eclipse.emf.ecore.EObject;

/** Explicit manual activation only. */
public final class ToggleHandler extends AbstractHandler {
    private static OutboundConnector active;
    @Override public Object execute(ExecutionEvent event) throws ExecutionException {
        Shell shell = HandlerUtil.getActiveShell(event);
        if (active != null) {
            active.close(); active = null;
            MessageDialog.openInformation(shell, "Capella MCP", "Connector stopped. Pending edits are not undone.");
            return null;
        }
        var selection = HandlerUtil.getCurrentSelection(event);
        if (!(selection instanceof IStructuredSelection structured) || structured.size() != 1 ||
            !(structured.getFirstElement() instanceof EObject root)) {
            MessageDialog.openError(shell,"Capella MCP","Select one architecture or logical component in the semantic tree.");
            return null;
        }
        var layer = ModelInventory.architecture(root);
        boolean engineering = root instanceof org.polarsys.capella.core.data.capellamodeller.SystemEngineering;
        boolean logical = root instanceof LogicalComponent && layer instanceof LogicalArchitecture;
        if (!(engineering || logical || (root == layer && java.util.Set.of("LogicalArchitecture","SystemAnalysis","PhysicalArchitecture",
                "OperationalAnalysis","EPBSArchitecture").contains(root.eClass().getName())))) {
            MessageDialog.openError(shell,"Capella MCP","Select an architecture root or a logical component.");
            return null;
        }
        LogicalFunction function = null;
        if (logical) {
            var pkg = ((LogicalArchitecture) layer).getContainedLogicalFunctionPkg();
            if (pkg == null || pkg.getOwnedLogicalFunctions().size()!=1) {
                MessageDialog.openError(shell,"Capella MCP","One root logical function is required for component pairing.");
                return null;
            }
            function = pkg.getOwnedLogicalFunctions().get(0);
        }
        var session = SessionManager.INSTANCE.getSession(root);
        if (session == null || !session.isOpen()) throw new ExecutionException("Selection has no open session");
        ConnectionDialog dialog = new ConnectionDialog(shell, logical ? "selected component subtree and logical function tree"
            : engineering ? "entire selected System Engineering subtree across its architecture levels" : "entire selected " + layer.eClass().getName() + " subtree");
        if (dialog.open() != Window.OK) return null;
        NativeController controller = logical ? new NativeController(session,(LogicalComponent)root,function)
            : engineering ? new NativeController(session,(org.polarsys.capella.core.data.capellamodeller.SystemEngineering)root) : new NativeController(session,layer);
        try {
            active = OutboundConnector.local(controller, dialog.file, shell.getDisplay());
            active.start();
        } catch (Exception failure) {
            controller.close(); active = null;
            throw new ExecutionException("Connector could not be enabled", failure);
        }
        return null;
    }
    private static final class ConnectionDialog extends TitleAreaDialog {
        private Text address;
        Path file;
        private final String scope;
        ConnectionDialog(Shell shell,String scope) { super(shell); this.scope = scope; }
        @Override protected Control createDialogArea(Composite parent) {
            Composite area = (Composite) super.createDialogArea(parent);
            setTitle("Connect to Claude Desktop — Development");
            setMessage("Allows Claude to inspect and edit the " + scope + " while this connector is enabled. Start with a disposable model. Changes remain unsaved. Run this command again to stop.");
            Composite form = new Composite(area, SWT.NONE);
            form.setLayoutData(new GridData(SWT.FILL, SWT.FILL, true, true));
            form.setLayout(new GridLayout(3, false));
            new Label(form, SWT.NONE).setText("Local connection file");
            address = new Text(form, SWT.BORDER); address.setLayoutData(new GridData(SWT.FILL, SWT.CENTER, true, false));
            String localData = System.getenv("LOCALAPPDATA");
            if (localData != null) address.setText(Path.of(localData, "IndependentCapellaMCP", "connection.json").toString());
            Button browse = new Button(form, SWT.PUSH); browse.setText("Browse…");
            browse.addListener(SWT.Selection, event -> {
                FileDialog chooser = new FileDialog(getShell(), SWT.OPEN);
                chooser.setText("Choose the Capella MCP connection file");
                chooser.setFilterExtensions(new String[] { "*.json" });
                String selected = chooser.open();
                if (selected != null) address.setText(selected);
            });
            return area;
        }
        @Override protected void okPressed() {
            try {
                file = Path.of(address.getText().trim());
                LocalConnection.read(file);
            } catch (Exception failure) { setErrorMessage("Start the Capella extension in Claude Desktop, then choose its connection.json file. Ask Claude for capella_connection if needed."); return; }
            super.okPressed();
        }
    }
}
