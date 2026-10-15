"""Autenticación y utilidades comunes para las rutas del Gateway."""

import hmac
import json
import os
from functools import wraps

from flask import current_app, g, jsonify, request

from Gateway.services import servicios


def registrar_seguridad(app):
    app.before_request(autenticar_solicitud)
    app.register_error_handler(413, carga_demasiado_grande)


def autenticar_solicitud():
    g.usuario_autenticado = None
    recibido = request.headers.get("Authorization", "")
    admin = os.getenv("DFS_ADMIN_TOKEN", "")
    if admin and recibido.startswith("Bearer ") and hmac.compare_digest(recibido[7:], admin):
        g.usuario_autenticado = "admin"
        return None
    if request.path == "/blocks" or request.path.startswith("/blocks/"):
        return jsonify({"exito": False, "mensaje": "Se requiere token de administrador"}), 403

    usuarios = os.getenv("DFS_USERS")
    if not usuarios:
        return jsonify({
            "exito": False,
            "mensaje": "El Gateway requiere credenciales individuales configuradas en DFS_USERS",
        }), 503
    try:
        tokens_por_usuario = json.loads(usuarios)
    except json.JSONDecodeError:
        current_app.logger.error("DFS_USERS debe contener un objeto JSON de usuario a token")
        return jsonify({"exito": False, "mensaje": "Configuración de autenticación inválida"}), 503
    if (
        not isinstance(tokens_por_usuario, dict)
        or not tokens_por_usuario
        or any(not isinstance(usuario, str) or not usuario.strip() for usuario in tokens_por_usuario)
        or any(not isinstance(token, str) or not token for token in tokens_por_usuario.values())
        or len(set(tokens_por_usuario.values())) != len(tokens_por_usuario)
    ):
        return jsonify({
            "exito": False,
            "mensaje": "DFS_USERS debe asignar un token único y no vacío a cada usuario",
        }), 503

    autorizacion = request.headers.get("Authorization", "")
    token = autorizacion[7:] if autorizacion.startswith("Bearer ") else ""
    for usuario, token_configurado in tokens_por_usuario.items():
        if hmac.compare_digest(token, token_configurado):
            g.usuario_autenticado = usuario
            return None
    return jsonify({"exito": False, "mensaje": "Autenticación requerida"}), 401


def carga_demasiado_grande(_error):
    return jsonify({"exito": False, "mensaje": "El archivo supera el límite configurado"}), 413


def usuario_solicitante():
    return g.usuario_autenticado


def autorizar_diagnostico():
    token_admin = os.getenv("DFS_ADMIN_TOKEN")
    if not token_admin:
        return jsonify({"exito": False, "mensaje": "Endpoint de diagnóstico deshabilitado"}), 404
    recibido = request.headers.get("Authorization", "")
    if not recibido.startswith("Bearer ") or not hmac.compare_digest(recibido[7:], token_admin):
        return jsonify({"exito": False, "mensaje": "Se requiere token de administrador"}), 403
    return None


def autorizar_administrador():
    if getattr(g, "usuario_autenticado", None) != "admin":
        return jsonify({"exito": False, "mensaje": "Se requiere token de administrador"}), 403
    return None


def bloquear_operacion_archivo(funcion):
    @wraps(funcion)
    def ejecutar(file_id, *args, **kwargs):
        with servicios()["catalogo"].bloquear_operacion(file_id):
            return funcion(file_id, *args, **kwargs)
    return ejecutar
