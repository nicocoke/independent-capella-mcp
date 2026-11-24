package org.example.capella.mcp;

import java.util.*;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.emf.common.command.Command;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.util.EcoreUtil;
import org.eclipse.sirius.business.api.dialect.DialectManager;
import org.eclipse.sirius.business.api.session.Session;
import org.eclipse.sirius.diagram.*;
import org.eclipse.sirius.diagram.description.*;
import org.eclipse.sirius.diagram.tools.api.command.view.CreateDDiagramElementCommand;
import org.polarsys.capella.core.data.cs.*;
import org.polarsys.capella.core.data.capellacommon.*;
import org.polarsys.capella.core.data.ctx.*;
import org.polarsys.capella.core.data.la.*;
import org.polarsys.capella.core.data.pa.*;
import org.polarsys.capella.core.data.oa.*;
import org.polarsys.capella.core.data.epbs.*;
import org.polarsys.capella.core.data.fa.*;
import org.polarsys.capella.core.model.handler.helpers.CapellaProjectHelper;

/** Adapter name retained for legacy callers. Mapping IDs come from the 7.1.0 VSMs. */
public final class LabDiagramAdapter implements DiagramAdapter {
    private final Set<DDiagram> created = new HashSet<>();

    public void preflight(Session session,List<NativeCommand> commands) {
        created.clear();
        for (var c : commands) if (c.recipe().equals("sirius_representation"))
            description(session, DiagramKind.valueOf(c.get("kind")));
    }
    private static DiagramDescription description(Session session, DiagramKind kind) {
        DiagramDescription found=null;
        for (var v : session.getSelectedViewpoints(false)) for (var r : v.getOwnedRepresentations())
            if (r instanceof DiagramDescription d && kind.title.equals(d.getName())) {
                if (found!=null) throw new IllegalStateException("Ambiguous diagram description");
                found=d;
            }
        if (found==null) throw new IllegalStateException("Enable the requested Capella viewpoint");
        return found;
    }
    private static <T> T mapping(DDiagram diagram,String name,Class<T> type) {
        for (var item : diagram.getDescription().getDefaultLayer().getReusedMappings())
            if (name.equals(item.getName()) && type.isInstance(item)) return type.cast(item);
        T found=null;
        var it=diagram.getDescription().eAllContents();
        while (it.hasNext()) {
            var item=it.next();
            if (item instanceof DiagramElementMapping m && name.equals(m.getName()) && type.isInstance(m)) {
                if (found!=null) throw new IllegalStateException("Ambiguous mapping "+name);
                found=type.cast(m);
            }
        }
        if (found==null) throw new IllegalStateException("Missing mapping "+name);
        return found;
    }
    public EObject execute(Session session, NativeCommand c, Map<String,EObject> refs) {
        if (c.recipe().equals("sirius_representation")) {
            EObject target=refs.get(c.get("target"));
            var kind = DiagramKind.valueOf(c.get("kind"));
            var desc = description(session, kind);
            if (target == null || (kind.semanticType != null && !isType(target, kind.semanticType)) ||
                !DialectManager.INSTANCE.canCreate(target,desc)) throw new IllegalArgumentException("Incompatible diagram target");
            var rep=RepresentationRecipes.create(session,target,c.get("name"),desc);
            created.add((DDiagram)rep);
            return rep;
        }
        if (!(refs.get(c.get("diagram")) instanceof DSemanticDiagram d))
            throw new IllegalArgumentException("Select a loaded supported Capella diagram");
        var kind = DiagramKind.fromTitle(d.getDescription().getName());
        if (description(session, kind) != d.getDescription())
            throw new IllegalArgumentException("Select an enabled Capella diagram");
        EObject item=refs.get(c.get("element"));
        var layer=ModelInventory.architecture(item);
        if (layer==null || layer!=ModelInventory.architecture(d.getTarget()))
            throw new IllegalArgumentException("Element and diagram must belong to the same architecture");
        if (kind.isBreakdown()) return breakdownView(session, d, kind, item);
        if (kind.isFlow()) return flowView(session, d, kind, item);
        if (kind == DiagramKind.OAB) return operationalEntityView(session, d, item, refs);
        if (kind == DiagramKind.FCD || kind == DiagramKind.OPD) {
            if (item == null || item.eContainer() != d.getTarget())
                throw new IllegalArgumentException("Select an involvement in the diagram's chain or process");
            if (item instanceof FunctionalChainInvolvementFunction)
                return node(session, d, item, "FC_AbstractFunction", d);
            if (item instanceof FunctionalChainInvolvementLink link)
                return edge(session, d, item, "FC_Exchange",
                    requireView(d, link.getSource()), requireView(d, link.getTarget()));
        }
        if (kind == DiagramKind.MSM) {
            if (item == null || item.eContainer() != d.getTarget()) throw new IllegalArgumentException("Select an element in the diagram region");
            if (item instanceof State || item instanceof Mode)
                return node(session, d, item, "MSM_ModeState_Container", d);
            if (item instanceof StateTransition transition)
                return edge(session, d, transition, "MSM_Transition",
                    requireView(d, transition.getSource()), requireView(d, transition.getTarget()));
        }
        if (kind == DiagramKind.EAB && item instanceof ConfigurationItem ci)
            return configurationView(session, d, ci);
        if (kind == DiagramKind.OEB && item instanceof Entity)
            return node(session,d,item,"OEB_OperationalEntities",d);
        if (kind == DiagramKind.CIBD && item instanceof ConfigurationItem)
            return node(session,d,item,"CIBD_ConfigurationItem",d);
        boolean la = kind == DiagramKind.LAB, sa = kind == DiagramKind.SAB, pa = kind == DiagramKind.PAB;
        if (item instanceof Component component && ((la && item instanceof LogicalComponent) ||
            (sa && item instanceof SystemComponent) || (pa && item instanceof PhysicalComponent))) {
            Part part=uniquePart(component);
            var existing=view(d,part);
            if (existing!=null) return existing;
            if (pa && !part.getDeployingParts().isEmpty()) {
                if (part.getDeployingParts().size()!=1) throw new IllegalArgumentException("Ambiguous deployment location");
                var host = part.getDeployingParts().get(0);
                if (!refs.containsValue(host) || !(requireView(d,host) instanceof DragAndDropTarget drop))
                    throw new IllegalArgumentException("Show the in-scope host Part first");
                return node(session,d,part,"PAB_Deployment",drop);
            }
            DragAndDropTarget container=d;
            if (component.eContainer() instanceof Component parent && parent.getRepresentingParts().size()==1) {
                var pv=view(d,parent.getRepresentingParts().get(0));
                if (pv instanceof DragAndDropTarget drop) container=drop;
            }
            String name=la?"LAB Logical Component":pa?"PAB_PC":component.isActor()?"System Actors":"System System";
            return node(session,d,part,name,container);
        }
        if (item instanceof AbstractFunction f && ((la && f instanceof LogicalFunction) ||
            (sa && f instanceof SystemFunction) || (pa && f instanceof PhysicalFunction))) {
            var existing=view(d,item);
            if (existing!=null) return existing;
            if (f.getAllocationBlocks().size()!=1 || !(f.getAllocationBlocks().get(0) instanceof Component comp)
                || !refs.containsValue(comp)) throw new IllegalArgumentException("A unique in-scope allocating component is required");
            var owner=requireView(d,uniquePart(comp));
            if (!(owner instanceof DragAndDropTarget drop)) throw new IllegalArgumentException("Show the allocating component first");
            return node(session,d,f,la?"LAB Logical Function":pa?"PAB_PhysicalFunction":"CA System Function",drop);
        }
        if ((la || sa || pa) && item instanceof FunctionalExchange e) {
            var existing=view(d,e);
            if (existing!=null) return existing;
            if (created.contains(d)) DialectManager.INSTANCE.refresh(d,new NullProgressMonitor());
            existing=view(d,e);
            if (existing!=null) return existing;
            String pin=la?"LAB Flow Port on Logical Function":pa?"PAB_Pin":"CA Flow Port on System Function";
            return edge(session,d,e,la?"LAB DataFlow between Function":pa?"PAB_FunctionExchange":"CA DataFlow between Function",
                port(session,d,e.getSource(),pin),port(session,d,e.getTarget(),pin));
        }
        if ((la || sa) && item instanceof ComponentExchange e &&
            e.getSource() instanceof ComponentPort from && e.getTarget() instanceof ComponentPort to) {
            String pin = la ? "LAB ComponentPort" : "CA Component Port";
            String mapping = la ? "LAB DataFlow between Logical Components" : "CA Data Flow Between Actors and System";
            return edge(session, d, e, mapping, componentPort(session, d, from, pin), componentPort(session, d, to, pin));
        }
        if (pa && item instanceof PhysicalLink link && link.getLinkEnds().size()==2 &&
            link.getLinkEnds().get(0) instanceof PhysicalPort from && link.getLinkEnds().get(1) instanceof PhysicalPort to)
            return edge(session,d,link,"PAB_PhysicalLink",physicalPort(session,d,from),physicalPort(session,d,to));
        throw new IllegalArgumentException("Unsupported element for selected diagram mapping");
    }

    private static boolean isType(EObject object, String type) {
        return object != null && type.equals(object.eClass().getName());
    }

    private static EObject operationalEntityView(Session session, DSemanticDiagram diagram, EObject item,
                                                 Map<String,EObject> refs) {
        if (item instanceof Entity entity) {
            DragAndDropTarget container = diagram;
            if (view(diagram, entity.eContainer()) instanceof DragAndDropTarget parent) container = parent;
            return node(session, diagram, entity, "OAB_Entity1", container);
        }
        if (item instanceof OperationalActivity activity) {
            if (activity.getAllocationBlocks().size() != 1 ||
                !(activity.getAllocationBlocks().get(0) instanceof Entity entity) ||
                !refs.containsValue(entity) ||
                !(requireView(diagram, entity) instanceof DragAndDropTarget owner))
                throw new IllegalArgumentException("Show the unique in-scope allocating entity first");
            return node(session, diagram, activity, "OAB_Activity", owner);
        }
        if (item instanceof FunctionalExchange exchange &&
            exchange.getSource() instanceof OperationalActivity && exchange.getTarget() instanceof OperationalActivity)
            return edge(session, diagram, exchange, "OAB Interaction",
                requireView(diagram, exchange.getSource()), requireView(diagram, exchange.getTarget()));
        throw new IllegalArgumentException("Expected an operational entity, allocated activity or interaction");
    }

    private static EObject flowView(Session session, DSemanticDiagram diagram, DiagramKind kind, EObject item) {
        if (!isType(diagram.getTarget(), kind.semanticType))
            throw new IllegalArgumentException("Select a function- or activity-owned flow diagram");
        if (isType(item, kind.semanticType)) {
            DragAndDropTarget container = diagram;
            if (view(diagram, item.eContainer()) instanceof DragAndDropTarget parent) container = parent;
            return node(session, diagram, item, kind.nodeMapping, container);
        }
        if (!(item instanceof FunctionalExchange exchange))
            throw new IllegalArgumentException("Select a function, activity or exchange");
        if (kind == DiagramKind.OAIB) {
            if (!(exchange.getSource() instanceof OperationalActivity) || !(exchange.getTarget() instanceof OperationalActivity))
                throw new IllegalArgumentException("Expected a direct operational interaction");
            return edge(session, diagram, exchange, kind.edgeMapping,
                requireView(diagram, exchange.getSource()), requireView(diagram, exchange.getTarget()));
        }
        if (!(exchange.getSource() instanceof FunctionOutputPort from) ||
            !(exchange.getTarget() instanceof FunctionInputPort to) ||
            !isType(from.eContainer(), kind.semanticType) || !isType(to.eContainer(), kind.semanticType))
            throw new IllegalArgumentException("Expected same-layer functional exchange ports");
        return edge(session, diagram, exchange, kind.edgeMapping,
            port(session, diagram, from, kind.pinMapping), port(session, diagram, to, kind.pinMapping));
    }

    private static EObject configurationView(Session session, DSemanticDiagram diagram, ConfigurationItem item) {
        if (item != diagram.getTarget() && !EcoreUtil.isAncestor(diagram.getTarget(), item))
            throw new IllegalArgumentException("Select a configuration item in the diagram's root subtree");
        DragAndDropTarget container = diagram;
        if (item.eContainer() instanceof ConfigurationItem parent && parent != diagram.getTarget()) {
            if (!(requireView(diagram, uniquePart(parent)) instanceof DragAndDropTarget owner))
                throw new IllegalArgumentException("Show the parent configuration item first");
            container = owner;
        }
        return node(session, diagram, uniquePart(item), "CI container mapping", container);
    }

    private static DNode breakdownNode(DDiagram diagram, EObject item, NodeMapping mapping) {
        DNode found = null;
        for (var view : diagram.getDiagramElements()) {
            if (view instanceof DNode node && node.getActualMapping() == mapping &&
                ModelInventory.raw(node, "target") == item) {
                if (found != null) throw new IllegalArgumentException("Ambiguous breakdown node");
                found = node;
            }
        }
        return found;
    }

    private static EObject breakdownView(Session session, DSemanticDiagram diagram, DiagramKind kind, EObject item) {
        EObject root = diagram.getTarget();
        if (!isType(item, kind.semanticType) || !isType(root, kind.semanticType) ||
            (item != root && !EcoreUtil.isAncestor(root, item)))
            throw new IllegalArgumentException("Select an element in the breakdown's root subtree");

        // The native mappings omit a layer's artificial root function or logical system.
        boolean hiddenRoot = !isType(root.eContainer(), kind.semanticType) &&
            (root instanceof AbstractFunction && root.eContainer() instanceof FunctionPkg &&
                root.eContainer().eContainer() instanceof BlockArchitecture
             || root instanceof Component component && ModelInventory.architecture(root).getSystem() == component);
        if (item == root && hiddenRoot) throw new IllegalArgumentException("Select a child of the architecture root");

        var nodeMapping = mapping(diagram, kind.nodeMapping, NodeMapping.class);
        var parent = item.eContainer();
        DNode parentView = null;
        if (item != root && !(parent == root && hiddenRoot)) {
            if (!isType(parent, kind.semanticType))
                throw new IllegalArgumentException("Only direct component or function containment is supported");
            parentView = breakdownNode(diagram, parent, nodeMapping);
            if (parentView == null) throw new IllegalArgumentException("Show the item's parent in the breakdown first");
        }
        Part part = null;
        if (item instanceof Component component) {
            if (item != root) part = uniquePart(component);
            if (CapellaProjectHelper.isReusableComponentsDriven(component) != CapellaProjectHelper.TriStateBoolean.False ||
                (part != null && part.eContainer() != parent))
                throw new IllegalArgumentException("Component breakdown edits require single-Part containment");
        }

        var domain = session.getTransactionalEditingDomain();
        DNode node = breakdownNode(diagram, item, nodeMapping);
        if (node == null) {
            execute(new CreateDDiagramElementCommand(domain, item, nodeMapping, diagram));
            node = breakdownNode(diagram, item, nodeMapping);
            if (node == null) throw new IllegalStateException("Native breakdown node missing");
        }
        if (parentView != null) {
            var relation = mapping(diagram, kind.edgeMapping, EdgeMapping.class);
            var child = node;
            var owner = parentView;
            boolean exists = diagram.getEdges().stream().anyMatch(edge ->
                edge.getActualMapping() == relation && edge.getSourceNode() == child && edge.getTargetNode() == owner);
            EObject edgeTarget = kind == DiagramKind.PCBD ? part : item;
            if (!exists) execute(new CreateDDiagramElementCommand(domain, edgeTarget, relation, child, owner));
        }
        return node;
    }
    private static Part uniquePart(Component c) {
        var parts=c.getRepresentingParts();
        if (parts.size()!=1) throw new IllegalArgumentException("Component needs one unambiguous Part");
        return parts.get(0);
    }

    private static DDiagramElement componentPort(Session session, DDiagram diagram, ComponentPort port, String mapping) {
        if (!(port.eContainer() instanceof Component component) ||
            !(requireView(diagram, uniquePart(component)) instanceof DragAndDropTarget owner))
            throw new IllegalArgumentException("Show both component Parts first");
        return node(session, diagram, port, mapping, owner);
    }
    private static DDiagramElement physicalPort(Session session, DDiagram d, PhysicalPort p) {
        var existing=view(d,p);
        if (existing!=null) return existing;
        if (!(p.eContainer() instanceof PhysicalComponent pc) ||
            !(requireView(d,uniquePart(pc)) instanceof DragAndDropTarget container))
            throw new IllegalArgumentException("Show physical nodes before their link");
        return node(session,d,p,"PAB_Port",container);
    }
    private static DDiagramElement port(Session s,DDiagram d,EObject port,String mapping) {
        if (port==null) throw new IllegalArgumentException("Missing port");
        var existing=view(d,port);
        if (existing!=null) return existing;
        if (!(requireView(d,port.eContainer()) instanceof DragAndDropTarget owner))
            throw new IllegalArgumentException("Show endpoint functions first");
        return node(s,d,port,mapping,owner);
    }
    private static DDiagramElement node(Session s,DDiagram d,EObject item,String name,DragAndDropTarget owner) {
        var existing=view(d,item);
        if (existing!=null) return existing;
        execute(new CreateDDiagramElementCommand(s.getTransactionalEditingDomain(), item, mapping(d,name,AbstractNodeMapping.class),owner));
        return requireView(d,item);
    }
    private static DDiagramElement edge(Session s,DDiagram d,EObject item,String name,DDiagramElement a,DDiagramElement b) {
        var existing=view(d,item);
        if (existing!=null) return existing;
        if (!(a instanceof EdgeTarget from) || !(b instanceof EdgeTarget to)) throw new IllegalArgumentException("Missing endpoint views");
        execute(new CreateDDiagramElementCommand(s.getTransactionalEditingDomain(),item,mapping(d,name,EdgeMapping.class),from,to));
        return requireView(d,item);
    }
    private static void execute(Command c) {
        if (!c.canExecute()) throw new IllegalStateException("Native view command rejected");
        c.execute();
    }
    private static DDiagramElement view(DDiagram d,EObject item) {
        DDiagramElement found=null;
        for (var v : d.getDiagramElements()) if (ModelInventory.raw(v,"target")==item) {
            if (found!=null) throw new IllegalArgumentException("Ambiguous existing view");
            found=v;
        }
        return found;
    }
    private static DDiagramElement requireView(DDiagram d,EObject item) {
        var v=view(d,item);
        if (v==null) throw new IllegalArgumentException("Required view missing");
        return v;
    }
}
