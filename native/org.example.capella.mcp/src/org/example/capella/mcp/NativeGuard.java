package org.example.capella.mcp;

import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.emf.common.util.Diagnostic;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.util.Diagnostician;
import org.eclipse.emf.transaction.ResourceSetChangeEvent;
import org.eclipse.emf.transaction.ResourceSetListenerImpl;
import org.eclipse.emf.validation.model.EvaluationMode;
import org.eclipse.emf.validation.service.IBatchValidator;
import org.eclipse.emf.validation.service.ModelValidationService;
import org.eclipse.sirius.business.api.session.Session;
import org.eclipse.swt.widgets.Display;

/** Revision follows committed EMF transactions, including unsaved manual edits. */
public final class NativeGuard extends ResourceSetListenerImpl implements SessionExecutor.Guard, AutoCloseable {
    private final Session selected;
    private final AtomicLong revision = new AtomicLong();
    private volatile boolean armed;
    public NativeGuard(Session selected) {
        this.selected = selected;
        selected.getTransactionalEditingDomain().addResourceSetListener(this);
        armed = true;
    }
    @Override public boolean isPostcommitOnly() { return true; }
    @Override public void resourceSetChanged(ResourceSetChangeEvent event) {
        if (event.getNotifications().stream().anyMatch(n -> !n.isTouch())) revision.incrementAndGet();
    }
    public long revision() { return revision.get(); }
    public void checkSessionRevision(String expected) { check(selected, expected); }
    @Override public void check(Session session, String expected) {
        if (!armed || session != selected || !session.isOpen()) throw new IllegalStateException("Session not enabled");
        if (Display.getCurrent() == null) throw new IllegalStateException("UI thread required");
        if (!Long.toString(revision()).equals(expected)) throw new IllegalStateException("Native revision conflict");
        for (var resource : session.getSemanticResources())
            if ("cdo".equals(resource.getURI().scheme())) throw new IllegalStateException("Collaborative sessions outside initial scope");
    }
    @Override public void validate(Session session, Map<String, EObject> changed) {
        for (EObject object : changed.values())
            if (Diagnostician.INSTANCE.validate(object).getSeverity() >= Diagnostic.ERROR)
                throw new IllegalStateException("EMF validation rejected created element");
        IBatchValidator validator = (IBatchValidator) ModelValidationService.getInstance().newValidator(EvaluationMode.BATCH);
        var status = validator.validate(changed.values(), new NullProgressMonitor());
        if (status.matches(org.eclipse.core.runtime.IStatus.ERROR | org.eclipse.core.runtime.IStatus.CANCEL))
            throw new IllegalStateException("Native batch validation rejected plan");
    }
    @Override public void close() {
        armed = false;
        selected.getTransactionalEditingDomain().removeResourceSetListener(this);
    }
}
