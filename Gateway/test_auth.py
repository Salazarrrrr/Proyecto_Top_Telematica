"""Pruebas de autenticación e aislamiento entre usuarios."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from Gateway.app import create_app
from Gateway.metadata import CatalogoArchivos


class TestAislamientoUsuarios(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        self.catalogo = CatalogoArchivos(Path(self.directorio.name) / "archivos.json")
        self.usuarios = {"ana": "token-ana-secreto", "luis": "token-luis-secreto"}
        self.variables = patch.dict(os.environ, {"DFS_USERS": json.dumps(self.usuarios)})
        self.variables.start()

        with patch("Gateway.app.CatalogoArchivos", return_value=self.catalogo), \
             patch("Gateway.app.ClusterManager", return_value=MagicMock()), \
             patch("Gateway.app.NodeClient", return_value=MagicMock()):
            self.app = create_app()
        self.cliente = self.app.test_client()

    def tearDown(self):
        self.variables.stop()
        self.directorio.cleanup()

    def cabecera(self, usuario):
        return {"Authorization": f"Bearer {self.usuarios[usuario]}"}

    def test_usuario_no_puede_listar_ni_descargar_archivos_ajenos(self):
        self.catalogo.guardar({
            "file_id": "archivo-ana",
            "usuario": "ana",
            "nombre": "privado.txt",
            "directorio": "/",
            "bloques": [],
        })

        listado = self.cliente.get(
            "/files?usuario=ana", headers=self.cabecera("luis")
        )
        descarga = self.cliente.get(
            "/files/archivo-ana?usuario=ana", headers=self.cabecera("luis")
        )
        borrado = self.cliente.delete(
            "/files/archivo-ana?usuario=ana", headers=self.cabecera("luis")
        )

        self.assertEqual(listado.status_code, 200)
        self.assertEqual(listado.json["archivos"], [])
        self.assertEqual(descarga.status_code, 404)
        self.assertEqual(borrado.status_code, 404)
        self.assertIsNotNone(self.catalogo.obtener("archivo-ana"))

    def test_usuario_no_puede_usar_el_nombre_de_otro_en_la_peticion(self):
        respuesta = self.cliente.post(
            "/directories",
            json={"path": "/carpeta-luis", "usuario": "ana"},
            headers=self.cabecera("luis"),
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(
            self.catalogo.listar_directorio("luis", "/")["directorios"],
            ["carpeta-luis"],
        )
        self.assertEqual(self.catalogo.listar_directorio("ana", "/")["directorios"], [])

    def test_rechaza_solicitudes_sin_credenciales_individuales(self):
        with patch.dict(os.environ, {"DFS_USERS": ""}):
            respuesta = self.cliente.get("/files")
        self.assertEqual(respuesta.status_code, 503)


if __name__ == "__main__":
    unittest.main()
