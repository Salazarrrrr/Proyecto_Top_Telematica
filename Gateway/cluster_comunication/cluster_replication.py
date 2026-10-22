"""Recuperación de réplicas y cambios en el factor de replicación."""

import grpc
import threading


class ReplicationOperations:
    def recuperar_replicas(self, archivos):
        recuperados = 0
        bloques_pendientes = []
        for archivo in archivos:
            for bloque in archivo["bloques"]:
                respuesta = self.leer_bloque(bloque["block_id"])
                if respuesta is None:
                    bloques_pendientes.append(bloque["block_id"])
                    continue
                exito, _ = self.escribir_bloque(
                    bloque["block_id"], archivo["file_id"], bloque["posicion"],
                    respuesta.contenido, bloque["checksum"],
                )
                if exito:
                    recuperados += 1
                    responsables = set(self.nodos_responsables(bloque["block_id"]))
                    for sobrante in set(self.direcciones) - responsables:
                        try:
                            self._invocar(sobrante, "eliminar_bloque", bloque["block_id"])
                        except grpc.RpcError:
                            self._limpiezas_pendientes.add((sobrante, bloque["block_id"]))
                else:
                    bloques_pendientes.append(bloque["block_id"])
        if bloques_pendientes:
            raise RuntimeError("Bloques pendientes de re-replicar: " + ", ".join(bloques_pendientes))
        return recuperados

    def cambiar_factor_replicacion(self, nuevo_factor, archivos):
        nuevo_factor = int(nuevo_factor)
        self._validar_quorums(nuevo_factor)
        anterior = self.factor_replicacion
        self.factor_replicacion = nuevo_factor
        guardados = 0
        eliminados = 0
        plan_eliminacion = []
        try:
            for archivo in archivos:
                for bloque in archivo["bloques"]:
                    respuesta = self.leer_bloque(bloque["block_id"])
                    if respuesta is None:
                        raise RuntimeError(f"No se pudo leer {bloque['block_id']}")
                    responsables = set(self.nodos_responsables(bloque["block_id"]))
                    confirmaciones = 0
                    for destino in responsables:
                        try:
                            ack = self._invocar(
                                destino, "escribir_bloque", bloque["block_id"],
                                archivo["file_id"], bloque["posicion"],
                                respuesta.contenido, bloque["checksum"],
                            )
                            confirmaciones += int(ack.exito)
                        except grpc.RpcError:
                            continue
                    quorum = self.quorum_escritura
                    if confirmaciones < quorum:
                        raise RuntimeError(f"No se alcanzó W al replicar {bloque['block_id']}")
                    guardados += confirmaciones
                    if nuevo_factor < anterior:
                        plan_eliminacion.append((bloque["block_id"], set(self.direcciones) - responsables))
        except Exception:
            self.factor_replicacion = anterior
            raise

        # El factor deseado ya es seguro una vez confirmadas las copias destino.
        # Si un nodo excedente está caído, conserva N y agenda la limpieza.
        for block_id, sobrantes in plan_eliminacion:
            for sobrante in sobrantes:
                try:
                    respuesta = self._invocar(sobrante, "eliminar_bloque", block_id)
                    if respuesta.exito:
                        eliminados += 1
                except grpc.RpcError as error:
                    self._limpiezas_pendientes.add((sobrante, block_id))
        try:
            self.guardar_factor_replicacion()
        except OSError as error:
            raise RuntimeError(f"No se pudo persistir el factor de replicación: {error}") from error
        return {
            "copias_confirmadas": guardados,
            "copias_eliminadas": eliminados,
            "limpieza_pendiente": len(self._limpiezas_pendientes),
        }

    def _reintentar_limpiezas_pendientes(self):
        for direccion, block_id in tuple(self._limpiezas_pendientes):
            if direccion not in self.clientes:
                self._limpiezas_pendientes.discard((direccion, block_id))
                continue
            try:
                self._invocar(direccion, "eliminar_bloque", block_id)
            except grpc.RpcError:
                continue
            self._limpiezas_pendientes.discard((direccion, block_id))

    def eliminar_bloque(self, block_id):
        errores = []
        for direccion in tuple(self.direcciones):
            try:
                self._invocar(direccion, "eliminar_bloque", block_id)
            except grpc.RpcError as error:
                errores.append(f"{direccion}: {error.code().name}")
        return not errores

    def cerrar(self):
        self._monitor_stop.set()
        if self._monitor_thread and self._monitor_thread is not threading.current_thread():
            self._monitor_thread.join(timeout=self.timeout + 1)
        for cliente in self.clientes.values():
            cliente.canal.close()
