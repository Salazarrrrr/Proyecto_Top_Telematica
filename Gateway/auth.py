"""Autenticación y utilidades comunes para las rutas del Gateway."""

import hmac
import json
import os
import hashlib
import secrets
import threading
import time
import re
from functools import wraps
from pathlib import Path

from flask import current_app, g, jsonify, request

from Gateway.services import servicios


def registrar_seguridad(app):
    app.extensions["auth"] = cargar_usuarios()
    app.before_request(autenticar_solicitud)
    app.register_error_handler(413, carga_demasiado_grande)


def _archivo_usuarios():
    return Path(os.getenv("DFS_AUTH_USERS_FILE", "metadata/usuarios.json"))


def _hash_password(password, salt=None, iteraciones=310000):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iteraciones)
    return f"pbkdf2_sha256${iteraciones}${salt}${digest.hex()}"


def _verificar_password(password, almacenado):
    try:
        algoritmo, iteraciones, salt, esperado = almacenado.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        calculado = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iteraciones)
        ).hex()
        return hmac.compare_digest(calculado, esperado)
    except (AttributeError, ValueError):
        return False


def cargar_usuarios():
    """Carga usuarios persistentes y siembra los definidos por entorno."""
    ruta = _archivo_usuarios()
    usuarios = {}
    try:
        if ruta.exists():
            usuarios = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        usuarios = {}
    if not isinstance(usuarios, dict):
        usuarios = {}
    try:
        configurados = json.loads(os.getenv("DFS_USER_PASSWORDS", "{}"))
    except json.JSONDecodeError:
        configurados = {}
    roles = _roles_configurados()
    if isinstance(configurados, dict):
        for nombre, password in configurados.items():
            if isinstance(nombre, str) and isinstance(password, str) and password:
                actual = usuarios.get(nombre, {})
                usuarios[nombre] = {
                    "password": actual.get("password") or _hash_password(password),
                    "rol": roles.get(nombre, actual.get("rol", "usuario")),
                }
    if "admin" in usuarios:
        usuarios["admin"]["rol"] = "admin"
    estado = {"usuarios": usuarios, "sesiones": {}, "bloqueo": threading.RLock(), "ruta": ruta}
    if usuarios and not ruta.exists():
        guardar_usuarios(estado)
    return estado


def _roles_configurados():
    try:
        valores = json.loads(os.getenv("DFS_USER_ROLES", "{}"))
        return valores if isinstance(valores, dict) else {}
    except json.JSONDecodeError:
        return {}


def guardar_usuarios(estado):
    ruta = estado["ruta"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(estado["usuarios"], indent=2), encoding="utf-8")
    os.replace(temporal, ruta)


def _sesion_valida(estado, token):
    if not token:
        return None
    with estado["bloqueo"]:
        sesion = estado["sesiones"].get(token)
        if not sesion:
            return None
        if sesion["expira"] <= time.time():
            estado["sesiones"].pop(token, None)
            return None
        return sesion


def autenticar_solicitud():
    g.usuario_autenticado = None
    g.rol = None
    if request.path in {"/auth/login", "/auth/register", "/health"}:
        return None
    estado = current_app.extensions["auth"]
    recibido = request.headers.get("Authorization", "")
    token = recibido[7:] if recibido.startswith("Bearer ") else ""
    sesion = _sesion_valida(estado, token)
    if sesion:
        g.usuario_autenticado = sesion["usuario"]
        g.rol = sesion["rol"]
        return None
    admin = os.getenv("DFS_ADMIN_TOKEN", "")
    if admin and token and hmac.compare_digest(token, admin):
        g.usuario_autenticado = "admin"
        g.rol = "admin"
        return None
    if request.path == "/blocks" or request.path.startswith("/blocks/"):
        return jsonify({"exito": False, "mensaje": "Se requiere token de administrador"}), 403

    usuarios = os.getenv("DFS_USERS")
    if not usuarios:
        if estado["usuarios"]:
            return jsonify({"exito": False, "mensaje": "Autenticación requerida"}), 401
        return jsonify({
            "exito": False,
            "mensaje": "El Gateway requiere usuarios con contraseña o tokens configurados en DFS_USERS",
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
    for usuario, token_configurado in tokens_por_usuario.items():
        if hmac.compare_digest(token, token_configurado):
            g.usuario_autenticado = usuario
            g.rol = estado["usuarios"].get(usuario, {}).get("rol", "admin" if usuario == "admin" else "usuario")
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
    if getattr(g, "rol", None) != "admin":
        return jsonify({"exito": False, "mensaje": "Se requiere token de administrador"}), 403
    return None


def iniciar_sesion(usuario, password):
    estado = current_app.extensions["auth"]
    registro = estado["usuarios"].get(usuario)
    if not registro or not _verificar_password(password, registro.get("password")):
        return None
    token = secrets.token_urlsafe(32)
    duracion = int(os.getenv("DFS_SESSION_TTL", "28800"))
    with estado["bloqueo"]:
        estado["sesiones"][token] = {
            "usuario": usuario, "rol": registro.get("rol", "usuario"),
            "expira": time.time() + duracion,
        }
    return {"token": token, "usuario": usuario, "rol": registro.get("rol", "usuario"), "expira_en": duracion}


def cerrar_sesion(token):
    estado = current_app.extensions["auth"]
    with estado["bloqueo"]:
        return estado["sesiones"].pop(token, None) is not None


def crear_usuario(usuario, password, rol):
    estado = current_app.extensions["auth"]
    if rol not in {"usuario", "admin"}:
        raise ValueError("El rol debe ser usuario o admin")
    if not isinstance(usuario, str):
        raise ValueError("Nombre de usuario inválido")
    usuario = usuario.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", usuario):
        raise ValueError("El usuario debe tener entre 3 y 64 caracteres: letras, números, punto, guion o guion bajo")
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    with estado["bloqueo"]:
        if usuario in estado["usuarios"]:
            raise ValueError("El usuario ya existe")
        estado["usuarios"][usuario] = {"password": _hash_password(password), "rol": rol}
        guardar_usuarios(estado)
    return usuario


def registrar_usuario(usuario, password):
    """Registro público: nunca permite elegir ni elevar privilegios."""
    return crear_usuario(usuario, password, "usuario")


def bloquear_operacion_archivo(funcion):
    @wraps(funcion)
    def ejecutar(file_id, *args, **kwargs):
        with servicios()["catalogo"].bloquear_operacion(file_id):
            return funcion(file_id, *args, **kwargs)
    return ejecutar
