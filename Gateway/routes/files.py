from flask import Blueprint, current_app, jsonify, request, send_file
import hashlib
import grpc
import os
import tempfile
import uuid
from pathlib import Path

from Gateway.auth import bloquear_operacion_archivo, usuario_solicitante
from Gateway.particionar import dividir_archivo
from Gateway.services import servicios

bp = Blueprint("files", __name__)

@bp.route("/files", methods=["GET"])
def listar_archivos():
    usuario = usuario_solicitante()
    return jsonify({"exito": True, "archivos": servicios()["catalogo"].listar(usuario)})


@bp.route("/files", methods=["POST"])
def subir_archivo():
    archivo_subido = request.files.get("archivo")
    usuario = usuario_solicitante()
    if archivo_subido is not None:
        nombre = Path(archivo_subido.filename or "").name
        if not nombre:
            return jsonify({"exito": False, "mensaje": "Falta el nombre del archivo"}), 400
        directorio = request.form.get("directorio", "/")
        try:
            servicios()["catalogo"].listar_directorio(usuario, directorio)
        except FileNotFoundError:
            return jsonify({"exito": False, "mensaje": "Directorio remoto no encontrado"}), 404
        except ValueError as error:
            return jsonify({"exito": False, "mensaje": str(error)}), 400
        temporal = tempfile.NamedTemporaryFile(prefix="dfsha-upload-", delete=False)
        temporal.close()
        ruta_archivo = Path(temporal.name)
        try:
            archivo_subido.save(ruta_archivo)
            return almacenar_archivo(ruta_archivo, usuario, nombre, directorio)
        finally:
            ruta_archivo.unlink(missing_ok=True)

    return jsonify({"exito": False, "mensaje": "Envía el archivo como multipart/form-data"}), 400


def almacenar_archivo(ruta_archivo, usuario, nombre, directorio="/"):
    if not ruta_archivo.is_file():
        return jsonify({"exito": False, "mensaje": "No se encontró el archivo de origen"}), 400
    try:
        tamano_inicial = ruta_archivo.stat().st_size
    except OSError as error:
        return jsonify({"exito": False, "mensaje": f"No se pudo inspeccionar el archivo: {error}"}), 400
    if tamano_inicial > current_app.config["MAX_CONTENT_LENGTH"]:
        return jsonify({"exito": False, "mensaje": "El archivo supera el límite configurado"}), 413

    file_id = str(uuid.uuid4())
    bloques = 0
    tamano_archivo = 0
    metadatos_bloques = []

    try:
        for posicion, contenido in dividir_archivo(ruta_archivo):

            block_id = f"{file_id}-{posicion}"
            if tamano_archivo + len(contenido) > current_app.config["MAX_CONTENT_LENGTH"]:
                for bloque in metadatos_bloques:
                    servicios()["cluster"].eliminar_bloque(bloque["block_id"])
                return jsonify({"exito": False, "mensaje": "El archivo superó el límite configurado durante la lectura"}), 413
            checksum = hashlib.sha256(contenido).hexdigest()

            exito, mensaje = servicios()["cluster"].escribir_bloque(
                block_id, file_id, posicion, contenido, checksum
            )

            if not exito:
                for bloque in metadatos_bloques:
                    servicios()["cluster"].eliminar_bloque(bloque["block_id"])
                servicios()["cluster"].eliminar_bloque(block_id)
                return jsonify({"exito": False, "mensaje": mensaje}), 503

            metadatos_bloques.append({
                "block_id": block_id,
                "posicion": posicion,
                "tamano": len(contenido),
                "checksum": checksum
            })
            tamano_archivo += len(contenido)
            bloques += 1
    except OSError as error:
        for bloque in metadatos_bloques:
            servicios()["cluster"].eliminar_bloque(bloque["block_id"])
        return jsonify({"exito": False, "mensaje": f"No se pudo leer el archivo: {error}"}), 400

    archivo = {
        "file_id": file_id,
        "usuario": usuario,
        "nombre": nombre,
        "directorio": servicios()["catalogo"].normalizar_ruta(directorio),
        "tamano": tamano_archivo,
        "bloques": metadatos_bloques
    }
    try:
        servicios()["catalogo"].guardar(archivo)
    except (OSError, ValueError) as error:
        for bloque in metadatos_bloques:
            servicios()["cluster"].eliminar_bloque(bloque["block_id"])
        return jsonify({"exito": False, "mensaje": f"No se pudo guardar el catálogo: {error}"}), 500

    return jsonify({
        "exito": True,
        "file_id": file_id,
        "nombre": nombre,
        "bloques": bloques,
        "mensaje": "Archivo dividido y almacenado correctamente"
    })


@bp.route("/files/<file_id>", methods=["GET"])
@bloquear_operacion_archivo
def descargar_archivo(file_id):
    usuario = usuario_solicitante()
    archivo = servicios()["catalogo"].obtener(file_id)

    if archivo is None or archivo["usuario"] != usuario:
        return jsonify({"exito": False, "mensaje": "Archivo no encontrado"}), 404

    contenido = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode="w+b")
    for bloque in sorted(archivo["bloques"], key=lambda dato: dato["posicion"]):
        respuesta = servicios()["cluster"].leer_bloque(bloque["block_id"])
        if respuesta is None:
            contenido.close()
            return jsonify({
                "exito": False,
                "mensaje": "No hay quórum de réplicas disponible para un bloque"
            }), 503

        if hashlib.sha256(respuesta.contenido).hexdigest() != bloque["checksum"]:
            contenido.close()
            return jsonify({
                "exito": False,
                "mensaje": "El checksum del bloque no coincide"
            }), 500
        contenido.write(respuesta.contenido)

    contenido.seek(0)
    respuesta = send_file(
        contenido,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=archivo["nombre"],
        conditional=False,
    )
    respuesta.call_on_close(contenido.close)
    respuesta.headers["X-DFS-File-ID"] = file_id
    return respuesta


@bp.route("/files/<file_id>", methods=["DELETE"])
@bloquear_operacion_archivo
def eliminar_archivo(file_id):
    usuario = usuario_solicitante()
    archivo = servicios()["catalogo"].obtener(file_id)

    if archivo is None or archivo["usuario"] != usuario:
        return jsonify({"exito": False, "mensaje": "Archivo no encontrado"}), 404

    for bloque in archivo["bloques"]:
        if not servicios()["cluster"].eliminar_bloque(bloque["block_id"]):
            return jsonify({
                "exito": False,
                "mensaje": "No se pudo confirmar el borrado en todos los nodos; se conservan los metadatos para reintentar"
            }), 503
    servicios()["catalogo"].eliminar(file_id)

    return jsonify({"exito": True, "mensaje": "Archivo eliminado correctamente"})
