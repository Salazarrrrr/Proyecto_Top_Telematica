import hashlib
from pathlib import Path

from Node.models import Bloque


class Almacenamiento:

    def __init__(self, directorio: str):
        self.directorio = Path(directorio)
        self.directorio.mkdir(parents=True, exist_ok=True)

    def guardar_bloque(self, bloque: Bloque):
        checksum = self.calcular_checksum(bloque.contenido)

        if bloque.checksum and bloque.checksum != checksum:
            raise ValueError("El checksum del bloque no coincide")

        ruta_bloque = self.directorio / f"{bloque.block_id}.bin"

        with open(ruta_bloque, "wb") as archivo:
            archivo.write(bloque.contenido)

        return checksum

    def leer_bloque(self, block_id: str):
        ruta_bloque = self.directorio / f"{block_id}.bin"

        if not ruta_bloque.exists():
            return None

        with open(ruta_bloque, "rb") as archivo:
            contenido = archivo.read()

        checksum = self.calcular_checksum(contenido)

        return contenido, checksum

    def eliminar_bloque(self, block_id: str):
        ruta_bloque = self.directorio / f"{block_id}.bin"

        if not ruta_bloque.exists():
            return False

        ruta_bloque.unlink()
        return True

    @staticmethod
    def calcular_checksum(contenido: bytes) -> str:
        return hashlib.sha256(contenido).hexdigest()