package org.example.capella.mcp;

import java.io.StringReader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;

public record LocalConnection(URI origin, String token) {
    public LocalConnection {
        if (!"http".equals(origin.getScheme()) || !"127.0.0.1".equals(origin.getHost()) ||
            origin.getPort() < 1 || origin.getPort() > 65535 || origin.getUserInfo() != null ||
            origin.getQuery() != null || origin.getFragment() != null ||
            !(origin.getPath().isEmpty() || origin.getPath().equals("/")) ||
            token == null || !token.matches("[A-Za-z0-9_-]{43,128}"))
            throw new IllegalArgumentException("Only an authenticated literal IPv4 loopback connection is allowed");
    }

    public static LocalConnection read(Path path) throws Exception {
        byte[] bytes;
        try (var stream = Files.newInputStream(path)) { bytes = stream.readNBytes(65537); }
        if (bytes.length > 65536) throw new IllegalArgumentException("Connection file too large");
        Map<String, String> values = new HashMap<>();
        try (var reader = new JsonReader(new StringReader(new String(bytes, StandardCharsets.UTF_8)))) {
            reader.setLenient(false);
            reader.beginObject();
            while (reader.hasNext()) {
                String name = reader.nextName();
                if (values.containsKey(name) || reader.peek() != JsonToken.STRING)
                    throw new IllegalArgumentException("Invalid connection file fields");
                values.put(name, reader.nextString());
            }
            reader.endObject();
            if (reader.peek() != JsonToken.END_DOCUMENT) throw new IllegalArgumentException("Trailing connection file data");
        }
        if (!values.keySet().equals(java.util.Set.of("format", "origin", "token")) ||
            !"capella-local-bridge/1".equals(values.get("format")))
            throw new IllegalArgumentException("Unsupported local connection file");
        return new LocalConnection(URI.create(values.get("origin")), values.get("token"));
    }
}
