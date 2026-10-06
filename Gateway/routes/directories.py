from flask import Blueprint, jsonify, request

from Gateway.auth import usuario_solicitante
from Gateway.services import servicios

bp = Blueprint("directories", __name__)

@bp.route("/directories", methods=["GET"])
def listar_directorio():
    usuario = usuario_solicitante()
    ruta = request.args.get("path", "/")
    try:
        contenido = servicios()["catalogo"].listar_directorio(usuario, ruta)
    except FileNotFoundError:
        return jsonify({"exito": False, "mensaje": "Directorio no encontrado"}), 404
    except ValueError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 400
    return jsonify({"exito": True, **contenido})


@bp.route("/directories", methods=["POST"])
def crear_directorio():
    usuario = usuario_solicitante()
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos, dict) or not datos.get("path"):
        return jsonify({"exito": False, "mensaje": "Falta path"}), 400
    try:
        ruta = servicios()["catalogo"].crear_directorio(usuario, datos["path"])
    except FileNotFoundError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 404
    except ValueError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 400
    return jsonify({"exito": True, "ruta": ruta}), 201


@bp.route("/directories", methods=["DELETE"])
def eliminar_directorio():
    usuario = usuario_solicitante()
    ruta = request.args.get("path", "")
    try:
        servicios()["catalogo"].eliminar_directorio(usuario, ruta)
    except FileNotFoundError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 404
    except ValueError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 400
    except OSError as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 409
    return jsonify({"exito": True, "mensaje": "Directorio eliminado"})
