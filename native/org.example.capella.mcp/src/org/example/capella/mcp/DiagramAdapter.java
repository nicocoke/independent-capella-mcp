package org.example.capella.mcp;

import java.util.List;
import java.util.Map;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.sirius.business.api.session.Session;

/** Version-specific palette mapping remains to be implemented and verified.
 * Preflight MUST reject unsupported tools before any semantic edit starts.
 */
public interface DiagramAdapter {
    void preflight(Session session, List<NativeCommand> commands);
    EObject execute(Session session, NativeCommand command, Map<String, EObject> bindings);

    static DiagramAdapter unavailable() {
        return new DiagramAdapter() {
            public void preflight(Session session, List<NativeCommand> commands) {
                if (commands.stream().anyMatch(c -> c.recipe().startsWith("sirius_")))
                    throw new UnsupportedOperationException("Native diagram mappings have not been verified");
            }
            public EObject execute(Session session, NativeCommand command, Map<String, EObject> bindings) {
                throw new UnsupportedOperationException("No diagram adapter installed");
            }
        };
    }
}
