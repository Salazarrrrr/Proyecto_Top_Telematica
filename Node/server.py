import grpc
from concurrent import futures

from Proto import bloque_servicio_pb2
from Proto import bloque_servicio_pb2_grpc

from Node.models import Bloque
from Node.storage import Almacenamiento


class BloqueServicio(bloque_servicio_pb2_grpc.BloqueServicioServicer):

    def __init__(self):
        self.almacenamiento = Almacenamiento("almacenamiento_bloques")

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
        resultado = self.almacenamiento.leer_bloque(request.block_id)

        if resultado is None:
            return bloque_servicio_pb2.LeerBloqueResponse(
                exito=False,
                mensaje="Bloque no encontrado",
                block_id=request.block_id
            )

        contenido, checksum = resultado

        return bloque_servicio_pb2.LeerBloqueResponse(
            exito=True,
            mensaje="Bloque leído correctamente",
            block_id=request.block_id,
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


def iniciar_servidor():
    servidor = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )

    bloque_servicio_pb2_grpc.add_BloqueServicioServicer_to_server(
        BloqueServicio(),
        servidor
    )

    servidor.add_insecure_port("[::]:50051")
    servidor.start()

    print("Node ejecutándose en el puerto 50051")

    servidor.wait_for_termination()


if __name__ == "__main__":
    iniciar_servidor()