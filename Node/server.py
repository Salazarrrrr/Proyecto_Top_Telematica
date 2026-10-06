import grpc
import hmac
import os
import shutil
import time
from concurrent import futures
from threading import RLock

from Proto import bloque_servicio_pb2
from Proto import bloque_servicio_pb2_grpc

from Node.models import Bloque
from Node.storage import Almacenamiento


class AutenticacionInterna(grpc.ServerInterceptor):
    def __init__(self, token):
        self.token = token

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None or not self.token:
            return handler
        metadata = dict(handler_call_details.invocation_metadata or ())
        recibido = metadata.get("authorization", "")
        if recibido.startswith("Bearer ") and hmac.compare_digest(
            recibido[7:], self.token
        ):
            return handler

        def rechazar(_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Token interno inválido")

        return grpc.unary_unary_rpc_method_handler(
            rechazar,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


class BloqueServicio(bloque_servicio_pb2_grpc.BloqueServicioServicer):

    def __init__(self, directorio="almacenamiento_bloques", node_id="localhost:50051"):
        self.almacenamiento = Almacenamiento(directorio)
        self.directorio = directorio
        self.node_id = node_id
        self.membresia = []
        self._lock_membresia = RLock()

    def Heartbeat(self, request, context):
        try:
            disponible = shutil.disk_usage(self.directorio).free
            return bloque_servicio_pb2.HeartbeatResponse(
                exito=True,
                node_id=self.node_id,
                estado="activo",
                last_heartbeat_unix_ms=int(time.time() * 1000),
                capacidad_disponible_bytes=disponible,
            )
        except OSError as error:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(error))
            return bloque_servicio_pb2.HeartbeatResponse(
                exito=False, node_id=self.node_id, estado="error"
            )

    def ActualizarMembresia(self, request, context):
        with self._lock_membresia:
            self.membresia = list(request.nodos)
        return bloque_servicio_pb2.ActualizarMembresiaResponse(
            exito=True, miembros=len(self.membresia)
        )

    def EscribirBloque(self, request, context):
        bloque = Bloque(
            block_id=request.block_id,
            file_id=request.file_id,
            posicion=request.posicion,
            contenido=request.contenido,
            checksum=request.checksum
        )

        try:
            checksum = self.almacenamiento.guardar_bloque(bloque)

            return bloque_servicio_pb2.EscribirBloqueResponse(
                exito=True,
                mensaje="Bloque guardado correctamente",
                block_id=bloque.block_id
            )

        except ValueError as error:
            return bloque_servicio_pb2.EscribirBloqueResponse(
                exito=False,
                mensaje=str(error),
                block_id=bloque.block_id
            )

    def LeerBloque(self, request, context):
        resultado = self.almacenamiento.leer_bloque_completo(request.block_id)

        if resultado is None:
            return bloque_servicio_pb2.LeerBloqueResponse(
                exito=False,
                mensaje="Bloque no encontrado",
                block_id=request.block_id
            )

        contenido, checksum, file_id, posicion = resultado

        return bloque_servicio_pb2.LeerBloqueResponse(
            exito=True,
            mensaje="Bloque leído correctamente",
            block_id=request.block_id,
            file_id=file_id,
            posicion=posicion,
            contenido=contenido,
            checksum=checksum
        )

    def EliminarBloque(self, request, context):
        eliminado = self.almacenamiento.eliminar_bloque(request.block_id)

        if not eliminado:
            return bloque_servicio_pb2.EliminarBloqueResponse(
                exito=False,
                mensaje="Bloque no encontrado"
            )

        return bloque_servicio_pb2.EliminarBloqueResponse(
            exito=True,
            mensaje="Bloque eliminado correctamente"
        )


def iniciar_servidor(puerto=50051, directorio="almacenamiento_bloques", node_id=None):
    bind = os.getenv("DFS_NODE_BIND", "127.0.0.1")
    token = os.getenv("DFS_NODE_TOKEN")
    cert_path = os.getenv("DFS_NODE_TLS_CERT")
    key_path = os.getenv("DFS_NODE_TLS_KEY")
    if bool(cert_path) != bool(key_path):
        raise RuntimeError("DFS_NODE_TLS_CERT y DFS_NODE_TLS_KEY deben configurarse juntos")
    remoto = bind not in {"localhost", "127.0.0.1", "::1"}
    if not os.getenv("DFS_STORAGE_KEY"):
        raise RuntimeError("DFS_STORAGE_KEY es obligatorio para cifrar bloques en almacenamiento")
    if remoto and (not token or not cert_path or not key_path):
        raise RuntimeError(
            "La exposición remota requiere DFS_NODE_TOKEN y TLS"
        )
    servidor = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=(AutenticacionInterna(token),),
    )

    bloque_servicio_pb2_grpc.add_BloqueServicioServicer_to_server(
        BloqueServicio(directorio, node_id or f"localhost:{puerto}"),
        servidor
    )

    destino = f"[{bind}]:{puerto}" if ":" in bind else f"{bind}:{puerto}"
    if cert_path:
        client_ca_path = os.getenv("DFS_NODE_CLIENT_CA")
        credenciales = grpc.ssl_server_credentials(
            ((open(key_path, "rb").read(), open(cert_path, "rb").read()),),
            root_certificates=open(client_ca_path, "rb").read() if client_ca_path else None,
            require_client_auth=bool(client_ca_path),
        )
        puerto_abierto = servidor.add_secure_port(destino, credenciales)
    else:
        puerto_abierto = servidor.add_insecure_port(destino)
    if not puerto_abierto:
        raise RuntimeError(f"No se pudo abrir el listener gRPC en {destino}")
    servidor.start()

    print(f"Node ejecutándose en el puerto {puerto}")

    servidor.wait_for_termination()


if __name__ == "__main__":
    iniciar_servidor(
        puerto=int(os.getenv("DFS_NODE_PORT", "50051")),
        directorio=os.getenv("DFS_NODE_STORAGE", "almacenamiento_bloques"),
        node_id=os.getenv("DFS_NODE_ID"),
    )
