"""Pruebas de particionado, almacenamiento y directorios."""

import tempfile
import unittest
import base64
import importlib.util
import os
from unittest.mock import patch
from pathlib import Path

from Gateway import particionar
from Gateway.metadata import CatalogoArchivos
from Node.models import Bloque
from Node.storage import Almacenamiento


class TestParticionamiento(unittest.TestCase):
    def test_particiona_archivo_binario_en_bloques_ordenados(self):
        with tempfile.TemporaryDirectory() as directorio:
            origen = Path(directorio) / "entrada.bin"
            origen.write_bytes(b"\x00abc\xff")
            with patch.object(particionar, "BLOCK_SIZE", 2):
                bloques = list(particionar.dividir_archivo(origen))
        self.assertEqual([pos for pos, _ in bloques], [0, 1, 2])
        self.assertEqual(b"".join(contenido for _, contenido in bloques), b"\x00abc\xff")
        self.assertEqual([len(contenido) for _, contenido in bloques], [2, 2, 1])


class TestAlmacenamiento(unittest.TestCase):
    def test_checksum_y_metadata_se_conservan(self):
        with tempfile.TemporaryDirectory() as directorio:
            almacenamiento = Almacenamiento(directorio)
            bloque = Bloque("archivo-0", "archivo", 0, b"contenido", "")
            checksum = almacenamiento.guardar_bloque(bloque)
            resultado = almacenamiento.leer_bloque_completo("archivo-0")
        self.assertEqual(resultado, (b"contenido", checksum, "archivo", 0))

    def test_checksum_invalido_no_reemplaza_el_bloque_existente(self):
        with tempfile.TemporaryDirectory() as directorio:
            almacenamiento = Almacenamiento(directorio)
            almacenamiento.guardar_bloque(Bloque("archivo-0", "archivo", 0, b"original", ""))
            with self.assertRaises(ValueError):
                almacenamiento.guardar_bloque(Bloque("archivo-0", "archivo", 0, b"otro", "incorrecto"))
            self.assertEqual(almacenamiento.leer_bloque("archivo-0")[0], b"original")

    def test_rechaza_identificadores_con_ruta(self):
        with tempfile.TemporaryDirectory() as directorio:
            almacenamiento = Almacenamiento(directorio)
            with self.assertRaises(ValueError):
                almacenamiento.guardar_bloque(Bloque("../afuera", "f", 0, b"x", ""))

    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "cryptography no está instalado")
    def test_cifrado_aesgcm_en_disco_y_detecta_alteracion(self):
        clave = base64.b64encode(os.urandom(32)).decode("ascii")
        with tempfile.TemporaryDirectory() as directorio, patch.dict(os.environ, {"DFS_STORAGE_KEY": clave}):
            almacenamiento = Almacenamiento(directorio)
            contenido = b"secreto del archivo"
            almacenamiento.guardar_bloque(Bloque("archivo-0", "archivo", 0, contenido, ""))
            ruta_bloque = Path(directorio) / "archivo-0.bin"
            cifrado = ruta_bloque.read_bytes()
            self.assertNotIn(contenido, cifrado)
            self.assertEqual(almacenamiento.leer_bloque("archivo-0")[0], contenido)
            ruta_bloque.write_bytes(cifrado[:-1] + bytes([cifrado[-1] ^ 1]))
            self.assertIsNone(almacenamiento.leer_bloque("archivo-0"))


class TestDirectorios(unittest.TestCase):
    def test_directorios_aislados_por_usuario_y_rmdir_solo_vacio(self):
        with tempfile.TemporaryDirectory() as directorio:
            catalogo = CatalogoArchivos(Path(directorio) / "archivos.json")
            catalogo.crear_directorio("ana", "/docs")
            self.assertEqual(catalogo.listar_directorio("ana", "/")["directorios"], ["docs"])
            self.assertEqual(catalogo.listar_directorio("luis", "/")["directorios"], [])
            catalogo.guardar({
                "file_id": "f1", "usuario": "ana", "nombre": "x.txt",
                "directorio": "/docs", "bloques": [],
            })
            with self.assertRaisesRegex(OSError, "no está vacío"):
                catalogo.eliminar_directorio("ana", "/docs")
            catalogo.eliminar("f1")
            catalogo.eliminar_directorio("ana", "/docs")
