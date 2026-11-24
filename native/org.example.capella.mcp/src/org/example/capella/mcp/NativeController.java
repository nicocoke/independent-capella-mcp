package org.example.capella.mcp;

import java.util.*;
import com.google.gson.*;
import org.eclipse.emf.ecore.EObject;
import org.polarsys.capella.core.data.la.*;
import org.eclipse.sirius.business.api.session.Session;

/** JSON boundary and session incarnation. Methods called only on the UI thread. */
public final class NativeController implements AutoCloseable {
    private final String epoch = UUID.randomUUID().toString();
    private final NativeGuard guard;
    private final SessionExecutor executor;
    private final ModelInventory inventory;
    private final Map<String, JsonObject> receipts = new HashMap<>();
    private final Map<String, String> requests = new HashMap<>();
    private boolean closed;
    public NativeController(Session session, LogicalComponent selectedRoot, LogicalFunction rootFunction) {
        this(session, Map.of("logical-system", selectedRoot, "root-function", rootFunction));
    }
    public NativeController(Session session, org.polarsys.capella.core.data.cs.BlockArchitecture layer) {
        this(session, Map.of("architecture", layer));
    }
    public NativeController(Session session, org.polarsys.capella.core.data.capellamodeller.SystemEngineering model) {
        this(session, Map.of("engineering", model));
    }
    private NativeController(Session session, Map<String,EObject> roots) {
        inventory = new ModelInventory(session, roots);
        guard = new NativeGuard(session);
        executor = new SessionExecutor(session, guard, new LabDiagramAdapter());
    }
    public JsonObject snapshot() {
        if (closed) throw new IllegalStateException("Connector stopped");
        guard.checkSessionRevision(Long.toString(guard.revision()));
        JsonObject result = inventory.read();
        result.addProperty("model_id","native-model");
        result.addProperty("session_epoch",epoch);
        result.addProperty("revision",guard.revision());
        return result;
    }
    public JsonObject execute(JsonObject job) {
        if (closed) throw new IllegalStateException("Connector stopped");
        String jobId = job.get("job_id").getAsString();
        JsonObject payload = job.getAsJsonObject("payload");
        String fingerprint = payload.toString();
        if (receipts.containsKey(jobId)) {
            if (!fingerprint.equals(requests.get(jobId))) throw new IllegalArgumentException("Job identity collision");
            return receipts.get(jobId).deepCopy();
        }
        JsonObject receipt = new JsonObject();
        receipt.addProperty("job_id", jobId);
        receipt.addProperty("lease", job.get("lease").getAsString());
        JsonObject result = new JsonObject();
        boolean enteredTransaction = false;
        try {
            Set<String> expected = Set.of("contract", "model_id", "expected_revision", "plan_digest", "commands", "save", "requires", "session_epoch");
            if (!payload.keySet().equals(expected) || !"capella-native-intent/1".equals(payload.get("contract").getAsString()) ||
                !"native-model".equals(payload.get("model_id").getAsString()) ||
                !epoch.equals(payload.get("session_epoch").getAsString()) || payload.get("save").getAsBoolean())
                throw new IllegalArgumentException("Wrong native contract, model, epoch or save request");
            var array = payload.getAsJsonArray("commands");
            if (array.size() < 1 || array.size() > 200) throw new IllegalArgumentException("Command limit");
            var commands = new ArrayList<NativeCommand>();
            for (var item : array) {
                JsonObject command = item.getAsJsonObject();
                var arguments = new HashMap<String, String>();
                for (var entry : command.entrySet()) if (!entry.getKey().equals("recipe")) {
                    if (!entry.getValue().isJsonPrimitive() || !entry.getValue().getAsJsonPrimitive().isString())
                        throw new IllegalArgumentException("Recipe arguments must be strings");
                    arguments.put(entry.getKey(), entry.getValue().getAsString());
                }
                commands.add(new NativeCommand(command.get("recipe").getAsString(), arguments));
            }
            guard.checkSessionRevision(payload.get("expected_revision").getAsString());
            inventory.read(); // Rebuild authority from live containment before every edit.
            enteredTransaction = true;
            var changed = executor.apply(commands, inventory.bindings, payload.get("expected_revision").getAsString());

            // A connector job must finish without opening a workbench editor or waiting on a dialog.
            result.add("references",inventory.resultReferences(changed));
            result.addProperty("created_aliases", changed.size());
            result.addProperty("revision", guard.revision());
            result.addProperty("saved", false);
            receipt.addProperty("status", "succeeded_unsaved");
        } catch (Exception failure) {
            receipt.addProperty("status", enteredTransaction ? "unknown_outcome" : "rejected");
            result.addProperty("error", failure.getClass().getSimpleName());
            result.addProperty("detail", "Inspect the isolated model before any retry");
        }
        receipt.add("result", result);
        requests.put(jobId, fingerprint);
        receipts.put(jobId, receipt.deepCopy());
        return receipt;
    }
    @Override public void close() { closed = true; guard.close(); }
}
