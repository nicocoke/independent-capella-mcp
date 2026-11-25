package org.example.capella.mcp.tests;

import java.util.*;
import com.google.gson.*;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.transaction.RecordingCommand;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.sirius.ui.business.api.dialect.DialectUIManager;
import org.eclipse.ui.PlatformUI;
import org.eclipse.gmf.runtime.notation.Bounds;
import org.eclipse.gmf.runtime.notation.Node;
import org.eclipse.sirius.business.api.dialect.DialectManager;
import org.eclipse.sirius.business.api.session.Session;
import org.eclipse.sirius.diagram.DDiagram;
import org.eclipse.sirius.diagram.DNode;
import org.example.capella.mcp.*;
import org.polarsys.capella.core.data.cs.*;
import org.polarsys.capella.core.data.fa.*;
import org.polarsys.capella.core.data.ctx.*;
import org.polarsys.capella.core.data.oa.*;
import org.polarsys.capella.core.data.pa.*;
import org.polarsys.capella.core.data.epbs.*;
import org.polarsys.capella.core.data.capellacore.CapellaElement;

/** Exercises the same controller boundary, rebinding through fresh snapshots between requests. */
final class ArchitectureTrial {
    final Session session;
    final JsonArray checks;
    NativeController controller;
    ArchitectureTrial(Session session, JsonArray checks) { this.session=session; this.checks=checks; }
    void check(String label,boolean ok) {
        JsonObject r=new JsonObject(); r.addProperty("check",label); r.addProperty("passed",ok); checks.add(r);
        if (!ok) throw new AssertionError(label);
    }
    JsonArray rows() { return controller.snapshot().getAsJsonArray("elements"); }
    JsonObject row(String alias) {
        for (var e:rows()) if (e.getAsJsonObject().get("alias").getAsString().equals(alias)) return e.getAsJsonObject();
        throw new AssertionError("Missing native reference "+alias);
    }
    String ref(EObject obj) {
        String id=((CapellaElement)obj).getId();
        for (var e:rows()) { var r=e.getAsJsonObject(); if (r.has("native_id") && id.equals(r.get("native_id").getAsString())) return r.get("alias").getAsString(); }
        throw new AssertionError("Missing fixture ID");
    }
    JsonObject cmd(String recipe,String id,String... fields) {
        var c=new JsonObject(); c.addProperty("recipe",recipe); c.addProperty("id",id);
        for (int i=0;i<fields.length;i+=2) c.addProperty(fields[i],fields[i+1]);
        return c;
    }
    JsonObject apply(JsonObject... commands) {
        var receipt = receipt(commands);
        var result = receipt.getAsJsonObject("result");
        check(commands[0].get("recipe").getAsString()+" committed unsaved ("+receipt.get("status")+")",
            "succeeded_unsaved".equals(receipt.get("status").getAsString()) && !result.get("saved").getAsBoolean());
        return result.getAsJsonObject("references");
    }
    private JsonObject receipt(JsonObject... commands) {
        var snapshot=controller.snapshot();
        var p=new JsonObject(); p.addProperty("contract","capella-native-intent/1"); p.addProperty("model_id","native-model");
        p.add("expected_revision",snapshot.get("revision")); p.add("session_epoch",snapshot.get("session_epoch"));
        p.addProperty("plan_digest","synthetic"); p.addProperty("save",false); p.add("requires",new JsonArray());
        var array=new JsonArray(); for (var c:commands) array.add(c); p.add("commands",array);
        var job=new JsonObject(); job.addProperty("job_id",UUID.randomUUID().toString()); job.addProperty("lease","synthetic");
        job.add("payload",p);
        return controller.execute(job);
    }
    JsonObject child(String recipe,String id,String parent) {
        return cmd(recipe,id,"name","Duplicate fixture label","parent",parent);
    }
    String diagram(String kind,String target,String element) {
        int editors = openEditorCount();
        var out=apply(cmd("sirius_representation","diagram","kind",kind,"target",target,"name","Synthetic "+kind));
        check(kind+" connector creation leaves workbench editors unchanged", openEditorCount() == editors);
        String id=out.get("diagram").getAsString();
        var before=row(id);
        check(kind+" discoverable by descriptor ID",before.get("loaded").getAsBoolean());
        apply(cmd("sirius_existing_element_view","member","diagram",id,"element",element));
        check(kind+" represented element in existing diagram",row(id).getAsJsonArray("represented").contains(new JsonPrimitive(element)));
        return id;
    }

    private int openEditorCount() {
        int count = 0;
        for (var window : PlatformUI.getWorkbench().getWorkbenchWindows())
            for (var page : window.getPages()) count += page.getEditorReferences().length;
        return count;
    }
    void show(String diagram,String... elements) {
        for (String id:elements) apply(cmd("sirius_existing_element_view","show","diagram",diagram,"element",id));
    }

    void breakdown(BlockArchitecture layer, String kind, String recipe, EObject root) {
        try (var c = new NativeController(session, layer)) {
            controller = c;
            String rootRef = ref(root);
            var initial = apply(child(recipe, "branch", rootRef), child(recipe, "outside", rootRef),
                child(recipe, "existing", "branch"));
            String branch = initial.get("branch").getAsString();
            String outside = initial.get("outside").getAsString();
            String existing = initial.get("existing").getAsString();
            String diagramRef = diagram(kind, branch, existing);
            var nativeDiagram = DialectManager.INSTANCE.getAllLoadedRepresentations(session).stream()
                .filter(rep -> rep.getName().equals("Synthetic " + kind)).map(DDiagram.class::cast)
                .findFirst().orElseThrow();
            DialectUIManager.INSTANCE.openEditor(session, nativeDiagram, new NullProgressMonitor());
            var oldViews = Set.copyOf(nativeDiagram.getDiagramElements());
            var positions = new IdentityHashMap<Bounds, List<Integer>>();
            for (var resource : session.getTransactionalEditingDomain().getResourceSet().getResources()) {
                var contents = resource.getAllContents();
                while (contents.hasNext()) {
                    if (contents.next() instanceof Bounds b && b.eContainer() instanceof Node n &&
                        n.getElement() != null && oldViews.contains(n.getElement())) positions.put(b, bounds(b));
                }
            }
            check(kind + " layout captured", !positions.isEmpty());
            var newChild = apply(child(recipe, "extra", existing),
                cmd("sirius_existing_element_view", "show", "diagram", diagramRef, "element", "extra"));
            String ref = newChild.get("extra").getAsString();
            String uid = row(ref).get("native_id").getAsString();
            String parentUid = row(existing).get("native_id").getAsString();
            check(kind + " publishes newly displayed child", row(diagramRef).getAsJsonArray("represented").contains(new JsonPrimitive(ref)));
            check(kind + " uses a native containment edge from child to parent",
                nativeDiagram.getEdges().stream().anyMatch(e ->
                    e.getSourceNode() instanceof DNode from && e.getTargetNode() instanceof DNode to &&
                    from.getTarget() instanceof CapellaElement source && uid.equals(source.getId()) &&
                    to.getTarget() instanceof CapellaElement target && parentUid.equals(target.getId())));
            int count = nativeDiagram.getDiagramElements().size();
            show(diagramRef, ref);
            check(kind + " repeated show preserves views and layout", count == nativeDiagram.getDiagramElements().size() &&
                nativeDiagram.getDiagramElements().containsAll(oldViews) &&
                positions.entrySet().stream().allMatch(e -> e.getKey().eResource() != null && e.getValue().equals(bounds(e.getKey()))));
            var invalid = cmd("sirius_existing_element_view", "denied", "diagram", diagramRef, "element", outside);
            check(kind + " rejects same-layer object outside the diagram root",
                !receipt(invalid).get("status").getAsString().equals("succeeded_unsaved") &&
                count == nativeDiagram.getDiagramElements().size());
        }
    }

    private List<Integer> bounds(Bounds b) {
        return List.of(b.getX(), b.getY(), b.getWidth(), b.getHeight());
    }

    void flow(BlockArchitecture layer, String kind, String recipe, AbstractFunction root) {
        try (var c = new NativeController(session, layer)) {
            controller = c;
            String rootRef = ref(root);
            var first = apply(child(recipe, "from", rootRef)).get("from").getAsString();
            String diagram = diagram(kind, rootRef, first);
            var nativeDiagram = DialectManager.INSTANCE.getAllLoadedRepresentations(session).stream()
                .filter(rep -> rep.getName().equals("Synthetic " + kind)).map(DDiagram.class::cast)
                .findFirst().orElseThrow();
            var originalViews = Set.copyOf(nativeDiagram.getDiagramElements());
            String exchangeRecipe = kind.equals("OAIB") ? "create_interaction" : "functional_exchange_with_ports";
            var added = apply(child(recipe, "to", rootRef),
                cmd(exchangeRecipe, "connection", "source", first, "target", "to", "name", "Flow fixture"),
                cmd("sirius_existing_element_view", "destination", "diagram", diagram, "element", "to"),
                cmd("sirius_existing_element_view", "edge", "diagram", diagram, "element", "connection"));
            String connection = added.get("connection").getAsString();
            String uid = row(connection).get("native_id").getAsString();
            check(kind + " native edge persisted in existing diagram",
                nativeDiagram.getEdges().stream().anyMatch(e ->
                    e.getTarget() instanceof FunctionalExchange f && uid.equals(f.getId()) &&
                    e.getSourceNode() != null && e.getTargetNode() != null));
            int count = nativeDiagram.getDiagramElements().size();
            show(diagram, connection);
            check(kind + " preserves existing views and avoids duplicate edge",
                nativeDiagram.getDiagramElements().size() == count && nativeDiagram.getDiagramElements().containsAll(originalViews));
        }
    }

    void epbsBlank(EPBSArchitecture layer) {
        try (var c = new NativeController(session, layer)) {
            controller = c;
            String pkg = ref(layer.getOwnedConfigurationItemPkg());
            String item = apply(cmd("create_configuration_item", "ci", "parent", pkg,
                "kind", "HWCI", "name", "Blank diagram fixture")).get("ci").getAsString();
            diagram("EAB", pkg, item);
        }
    }

    void operationalEntityBlank(OperationalAnalysis layer) {
        try (var c = new NativeController(session, layer)) {
            controller = c;
            String pkg = ref(layer.getOwnedEntityPkg());
            String root = ref(layer.getContainedOperationalActivityPkg().getOwnedOperationalActivities().get(0));
            var items = apply(child("create_entity", "actor", pkg), child("create_activity", "activity", root),
                cmd("component_function_allocation", "allocation", "component", "actor", "function", "activity"));
            String diagram = diagram("OAB", pkg, items.get("actor").getAsString());
            String activity = items.get("activity").getAsString();
            show(diagram, activity);
            check("OAB displays allocated activity", row(diagram).getAsJsonArray("represented").contains(new JsonPrimitive(activity)));
        }
    }

    void stateMachine(BlockArchitecture layer) {
        var factory = org.polarsys.capella.core.data.capellacommon.CapellacommonFactory.eINSTANCE;
        var machine = factory.createStateMachine();
        var region = factory.createRegion();
        var domain = session.getTransactionalEditingDomain();
        domain.getCommandStack().execute(new RecordingCommand(domain) {
            @Override protected void doExecute() {
                layer.getSystem().getOwnedStateMachines().add(machine);
                machine.setName("Fixture modes");
                machine.getOwnedRegions().add(region);
                region.setName("Fixture region");
            }
        });
        try (var c = new NativeController(session, layer)) {
            controller = c;
            String root = ref(region);
            var states = apply(child("create_state", "first", root), child("create_state", "second", root));
            String first = states.get("first").getAsString(), second = states.get("second").getAsString();
            String diagram = diagram("MSM", root, first);
            var transition = apply(cmd("create_transition", "transition", "source", first, "target", second,
                "name", "Fixture transition")).get("transition").getAsString();
            show(diagram, second, transition);
            check("MSM displays transition", row(diagram).getAsJsonArray("represented").contains(new JsonPrimitive(transition)));
        }
    }

    void synchronizedStateMachine(OperationalAnalysis layer) {
        var factory = org.polarsys.capella.core.data.capellacommon.CapellacommonFactory.eINSTANCE;
        var entity = OaFactory.eINSTANCE.createEntity();
        var machine = factory.createStateMachine();
        var root = factory.createRegion();
        var parent = factory.createState();
        var unrelated = factory.createRegion();
        var outside = factory.createState();
        var domain = session.getTransactionalEditingDomain();
        domain.getCommandStack().execute(new RecordingCommand(domain) {
            @Override protected void doExecute() {
                layer.getOwnedEntityPkg().getOwnedEntities().add(entity);
                entity.setName("Synthetic mission owner");
                entity.getOwnedStateMachines().add(machine);
                machine.setName("Synthetic mission phases");
                machine.getOwnedRegions().add(root);
                root.setName("Mission root");
                root.getOwnedStates().add(parent);
                parent.setName("Operational mission");
                machine.getOwnedRegions().add(unrelated);
                unrelated.setName("Unrelated region");
                unrelated.getOwnedStates().add(outside);
                outside.setName("Unrelated state");
            }
        });
        try (var c = new NativeController(session, layer)) {
            controller = c;
            var output = apply(cmd("sirius_representation", "diagram", "kind", "MSM", "target", ref(root),
                                   "name", "Synchronized synthetic MSM"));
            String diagramRef = output.get("diagram").getAsString();
            var diagram = DialectManager.INSTANCE.getAllLoadedRepresentations(session).stream()
                .filter(rep -> rep.getName().equals("Synchronized synthetic MSM"))
                .map(DDiagram.class::cast).findFirst().orElseThrow();
            var nested = List.of(factory.createRegion(), factory.createRegion());
            domain.getCommandStack().execute(new RecordingCommand(domain) {
                @Override protected void doExecute() {
                    diagram.setSynchronized(true);
                    parent.getOwnedRegions().addAll(nested);
                    nested.get(0).setName("Primary execution");
                    nested.get(1).setName("Concurrent execution");
                }
            });
            var members = new ArrayList<JsonPrimitive>();
            for (int i = 0; i < 5; i++) {
                String owner = ref(nested.get(i % nested.size()));
                var pair = apply(cmd("create_state", "from", "parent", owner, "name", "Phase " + i + " start"),
                                 cmd("create_state", "to", "parent", owner, "name", "Phase " + i + " finish"),
                                 cmd("create_transition", "transition", "source", "from", "target", "to", "name", "Handover " + i));
                for (var key : List.of("from", "to", "transition")) members.add(pair.getAsJsonPrimitive(key));
            }
            domain.getCommandStack().execute(new RecordingCommand(domain) {
                @Override protected void doExecute() {
                    DialectManager.INSTANCE.refresh(diagram, new NullProgressMonitor());
                }
            });
            var represented = row(diagramRef).getAsJsonArray("represented");
            check("Synchronized OA MSM already displays ten nested states and five transitions",
                  members.stream().allMatch(represented::contains));
            var before = List.copyOf(diagram.getDiagramElements());
            var revision = c.snapshot().get("revision");
            int editors = openEditorCount();
            var commands = new ArrayList<JsonObject>();
            for (int i = 0; i < members.size(); i++)
                commands.add(cmd("sirius_existing_element_view", "member" + i, "diagram", diagramRef,
                                 "element", members.get(i).getAsString()));
            var receipt = receipt(commands.toArray(JsonObject[]::new));
            check("Existing nested MSM views return success without saving or advancing revision",
                  "succeeded_unsaved".equals(receipt.get("status").getAsString()) &&
                  !receipt.getAsJsonObject("result").get("saved").getAsBoolean() && revision.equals(c.snapshot().get("revision")));
            check("Nested MSM no-op preserves all view identities and editor count",
                  before.equals(List.copyOf(diagram.getDiagramElements())) && editors == openEditorCount());
            var outsideReceipt = receipt(cmd("sirius_existing_element_view", "outside", "diagram", diagramRef, "element", ref(outside)));
            check("MSM still rejects states from outside its region subtree",
                  !"succeeded_unsaved".equals(outsideReceipt.get("status").getAsString()) &&
                  before.equals(List.copyOf(diagram.getDiagramElements())));
        }
    }

    void trace(org.polarsys.capella.core.data.capellamodeller.SystemEngineering model) {
        try (var c = new NativeController(session, model)) {
            controller = c;
            var refs = new HashMap<String, String>();
            for (var element : rows()) {
                var row = element.getAsJsonObject();
                refs.putIfAbsent(row.get("type").getAsString(), row.get("alias").getAsString());
            }
            var chain = apply(
                child("create_operational_capability", "oa", refs.get("OperationalCapabilityPkg")),
                child("create_system_capability", "sa", refs.get("CapabilityPkg")),
                child("create_logical_capability", "la", refs.get("CapabilityRealizationPkg")),
                cmd("involve_operational_entity", "involvesEntity", "parent", "oa", "element", refs.get("Entity")),
                cmd("involve_capability_path", "involvesProcess", "parent", "oa", "element", refs.get("OperationalProcess")),
                cmd("realize_capability", "saToOa", "source", "sa", "target", "oa"),
                cmd("realize_capability", "laToSa", "source", "la", "target", "sa"),
                child("create_activity", "activity", refs.get("OperationalActivity")),
                child("create_system_function", "systemFn", refs.get("SystemFunction")),
                child("logical_function", "logicalFn", refs.get("LogicalFunction")),
                cmd("realize_function", "systemTrace", "source", "systemFn", "target", "activity"),
                cmd("realize_function", "logicalTrace", "source", "logicalFn", "target", "systemFn"));
            check("OA-to-SA capability trace publishes explicit endpoint",
                row(chain.get("saToOa").getAsString()).getAsJsonObject("links")
                    .getAsJsonArray("targetElement").contains(chain.get("oa")));
            check("OA capability publishes operational process involvement",
                row(chain.get("involvesProcess").getAsString()).getAsJsonObject("links")
                    .getAsJsonArray("involved").contains(new JsonPrimitive(refs.get("OperationalProcess"))));
            check("SA-to-LA function trace publishes explicit endpoint",
                row(chain.get("logicalTrace").getAsString()).getAsJsonObject("links")
                    .getAsJsonArray("targetElement").contains(chain.get("systemFn")));
        }
    }

    void chain(BlockArchitecture layer, AbstractFunction root, String code) {
        boolean operational = code.equals("OPD");
        FunctionalChain chain = operational ? OaFactory.eINSTANCE.createOperationalProcess() : FaFactory.eINSTANCE.createFunctionalChain();
        var domain = session.getTransactionalEditingDomain();
        domain.getCommandStack().execute(new RecordingCommand(domain) {
            @Override protected void doExecute() {
                root.getOwnedFunctionalChains().add(chain);
                chain.setName("Fixture " + code);
            }
        });
        try (var c = new NativeController(session, layer)) {
            controller = c;
            String rootRef = ref(root), owner = ref(chain);
            String recipe = operational ? "create_activity" : "logical_function";
            var path = apply(child(recipe, "first", rootRef), child(recipe, "last", rootRef),
                cmd(operational ? "create_interaction" : "functional_exchange_with_ports",
                    "exchange", "name", "Signal", "source", "first", "target", "last"),
                cmd("add_chain_function", "from", "parent", owner, "function", "first"),
                cmd("add_chain_function", "to", "parent", owner, "function", "last"),
                cmd("add_chain_exchange", "link", "parent", owner, "exchange", "exchange", "source", "from", "target", "to"));
            String diagram = diagram(code, owner, path.get("from").getAsString());
            String link = path.get("link").getAsString();
            show(diagram, path.get("to").getAsString(), link);
            check(code + " displays chain link", row(diagram).getAsJsonArray("represented").contains(new JsonPrimitive(link)));
        }
    }
    void logical(org.polarsys.capella.core.data.la.LogicalComponent system,
                 org.polarsys.capella.core.data.la.LogicalFunction rf, DDiagram d,
                 org.polarsys.capella.core.data.la.LogicalFunction from, org.polarsys.capella.core.data.la.LogicalFunction to,
                 org.polarsys.capella.core.data.la.LogicalComponent comp) {
        try (var c=new NativeController(session,system,rf)) {
            controller=c;
            String id=null;
            for (var e:rows()) {
                var r=e.getAsJsonObject();
                if (r.has("diagram_kind") && d.getName().equals(r.get("name").getAsString())) id=r.get("alias").getAsString();
            }
            check("Pre-existing LAB discovered on fresh pairing",id!=null);
            var nodes=new IdentityHashMap<org.eclipse.gmf.runtime.notation.Bounds,List<Integer>>();
            for (var r:session.getTransactionalEditingDomain().getResourceSet().getResources()) {
                var it=r.getAllContents();
                while (it.hasNext()) if (it.next() instanceof org.eclipse.gmf.runtime.notation.Bounds b &&
                    b.eContainer() instanceof org.eclipse.gmf.runtime.notation.Node n &&
                    n.getElement() instanceof org.eclipse.sirius.diagram.DDiagramElement e && d.getDiagramElements().contains(e))
                    nodes.put(b,List.of(b.getX(),b.getY(),b.getWidth(),b.getHeight()));
            }
            check("Existing layout captured",!nodes.isEmpty());
            var preserved=new HashSet<>(d.getDiagramElements());
            var originalOwner=comp.eContainer();
            String name=comp.getName();
            var more=apply(child("logical_function","one",ref(rf)),cmd("component_function_allocation","oneAlloc","component",ref(comp),"function","one"));
            var wire=apply(cmd("functional_exchange_with_ports","wire","source",ref(from),"target",ref(to),"name","Second signal"));
            apply(cmd("sirius_existing_element_view","v","diagram",id,"element",wire.get("wire").getAsString()));
            check("New connection visible in previously paired LAB",row(id).getAsJsonArray("represented").contains(wire.get("wire")));
            check("Existing views and layout constraints preserved",d.getDiagramElements().containsAll(preserved) &&
                nodes.entrySet().stream().allMatch(x -> {var b=x.getKey();return b.eResource()!=null &&
                    x.getValue().equals(List.of(b.getX(),b.getY(),b.getWidth(),b.getHeight()));}));
            check("Unrelated component name and owner preserved",name.equals(comp.getName()) && comp.eContainer()==originalOwner);
            check("Rebound function allocated to pre-existing component",row(more.get("oneAlloc").getAsString())
                .getAsJsonObject("links").getAsJsonArray("sourceElement").contains(new JsonPrimitive(ref(comp))));
            var other = system.getOwnedLogicalComponents().stream()
                .filter(x -> x != comp && x.getOwnedFunctionalAllocation().stream().anyMatch(a -> a.getTargetElement() == to))
                .findFirst().orElseThrow();
            verifyComponentExchange(id, ref(comp), ref(other), "LAB");
        }
    }
    void scope(org.polarsys.capella.core.data.la.LogicalComponent selected,
               org.polarsys.capella.core.data.la.LogicalComponent elsewhere,
               org.polarsys.capella.core.data.la.LogicalFunction rf) {
        try (var c=new NativeController(session,selected,rf)) {
            controller=c;
            var r=apply(child("logical_component_with_part","moving","logical-system"));
            String id=r.get("moving").getAsString();
            var moved=selected.getOwnedLogicalComponents().stream().filter(x->ref(x).equals(id)).findFirst().orElseThrow();
            var part=moved.getRepresentingParts().get(0);
            session.getTransactionalEditingDomain().getCommandStack().execute(new org.eclipse.emf.transaction.RecordingCommand(session.getTransactionalEditingDomain()) {
                @Override protected void doExecute() {
                    elsewhere.getOwnedLogicalComponents().add(moved);
                    elsewhere.getOwnedFeatures().add(part);
                }
            });
            for (var e:rows()) if (e.getAsJsonObject().get("alias").getAsString().equals(id)) throw new AssertionError("Moved object leaked");
            check("Moved object excluded on refreshed subtree publication",moved.eContainer()==elsewhere);
            int count=moved.getOwnedLogicalComponents().size();
            var snap=controller.snapshot();
            var payload=new JsonObject(); payload.addProperty("contract","capella-native-intent/1");
            payload.addProperty("model_id","native-model"); payload.add("expected_revision",snap.get("revision"));
            payload.add("session_epoch",snap.get("session_epoch")); payload.addProperty("save",false);
            payload.addProperty("plan_digest","synthetic"); payload.add("requires",new JsonArray());
            var commands=new JsonArray();commands.add(child("logical_component_with_part","outside",id));payload.add("commands",commands);
            var job=new JsonObject();job.add("payload",payload);job.addProperty("lease","fixture");job.addProperty("job_id","stale-ref");
            var receipt=controller.execute(job);
            check("Old reference cannot write into moved branch at current revision",
                !receipt.get("status").getAsString().equals("succeeded_unsaved") && count==moved.getOwnedLogicalComponents().size());
        }
    }
    void run(BlockArchitecture layer) {
        try (var c=new NativeController(session,layer)) {
            controller=c;
            if (layer instanceof SystemAnalysis sa) {
                var sys=(SystemComponent)sa.getSystem(); String root=ref(sys), pkg=ref(sys.eContainer());
                var rf=sa.getContainedSystemFunctionPkg().getOwnedSystemFunctions().get(0);
                var a=apply(child("create_system_actor","actor",pkg),child("create_system_function","f",ref(rf)),
                    cmd("component_function_allocation","alloc","function","f","component","actor"));
                String actor=a.get("actor").getAsString(), f=a.get("f").getAsString();
                check("System actor and function retain distinct IDs",!actor.equals(f));
                apply(cmd("reassign_allocation","adjust","allocation",a.get("alloc").getAsString(),"component",root));
                check("Existing allocation identity and new owner",row(a.get("alloc").getAsString()).get("owner").getAsString().equals(root));
                String sab=diagram("SAB",root,actor);
                var extra=apply(child("create_system_function","second",ref(rf)),cmd("component_function_allocation","aa","function","second","component",actor));
                var exchange=apply(cmd("functional_exchange_with_ports","send","source",f,"target",extra.get("second").getAsString(),"name","Command"));
                show(sab,root,f,extra.get("second").getAsString(),exchange.get("send").getAsString());
                check("SAB contains new functional exchange",row(sab).getAsJsonArray("represented").contains(exchange.get("send")));
                verifyComponentExchange(sab, actor, root, "SAB");
            } else if (layer instanceof PhysicalArchitecture pa) {
                var sys=(PhysicalComponent)pa.getSystem(); String root=ref(sys);
                var a=apply(child("create_node_component","nodeA",root),child("create_node_component","nodeB",root),
                    child("create_behavior_component","behavior",root),child("create_physical_port","p","nodeA"),
                    child("create_physical_port","q","nodeB"),cmd("connect_physical_ports","link","source","p","target","q","name","Fixture cable"));
                check("Same-name physical nodes are individually addressable",
                    !a.get("nodeA").equals(a.get("nodeB")) && row(a.get("nodeA").getAsString()).get("name").equals(row(a.get("nodeB").getAsString()).get("name")));
                String node=a.get("nodeA").getAsString(), behavior=a.get("behavior").getAsString();
                var pcA=sys.getOwnedPhysicalComponents().stream().filter(pc->ref(pc).equals(node)).findFirst().orElseThrow();
                var bc=sys.getOwnedPhysicalComponents().stream().filter(pc->ref(pc).equals(behavior)).findFirst().orElseThrow();
                apply(cmd("deploy_behavior","deploy","host",ref(pcA.getRepresentingParts().get(0)),"deployed",ref(bc.getRepresentingParts().get(0))));
                check("Deployment points to behavior Part",pcA.getRepresentingParts().get(0).getDeployedParts().contains(bc.getRepresentingParts().get(0)));
                check("Physical link has two physical port references",row(a.get("link").getAsString()).getAsJsonObject("links").getAsJsonArray("linkEnds").size()==2);
                String pab=diagram("PAB",root,node);
                show(pab,a.get("nodeB").getAsString(),behavior,a.get("link").getAsString());
                check("PAB contains cable and deployed behavior",row(pab).getAsJsonArray("represented").contains(a.get("link")) &&
                    row(pab).getAsJsonArray("represented").contains(a.get("behavior")));
                String pf=ref(pa.getContainedPhysicalFunctionPkg().getOwnedPhysicalFunctions().get(0));
                var funcs=apply(child("create_physical_function","one",pf),child("create_physical_function","two",pf),
                    cmd("component_function_allocation","a","component",behavior,"function","one"),
                    cmd("component_function_allocation","b","component",behavior,"function","two"),
                    cmd("functional_exchange_with_ports","signal","source","one","target","two","name","Status"));
                show(pab,funcs.get("one").getAsString(),funcs.get("two").getAsString(),funcs.get("signal").getAsString());
                check("PAB contains physical function exchange",row(pab).getAsJsonArray("represented").contains(funcs.get("signal")));
            } else if (layer instanceof OperationalAnalysis oa) {
                var pkg=oa.getOwnedEntityPkg(); var rf=oa.getContainedOperationalActivityPkg().getOwnedOperationalActivities().get(0);
                var a=apply(child("create_entity","entity",ref(pkg)),child("create_activity","a",ref(rf)),child("create_activity","b",ref(rf)),
                    cmd("create_interaction","interaction","source","a","target","b","name","Operational handover"),
                    cmd("component_function_allocation","allocation","function","a","component","entity"));
                check("Interaction source is activity",row(a.get("interaction").getAsString()).getAsJsonObject("links").getAsJsonArray("source").contains(a.get("a")));
                var actor=apply(child("create_operational_actor","individual",ref(pkg)));
                check("Operational actor flag present",row(actor.get("individual").getAsString()).getAsJsonObject("properties").get("actor").getAsString().equals("true"));
                diagram("OEB",ref(pkg),a.get("entity").getAsString());
            } else if (layer instanceof EPBSArchitecture epbs) {
                var pkg=epbs.getOwnedConfigurationItemPkg();
                var a=apply(cmd("create_configuration_item","ci","parent",ref(pkg),"kind","HWCI","name","Fixture hardware"));
                check("CI kind persisted","HWCI".equals(row(a.get("ci").getAsString()).getAsJsonObject("properties").get("kind").getAsString()));
                diagram("CIBD",ref(pkg),a.get("ci").getAsString());
            }
        }
    }

    private void verifyComponentExchange(String diagram, String source, String target, String kind) {
        var result = apply(cmd("connect_components", "flow", "source", source, "target", target, "name", kind + " port flow"));
        String exchange = result.get("flow").getAsString();
        show(diagram, exchange);
        check(kind + " displays port-based component exchange", row(diagram).getAsJsonArray("represented").contains(new JsonPrimitive(exchange)));
    }
}

