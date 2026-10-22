"""Pruebas de quórums y operaciones del clúster."""

import hashlib
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path

from Gateway.cluster_comunication import ClusterManager


class TestQuorum(unittest.TestCase):
    def test_asignacion_de_bloque_consulta_servicio_java(self):
        with patch.dict(os.environ, {"DFS_CLUSTER_JAVA_URL": "http://cluster-java:8081"}), \
             patch("Gateway.cluster.cluster_core.NodeClient") as cliente:
            cliente.return_value.canal = SimpleNamespace(close=lambda: None)
            cluster = ClusterManager(
                nodos="nodo-a:1,nodo-b:2,nodo-c:3", factor_replicacion=2,
                quorum_lectura=1, quorum_escritura=2,
            )
            try:
                cluster.java_cluster.responsables = MagicMock(return_value=["nodo-c:3", "nodo-a:1"])
                self.assertEqual(cluster.nodos_responsables("archivo-0"), ["nodo-c:3", "nodo-a:1"])
                cluster.java_cluster.responsables.assert_called_once_with(
                    "archivo-0", ["nodo-a:1", "nodo-b:2", "nodo-c:3"], 2
                )
            finally:
                cluster.cerrar()

    def test_factor_se_conserva_al_reiniciar_el_gateway(self):
        with tempfile.TemporaryDirectory() as directorio, patch.dict(
            os.environ, {"DFS_CLUSTER_CONFIG": os.path.join(directorio, "cluster.json")}
        ), patch("Gateway.cluster.cluster_core.NodeClient") as cliente:
            cliente.return_value.canal = SimpleNamespace(close=lambda: None)
            primero = ClusterManager(
                nodos="nodo-a:1,nodo-b:2,nodo-c:3", factor_replicacion=3,
                quorum_lectura=2, quorum_escritura=2,
            )
            primero.factor_replicacion = 2
            primero.guardar_factor_replicacion()
            primero.cerrar()
            segundo = ClusterManager(
                nodos="nodo-a:1,nodo-b:2,nodo-c:3",
                quorum_lectura=2, quorum_escritura=2,
            )
            try:
                self.assertEqual(segundo.factor_replicacion, 2)
                self.assertEqual(
                    json.loads(Path(os.path.join(directorio, "cluster.json")).read_text())[
                        "factor_replicacion"
                    ], 2,
                )
            finally:
                segundo.cerrar()

    def test_rechaza_quorums_sin_interseccion(self):
        with self.assertRaisesRegex(ValueError, r"R \+ W"):
            ClusterManager(
                nodos="nodo-a:1,nodo-b:2,nodo-c:3", factor_replicacion=3,
                quorum_lectura=1, quorum_escritura=2,
            )

    def test_lectura_no_elige_una_copia_sin_quorum_de_contenido(self):
        cluster = ClusterManager(
            nodos="nodo-a:1,nodo-b:2,nodo-c:3", factor_replicacion=3,
            quorum_lectura=2, quorum_escritura=2,
        )

        class ClienteFalso:
            canal = SimpleNamespace(close=lambda: None)

            def __init__(self, contenido):
                self.contenido = contenido

            def leer_bloque(self, *_args, timeout=None):
                if self.contenido is None:
                    return SimpleNamespace(exito=False, mensaje="nodo sin bloque")
                return SimpleNamespace(
                    exito=True, contenido=self.contenido,
                    checksum=hashlib.sha256(self.contenido).hexdigest(),
                    file_id="archivo", posicion=0,
                )

        for cliente in cluster.clientes.values():
            cliente.canal.close()
        cluster.clientes = {
            "nodo-a:1": ClienteFalso(b"copia-a"),
            "nodo-b:2": ClienteFalso(b"copia-b"),
            "nodo-c:3": ClienteFalso(None),
        }
        try:
            self.assertIsNone(cluster.leer_bloque("bloque"))
        finally:
            cluster.cerrar()

    def test_escritura_solo_confirma_al_alcanzar_w(self):
        cluster = ClusterManager(
            nodos="nodo-a:1,nodo-b:2,nodo-c:3", factor_replicacion=3,
            quorum_escritura=2, timeout=0.01,
        )

        class ClienteFalso:
            def __init__(self, exito):
                self.exito = exito
                self.canal = SimpleNamespace(close=lambda: None)

            def escribir_bloque(self, *args, timeout=None):
                return SimpleNamespace(exito=self.exito, mensaje="fallo")

        for cliente in cluster.clientes.values():
            cliente.canal.close()
        cluster.clientes = {
            "nodo-a:1": ClienteFalso(True),
            "nodo-b:2": ClienteFalso(True),
            "nodo-c:3": ClienteFalso(False),
        }
        try:
            exito, _ = cluster.escribir_bloque("bloque", "archivo", 0, b"x", "sum")
            self.assertTrue(exito)
            cluster.clientes["nodo-b:2"].exito = False
            exito, mensaje = cluster.escribir_bloque("bloque", "archivo", 0, b"x", "sum")
            self.assertFalse(exito)
            self.assertIn("Quórum", mensaje)
        finally:
            cluster.cerrar()

    def test_rebalanceo_copia_a_nuevos_responsables_y_limpia_excedente(self):
        cluster = ClusterManager(
            nodos="nodo-a:1,nodo-b:2,nodo-c:3", factor_replicacion=3,
            quorum_lectura=2, quorum_escritura=2,
        )

        class ClienteFalso:
            def __init__(self, nombre):
                self.nombre = nombre
                self.canal = SimpleNamespace(close=lambda: None)
                self.eliminados = []

            def heartbeat(self, *_args, timeout=None):
                return SimpleNamespace(exito=True)

            def leer_bloque(self, *_args, timeout=None):
                return SimpleNamespace(
                    exito=True, contenido=b"dato",
                    checksum=hashlib.sha256(b"dato").hexdigest(),
                    file_id="f", posicion=0,
                )

            def escribir_bloque(self, *_args, timeout=None):
                return SimpleNamespace(exito=True)

            def eliminar_bloque(self, block_id, timeout=None):
                self.eliminados.append(block_id)
                return SimpleNamespace(exito=True)

        for cliente in cluster.clientes.values():
            cliente.canal.close()
        nodos = {nombre: ClienteFalso(nombre) for nombre in ("nodo-a:1", "nodo-b:2", "nodo-c:3", "nodo-d:4")}
        cluster.clientes = {nombre: nodos[nombre] for nombre in ("nodo-a:1", "nodo-b:2", "nodo-c:3")}
        cluster.nodos_responsables = lambda _block: (
            ["nodo-a:1", "nodo-b:2", "nodo-c:3"] if len(cluster.direcciones) == 3
            else ["nodo-a:1", "nodo-b:2", "nodo-d:4"]
        )
        archivo = {"file_id": "f", "bloques": [{
            "block_id": "f-0", "posicion": 0,
            "checksum": hashlib.sha256(b"dato").hexdigest(),
        }]}
        try:
            with patch("Gateway.cluster.cluster_membership.NodeClient", return_value=nodos["nodo-d:4"]):
                resultado = cluster.agregar_nodo_y_rebalancear("nodo-d:4", [archivo])
            self.assertEqual(resultado["copias_confirmadas"], 3)
            self.assertEqual(nodos["nodo-c:3"].eliminados, ["f-0"])
            self.assertEqual(resultado["limpieza_pendiente"], 0)
        finally:
            cluster.cerrar()


if __name__ == "__main__":
    unittest.main()
