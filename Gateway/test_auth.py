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

    def test_operaciones_de_cluster_requieren_token_administrador(self):
        respuesta = self.cliente.put(
            "/cluster/replication",
            json={"factor": 2},
            headers=self.cabecera("ana"),
        )
        self.assertEqual(respuesta.status_code, 403)


class TestSesionesYRoles(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        variables = {
            "DFS_USERS": json.dumps({"demo": "token-demo"}),
            "DFS_USER_PASSWORDS": json.dumps({"admin": "Admin123!", "demo": "Demo123!"}),
            "DFS_USER_ROLES": json.dumps({"admin": "admin", "demo": "usuario"}),
            "DFS_AUTH_USERS_FILE": str(Path(self.directorio.name) / "usuarios.json"),
        }
        self.variables = patch.dict(os.environ, variables)
        self.variables.start()
        with patch("Gateway.app.CatalogoArchivos", return_value=CatalogoArchivos(Path(self.directorio.name) / "archivos.json")), \
             patch("Gateway.app.ClusterManager", return_value=MagicMock()), \
             patch("Gateway.app.NodeClient", return_value=MagicMock()):
            self.app = create_app()
        self.cliente = self.app.test_client()

    def tearDown(self):
        self.variables.stop()
        self.directorio.cleanup()

    def test_login_logout_y_roles(self):
        demo = self.cliente.post("/auth/login", json={"usuario": "demo", "password": "Demo123!"})
        self.assertEqual(demo.status_code, 200)
        token_demo = demo.json["token"]
        self.assertEqual(self.cliente.get("/auth/me", headers={"Authorization": f"Bearer {token_demo}"}).json["rol"], "usuario")
        self.assertEqual(self.cliente.post("/auth/users", json={"usuario": "otro", "password": "Password1!"}, headers={"Authorization": f"Bearer {token_demo}"}).status_code, 403)
        admin = self.cliente.post("/auth/login", json={"usuario": "admin", "password": "Admin123!"})
        self.assertEqual(admin.status_code, 200)
        token_admin = admin.json["token"]
        creado = self.cliente.post("/auth/users", json={"usuario": "otro", "password": "Password1!", "rol": "usuario"}, headers={"Authorization": f"Bearer {token_admin}"})
        self.assertEqual(creado.status_code, 201)
        self.assertEqual(self.cliente.post("/auth/logout", headers={"Authorization": f"Bearer {token_demo}"}).status_code, 200)
        self.assertEqual(self.cliente.get("/auth/me", headers={"Authorization": f"Bearer {token_demo}"}).status_code, 401)

    def test_sesion_no_depende_de_tokens_estaticos(self):
        with patch.dict(os.environ, {"DFS_USERS": ""}):
            login = self.cliente.post("/auth/login", json={"usuario": "demo", "password": "Demo123!"})
            self.assertEqual(login.status_code, 200)
            respuesta = self.cliente.get(
                "/files", headers={"Authorization": f"Bearer {login.json['token']}"}
            )
        self.assertEqual(respuesta.status_code, 200)

    def test_health_esta_disponible_sin_autenticacion(self):
        respuesta = self.cliente.get("/health")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json["servicio"], "gateway")


if __name__ == "__main__":
    unittest.main()
