"""Arranque y configuración de la API REST del Gateway."""

import os
from pathlib import Path

from flask import Flask

from Gateway.auth import registrar_seguridad
from Gateway.cluster import ClusterManager
from Gateway.metadata import CatalogoArchivos
from Gateway.node_client import NodeClient
from Gateway.routes import blocks, cluster as cluster_routes, directories, files


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("DFS_MAX_UPLOAD_BYTES", str(1024 ** 3)))

    catalogo = CatalogoArchivos(Path(__file__).resolve().parent.parent / "metadata" / "archivos.json")
    cluster = ClusterManager()
    cluster.proveedor_archivos = catalogo.todos
    app.extensions["dfsha"] = {
        "node_client": NodeClient(),
        "cluster": cluster,
        "catalogo": catalogo,
    }

    registrar_seguridad(app)
    for blueprint in (blocks.bp, files.bp, directories.bp, cluster_routes.bp):
        app.register_blueprint(blueprint)
    return app


app = create_app()
servicios = app.extensions["dfsha"]
node_client = servicios["node_client"]
cluster = servicios["cluster"]
catalogo = servicios["catalogo"]


def main():
    cluster.iniciar_monitor(float(os.getenv("DFS_HEARTBEAT_INTERVAL", "5")))
    host = os.getenv("DFS_GATEWAY_BIND", "127.0.0.1")
    cert_path = os.getenv("DFS_GATEWAY_TLS_CERT")
    key_path = os.getenv("DFS_GATEWAY_TLS_KEY")
    if bool(cert_path) != bool(key_path):
        raise RuntimeError("DFS_GATEWAY_TLS_CERT y DFS_GATEWAY_TLS_KEY deben configurarse juntos")
    remoto = host not in {"localhost", "127.0.0.1", "::1"}
    autenticacion = os.getenv("DFS_USERS")
    if remoto and (not cert_path or not key_path or not autenticacion):
        raise RuntimeError("La exposición remota requiere HTTPS y credenciales individuales en DFS_USERS")
    app.run(
        host=host,
        port=int(os.getenv("DFS_GATEWAY_PORT", "8000")),
        debug=False,
        ssl_context=(cert_path, key_path) if cert_path and key_path else None,
        threaded=True,
    )


if __name__ == "__main__":
    main()
