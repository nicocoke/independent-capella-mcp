package org.example.capella.mcp;

import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.sirius.business.api.dialect.DialectManager;
import org.eclipse.sirius.business.api.session.Session;
import org.eclipse.sirius.viewpoint.DRepresentation;
import org.eclipse.sirius.viewpoint.description.RepresentationDescription;

/** Explicit native representation creation; no view insertion or editor opening.
 * The caller must select a compatible enabled LAB description in the disposable
 * test session. Never guess a description ID or silently activate a viewpoint.
 * Execute only inside SessionExecutor's transaction. Target-platform unverified.
 */
public final class RepresentationRecipes {
    private RepresentationRecipes() {}

    public static DRepresentation create(Session session, EObject target, String name,
                                         RepresentationDescription description) {
        if (target == null || target.eResource() == null ||
            !session.getSemanticResources().contains(target.eResource()))
            throw new IllegalArgumentException("Target outside explicitly bound session");
        if (description == null || name == null || name.isBlank() || name.length() > 160)
            throw new IllegalArgumentException("Explicit description and name required");
        return DialectManager.INSTANCE.createRepresentation(name, target, description,
                                                            session, new NullProgressMonitor());
    }
}
