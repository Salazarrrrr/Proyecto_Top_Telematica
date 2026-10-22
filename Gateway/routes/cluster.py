from flask import Blueprint, jsonify, request
import grpc

from Gateway.services import servicios
from Gateway.auth import autorizar_administrador

bp = Blueprint("cluster", __name__)

@bp.route("/cluster", methods=["GET"])
def estado_cluster():
    membresia = servicios()["cluster"].estado_nodos()
    servicios()["cluster"].difundir_membresia(membresia)
    return jsonify({
        "nodos": servicios()["cluster"].direcciones,
        "factor_replicacion": servicios()["cluster"].factor_replicacion,
        "quorum_lectura": servicios()["cluster"].quorum_lectura,
        "quorum_escritura": servicios()["cluster"].quorum_escritura,
        "asignador": "java" if servicios()["cluster"].java_cluster.activo else "python",
        "membresia": membresia,
    })


@bp.route("/cluster/rebalance", methods=["POST"])
def rebalancear_cluster():
    no_autorizado = autorizar_administrador()
    if no_autorizado:
        return no_autorizado
    datos = request.get_json(silent=True) or {}
    direccion = datos.get("direccion")
    if not direccion:
        return jsonify({"exito": False, "mensaje": "Falta la dirección del nodo"}), 400

    try:
        resultado = servicios()["cluster"].agregar_nodo_y_rebalancear(direccion, servicios()["catalogo"].todos())
    except (RuntimeError, grpc.RpcError) as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 503
    servicios()["cluster"].difundir_membresia()
    return jsonify({
        "exito": True,
        "nodo": direccion,
        "bloques_rebalanceados": resultado["copias_confirmadas"],
        "limpieza_pendiente": resultado["limpieza_pendiente"],
        "nodos": servicios()["cluster"].direcciones
    })


@bp.route("/cluster/replication", methods=["PUT"])
def cambiar_factor_replicacion():
    no_autorizado = autorizar_administrador()
    if no_autorizado:
        return no_autorizado
    datos = request.get_json(silent=True) or {}
    try:
        resultado = servicios()["cluster"].cambiar_factor_replicacion(
            datos.get("factor"), servicios()["catalogo"].todos()
        )
    except (TypeError, ValueError) as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 400
    except (RuntimeError, grpc.RpcError) as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 503
    return jsonify({
        "exito": True,
        "factor_replicacion": servicios()["cluster"].factor_replicacion,
        **resultado,
    })


@bp.route("/cluster/nodes/<path:direccion>", methods=["DELETE"])
def retirar_nodo(direccion):
    no_autorizado = autorizar_administrador()
    if no_autorizado:
        return no_autorizado
    if direccion not in servicios()["cluster"].direcciones:
        return jsonify({"exito": False, "mensaje": "Nodo no registrado"}), 404
    if len(servicios()["cluster"].direcciones) <= 1:
        return jsonify({"exito": False, "mensaje": "No se puede retirar el último nodo"}), 409
    try:
        bloques_migrados = servicios()["cluster"].salida_controlada(direccion, servicios()["catalogo"].todos())
        servicios()["cluster"].difundir_membresia()
    except (ValueError, RuntimeError, grpc.RpcError) as error:
        return jsonify({"exito": False, "mensaje": str(error)}), 503
    return jsonify({"exito": True, "nodo": direccion, "bloques_migrados": bloques_migrados,
                    "nodos": servicios()["cluster"].direcciones})
