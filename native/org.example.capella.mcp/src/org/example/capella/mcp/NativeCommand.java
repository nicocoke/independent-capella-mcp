package org.example.capella.mcp;

import java.util.Map;
import java.util.Set;

/** Typed, bounded intermediate command. No arbitrary EMF feature editing. */
public record NativeCommand(String recipe, Map<String, String> arguments) {
    private static final Map<String, Set<String>> FIELDS = Map.ofEntries(
        Map.entry("involve_operational_entity", Set.of("id", "parent", "element")),
        Map.entry("involve_capability_path", Set.of("id", "parent", "element")),
        Map.entry("connect_components", Set.of("id", "name", "source", "target")),
        Map.entry("create_operational_capability", Set.of("id", "name", "parent")),
        Map.entry("create_system_capability", Set.of("id", "name", "parent")),
        Map.entry("create_logical_capability", Set.of("id", "name", "parent")),
        Map.entry("realize_capability", Set.of("id", "source", "target")),
        Map.entry("realize_function", Set.of("id", "source", "target")),
        Map.entry("realize_system_component", Set.of("id", "source", "target")),
        Map.entry("create_state", Set.of("id", "name", "parent")),
        Map.entry("create_mode", Set.of("id", "name", "parent")),
        Map.entry("create_transition", Set.of("id", "name", "source", "target")),
        Map.entry("add_chain_function", Set.of("id", "parent", "function")),
        Map.entry("add_chain_exchange", Set.of("id", "parent", "exchange", "source", "target")),
        Map.entry("logical_component_with_part", Set.of("id", "name", "parent")),
        Map.entry("logical_function", Set.of("id", "name", "parent")),
        Map.entry("component_function_allocation", Set.of("component", "function", "id")),
        Map.entry("functional_exchange_with_ports", Set.of("id", "name", "source", "target")),
        Map.entry("sirius_representation", Set.of("id", "kind", "name", "target")),
        Map.entry("sirius_existing_element_view", Set.of("diagram", "element", "id")),
        Map.entry("create_system_actor", Set.of("id", "name", "parent")),
        Map.entry("create_system_function", Set.of("id", "name", "parent")),
        Map.entry("create_node_component", Set.of("id", "name", "parent")),
        Map.entry("create_behavior_component", Set.of("id", "name", "parent")),
        Map.entry("create_physical_function", Set.of("id", "name", "parent")),
        Map.entry("create_physical_port", Set.of("id", "name", "parent")),
        Map.entry("connect_physical_ports", Set.of("id", "name", "source", "target")),
        Map.entry("deploy_behavior", Set.of("deployed", "host", "id")),
        Map.entry("create_entity", Set.of("id", "name", "parent")),
        Map.entry("create_operational_actor", Set.of("id", "name", "parent")),
        Map.entry("create_activity", Set.of("id", "name", "parent")),
        Map.entry("create_interaction", Set.of("id", "name", "source", "target")),
        Map.entry("create_configuration_item", Set.of("id", "kind", "name", "parent")),
        Map.entry("reassign_allocation", Set.of("allocation", "component", "id")));

    public NativeCommand {
        arguments = Map.copyOf(arguments);
        if (!FIELDS.containsKey(recipe) || !FIELDS.get(recipe).equals(arguments.keySet()))
            throw new IllegalArgumentException("Unsupported recipe or fields");
        for (var entry : arguments.entrySet()) {
            String value = entry.getValue();
            if (value.isBlank() || value.length() > 160)
                throw new IllegalArgumentException("Invalid argument length");
            if (!entry.getKey().equals("name") && !value.matches("[a-zA-Z][a-zA-Z0-9_-]{0,63}"))
                throw new IllegalArgumentException("Invalid alias");
        }
        if (recipe.equals("sirius_representation")) DiagramKind.valueOf(arguments.get("kind"));
    }
    public String get(String key) { return arguments.get(key); }
}
