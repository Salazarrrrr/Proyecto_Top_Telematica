"""Cliente del servicio Java que decide la ubicación de los bloques."""

import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen


class JavaClusterClient:
    def __init__(self, base_url=None, timeout=2):
        self.base_url = (base_url or os.getenv("DFS_CLUSTER_JAVA_URL", "")).rstrip("/")
        self.timeout = timeout

    @property
    def activo(self):
        return bool(self.base_url)

    def responsables(self, bloque, nodos, replicas):
        if not self.activo:
            return None
        parametros = urlencode({"bloque": bloque, "nodos": ",".join(nodos), "replicas": replicas})
        try:
            with urlopen(f"{self.base_url}/responsables?{parametros}", timeout=self.timeout) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(f"No se pudo consultar el clúster Java: {error}") from error
        resultado = datos.get("nodos")
        if not isinstance(resultado, list) or not resultado or any(nodo not in nodos for nodo in resultado):
            raise RuntimeError("El clúster Java devolvió una asignación inválida")
        return resultado
