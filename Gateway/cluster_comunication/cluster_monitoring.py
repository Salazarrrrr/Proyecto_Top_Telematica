"""Heartbeats y difusión de la membresía del clúster."""

import threading
from datetime import datetime, timezone

import grpc


class ClusterMonitoring:
    def estado_nodos(self):
        estados = []
        for direccion in tuple(self.direcciones):
            try:
                respuesta = self._invocar(direccion, "heartbeat", "gateway")
                activo = respuesta.exito
                if activo:
                    instante = datetime.fromtimestamp(
                        respuesta.last_heartbeat_unix_ms / 1000, timezone.utc
                    ).isoformat()
                    self._ultimo_heartbeat[direccion] = instante
                    self._capacidades[direccion] = respuesta.capacidad_disponible_bytes
                    self._node_ids[direccion] = respuesta.node_id
            except grpc.RpcError:
                activo = False
            try:
                puerto = int(direccion.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                puerto = None
            estados.append({
                "nodeId": self._node_ids.get(direccion, direccion),
                "direccion": direccion,
                "puerto": puerto,
                "estado": "activo" if activo else "no_disponible",
                "hashPosition": f"{self._hash(direccion):064x}",
                "lastHeartbeat": self._ultimo_heartbeat.get(direccion),
                "capacidadDisponible": self._capacidades.get(direccion),
            })
        self._miembros_activos = [
            nodo["direccion"] for nodo in estados if nodo["estado"] == "activo"
        ]
        return estados

    def difundir_membresia(self, estados=None):
        estados = estados if estados is not None else self.estado_nodos()
        nodos = [
            {
                "node_id": nodo["nodeId"],
                "direccion": nodo["direccion"],
                "puerto": nodo["puerto"] or 0,
                "estado": nodo["estado"],
                "hash_position": nodo["hashPosition"],
                "last_heartbeat": nodo["lastHeartbeat"] or "",
                "capacidad_disponible_bytes": nodo["capacidadDisponible"] or 0,
            }
            for nodo in estados
        ]
        confirmaciones = 0
        for direccion in tuple(self.direcciones):
            try:
                respuesta = self._invocar(direccion, "actualizar_membresia", nodos)
                confirmaciones += int(respuesta.exito)
            except grpc.RpcError:
                continue
        return confirmaciones

    def iniciar_monitor(self, intervalo=5.0):
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        def monitorear():
            while not self._monitor_stop.is_set():
                estados = self.estado_nodos()
                self.difundir_membresia(estados)
                estados_actuales = {nodo["direccion"]: nodo["estado"] for nodo in estados}
                hubo_cambio = (
                    self._estados_previos is not None
                    and estados_actuales != self._estados_previos
                )
                primer_estado = self._estados_previos is None
                self._estados_previos = estados_actuales
                if (hubo_cambio or primer_estado) and self.proveedor_archivos:
                    try:
                        self.recuperar_replicas(self.proveedor_archivos())
                    except (RuntimeError, grpc.RpcError):
                        pass
                if self._limpiezas_pendientes:
                    self._reintentar_limpiezas_pendientes()
                self._monitor_stop.wait(intervalo)

        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=monitorear, name="dfsha-heartbeat", daemon=True
        )
        self._monitor_thread.start()
