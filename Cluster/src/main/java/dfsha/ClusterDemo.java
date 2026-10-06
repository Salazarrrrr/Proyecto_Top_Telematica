package dfsha;

import java.util.List;

/** Ejemplo breve de asignación de un bloque. */
public final class ClusterDemo {
    private ClusterDemo() {}

    public static void main(String[] args) {
        ConsistentHashRing anillo = new ConsistentHashRing(
                List.of("Node-1", "Node-2", "Node-3"), 3);
        System.out.println(anillo.nodosResponsables("bloque-0"));
    }
}
