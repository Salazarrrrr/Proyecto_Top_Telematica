"""Configuración, quórums, heartbeats y acceso a bloques."""

import hashlib
import json
import os
import threading
from pathlib import Path

import grpc

from Gateway.node_client import NodeClient
from Gateway.java_cluster_client import JavaClusterClient


class ClusterCore:
    def __init__(self, nodos=None, factor_replicacion=None, quorum_lectura=None,
                 quorum_escritura=None, timeout=1.0):
        nodos = nodos if nodos is not None else os.getenv("DFS_NODES", "localhost:50051")
        self.direcciones = list(dict.fromkeys(
            direccion.strip() for direccion in nodos.split(",") if direccion.strip()
        ))
        self.configuracion_path = Path(os.getenv(
            "DFS_CLUSTER_CONFIG", "metadata/cluster.json"
        ))
        factor_guardado = self._leer_factor_guardado()
        self.factor_replicacion = max(1, int(
            factor_replicacion if factor_replicacion is not None
            else factor_guardado if factor_guardado is not None
            else os.getenv("DFS_REPLICATION_FACTOR", "3")
        ))
        self.quorum_lectura = max(1, int(
            quorum_lectura if quorum_lectura is not None
            else os.getenv("DFS_READ_QUORUM", "2")
        ))
        self.quorum_escritura = max(1, int(
            quorum_escritura if quorum_escritura is not None
            else os.getenv("DFS_WRITE_QUORUM", "2")
        ))
        self._validar_quorums(self.factor_replicacion)
        self.timeout = timeout
        self.clientes = {direccion: NodeClient(direccion) for direccion in self.direcciones}
        self.java_cluster = JavaClusterClient(timeout=timeout)
        self._lock = threading.RLock()
        self._ultimo_heartbeat = {}
        self._capacidades = {}
        self._node_ids = {}
        self._miembros_activos = None
        self._estados_previos = None
        self._limpiezas_pendientes = set()
        self.proveedor_archivos = None
        self._monitor_stop = threading.Event()
        self._monitor_thread = None

    def _leer_factor_guardado(self):
        try:
            datos = json.loads(self.configuracion_path.read_text(encoding="utf-8"))
            factor = datos.get("factor_replicacion")
            return int(factor) if factor is not None else None
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def guardar_factor_replicacion(self):
        self.configuracion_path.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.configuracion_path.with_suffix(".tmp")
        contenido = json.dumps(
            {"factor_replicacion": self.factor_replicacion},
            ensure_ascii=False,
            indent=2,
        )
        temporal.write_text(contenido + "\n", encoding="utf-8")
        os.replace(temporal, self.configuracion_path)

    def _validar_quorums(self, replicas):
        replicas = int(replicas)
        if replicas < 1:
            raise ValueError("El factor de replicación debe ser mayor que cero")
        if self.quorum_lectura > replicas or self.quorum_escritura > replicas:
            raise ValueError("R y W no pueden superar el factor de replicación")
        if self.quorum_escritura <= replicas // 2:
            raise ValueError("W debe ser mayoría para evitar escrituras divergentes")
        if self.quorum_lectura + self.quorum_escritura <= replicas:
            raise ValueError("R + W debe ser mayor que N para garantizar intersección")

    @staticmethod
    def _hash(valor):
        return int(hashlib.sha256(valor.encode("utf-8")).hexdigest(), 16)

    def _ordenar_nodos(self, block_id):
        posicion_bloque = self._hash(block_id)
        return sorted(
            self.direcciones,
            key=lambda direccion: (self._hash(direccion) - posicion_bloque) % (1 << 256),
        )

    def nodos_responsables(self, block_id):
        nodos = self._miembros_activos
        if nodos is None:
            nodos = self.direcciones
        asignados_java = self.java_cluster.responsables(
            block_id, nodos, self.factor_replicacion
        )
        if asignados_java is not None:
            return asignados_java
        posicion = self._hash(block_id)
        ordenados = sorted(
            nodos,
            key=lambda direccion: (self._hash(direccion) - posicion) % (1 << 256),
        )
        return ordenados[:min(self.factor_replicacion, len(ordenados))]

    def _invocar(self, direccion, operacion, *args):
        return getattr(self.clientes[direccion], operacion)(*args, timeout=self.timeout)

    def escribir_bloque(self, block_id, file_id, posicion, contenido, checksum):
        exitos = 0
        errores = []
        destinos = self.nodos_responsables(block_id)
        if not destinos:
            return False, "No hay nodos registrados en el clúster"
        for direccion in destinos:
            try:
                respuesta = self._invocar(
                    direccion, "escribir_bloque", block_id, file_id, posicion, contenido, checksum
                )
                if respuesta.exito:
                    exitos += 1
                else:
                    errores.append(f"{direccion}: {respuesta.mensaje}")
            except grpc.RpcError as error:
                errores.append(f"{direccion}: {error.code().name}")

        quorum = self.quorum_escritura
        if exitos < quorum:
            return False, (
                f"Quórum de escritura no alcanzado: {exitos}/{quorum} réplica(s). "
                + "; ".join(errores)
            ).strip()
        return True, f"Bloque confirmado en {exitos} nodo(s); quórum W={quorum} alcanzado"

    def leer_bloque(self, block_id):
        respuestas = []
        errores = []
        destinos = list(self._miembros_activos if self._miembros_activos is not None else self.direcciones)
        if not destinos:
            return None
        for direccion in self.nodos_responsables(block_id):
            try:
                respuesta = self._invocar(direccion, "leer_bloque", block_id)
                if respuesta.exito:
                    checksum = hashlib.sha256(respuesta.contenido).hexdigest()
                    if checksum == respuesta.checksum:
                        respuestas.append((direccion, respuesta))
                    else:
                        errores.append(f"{direccion}: checksum inválido")
                else:
                    errores.append(f"{direccion}: {respuesta.mensaje}")
            except grpc.RpcError as error:
                errores.append(f"{direccion}: {error.code().name}")

        quorum = self.quorum_lectura
        if len(respuestas) < quorum:
            return None

        # Sin versionado, se selecciona la respuesta íntegra más frecuente y se
        # repara cualquier réplica ausente o divergente con esa copia.
        conteos = {}
        for _, respuesta in respuestas:
            firma = (respuesta.checksum, respuesta.contenido)
            conteos[firma] = conteos.get(firma, 0) + 1
        firma_ganadora = max(conteos, key=conteos.get)
        if conteos[firma_ganadora] < quorum:
            return None
        _, respuesta_valida = next(
            (par for par in respuestas if (par[1].checksum, par[1].contenido) == firma_ganadora)
        )
        for direccion in destinos:
            if any(d == direccion and (r.checksum, r.contenido) == firma_ganadora
                   for d, r in respuestas):
                continue
            try:
                self._invocar(
                    direccion, "escribir_bloque", block_id, respuesta_valida.file_id,
                    respuesta_valida.posicion, respuesta_valida.contenido,
                    respuesta_valida.checksum,
                )
            except grpc.RpcError:
                pass
        return respuesta_valida
