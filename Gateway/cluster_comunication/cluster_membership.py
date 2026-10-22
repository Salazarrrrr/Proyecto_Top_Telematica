"""Alta, salida y rebalanceo de nodos."""

import grpc

from Gateway.node_client import NodeClient


class MembershipOperations:
    def agregar_nodo(self, direccion):
        direccion = direccion.strip()
        if not direccion:
            raise ValueError("La dirección del nodo no puede estar vacía")
        with self._lock:
            if direccion not in self.clientes:
                cliente = NodeClient(direccion)
                try:
                    respuesta = cliente.heartbeat("gateway", timeout=self.timeout)
                    if not respuesta.exito:
                        raise RuntimeError(f"El nodo {direccion} no aceptó heartbeat")
                except grpc.RpcError as error:
                    cliente.canal.close()
                    raise RuntimeError(f"No se pudo contactar el nodo {direccion}: {error.code().name}") from error
                self.direcciones.append(direccion)
                self.clientes[direccion] = cliente
                if self._miembros_activos is not None:
                    self._miembros_activos.append(direccion)

    def retirar_nodo(self, direccion):
        with self._lock:
            if direccion not in self.clientes:
                return False
            self.direcciones.remove(direccion)
            cliente = self.clientes.pop(direccion)
            if self._miembros_activos is not None and direccion in self._miembros_activos:
                self._miembros_activos.remove(direccion)
            cliente.canal.close()
            return True

    def salida_controlada(self, direccion, archivos):
        # Recupera primero los bloques mientras todavía está vigente la
        # membresía anterior y puede alcanzarse el quórum R configurado.
        contenido_bloques = []
        for archivo in archivos:
            for bloque in archivo["bloques"]:
                respuesta = self.leer_bloque(bloque["block_id"])
                if respuesta is None:
                    raise RuntimeError(f"No se pudo leer {bloque['block_id']} antes de retirar el nodo")
                contenido_bloques.append((archivo, bloque, respuesta.contenido))

        with self._lock:
            if direccion not in self.clientes:
                raise ValueError("Nodo no registrado")
            if len(self.direcciones) <= 1:
                raise ValueError("No se puede retirar el último nodo")
            direcciones_originales = list(self.direcciones)
            activos_originales = (
                list(self._miembros_activos) if self._miembros_activos is not None else None
            )
            cliente = self.clientes[direccion]
            self.direcciones.remove(direccion)
            if self._miembros_activos is not None:
                self._miembros_activos = [n for n in self._miembros_activos if n != direccion]
        try:
            for archivo, bloque, contenido in contenido_bloques:
                exito, mensaje = self.escribir_bloque(
                    bloque["block_id"], archivo["file_id"], bloque["posicion"],
                    contenido, bloque["checksum"],
                )
                if not exito:
                    raise RuntimeError(f"No se pudo migrar {bloque['block_id']}: {mensaje}")
        except Exception:
            with self._lock:
                self.direcciones = direcciones_originales
                self._miembros_activos = activos_originales
            raise
        for _, bloque, _ in contenido_bloques:
            try:
                self._invocar(direccion, "eliminar_bloque", bloque["block_id"])
            except grpc.RpcError:
                # El nodo sale de la membresía aunque esté caído; al volver
                # necesitará sincronizar su almacenamiento antes de reingresar.
                pass
        with self._lock:
            self.clientes.pop(direccion, None)
            self._ultimo_heartbeat.pop(direccion, None)
            self._capacidades.pop(direccion, None)
            self._node_ids.pop(direccion, None)
        cliente.canal.close()
        return len(contenido_bloques)

    def agregar_nodo_y_rebalancear(self, direccion, archivos):
        # Leer con la membresía anterior: el nodo nuevo todavía no tiene copias
        # y no debe consumir el quórum de lectura durante el rebalanceo.
        contenido_bloques = []
        for archivo in archivos:
            for bloque in archivo["bloques"]:
                respuesta = self.leer_bloque(bloque["block_id"])
                if respuesta is None:
                    raise RuntimeError(f"No se pudo recuperar {bloque['block_id']} antes del rebalanceo")
                contenido_bloques.append((archivo, bloque, respuesta.contenido))

        era_miembro = direccion in self.clientes
        self.agregar_nodo(direccion)
        self.difundir_membresia()
        guardados = 0
        plan_limpieza = []
        try:
            for archivo, bloque, contenido in contenido_bloques:
                responsables = self.nodos_responsables(bloque["block_id"])
                exito, confirmaciones, mensaje = self._escribir_en_destinos(
                    responsables,
                    bloque["block_id"],
                    archivo["file_id"],
                    bloque["posicion"],
                    contenido,
                    bloque["checksum"],
                )
                if not exito:
                    raise RuntimeError(
                        f"No se alcanzó W al rebalancear {bloque['block_id']}: "
                        f"{confirmaciones}/{self.quorum_escritura}. {mensaje}"
                    )
                guardados += confirmaciones
                plan_limpieza.append((
                    bloque["block_id"],
                    set(self.direcciones) - set(responsables),
                ))
        except Exception:
            if not era_miembro:
                self.retirar_nodo(direccion)
            raise

        errores_limpieza = []
        for block_id, sobrantes in plan_limpieza:
            for sobrante in sobrantes:
                try:
                    respuesta = self._invocar(sobrante, "eliminar_bloque", block_id)
                    if not respuesta.exito:
                        errores_limpieza.append(f"{sobrante}/{block_id}: borrado no confirmado")
                except grpc.RpcError as error:
                    errores_limpieza.append(f"{sobrante}/{block_id}: {error.code().name}")
        if errores_limpieza:
            self._limpiezas_pendientes.update(
                (sobrante, block_id)
                for block_id, sobrantes in plan_limpieza
                for sobrante in sobrantes
                if any(error.startswith(f"{sobrante}/{block_id}:") for error in errores_limpieza)
            )
        return {
            "copias_confirmadas": guardados,
            "limpieza_pendiente": len(errores_limpieza),
        }
