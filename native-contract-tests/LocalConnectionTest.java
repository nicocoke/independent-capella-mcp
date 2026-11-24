package org.example.capella.mcp;

import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LocalConnectionTest {
    private static int checks;
    private static final String TOKEN = "a".repeat(43);

    private static void rejected(String origin, String token) {
        try {
            new LocalConnection(URI.create(origin), token);
            throw new AssertionError("Unsafe local origin or credential accepted");
        } catch (IllegalArgumentException expected) { checks++; }
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 1) throw new IllegalArgumentException("Explicit disposable test folder required");
        Path folder = Path.of(arguments[0]).toAbsolutePath().normalize();
        Files.createDirectory(folder);
        Path profile = folder.resolve("connection.json");
        new LocalConnection(URI.create("http://127.0.0.1:4321"), TOKEN); checks++;
        for (String origin : new String[] { "https://127.0.0.1:4321", "http://localhost:4321",
                "http://192.168.1.1:4321", "http://0.0.0.0:4321", "http://[::1]:4321",
                "http://127.0.0.1", "http://127.0.0.1:0", "http://127.0.0.1:65536",
                "http://127.0.0.1:4321/connector", "http://user@127.0.0.1:4321",
                "http://127.0.0.1:4321?query", "http://127.0.0.1:4321#fragment",
                "http://127.0.0.1.example.com:4321" }) rejected(origin, TOKEN);
        for (String token : new String[] { "short", "a".repeat(129), "x".repeat(42) + "\n" })
            rejected("http://127.0.0.1:4321", token);
        String valid = "{\"format\":\"capella-local-bridge/1\",\"origin\":\"http://127.0.0.1:4321\",\"token\":\"" + TOKEN + "\"}";
        Files.writeString(profile, valid);
        if (!LocalConnection.read(profile).token().equals(TOKEN)) throw new AssertionError("Valid file rejected");
        checks++;
        for (String invalid : new String[] { valid + "{}", valid.replace("\"format\":", "\"format\":null,\"format\":"),
                valid.replace("capella-local-bridge/1", "other"), valid.replace("\"token\":\"" + TOKEN + "\"", "\"token\":123"),
                valid.replace("\"origin\":", "\"extra\":\"field\",\"origin\":"), " ".repeat(65537) }) {
            Files.writeString(profile, invalid);
            boolean denied = false;
            try { LocalConnection.read(profile); } catch (Exception expected) { denied = true; }
            if (!denied) throw new AssertionError("Invalid connection file accepted");
            checks++;
        }
        Files.delete(profile);
        Files.delete(folder);
        System.out.println(checks + " local connector boundary checks passed; no Capella loaded.");
    }
}
