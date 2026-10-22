package dfsha;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/** Servicio HTTP interno que asigna bloques usando el anillo Java. */
public final class ClusterService {
    private ClusterService() {}

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getenv().getOrDefault("DFS_CLUSTER_JAVA_PORT", "8081"));
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        server.createContext("/health", exchange -> responder(exchange, 200, "{\"exito\":true,\"servicio\":\"cluster-java\"}"));
        server.createContext("/responsables", ClusterService::responsables);
        server.setExecutor(null);
        server.start();
        System.out.println("Servicio de clúster Java en puerto " + port);
    }

    private static void responsables(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            responder(exchange, 405, "{\"error\":\"Método no permitido\"}");
            return;
        }
        Map<String, String> query = query(exchange.getRequestURI().getRawQuery());
        String bloque = query.get("bloque");
        String nodos = query.get("nodos");
        try {
            int replicas = Integer.parseInt(query.getOrDefault("replicas", "0"));
            List<String> miembros = Arrays.stream(nodos == null ? new String[0] : nodos.split(","))
                    .filter(n -> !n.isBlank()).collect(Collectors.toList());
            if (bloque == null || bloque.isBlank() || miembros.isEmpty() || replicas < 1) {
                throw new IllegalArgumentException("Parámetros bloque, nodos y replicas son obligatorios");
            }
            List<String> resultado = new ConsistentHashRing(miembros, replicas).nodosResponsables(bloque);
            String json = resultado.stream().map(ClusterService::json).collect(Collectors.joining(",", "{\"nodos\":[", "]}"));
            responder(exchange, 200, json);
        } catch (IllegalArgumentException error) {
            responder(exchange, 400, "{\"error\":" + json(error.getMessage()) + "}");
        }
    }

    private static Map<String, String> query(String raw) {
        Map<String, String> result = new LinkedHashMap<>();
        if (raw == null || raw.isBlank()) return result;
        for (String part : raw.split("&")) {
            String[] pair = part.split("=", 2);
            result.put(URLDecoder.decode(pair[0], StandardCharsets.UTF_8),
                    pair.length == 2 ? URLDecoder.decode(pair[1], StandardCharsets.UTF_8) : "");
        }
        return result;
    }

    private static String json(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static void responder(HttpExchange exchange, int status, String body) throws IOException {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, data.length);
        exchange.getResponseBody().write(data);
        exchange.close();
    }
}
