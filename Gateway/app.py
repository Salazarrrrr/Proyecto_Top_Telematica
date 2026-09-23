from flask import Flask, jsonify, request
import uuid

from node_client import NodeClient
from particionar import dividir_archivo

app = Flask(__name__)
node_client = NodeClient()


@app.route("/blocks", methods=["POST"])
def escribir_bloque():
    datos = request.get_json()

    respuesta = node_client.escribir_bloque(
        block_id=datos["block_id"],
        file_id=datos["file_id"],
        posicion=datos["posicion"],
        contenido=datos["contenido"].encode(),
        checksum=datos.get("checksum", "")
    )

    return jsonify({
        "exito": respuesta.exito,
        "mensaje": respuesta.mensaje,
        "block_id": respuesta.block_id
    })


@app.route("/blocks/<block_id>", methods=["GET"])
def leer_bloque(block_id):
    respuesta = node_client.leer_bloque(block_id)

    if not respuesta.exito:
        return jsonify({
            "exito": False,
            "mensaje": respuesta.mensaje
        }), 404

    return jsonify({
        "exito": True,
        "mensaje": respuesta.mensaje,
        "block_id": respuesta.block_id,
        "contenido": respuesta.contenido.decode(),
        "checksum": respuesta.checksum
    })


@app.route("/blocks/<block_id>", methods=["DELETE"])
def eliminar_bloque(block_id):
    respuesta = node_client.eliminar_bloque(block_id)

    return jsonify({
        "exito": respuesta.exito,
        "mensaje": respuesta.mensaje
    })


@app.route("/files", methods=["POST"])
def subir_archivo():
    ruta_archivo = request.json["ruta"]
    file_id = str(uuid.uuid4())

    bloques = 0

    for posicion, contenido in dividir_archivo(ruta_archivo):

        block_id = f"{file_id}-{posicion}"

        respuesta = node_client.escribir_bloque(
            block_id=block_id,
            file_id=file_id,
            posicion=posicion,
            contenido=contenido,
            checksum=""
        )

        if not respuesta.exito:
            return jsonify({
                "exito": False,
                "mensaje": respuesta.mensaje
            }), 500

        bloques += 1

    return jsonify({
        "exito": True,
        "file_id": file_id,
        "bloques": bloques,
        "mensaje": "Archivo dividido y almacenado correctamente"
    })


if __name__ == "__main__":
    app.run(port=8000, debug=True)