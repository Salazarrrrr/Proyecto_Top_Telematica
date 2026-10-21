"""Arranque y configuración de la API REST del Gateway."""

import os
from pathlib import Path

from flask import Flask, jsonify

from Gateway.auth import registrar_seguridad
from Gateway.cluster import ClusterManager
from Gateway.metadata import CatalogoArchivos
from Gateway.node_client import NodeClient
from Gateway.routes import auth as auth_routes, blocks, cluster as cluster_routes, directories, files


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

    @app.get("/health")
    def health():
        return jsonify({"exito": True, "servicio": "gateway"})

    registrar_seguridad(app)
    for blueprint in (auth_routes.bp, blocks.bp, files.bp, directories.bp, cluster_routes.bp):
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
    tls_terminado = os.getenv("DFS_GATEWAY_TLS_TERMINATED", "0").lower() in {"1", "true", "yes"}
    if bool(cert_path) != bool(key_path):
        raise RuntimeError("DFS_GATEWAY_TLS_CERT y DFS_GATEWAY_TLS_KEY deben configurarse juntos")
    if tls_terminado and (cert_path or key_path):
        raise RuntimeError("No configures certificados en el Gateway cuando el proxy termina TLS")
    remoto = host not in {"localhost", "127.0.0.1", "::1"}
    autenticacion = os.getenv("DFS_USERS") or os.getenv("DFS_USER_PASSWORDS")
    requiere_tls_gateway = not tls_terminado and (not cert_path or not key_path)
    if remoto and (requiere_tls_gateway or not autenticacion):
        raise RuntimeError("La exposición remota requiere HTTPS y usuarios configurados")
    app.run(
        host=host,
        port=int(os.getenv("DFS_GATEWAY_PORT", "8000")),
        debug=False,
        ssl_context=(cert_path, key_path) if cert_path and key_path else None,
        threaded=True,
    )


if __name__ == "__main__":
    main()
