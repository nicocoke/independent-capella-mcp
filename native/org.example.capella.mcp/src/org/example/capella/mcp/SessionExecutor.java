package org.example.capella.mcp;

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.transaction.RecordingCommand;
import org.eclipse.emf.transaction.TransactionalCommandStack;
import org.eclipse.sirius.business.api.session.Session;

/** Transaction boundary for a session supplied by the manually enabled connector.
 * No session discovery, save, workspace loading or network access in this class.
 */
public final class SessionExecutor {
    public interface Guard {
        // Check selected session, permission, UI thread, lock and revision INSIDE transaction.
        void check(Session session, String expectedRevision);
        // Throws on native validation errors before the transaction commits.
        void validate(Session session, Map<String, EObject> changed);
    }

    private final Session session;
    private final Guard guard;
    private final DiagramAdapter diagrams;

    public SessionExecutor(Session session, Guard guard, DiagramAdapter diagrams) {
        this.session = java.util.Objects.requireNonNull(session);
        this.guard = java.util.Objects.requireNonNull(guard);
        this.diagrams = java.util.Objects.requireNonNull(diagrams);
    }

    public Map<String, EObject> apply(List<NativeCommand> input, Map<String, EObject> suppliedBindings,
                                     String expectedRevision) throws Exception {
        List<NativeCommand> commands = List.copyOf(input);
        if (commands.isEmpty() || commands.size() > 200) throw new IllegalArgumentException("Invalid plan size");
        Map<String, EObject> bindings = new HashMap<>(suppliedBindings);
        var ids = new HashSet<>(bindings.keySet());
        for (NativeCommand command : commands)
            if (!ids.add(command.get("id"))) throw new IllegalArgumentException("Duplicate alias");
        var domain = session.getTransactionalEditingDomain();
        for (EObject value : bindings.values()) {
            if (value == null || value.eResource() == null ||
                value.eResource().getResourceSet() != domain.getResourceSet())
                throw new IllegalArgumentException("Binding outside selected semantic resources");
        }
        diagrams.preflight(session, commands);
        var changes = new HashMap<String, EObject>();
        RecordingCommand transaction = new RecordingCommand(domain, "MCP development plan") {
            @Override protected void doExecute() {
                guard.check(session, expectedRevision);
                for (NativeCommand command : commands) {
                    EObject result = command.recipe().startsWith("sirius_")
                        ? diagrams.execute(session, command, bindings)
                        : SemanticRecipes.execute(command, bindings);
                    if (result == null) throw new IllegalStateException("Recipe produced no result");
                    bindings.put(command.get("id"), result);
                    changes.put(command.get("id"), result);
                }
                guard.validate(session, Map.copyOf(changes));
            }
        };
        if (!(domain.getCommandStack() instanceof TransactionalCommandStack stack))
            throw new IllegalStateException("Transactional stack required");
        // Overload propagates rollback failures; never disable transaction validation.
        stack.execute(transaction, Map.of());
        return Map.copyOf(changes);
    }
}
