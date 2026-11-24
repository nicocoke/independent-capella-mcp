package org.example.capella.mcp;

import org.polarsys.capella.core.data.fa.AbstractFunction;
import org.polarsys.capella.core.data.cs.Component;
import java.util.HashSet;
import java.util.Map;
import org.eclipse.emf.ecore.EObject;
import org.polarsys.capella.core.data.capellacore.CapellaElement;
import org.polarsys.capella.core.data.capellacore.NamedElement;
import org.polarsys.capella.core.data.la.LaFactory;
import org.polarsys.capella.core.data.la.LogicalComponent;
import org.polarsys.capella.core.data.la.LogicalFunction;
import org.polarsys.capella.core.data.fa.FaFactory;
import org.polarsys.capella.core.model.helpers.CapellaElementExt;

/** Native source prototype. Must only execute within the selected session transaction.
 * Creation services supply Capella initialization, including component Parts.
 * Compiled against Capella 7.0.1; native behavior requires an isolated runtime trial.
 */
final class SemanticRecipes {
    private SemanticRecipes() {}

    private static <T> T resolve(Map<String, EObject> bindings, String alias, Class<T> type) {
        EObject value = bindings.get(alias);
        if (!type.isInstance(value)) throw new IllegalArgumentException("Wrong or missing reference: " + alias);
        return type.cast(value);
    }

    static void initialize(CapellaElement element, String name) {
        CapellaElementExt.creationService(element);
        // Native creation may assign a default name. Apply the requested name afterwards.
        if (name != null && element instanceof NamedElement named) named.setName(name);
    }

    static EObject execute(NativeCommand command, Map<String, EObject> bindings) {
        switch (command.recipe()) {
        case "logical_component_with_part": {
            var parent = resolve(bindings, command.get("parent"), LogicalComponent.class);
            var child = LaFactory.eINSTANCE.createLogicalComponent();
            parent.getOwnedLogicalComponents().add(child);
            initialize(child, command.get("name"));
            return child;
        }
        case "logical_function": {
            var parent = resolve(bindings, command.get("parent"), LogicalFunction.class);
            var child = LaFactory.eINSTANCE.createLogicalFunction();
            parent.getOwnedFunctions().add(child);
            initialize(child, command.get("name"));
            return child;
        }
        case "component_function_allocation": {
            var component = resolve(bindings, command.get("component"), Component.class);
            var function = resolve(bindings, command.get("function"), AbstractFunction.class);
            if (!ArchitectureRecipes.compatible(component,function) || !function.getComponentFunctionalAllocations().isEmpty())
                throw new IllegalArgumentException("Allocation already exists");
            var allocation = FaFactory.eINSTANCE.createComponentFunctionalAllocation();
            component.getOwnedFunctionalAllocation().add(allocation);
            allocation.setSourceElement(component);
            allocation.setTargetElement(function);
            initialize(allocation, null);
            return allocation;
        }
        case "functional_exchange_with_ports": {
            var source = resolve(bindings, command.get("source"), AbstractFunction.class);
            var target = resolve(bindings, command.get("target"), AbstractFunction.class);
            if (source == target || source.eClass()!=target.eClass() || !(source instanceof LogicalFunction || source instanceof org.polarsys.capella.core.data.ctx.SystemFunction || source instanceof org.polarsys.capella.core.data.pa.PhysicalFunction)) throw new IllegalArgumentException("Self exchange outside initial scope");
            var owner = commonOwner(source, target);
            var output = FaFactory.eINSTANCE.createFunctionOutputPort();
            source.getOutputs().add(output);
            initialize(output, command.get("name") + " out");
            var input = FaFactory.eINSTANCE.createFunctionInputPort();
            target.getInputs().add(input);
            initialize(input, command.get("name") + " in");
            var exchange = FaFactory.eINSTANCE.createFunctionalExchange();
            owner.getOwnedFunctionalExchanges().add(exchange);
            exchange.setSource(output);
            exchange.setTarget(input);
            initialize(exchange, command.get("name"));
            return exchange;
        }
        default: return ArchitectureRecipes.execute(command,bindings);
        }
    }

    static AbstractFunction commonOwner(AbstractFunction source, AbstractFunction target) {
        var ancestors = new HashSet<EObject>();
        for (EObject item = source.eContainer(); item != null; item = item.eContainer()) ancestors.add(item);
        for (EObject item = target.eContainer(); item != null; item = item.eContainer())
            if (item instanceof AbstractFunction function && ancestors.contains(item)) return function;
        throw new IllegalArgumentException("No common logical function owner");
    }
}
