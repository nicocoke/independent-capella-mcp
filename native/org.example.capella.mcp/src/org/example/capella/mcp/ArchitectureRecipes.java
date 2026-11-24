package org.example.capella.mcp;

import java.util.Map;
import org.eclipse.emf.ecore.EObject;
import org.polarsys.capella.core.data.interaction.AbstractCapability;
import org.polarsys.capella.core.data.interaction.InteractionFactory;
import org.polarsys.capella.core.data.capellacommon.*;
import org.polarsys.capella.core.data.cs.*;
import org.polarsys.capella.core.data.ctx.*;
import org.polarsys.capella.core.data.fa.*;
import org.polarsys.capella.core.data.la.*;
import org.polarsys.capella.core.data.pa.*;
import org.polarsys.capella.core.data.pa.deployment.DeploymentFactory;
import org.polarsys.capella.core.data.oa.*;
import org.polarsys.capella.core.data.epbs.*;
import org.polarsys.capella.core.data.capellacore.CapellaElement;
import org.polarsys.capella.core.model.handler.helpers.CapellaProjectHelper;
import org.polarsys.capella.core.model.helpers.PhysicalLinkExt;
import org.polarsys.capella.core.model.helpers.ComponentExchangeExt;

final class ArchitectureRecipes {
    private ArchitectureRecipes() {}

    static boolean compatible(Component component, AbstractFunction function) {
        if (ModelInventory.architecture(component) != ModelInventory.architecture(function)) return false;
        return component instanceof LogicalComponent && function instanceof LogicalFunction
            || component instanceof SystemComponent && function instanceof SystemFunction
            || component instanceof Entity && function instanceof OperationalActivity
            || component instanceof PhysicalComponent p && p.getNature()==PhysicalComponentNature.BEHAVIOR
               && function instanceof PhysicalFunction;
    }
    private static PhysicalComponent node(EObject item) {
        if (!(item instanceof PhysicalComponent p) || p.getNature()!=PhysicalComponentNature.NODE)
            throw new IllegalArgumentException("A node physical component is required");
        return p;
    }
    static EObject execute(NativeCommand c, Map<String,EObject> refs) {
        EObject parent = refs.get(c.get("parent"));
        CapellaElement result;
        switch(c.recipe()) {
        case "involve_operational_entity": {
            var capability = (OperationalCapability) parent;
            var entity = (Entity) refs.get(c.get("element"));
            if (ModelInventory.architecture(capability) != ModelInventory.architecture(entity) ||
                capability.getInvolvedEntities().contains(entity)) throw new IllegalArgumentException("Invalid or duplicate entity involvement");
            var involvement = OaFactory.eINSTANCE.createEntityOperationalCapabilityInvolvement();
            capability.getOwnedEntityOperationalCapabilityInvolvements().add(involvement);
            involvement.setInvolved(entity);
            result = involvement; break;
        }
        case "involve_capability_path": {
            var capability = (AbstractCapability) parent;
            var path = (FunctionalChain) refs.get(c.get("element"));
            if (ModelInventory.architecture(capability) != ModelInventory.architecture(path) ||
                (capability instanceof OperationalCapability) != (path instanceof OperationalProcess) ||
                capability.getInvolvedFunctionalChains().contains(path))
                throw new IllegalArgumentException("Invalid or duplicate capability path involvement");
            var involvement = InteractionFactory.eINSTANCE.createFunctionalChainAbstractCapabilityInvolvement();
            capability.getOwnedFunctionalChainAbstractCapabilityInvolvements().add(involvement);
            involvement.setInvolved(path);
            result = involvement; break;
        }
        case "connect_components": {
            var source = (Component) refs.get(c.get("source"));
            var target = (Component) refs.get(c.get("target"));
            if (source == target || source.eClass() != target.eClass() ||
                !(source instanceof SystemComponent || source instanceof LogicalComponent) ||
                ModelInventory.architecture(source) != ModelInventory.architecture(target) ||
                CapellaProjectHelper.isReusableComponentsDriven(source) != CapellaProjectHelper.TriStateBoolean.False)
                throw new IllegalArgumentException("Expected distinct same-layer singleton system or logical components");
            var out = FaFactory.eINSTANCE.createComponentPort();
            var in = FaFactory.eINSTANCE.createComponentPort();
            out.setKind(ComponentPortKind.FLOW);
            in.setKind(ComponentPortKind.FLOW);
            out.setOrientation(OrientationPortKind.OUT);
            in.setOrientation(OrientationPortKind.IN);
            source.getOwnedFeatures().add(out);
            target.getOwnedFeatures().add(in);
            SemanticRecipes.initialize(out, c.get("name") + " out");
            SemanticRecipes.initialize(in, c.get("name") + " in");
            var exchange = FaFactory.eINSTANCE.createComponentExchange();
            exchange.setKind(ComponentExchangeKind.FLOW);
            exchange.setOriented(true);
            exchange.setSource(out);
            exchange.setTarget(in);
            ComponentExchangeExt.attachToDefaultContainer(exchange);
            if (!refs.containsValue(exchange.eContainer()))
                throw new IllegalArgumentException("Component exchange owner is outside the paired publication");
            result = exchange; break;
        }
        case "create_operational_capability": {
            var capability = OaFactory.eINSTANCE.createOperationalCapability();
            ((OperationalCapabilityPkg) parent).getOwnedOperationalCapabilities().add(capability);
            result = capability; break;
        }
        case "create_system_capability": {
            var capability = CtxFactory.eINSTANCE.createCapability();
            ((CapabilityPkg) parent).getOwnedCapabilities().add(capability);
            result = capability; break;
        }
        case "create_logical_capability": {
            var capability = LaFactory.eINSTANCE.createCapabilityRealization();
            ((CapabilityRealizationPkg) parent).getOwnedCapabilityRealizations().add(capability);
            result = capability; break;
        }
        case "realize_capability": {
            var source = (AbstractCapability) refs.get(c.get("source"));
            var target = (AbstractCapability) refs.get(c.get("target"));
            if (!(source instanceof Capability && target instanceof OperationalCapability ||
                  source instanceof CapabilityRealization && target instanceof Capability) ||
                source.getOwnedAbstractCapabilityRealizations().stream().anyMatch(r -> r.getTargetElement() == target))
                throw new IllegalArgumentException("Invalid or duplicate capability realization");
            var realization = InteractionFactory.eINSTANCE.createAbstractCapabilityRealization();
            source.getOwnedAbstractCapabilityRealizations().add(realization);
            realization.setSourceElement(source);
            realization.setTargetElement(target);
            result = realization; break;
        }
        case "realize_function": {
            var source = (AbstractFunction) refs.get(c.get("source"));
            var target = (AbstractFunction) refs.get(c.get("target"));
            if (!(source instanceof SystemFunction && target instanceof OperationalActivity ||
                  source instanceof LogicalFunction && target instanceof SystemFunction) ||
                source.getOwnedFunctionRealizations().stream().anyMatch(r -> r.getTargetElement() == target))
                throw new IllegalArgumentException("Invalid or duplicate function realization");
            var realization = FaFactory.eINSTANCE.createFunctionRealization();
            source.getOwnedFunctionRealizations().add(realization);
            realization.setSourceElement(source);
            realization.setTargetElement(target);
            result = realization; break;
        }
        case "realize_system_component": {
            var source = (LogicalComponent) refs.get(c.get("source"));
            var target = (SystemComponent) refs.get(c.get("target"));
            if (source.isActor() != target.isActor() ||
                source.getOwnedComponentRealizations().stream().anyMatch(r -> r.getTargetElement() == target))
                throw new IllegalArgumentException("Invalid or duplicate component realization");
            var realization = CsFactory.eINSTANCE.createComponentRealization();
            source.getOwnedComponentRealizations().add(realization);
            realization.setSourceElement(source);
            realization.setTargetElement(target);
            result = realization; break;
        }
        case "add_chain_function": {
            var chain = (FunctionalChain) parent;
            var function = (AbstractFunction) refs.get(c.get("function"));
            if (ModelInventory.architecture(chain) != ModelInventory.architecture(function) ||
                (chain instanceof OperationalProcess) != (function instanceof OperationalActivity))
                throw new IllegalArgumentException("Chain and function must belong to the same architecture");
            var involvement = FaFactory.eINSTANCE.createFunctionalChainInvolvementFunction();
            chain.getOwnedFunctionalChainInvolvements().add(involvement);
            involvement.setInvolved(function);
            result = involvement; break;
        }
        case "add_chain_exchange": {
            var chain = (FunctionalChain) parent;
            var from = (FunctionalChainInvolvementFunction) refs.get(c.get("source"));
            var to = (FunctionalChainInvolvementFunction) refs.get(c.get("target"));
            var exchange = (FunctionalExchange) refs.get(c.get("exchange"));
            if (from == to || from.eContainer() != chain || to.eContainer() != chain ||
                ModelInventory.architecture(chain) != ModelInventory.architecture(exchange) ||
                !matchesEndpoint(exchange.getSource(), from.getInvolved()) ||
                !matchesEndpoint(exchange.getTarget(), to.getInvolved()))
                throw new IllegalArgumentException("Exchange endpoints must match involvements in the selected chain");
            var link = FaFactory.eINSTANCE.createFunctionalChainInvolvementLink();
            chain.getOwnedFunctionalChainInvolvements().add(link);
            link.setInvolved(exchange);
            link.setSource(from);
            link.setTarget(to);
            result = link; break;
        }
        case "create_state": case "create_mode": {
            var region = (Region) parent;
            AbstractState state = c.recipe().equals("create_state")
                ? CapellacommonFactory.eINSTANCE.createState() : CapellacommonFactory.eINSTANCE.createMode();
            region.getOwnedStates().add(state);
            result = state; break;
        }
        case "create_transition": {
            var from = (AbstractState) refs.get(c.get("source"));
            var to = (AbstractState) refs.get(c.get("target"));
            if (!(from instanceof State || from instanceof Mode) || !(to instanceof State || to instanceof Mode) ||
                !(from.eContainer() instanceof Region region) || to.eContainer() != region || !refs.containsValue(region))
                throw new IllegalArgumentException("Select two states or modes in one region");
            var transition = CapellacommonFactory.eINSTANCE.createStateTransition();
            region.getOwnedTransitions().add(transition);
            transition.setSource(from);
            transition.setTarget(to);
            result = transition; break;
        }
        case "create_system_actor": {
            var actor = CtxFactory.eINSTANCE.createSystemComponent();
            actor.setActor(true);
            ((SystemComponentPkg)parent).getOwnedSystemComponents().add(actor);
            result = actor; break;
        }
        case "create_system_function": {
            var function = CtxFactory.eINSTANCE.createSystemFunction();
            ((SystemFunction)parent).getOwnedFunctions().add(function);
            result = function; break;
        }
        case "create_node_component": case "create_behavior_component": {
            var child = PaFactory.eINSTANCE.createPhysicalComponent();
            var owner = (PhysicalComponent)parent;
            boolean behavior = c.recipe().equals("create_behavior_component");
            if (!behavior && owner.getNature()==PhysicalComponentNature.BEHAVIOR)
                throw new IllegalArgumentException("Behavior components cannot own node components");
            child.setNature(behavior ? PhysicalComponentNature.BEHAVIOR : PhysicalComponentNature.NODE);
            owner.getOwnedPhysicalComponents().add(child);
            result = child; break;
        }
        case "create_physical_function": {
            var child = PaFactory.eINSTANCE.createPhysicalFunction();
            ((PhysicalFunction)parent).getOwnedFunctions().add(child);
            result = child; break;
        }
        case "deploy_behavior": {
            var host = (Part) refs.get(c.get("host"));
            var deployed = (Part) refs.get(c.get("deployed"));
            node(host.getAbstractType());
            if (!(deployed.getAbstractType() instanceof PhysicalComponent pc) || pc.getNature()!=PhysicalComponentNature.BEHAVIOR
                || host.eContainer()!=deployed.eContainer() || !deployed.getDeployingParts().isEmpty())
                throw new IllegalArgumentException("Deployment requires sibling node and undeployed behavior Parts");
            var link = DeploymentFactory.eINSTANCE.createPartDeploymentLink();
            host.getOwnedDeploymentLinks().add(link);
            link.setLocation(host); link.setDeployedElement(deployed);
            result = link; break;
        }
        case "create_physical_port": {
            var port = CsFactory.eINSTANCE.createPhysicalPort();
            node(parent).getOwnedFeatures().add(port);
            result = port; break;
        }
        case "connect_physical_ports": {
            var from = (PhysicalPort)refs.get(c.get("source"));
            var to = (PhysicalPort)refs.get(c.get("target"));
            var source = node(from.eContainer());
            var target = node(to.eContainer());
            if (source==target || source.eContainer()!=target.eContainer() ||
                !(source.eContainer() instanceof PhysicalComponent) ||
                CapellaProjectHelper.isReusableComponentsDriven(source)!=CapellaProjectHelper.TriStateBoolean.False)
                throw new IllegalArgumentException("Requires distinct sibling nodes in a single-Part physical model");
            var link = CsFactory.eINSTANCE.createPhysicalLink();
            link.getLinkEnds().add(from); link.getLinkEnds().add(to);
            PhysicalLinkExt.attachToDefaultContainer(link);
            if (ModelInventory.architecture(link)!=ModelInventory.architecture(source))
                throw new IllegalStateException("Invalid physical link owner");
            result = link; break;
        }
        case "create_entity": case "create_operational_actor": {
            var entity = OaFactory.eINSTANCE.createEntity();
            entity.setActor(c.recipe().equals("create_operational_actor"));
            if (parent instanceof EntityPkg pkg) pkg.getOwnedEntities().add(entity);
            else if (parent instanceof Entity owner && !owner.isActor()) owner.getOwnedEntities().add(entity);
            else throw new IllegalArgumentException("Select an entity package or non-actor entity");
            result = entity; break;
        }
        case "create_activity": {
            var child = OaFactory.eINSTANCE.createOperationalActivity();
            ((OperationalActivity)parent).getOwnedFunctions().add(child);
            result = child; break;
        }
        case "create_interaction": {
            var source = (OperationalActivity)refs.get(c.get("source"));
            var target = (OperationalActivity)refs.get(c.get("target"));
            if (source==target) throw new IllegalArgumentException("Distinct activities required");
            var exchange = FaFactory.eINSTANCE.createFunctionalExchange();
            SemanticRecipes.commonOwner(source,target).getOwnedFunctionalExchanges().add(exchange);
            exchange.setSource(source); exchange.setTarget(target);
            result = exchange; break;
        }
        case "create_configuration_item": {
            var child = EpbsFactory.eINSTANCE.createConfigurationItem();
            var kind = ConfigurationItemKind.get(c.get("kind"));
            if (kind==null || kind==ConfigurationItemKind.UNSET) throw new IllegalArgumentException("Explicit CI kind required");
            child.setKind(kind);
            if (parent instanceof ConfigurationItemPkg pkg) pkg.getOwnedConfigurationItems().add(child);
            else ((ConfigurationItem)parent).getOwnedConfigurationItems().add(child);
            result = child; break;
        }
        case "reassign_allocation": {
            var allocation = (ComponentFunctionalAllocation)refs.get(c.get("allocation"));
            var component = (Component)refs.get(c.get("component"));
            var function = allocation.getFunction();
            if (function==null || !refs.containsValue(function) || !compatible(component,function) ||
                !(allocation.eContainer() instanceof Component old) || allocation.getSourceElement()!=old ||
                !refs.containsValue(old) || old==component || function.getComponentFunctionalAllocations().size()!=1)
                throw new IllegalArgumentException("Select a uniquely allocated in-scope function and a different compatible component");
            component.getOwnedFunctionalAllocation().add(allocation);
            allocation.setSourceElement(component);
            return allocation;
        }
        default: throw new IllegalArgumentException("Unknown architecture recipe");
        }
        SemanticRecipes.initialize(result,c.get("name"));
        return result;
    }

    private static boolean matchesEndpoint(EObject endpoint, EObject function) {
        return endpoint != null && function != null && (endpoint == function || endpoint.eContainer() == function);
    }
}
