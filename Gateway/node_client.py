import grpc

from Proto import bloque_servicio_pb2
from Proto import bloque_servicio_pb2_grpc


class NodeClient:

    def __init__(self, direccion="localhost:50051"):
        self.canal = grpc.insecure_channel(direccion)
        self.cliente = bloque_servicio_pb2_grpc.BloqueServicioStub(self.canal)

    def escribir_bloque(self, block_id, file_id, posicion, contenido, checksum=""):
        return self.cliente.EscribirBloque(
            bloque_servicio_pb2.EscribirBloqueRequest(
                block_id=block_id,
                file_id=file_id,
                posicion=posicion,
                contenido=contenido,
                checksum=checksum
            )
        )

    def leer_bloque(self, block_id):
        return self.cliente.LeerBloque(
            bloque_servicio_pb2.LeerBloqueRequest(
                block_id=block_id
            )
        )

    def eliminar_bloque(self, block_id):
        return self.cliente.EliminarBloque(
            bloque_servicio_pb2.EliminarBloqueRequest(
                block_id=block_id
            )
        )