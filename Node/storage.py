import hashlib
import base64
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from Node.models import Bloque


class Almacenamiento:

    MARCA_CIFRADO = b"DFSAESG1"

    def __init__(self, directorio: str):
        self.directorio = Path(directorio)
        self.directorio.mkdir(parents=True, exist_ok=True)
        self._cifrador = None
        clave = os.getenv("DFS_STORAGE_KEY", "")
        if clave:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                bytes_clave = base64.b64decode(clave, altchars=b"-_", validate=True)
            except (ImportError, ValueError) as error:
                raise RuntimeError("DFS_STORAGE_KEY debe ser Base64 y requiere cryptography") from error
            if len(bytes_clave) != 32:
                raise RuntimeError("DFS_STORAGE_KEY debe decodificar exactamente 32 bytes")
            self._cifrador = AESGCM(bytes_clave)

    @staticmethod
    def _aad(metadata, block_id):
        canonica = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return canonica + block_id.encode("utf-8")

    def guardar_bloque(self, bloque: Bloque):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", bloque.block_id or ""):
            raise ValueError("Identificador de bloque inválido")
        checksum = self.calcular_checksum(bloque.contenido)

        if bloque.checksum and bloque.checksum != checksum:
            raise ValueError("El checksum del bloque no coincide")

        ruta_bloque = self.directorio / f"{bloque.block_id}.bin"
        ruta_metadata = self.directorio / f"{bloque.block_id}.json"
        metadata = {
            "file_id": bloque.file_id,
            "posicion": bloque.posicion,
            "tamano": len(bloque.contenido),
            "checksum": checksum,
        }
        contenido_disco = bloque.contenido
        if self._cifrador:
            nonce = os.urandom(12)
            contenido_disco = (
                self.MARCA_CIFRADO + nonce
                + self._cifrador.encrypt(nonce, bloque.contenido, self._aad(metadata, bloque.block_id))
            )
        temporal = self.directorio / f".{bloque.block_id}.{uuid4().hex}.tmp"
        temporal_metadata = self.directorio / f".{bloque.block_id}.{uuid4().hex}.json.tmp"
        try:
            with temporal.open("xb") as archivo:
                archivo.write(contenido_disco)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, ruta_bloque)
            with temporal_metadata.open("x", encoding="utf-8") as archivo:
                json.dump(metadata, archivo)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal_metadata, ruta_metadata)
        finally:
            temporal.unlink(missing_ok=True)
            temporal_metadata.unlink(missing_ok=True)

        return checksum

    def leer_bloque(self, block_id: str):
        resultado = self.leer_bloque_completo(block_id)
        if resultado is None:
            return None
        return resultado[0], resultado[1]

    def leer_bloque_completo(self, block_id: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", block_id or ""):
            return None
        ruta_bloque = self.directorio / f"{block_id}.bin"

        if not ruta_bloque.exists():
            return None

        with open(ruta_bloque, "rb") as archivo:
            contenido = archivo.read()

        ruta_metadata = self.directorio / f"{block_id}.json"
        try:
            metadata = json.loads(ruta_metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if self._cifrador:
            prefijo = len(self.MARCA_CIFRADO)
            if not contenido.startswith(self.MARCA_CIFRADO) or len(contenido) < prefijo + 12:
                return None
            nonce = contenido[prefijo:prefijo + 12]
            try:
                contenido = self._cifrador.decrypt(
                    nonce, contenido[prefijo + 12:], self._aad(metadata, block_id)
                )
            except Exception:
                return None
        checksum = self.calcular_checksum(contenido)
        if metadata.get("checksum", checksum) != checksum:
            return None
        return contenido, checksum, metadata.get("file_id", ""), int(metadata.get("posicion", 0))

    def eliminar_bloque(self, block_id: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", block_id or ""):
            return False
        ruta_bloque = self.directorio / f"{block_id}.bin"

        if not ruta_bloque.exists():
            return False

        ruta_bloque.unlink()
        (self.directorio / f"{block_id}.json").unlink(missing_ok=True)
        return True

    @staticmethod
    def calcular_checksum(contenido: bytes) -> str:
        return hashlib.sha256(contenido).hexdigest()
