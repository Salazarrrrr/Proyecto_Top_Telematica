"""Pruebas de propagación directa de bloques entre nodos."""

import hashlib
import os
import tempfile
import unittest
from concurrent import futures
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import grpc

from Node.client import NodeClient, max_message_bytes
from Node.server import AutenticacionInterna, BloqueServicio
from Proto import bloque_servicio_pb2
from Proto import bloque_servicio_pb2_grpc


class TestPeerReplication(unittest.TestCase):
    def test_rpc_autenticado_replica_entre_tres_nodos(self):
        token = "token-de-prueba"
        with tempfile.TemporaryDirectory() as directorio, patch.dict(
            os.environ,
            {
                "DFS_NODE_TLS_CA": "",
                "DFS_NODE_TLS_REQUIRED": "0",
                "DFS_NODE_TOKEN": token,
            },
        ):
            servicios = []
            servidores = []
            direcciones = []
            cliente_gateway = None
            try:
                for indice in range(3):
                    servicio = BloqueServicio(
                        os.path.join(directorio, f"nodo-{indice}"),
                        f"pendiente:{indice}",
                    )
                    servidor = grpc.server(
                        futures.ThreadPoolExecutor(max_workers=4),
                        interceptors=(AutenticacionInterna(token),),
                        options=(
                            ("grpc.max_send_message_length", max_message_bytes()),
                            ("grpc.max_receive_message_length", max_message_bytes()),
                        ),
                    )
                    bloque_servicio_pb2_grpc.add_BloqueServicioServicer_to_server(
                        servicio, servidor
                    )
                    puerto = servidor.add_insecure_port("127.0.0.1:0")
                    servidor.start()
                    servicio.node_id = f"127.0.0.1:{puerto}"
                    servicios.append(servicio)
                    servidores.append(servidor)
                    direcciones.append(servicio.node_id)

                miembros = [
                    bloque_servicio_pb2.NodoMembresia(
                        direccion=direccion, estado="activo"
                    )
                    for direccion in direcciones
                ]
                for servicio in servicios:
                    servicio.membresia = miembros

                cliente_gateway = NodeClient(direcciones[0])
                contenido = b"x" * (5 * 1024 * 1024)
                checksum = hashlib.sha256(contenido).hexdigest()
                respuesta = cliente_gateway.replicar_bloque(
                    "archivo-0",
                    "archivo",
                    0,
                    contenido,
                    checksum,
                    direcciones[1:],
                    timeout=3,
                )

                self.assertTrue(respuesta.exito)
                self.assertEqual(respuesta.replicas_confirmadas, 3)
                for servicio in servicios:
                    self.assertEqual(
                        servicio.almacenamiento.leer_bloque("archivo-0"),
                        (contenido, checksum),
                    )
            finally:
                if cliente_gateway is not None:
                    cliente_gateway.canal.close()
                for servicio in servicios:
                    servicio.cerrar()
                for servidor in servidores:
                    servidor.stop(0).wait()

    def test_replica_localmente_y_reenvia_a_cada_destino_unico(self):
        contenido = b"bloque distribuido"
        checksum = hashlib.sha256(contenido).hexdigest()
        clientes = {}

        class ClienteFalso:
            def __init__(self, direccion):
                self.direccion = direccion
                self.canal = SimpleNamespace(close=lambda: None)
                self.escrituras = []

            def escribir_bloque(self, *args, timeout=None):
                self.escrituras.append(args)
                return SimpleNamespace(exito=True, mensaje="guardado")

        def crear_cliente(direccion):
            clientes[direccion] = ClienteFalso(direccion)
            return clientes[direccion]

        with tempfile.TemporaryDirectory() as directorio, patch(
            "Node.server.NodeClient", side_effect=crear_cliente
        ):
            servicio = BloqueServicio(directorio, "nodo-a:50051")
            servicio.membresia = [
                bloque_servicio_pb2.NodoMembresia(
                    direccion=direccion, estado="activo"
                )
                for direccion in ("nodo-a:50051", "nodo-b:50052", "nodo-c:50053")
            ]
            request = bloque_servicio_pb2.ReplicarBloqueRequest(
                block_id="archivo-0",
                file_id="archivo",
                posicion=0,
                contenido=contenido,
                checksum=checksum,
                destinos=["nodo-b:50052", "nodo-c:50053", "nodo-b:50052"],
            )
            try:
                respuesta = servicio.ReplicarBloque(request, MagicMock())
                guardado = servicio.almacenamiento.leer_bloque("archivo-0")
                self.assertTrue(respuesta.exito)
                self.assertEqual(respuesta.replicas_confirmadas, 3)
                self.assertEqual(guardado, (contenido, checksum))
                self.assertEqual(set(clientes), {"nodo-b:50052", "nodo-c:50053"})
                self.assertEqual(len(clientes["nodo-b:50052"].escrituras), 1)
            finally:
                servicio.cerrar()

    def test_no_envia_replica_a_un_nodo_fuera_de_membresia_activa(self):
        contenido = b"bloque"
        checksum = hashlib.sha256(contenido).hexdigest()
        with tempfile.TemporaryDirectory() as directorio, patch(
            "Node.server.NodeClient"
        ) as crear_cliente:
            servicio = BloqueServicio(directorio, "nodo-a:50051")
            servicio.membresia = [
                bloque_servicio_pb2.NodoMembresia(
                    direccion="nodo-a:50051", estado="activo"
                )
            ]
            request = bloque_servicio_pb2.ReplicarBloqueRequest(
                block_id="archivo-0",
                file_id="archivo",
                posicion=0,
                contenido=contenido,
                checksum=checksum,
                destinos=["nodo-no-autorizado:50054"],
            )
            try:
                respuesta = servicio.ReplicarBloque(request, MagicMock())
                self.assertEqual(respuesta.replicas_confirmadas, 1)
                self.assertIn("fuera de la membresía activa", respuesta.mensaje)
                crear_cliente.assert_not_called()
            finally:
                servicio.cerrar()
