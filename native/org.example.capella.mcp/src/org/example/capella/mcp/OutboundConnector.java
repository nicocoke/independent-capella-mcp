package org.example.capella.mcp;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;
import com.google.gson.*;
import org.eclipse.swt.widgets.Display;

/** No inbound port. Construct/start only through explicit operator action. */
public final class OutboundConnector implements AutoCloseable {
    private final NativeController controller;
    private final URI base;
    private final String token;
    private final Path connectionFile;
    private final Display display;
    private final HttpClient client;
    private ScheduledExecutorService worker;
    private JsonObject pendingReceipt;
    private volatile String status = "Stopped";
    public OutboundConnector(NativeController controller, URI base, String token, Display display) {
        if (!"https".equals(base.getScheme()) || base.getHost() == null || base.getUserInfo() != null ||
            base.getQuery() != null || base.getFragment() != null ||
            !(base.getPath().isEmpty() || base.getPath().equals("/")) || token.length() < 32)
            throw new IllegalArgumentException("Explicit HTTPS relay origin and credential required");
        this.controller = controller; this.base = base; this.token = token; this.display = display;
        connectionFile = null;
        client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10))
            .followRedirects(HttpClient.Redirect.NEVER).build();
    }
    private OutboundConnector(NativeController controller, Path file, Display display) throws Exception {
        LocalConnection.read(file);
        this.controller = controller; this.base = null; this.token = null; this.display = display;
        connectionFile = file.toAbsolutePath().normalize();
        client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
            .proxy(new java.net.ProxySelector() {
                @Override public java.util.List<java.net.Proxy> select(URI uri) { return java.util.List.of(java.net.Proxy.NO_PROXY); }
                @Override public void connectFailed(URI uri, java.net.SocketAddress address, java.io.IOException failure) { }
            }).followRedirects(HttpClient.Redirect.NEVER).build();
    }
    public static OutboundConnector local(NativeController controller, Path file, Display display) throws Exception {
        return new OutboundConnector(controller, file, display);
    }
    public synchronized void start() {
        if (worker != null) throw new IllegalStateException("Already started");
        worker = Executors.newSingleThreadScheduledExecutor(r -> { var thread = new Thread(r, "Capella MCP explicit connector"); thread.setDaemon(true); return thread; });
        worker.scheduleWithFixedDelay(this::tick, 0, 3, TimeUnit.SECONDS);
    }
    private <T> T ui(Supplier<T> call) {
        AtomicReference<T> value = new AtomicReference<>();
        AtomicReference<RuntimeException> failure = new AtomicReference<>();
        display.syncExec(() -> { try { value.set(call.get()); } catch (RuntimeException e) { failure.set(e); } });
        if (failure.get() != null) throw failure.get();
        return value.get();
    }
    private JsonObject post(URI origin, String credential, String route, JsonObject body) throws Exception {
        var request = HttpRequest.newBuilder(origin.resolve(route)).timeout(Duration.ofSeconds(30))
            .header("Authorization", "Bearer " + credential).header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body.toString(), StandardCharsets.UTF_8)).build();
        var response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
        try (var input = response.body()) {
            byte[] bytes = input.readNBytes(524289);
            if (response.statusCode() != 200 || bytes.length > 524288) throw new IllegalStateException("Relay response rejected");
            return JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8)).getAsJsonObject();
        }
    }
    private void tick() {
        if (Thread.currentThread().isInterrupted() || display.isDisposed()) return;
        try {
            LocalConnection local = connectionFile == null ? null : LocalConnection.read(connectionFile);
            URI origin = local == null ? base : local.origin();
            String credential = local == null ? token : local.token();
            if (pendingReceipt != null) {
                post(origin, credential, "/connector/result", pendingReceipt);
                pendingReceipt = null;
            }
            post(origin, credential, "/connector/snapshot", ui(controller::snapshot));
            JsonObject claimed = post(origin, credential, "/connector/claim", new JsonObject());
            if (!claimed.get("job").isJsonNull()) {
                pendingReceipt = ui(() -> controller.execute(claimed.getAsJsonObject("job")));
                post(origin, credential, "/connector/result", pendingReceipt);
                pendingReceipt = null;
            }
            status = "Connected; last poll succeeded";
        } catch (Exception error) { status = "Connection or execution needs attention: " + error.getClass().getSimpleName(); }
    }
    public String status() { return status; }
    @Override public synchronized void close() {
        if (worker != null) worker.shutdownNow();
        controller.close();
        status = "Stopped";
    }
}
