from flask import Blueprint, jsonify, request
import base64
import grpc

from Gateway.auth import autorizar_diagnostico
from Gateway.services import servicios

bp = Blueprint("blocks", __name__)

@bp.route("/blocks", methods=["POST"])
def escribir_bloque():
    no_autorizado = autorizar_diagnostico()
    if no_autorizado:
        return no_autorizado
    datos = request.get_json(silent=True) or {}
    requeridos = {"block_id", "file_id", "posicion", "contenido"}
    if not requeridos.issubset(datos):
        return jsonify({"exito": False, "mensaje": "Faltan campos obligatorios"}), 400
    try:
        contenido = base64.b64decode(datos["contenido"], validate=True)
    except (ValueError, TypeError):
        return jsonify({"exito": False, "mensaje": "El contenido no es Base64 válido"}), 400

    try:
        respuesta = servicios()["node_client"].escribir_bloque(
            block_id=datos["block_id"], file_id=datos["file_id"],
            posicion=datos["posicion"], contenido=contenido,
            checksum=datos.get("checksum", ""), timeout=servicios()["cluster"].timeout,
        )
    except grpc.RpcError as error:
        return jsonify({"exito": False, "mensaje": error.code().name}), 503

    return jsonify({
        "exito": respuesta.exito,
        "mensaje": respuesta.mensaje,
        "block_id": respuesta.block_id
    })


@bp.route("/blocks/<block_id>", methods=["GET"])
def leer_bloque(block_id):
    no_autorizado = autorizar_diagnostico()
    if no_autorizado:
        return no_autorizado
    try:
        respuesta = servicios()["node_client"].leer_bloque(block_id, timeout=servicios()["cluster"].timeout)
    except grpc.RpcError as error:
        return jsonify({"exito": False, "mensaje": error.code().name}), 503

    if not respuesta.exito:
        return jsonify({
            "exito": False,
            "mensaje": respuesta.mensaje
        }), 404

    return jsonify({
        "exito": True,
        "mensaje": respuesta.mensaje,
        "block_id": respuesta.block_id,
        "contenido": base64.b64encode(respuesta.contenido).decode("ascii"),
        "checksum": respuesta.checksum
    })


@bp.route("/blocks/<block_id>", methods=["DELETE"])
def eliminar_bloque(block_id):
    no_autorizado = autorizar_diagnostico()
    if no_autorizado:
        return no_autorizado
    try:
        respuesta = servicios()["node_client"].eliminar_bloque(block_id, timeout=servicios()["cluster"].timeout)
    except grpc.RpcError as error:
        return jsonify({"exito": False, "mensaje": error.code().name}), 503

    return jsonify({
        "exito": respuesta.exito,
        "mensaje": respuesta.mensaje
    })
