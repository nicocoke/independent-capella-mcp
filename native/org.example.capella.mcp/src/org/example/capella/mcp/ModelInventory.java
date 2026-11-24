package org.example.capella.mcp;

import java.util.*;
import com.google.gson.*;
import org.eclipse.emf.ecore.*;
import org.eclipse.emf.ecore.util.EcoreUtil;
import org.eclipse.emf.ecore.util.InternalEList;
import org.eclipse.sirius.business.api.session.Session;
import org.eclipse.sirius.diagram.*;
import org.eclipse.sirius.viewpoint.*;
import org.polarsys.capella.core.data.capellacore.CapellaElement;
import org.polarsys.capella.core.data.capellacore.NamedElement;
import org.polarsys.capella.core.data.cs.BlockArchitecture;

/** An index of loaded contents under the roots chosen at activation. No URI lookup. */
final class ModelInventory {
    private final Session session;
    private final Map<String,EObject> roots;
    private final BlockArchitecture layer;
    private final org.eclipse.emf.ecore.resource.Resource pairedResource;
    final Map<String,EObject> bindings = new LinkedHashMap<>();
    private final Map<EObject,String> refs = new IdentityHashMap<>();
    private final Map<String,JsonObject> diagrams = new LinkedHashMap<>();
    private final Set<String> limits = new LinkedHashSet<>();
    private static final Set<String> PROPERTIES = Set.of("kind","nature","actor","human","itemIdentifier","summary");
    private static final Set<String> LINKS = Set.of("source","target","sourceElement","targetElement",
        "abstractType","linkEnds","port","part","deployedElement","location","involved");
    ModelInventory(Session session, Map<String,EObject> roots) {
        this.session = session;
        this.roots = new LinkedHashMap<>(roots);
        layer = architecture(roots.values().iterator().next());
        pairedResource = roots.values().iterator().next().eResource();
        if (layer == null && !(roots.values().iterator().next() instanceof org.polarsys.capella.core.data.capellamodeller.SystemEngineering)) throw new IllegalArgumentException("Select an architecture or its logical component");
    }
    static BlockArchitecture architecture(EObject item) {
        for (; item != null; item = item.eContainer()) if (item instanceof BlockArchitecture a) return a;
        return null;
    }
    private String layerName(EObject item) {
        var arch = architecture(item);
        return arch == null ? "SystemEngineering" : arch.eClass().getName();
    }
    private void index(String alias, EObject obj) {
        if (bindings.putIfAbsent(alias, obj) != null && bindings.get(alias) != obj)
            throw new IllegalStateException("Duplicate native ID in selected scope");
        refs.putIfAbsent(obj, alias);
    }
    private void indexElement(EObject item) {
        if (item instanceof CapellaElement e && !refs.containsKey(item)) {
            if (e.getId() != null && e.getId().matches("[a-zA-Z0-9_-]{1,56}")) index("native_" + e.getId(), e);
            else limits.add("Elements without supported native IDs omitted");
        }
    }
    // Read stored reference values without resolving proxies, derived inverses or external resources.
    static EObject raw(EObject owner, String name) {
        var f = owner.eClass().getEStructuralFeature(name);
        return f != null && owner.eGet(f,false) instanceof EObject e && !e.eIsProxy() ? e : null;
    }
    private String bounded(String value, int max) {
        if (value == null) return "";
        if (value.length() <= max) return value;
        limits.add("Text clipped");
        return value.substring(0,max);
    }
    private void discoverDiagrams() {
        int visited = 0;
        // Inspect only already loaded analysis roots in the selected session resource.
        for (var content : session.getSessionResource().getContents()) if (content instanceof DAnalysis a)
            for (var view : a.getOwnedViews()) for (var desc : view.getOwnedRepresentationDescriptors()) {
                if (++visited > 512) { limits.add("Descriptor scan limit"); return; }
                EObject target = raw(desc,"target");
                if (!refs.containsKey(target)) continue;
                String uid = desc.getUid();
                if (uid == null || !uid.matches("[a-zA-Z0-9_-]{1,55}")) { limits.add("Descriptor without usable ID"); continue; }
                String alias = "diagram_" + uid;
                JsonObject row = new JsonObject();
                row.addProperty("alias",alias);
                row.addProperty("architecture",layerName(target));
                row.addProperty("name",bounded(desc.getName(),160));
                row.addProperty("owner",refs.get(target));
                var definition = raw(desc,"description") instanceof org.eclipse.sirius.viewpoint.description.RepresentationDescription description ? description : null;
                row.addProperty("diagram_kind", definition == null ? "unknown" : bounded(definition.getName(),160));
                boolean loaded = desc.isLoadedRepresentation();
                var rep = loaded ? raw(desc,"representation") : null;
                row.addProperty("type",rep instanceof DDiagram ? rep.eClass().getName() : "DRepresentationDescriptor");
                row.addProperty("loaded",rep != null);
                if (rep instanceof DDiagram d) {
                    index(alias,d);
                    JsonArray members = new JsonArray();
                    Set<String> seen = new LinkedHashSet<>();
                    int count = 0;
                    var iter = EcoreUtil.getAllProperContents(d,false);
                    while (iter.hasNext()) {
                        if (++count > 2048 || seen.size() >= 96) { limits.add("Diagram member limit"); break; }
                        var item = iter.next();
                        if (item instanceof DDiagramElement v) {
                            EObject semantic = raw(v,"target");
                            if (semantic != null && semantic.eClass().getName().equals("Part"))
                                semantic = raw(semantic,"abstractType");
                            String ref = refs.get(semantic);
                            if (ref != null) seen.add(ref);
                            else limits.add("Unindexed diagram targets omitted");
                        }
                    }
                    seen.forEach(members::add);
                    row.add("represented",members);
                }
                if (diagrams.putIfAbsent(alias,row) != null) throw new IllegalStateException("Duplicate descriptor ID");
            }
    }
    private JsonObject describe(String alias, EObject e) {
        JsonObject row = new JsonObject();
        row.addProperty("alias",alias);
        row.addProperty("type",e.eClass().getName());
        row.addProperty("architecture",layerName(e));
        if (refs.containsKey(e.eContainer())) row.addProperty("owner",refs.get(e.eContainer()));
        if (e.eContainmentFeature() != null) row.addProperty("containment",e.eContainmentFeature().getName());
        if (e instanceof NamedElement n) row.addProperty("name",bounded(n.getName(),160));
        if (e instanceof CapellaElement c) {
            row.addProperty("native_id",bounded(c.getId(),80));
            if (c.getDescription()!=null && !c.getDescription().isEmpty()) row.addProperty("description",bounded(c.getDescription(),512));
        }
        JsonObject props = new JsonObject(), links = new JsonObject();
        for (var f : e.eClass().getEAllStructuralFeatures()) {
            if (f.isDerived() || f.isTransient() || !e.eIsSet(f)) continue;
            if (PROPERTIES.contains(f.getName()) && f instanceof EAttribute)
                props.addProperty(f.getName(),bounded(String.valueOf(e.eGet(f,false)),160));
            if (!(f instanceof EReference) || !LINKS.contains(f.getName())) continue;
            Object value = e.eGet(f,false);
            Iterator<?> it = value instanceof InternalEList<?> l ? l.basicIterator() : Collections.singleton(value).iterator();
            JsonArray ids = new JsonArray();
            int n = 0;
            while (it.hasNext() && n++ < 16) {
                var dest = it.next();
                String id = refs.get(dest);
                if (id != null) ids.add(id);
                else { ids.add(JsonNull.INSTANCE); limits.add("Reference outside indexed scope or unloaded"); }
            }
            if (it.hasNext()) limits.add("Reference list clipped");
            links.add(f.getName(),ids);
        }
        if (props.size()>0) row.add("properties",props);
        if (links.size()>0) row.add("links",links);
        return row;
    }
    JsonObject resultReferences(Map<String,EObject> changes) {
        read();
        JsonObject result = new JsonObject();
        changes.forEach((alias,obj) -> {
            String ref = refs.get(obj);
            if (ref != null && bindings.containsKey(ref)) result.addProperty(alias,ref);
        });
        return result;
    }
    JsonObject read() {
        bindings.clear(); refs.clear(); diagrams.clear(); limits.clear();
        for (var entry : roots.entrySet()) {
            var root = entry.getValue();
            if (architecture(root) != layer || root.eResource()!=pairedResource || pairedResource==null || !session.getSemanticResources().contains(root.eResource()))
                throw new IllegalStateException("Selected root detached or outside paired architecture");
            index(entry.getKey(),root);
        }
        for (var root : roots.values()) {
            var it = EcoreUtil.<EObject>getAllProperContents(root,false);
            int n=0;
            while (it.hasNext() && n++ < 1500) {
                EObject next = it.next();
                if (next.eIsProxy()) { it.prune(); limits.add("Unloaded subtree"); }
                else indexElement(next);
            }
            if (it.hasNext()) limits.add("1500 descendants per paired root");
        }
        discoverDiagrams();
        JsonArray rows = new JsonArray();
        // Bound the publication even for heavily escaped Unicode. Reserve room for metadata.
        int budget = 216000;
        var included = new HashSet<String>();
        var records = new LinkedHashMap<String,JsonObject>();
        roots.forEach((alias,obj) -> records.put(alias,describe(alias,obj)));
        records.putAll(diagrams);
        for (var entry : bindings.entrySet()) if (!records.containsKey(entry.getKey()))
            records.put(entry.getKey(),describe(entry.getKey(),entry.getValue()));
        for (var entry : records.entrySet()) {
            String json = entry.getValue().toString();
            int cost = json.length()+1;
            for (int i=0;i<json.length();i++) if (json.charAt(i)>127) cost+=5;
            if (cost > budget) { limits.add("Publication byte limit"); continue; }
            budget -= cost;
            included.add(entry.getKey());
            rows.add(entry.getValue());
        }
        bindings.keySet().retainAll(included);
        JsonObject result = new JsonObject();
        result.add("elements",rows);
        JsonArray warnings = new JsonArray();
        limits.forEach(warnings::add);
        result.add("limits",warnings);
        return result;
    }
}
