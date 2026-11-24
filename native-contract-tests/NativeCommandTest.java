package org.example.capella.mcp;
import java.util.HashMap;
import java.util.Map;

/** Pure Java contract checks. No Eclipse/Capella classes, sockets or files used. */
public final class NativeCommandTest {
    private static int checks;
    private static void check(boolean value) {
        checks++;
        if (!value) throw new AssertionError("Check " + checks + " failed");
    }
    private static void reject(Runnable action) {
        try { action.run(); } catch (IllegalArgumentException | NullPointerException expected) { checks++; return; }
        throw new AssertionError("Invalid command accepted");
    }
    public static void main(String[] args) {
        var fields = new HashMap<>(Map.of("id", "component-A", "name", "Controller", "parent", "logical-system"));
        var command = new NativeCommand("logical_component_with_part", fields);
        check(command.get("name").equals("Controller"));
        fields.put("name", "Changed after validation");
        check(command.get("name").equals("Controller"));
        try { command.arguments().put("name", "mutation"); throw new AssertionError(); }
        catch (UnsupportedOperationException expected) { checks++; }
        reject(() -> new NativeCommand("execute_shell", fields));
        reject(() -> new NativeCommand("logical_function", Map.of("id", "f", "parent", "root-function")));
        reject(() -> new NativeCommand("logical_function", Map.of("id", "f", "name", "F", "parent", "root-function", "save", "true")));
        reject(() -> new NativeCommand("logical_function", Map.of("id", "../unsafe", "name", "F", "parent", "root-function")));
        reject(() -> new NativeCommand("logical_function", Map.of("id", "f", "name", " ", "parent", "root-function")));
        reject(() -> new NativeCommand("logical_function", Map.of("id", "f", "name", "x".repeat(161), "parent", "root-function")));
        reject(() -> new NativeCommand("logical_function", Map.of("id", "x".repeat(65), "name", "F", "parent", "root-function")));
        reject(() -> new NativeCommand("sirius_representation", Map.of("id", "d", "name", "Diagram", "kind", "UNSUPPORTED", "target", "logical-system")));
        reject(() -> new NativeCommand(null, fields));
        check(new NativeCommand("sirius_representation", Map.of("id", "d", "name", "Diagram", "kind", "LAB", "target", "logical-system")).get("kind").equals("LAB"));
        for (String kind : new String[] { "LFBD", "LCBD", "SFBD", "PFBD", "OABD" }) {
            check(new NativeCommand("sirius_representation",
                Map.of("id", "d", "name", "Breakdown", "kind", kind, "target", "root")).get("kind").equals(kind));
        }
        check(new NativeCommand("component_function_allocation", Map.of("id", "a", "component", "c", "function", "f")).get("function").equals("f"));
        check(new NativeCommand("functional_exchange_with_ports", Map.of("id", "e", "name", "Signal", "source", "f1", "target", "f2")).get("target").equals("f2"));
        check(new NativeCommand("sirius_existing_element_view", Map.of("id", "v", "diagram", "d", "element", "c")).get("element").equals("c"));
        System.out.println(checks + " native command contract checks passed; no Capella runtime loaded.");
    }
}
