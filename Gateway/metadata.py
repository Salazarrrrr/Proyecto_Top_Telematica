import json
import os
import posixpath
import threading
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


class CatalogoArchivos:

    def __init__(self, ruta="metadata/archivos.json"):
        self.ruta = Path(ruta)
        self.ruta_directorios = self.ruta.with_name("directorios.json")
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._bloqueos_operacion = [threading.RLock() for _ in range(64)]
        if not self.ruta.exists():
            self._guardar({})
        if not self.ruta_directorios.exists():
            self._guardar_directorios({})

    def _cargar(self):
        with self.ruta.open("r", encoding="utf-8") as archivo:
            return json.load(archivo)

    def _guardar(self, archivos):
        temporal = self.ruta.with_name(f".{self.ruta.name}.{uuid4().hex}.tmp")
        try:
            with temporal.open("x", encoding="utf-8") as archivo:
                json.dump(archivos, archivo, indent=2, ensure_ascii=True)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, self.ruta)
        finally:
            temporal.unlink(missing_ok=True)

    def _guardar_directorios(self, directorios):
        temporal = self.ruta_directorios.with_name(
            f".{self.ruta_directorios.name}.{uuid4().hex}.tmp"
        )
        try:
            with temporal.open("x", encoding="utf-8") as archivo:
                json.dump(directorios, archivo, indent=2, ensure_ascii=True)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, self.ruta_directorios)
        finally:
            temporal.unlink(missing_ok=True)

    @staticmethod
    def normalizar_ruta(ruta, actual="/"):
        ruta = str(ruta or ".").replace("\\", "/")
        base = "/" if ruta.startswith("/") else str(actual or "/")
        normalizada = posixpath.normpath(posixpath.join(base, ruta))
        if not normalizada.startswith("/"):
            raise ValueError("La ruta debe permanecer dentro del espacio DFS del usuario")
        return normalizada

    def crear_directorio(self, usuario, ruta):
        ruta = self.normalizar_ruta(ruta)
        if ruta == "/":
            return ruta
        with self._lock:
            directorios = json.loads(self.ruta_directorios.read_text(encoding="utf-8"))
            existentes = set(directorios.get(usuario, ["/"]))
            padre = posixpath.dirname(ruta) or "/"
            if padre not in existentes:
                raise FileNotFoundError("El directorio padre no existe")
            existentes.add(ruta)
            directorios[usuario] = sorted(existentes)
            self._guardar_directorios(directorios)
        return ruta

    def listar_directorio(self, usuario, ruta="/"):
        ruta = self.normalizar_ruta(ruta)
        with self._lock:
            directorios = json.loads(self.ruta_directorios.read_text(encoding="utf-8"))
            existentes = set(directorios.get(usuario, ["/"]))
            if ruta not in existentes:
                raise FileNotFoundError("Directorio no encontrado")
            subdirectorios = sorted(
                posixpath.basename(item) for item in existentes
                if posixpath.dirname(item) == ruta and item != ruta
            )
            archivos = [
                {**archivo, "ruta": posixpath.join(archivo.get("directorio", "/"), archivo["nombre"])}
                for archivo in self._cargar().values()
                if archivo["usuario"] == usuario and archivo.get("directorio", "/") == ruta
            ]
            return {"ruta": ruta, "directorios": subdirectorios, "archivos": archivos}

    def eliminar_directorio(self, usuario, ruta):
        ruta = self.normalizar_ruta(ruta)
        if ruta == "/":
            raise ValueError("No se puede eliminar el directorio raíz")
        with self._lock:
            directorios = json.loads(self.ruta_directorios.read_text(encoding="utf-8"))
            existentes = set(directorios.get(usuario, ["/"]))
            if ruta not in existentes:
                raise FileNotFoundError("Directorio no encontrado")
            tiene_subdirectorios = any(item.startswith(ruta + "/") for item in existentes)
            tiene_archivos = any(
                archivo["usuario"] == usuario and archivo.get("directorio", "/") == ruta
                for archivo in self._cargar().values()
            )
            if tiene_subdirectorios or tiene_archivos:
                raise OSError("El directorio no está vacío")
            existentes.remove(ruta)
            directorios[usuario] = sorted(existentes)
            self._guardar_directorios(directorios)
        return ruta

    def guardar(self, archivo):
        with self._lock:
            archivo.setdefault("directorio", "/")
            directorios = json.loads(self.ruta_directorios.read_text(encoding="utf-8"))
            if archivo["directorio"] not in set(directorios.get(archivo["usuario"], ["/"])):
                raise ValueError("El directorio remoto no existe para este usuario")
            archivos = self._cargar()
            archivos[archivo["file_id"]] = archivo
            self._guardar(archivos)

    def obtener(self, file_id):
        with self._lock:
            return self._cargar().get(file_id)

    def listar(self, usuario):
        with self._lock:
            return [archivo for archivo in self._cargar().values()
                    if archivo["usuario"] == usuario]

    def todos(self):
        with self._lock:
            return list(self._cargar().values())

    def buscar_por_nombre(self, usuario, nombre):
        for archivo in self.listar(usuario):
            if archivo["nombre"] == nombre:
                return archivo
        return None

    @contextmanager
    def bloquear_operacion(self, file_id):
        indice = int(sha256(file_id.encode("utf-8")).hexdigest(), 16) % len(self._bloqueos_operacion)
        with self._bloqueos_operacion[indice]:
            yield

    def eliminar(self, file_id):
        with self._lock:
            archivos = self._cargar()
            archivo = archivos.pop(file_id, None)
            if archivo is not None:
                self._guardar(archivos)
            return archivo
