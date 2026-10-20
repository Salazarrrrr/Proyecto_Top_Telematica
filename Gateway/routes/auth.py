from flask import Blueprint, jsonify, request, g

from Gateway.auth import autorizar_administrador, cerrar_sesion, crear_usuario, iniciar_sesion

bp = Blueprint("auth", __name__)


@bp.post("/auth/login")
def login():
    datos = request.get_json(silent=True) or {}
    usuario = datos.get("usuario")
    password = datos.get("password")
    if not isinstance(usuario, str) or not isinstance(password, str):
        return jsonify({"exito": False, "mensaje": "Envía usuario y password"}), 400
    sesion = iniciar_sesion(usuario, password)
    if not sesion:
        return jsonify({"exito": False, "mensaje": "Usuario o contraseña incorrectos"}), 401
    return jsonify({"exito": True, **sesion})


@bp.post("/auth/logout")
def logout():
    token = request.headers.get("Authorization", "")
    token = token[7:] if token.startswith("Bearer ") else ""
    cerrar_sesion(token)
    return jsonify({"exito": True, "mensaje": "Sesión cerrada"})


@bp.get("/auth/me")
def me():
    # La identidad ya fue validada por before_request; no se exponen contraseñas.
    return jsonify({"exito": True, "usuario": g.usuario_autenticado, "rol": g.rol})


@bp.post("/auth/users")
def users_create():
    no_autorizado = autorizar_administrador()
    if no_autorizado:
        return no_autorizado
    datos = request.get_json(silent=True) or {}
    try:
        crear_usuario(datos.get("usuario"), datos.get("password"), datos.get("rol", "usuario"))
    except ValueError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 400
    return jsonify({"exito": True, "usuario": datos["usuario"], "rol": datos.get("rol", "usuario")}), 201
