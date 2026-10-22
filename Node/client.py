"""Cliente gRPC compartido para que Gateway y nodos llamen a servicios de bloque."""

import os

import grpc

from Proto import bloque_servicio_pb2
from Proto import bloque_servicio_pb2_grpc


def max_message_bytes():
    return int(os.getenv("DFS_GRPC_MAX_MESSAGE_BYTES", str(65 * 1024 * 1024)))


def peer_timeout_seconds():
    timeout = float(os.getenv("DFS_NODE_PEER_TIMEOUT", "10"))
    if timeout <= 0:
        raise ValueError("DFS_NODE_PEER_TIMEOUT debe ser mayor que cero")
    return timeout


def _leer_certificado(ruta):
    if not ruta:
        return None
    with open(ruta, "rb") as archivo:
        return archivo.read()


class NodeClient:
    def __init__(self, direccion="localhost:50051"):
        ruta_ca = os.getenv("DFS_NODE_TLS_CA")
        tls_requerido = os.getenv("DFS_NODE_TLS_REQUIRED", "0").lower() in {
            "1", "true", "yes"
        }
        certificado = os.getenv("DFS_NODE_CLIENT_CERT")
        clave = os.getenv("DFS_NODE_CLIENT_KEY")
        if bool(certificado) != bool(clave):
            raise ValueError(
                "DFS_NODE_CLIENT_CERT y DFS_NODE_CLIENT_KEY deben configurarse juntos"
            )
        if ruta_ca:
            credenciales = grpc.ssl_channel_credentials(
                root_certificates=_leer_certificado(ruta_ca),
                private_key=_leer_certificado(clave),
                certificate_chain=_leer_certificado(certificado),
            )
            nombre_tls = os.getenv("DFS_NODE_TLS_SERVER_NAME")
            opciones = []
            if nombre_tls:
                opciones.append(("grpc.ssl_target_name_override", nombre_tls))
            opciones.extend(_opciones_tamano_mensaje())
            self.canal = grpc.secure_channel(direccion, credenciales, options=opciones)
        elif tls_requerido:
            raise RuntimeError("DFS_NODE_TLS_CA es obligatorio porque se requiere TLS")
        else:
            self.canal = grpc.insecure_channel(
                direccion, options=_opciones_tamano_mensaje()
            )
        self.cliente = bloque_servicio_pb2_grpc.BloqueServicioStub(self.canal)
        token = os.getenv("DFS_NODE_TOKEN")
        self.metadata = (("authorization", "Bearer " + token),) if token else None

    def escribir_bloque(
        self, block_id, file_id, posicion, contenido, checksum="", timeout=None
    ):
        return self.cliente.EscribirBloque(
            bloque_servicio_pb2.EscribirBloqueRequest(
                block_id=block_id,
                file_id=file_id,
                posicion=posicion,
                contenido=contenido,
                checksum=checksum,
            ),
            timeout=timeout,
            metadata=self.metadata,
        )

    def replicar_bloque(
        self, block_id, file_id, posicion, contenido, checksum, destinos, timeout=None
    ):
        return self.cliente.ReplicarBloque(
            bloque_servicio_pb2.ReplicarBloqueRequest(
                block_id=block_id,
                file_id=file_id,
                posicion=posicion,
                contenido=contenido,
                checksum=checksum,
                destinos=destinos,
            ),
            timeout=timeout,
            metadata=self.metadata,
        )

    def leer_bloque(self, block_id, timeout=None):
        return self.cliente.LeerBloque(
            bloque_servicio_pb2.LeerBloqueRequest(block_id=block_id),
            timeout=timeout,
            metadata=self.metadata,
        )

    def eliminar_bloque(self, block_id, timeout=None):
        return self.cliente.EliminarBloque(
            bloque_servicio_pb2.EliminarBloqueRequest(block_id=block_id),
            timeout=timeout,
            metadata=self.metadata,
        )

    def heartbeat(self, node_id="", timeout=None):
        return self.cliente.Heartbeat(
            bloque_servicio_pb2.HeartbeatRequest(requester_id=node_id),
            timeout=timeout,
            metadata=self.metadata,
        )

    def actualizar_membresia(self, nodos, timeout=None):
        return self.cliente.ActualizarMembresia(
            bloque_servicio_pb2.ActualizarMembresiaRequest(nodos=nodos),
            timeout=timeout,
            metadata=self.metadata,
        )


def _opciones_tamano_mensaje():
    limite = max_message_bytes()
    return (
        ("grpc.max_send_message_length", limite),
        ("grpc.max_receive_message_length", limite),
    )
