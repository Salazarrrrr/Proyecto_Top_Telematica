package dfsha;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** Anillo de hashing consistente para asignar bloques a nodos. */
public class ConsistentHashRing {
    private final TreeMap<BigInteger, String> nodos = new TreeMap<>();
    private final int factorReplicacion;

    public ConsistentHashRing(List<String> nodos, int factorReplicacion) {
        if (nodos == null || nodos.isEmpty()) {
            throw new IllegalArgumentException("Debe existir al menos un nodo");
        }
        this.factorReplicacion = Math.max(1, factorReplicacion);
        for (String nodo : nodos) {
            this.nodos.put(Hashing.sha256(nodo), nodo);
        }
    }

    public List<String> nodosResponsables(String idBloque) {
        int cantidad = Math.min(factorReplicacion, nodos.size());
        Map<BigInteger, String> posteriores = nodos.tailMap(Hashing.sha256(idBloque), true);
        List<String> responsables = new ArrayList<>();
        agregarNodos(posteriores, responsables, cantidad);
        agregarNodos(nodos, responsables, cantidad);
        return responsables;
    }

    private void agregarNodos(
            Map<BigInteger, String> candidatos, List<String> resultado, int cantidad) {
        for (String nodo : candidatos.values()) {
            if (!resultado.contains(nodo)) {
                resultado.add(nodo);
            }
            if (resultado.size() == cantidad) {
                return;
            }
        }
    }
}
