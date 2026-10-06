import argparse
import http.client
import json
import os
import posixpath
import shlex
import ssl
import tempfile
import uuid
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


GATEWAY = os.getenv("DFS_GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_USER = os.getenv("DFS_DEFAULT_USER", "demo")


def contexto_https(url):
    if urlsplit(url).scheme != "https":
        return None
    ca = os.getenv("DFS_GATEWAY_TLS_CA")
    return ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()


def solicitar(method, path, datos=None, usuario=None):
    cuerpo = None
    headers = {"Accept": "application/json"}
    token = token_para_usuario(usuario or (datos.get("usuario") if datos else None))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if datos is not None:
        cuerpo = json.dumps(datos).encode("utf-8")
        headers["Content-Type"] = "application/json"
    respuesta = urlopen(
        Request(GATEWAY + path, data=cuerpo, headers=headers, method=method),
        timeout=30, context=contexto_https(GATEWAY),
    )
    return json.loads(respuesta.read().decode("utf-8"))


def token_para_usuario(usuario=None):
    identidad = os.getenv("DFS_DEFAULT_USER", DEFAULT_USER)
    usuario = usuario or identidad
    if usuario != identidad:
        raise ValueError(
            f"Esta CLI está autenticada como '{identidad}' y no puede cambiar a '{usuario}'"
        )
    token = os.getenv("DFS_USER_TOKEN")
    if not token:
        raise ValueError("Define DFS_USER_TOKEN con el token individual de este usuario")
    return token


def subir_archivo_local(ruta, usuario, directorio="/"):
    ruta = os.path.abspath(ruta)
    if not os.path.isfile(ruta):
        raise ValueError("No se encontró el archivo local")
    destino = urlsplit(GATEWAY)
    conexion_cls = http.client.HTTPSConnection if destino.scheme == "https" else http.client.HTTPConnection
    conexion_args = {"timeout": 120}
    if destino.scheme == "https":
        conexion_args["context"] = contexto_https(GATEWAY)
    conexion = conexion_cls(destino.hostname, destino.port, **conexion_args)
    boundary = "----DFSha" + uuid.uuid4().hex
    nombre = os.path.basename(ruta).replace('"', "_").replace("\r", "_").replace("\n", "_")
    inicio = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"usuario\"\r\n\r\n"
        f"{usuario}\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"directorio\"\r\n\r\n"
        f"{directorio}\r\n--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"archivo\"; filename=\"{nombre}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    fin = f"\r\n--{boundary}--\r\n".encode("ascii")
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(inicio) + os.path.getsize(ruta) + len(fin)),
        "Accept": "application/json",
    }
    token = token_para_usuario(usuario)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        conexion.putrequest("POST", (destino.path or "") + "/files")
        for nombre_header, valor in headers.items():
            conexion.putheader(nombre_header, valor)
        conexion.endheaders()
        conexion.send(inicio)
        with open(ruta, "rb") as origen:
            while fragmento := origen.read(1024 * 1024):
                conexion.send(fragmento)
        conexion.send(fin)
        respuesta = conexion.getresponse()
        cuerpo = respuesta.read().decode("utf-8")
        if respuesta.status >= 400:
            try:
                mensaje = json.loads(cuerpo).get("mensaje", cuerpo)
            except json.JSONDecodeError:
                mensaje = cuerpo
            raise ValueError(f"HTTP {respuesta.status}: {mensaje}")
        return json.loads(cuerpo)
    finally:
        conexion.close()


def descargar_archivo_remoto(file_id, usuario, salida):
    destino = urlsplit(GATEWAY)
    conexion_cls = http.client.HTTPSConnection if destino.scheme == "https" else http.client.HTTPConnection
    conexion_args = {"timeout": 120}
    if destino.scheme == "https":
        conexion_args["context"] = contexto_https(GATEWAY)
    conexion = conexion_cls(destino.hostname, destino.port, **conexion_args)
    path = (destino.path or "").rstrip("/") + f"/files/{quote(file_id, safe='')}?"
    path += urlencode({"usuario": usuario})
    headers = {"Accept": "application/octet-stream"}
    token = token_para_usuario(usuario)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    salida = os.path.abspath(salida)
    temporal = None
    try:
        conexion.request("GET", path, headers=headers)
        respuesta = conexion.getresponse()
        if respuesta.status >= 400:
            cuerpo = respuesta.read().decode("utf-8", errors="replace")
            try:
                mensaje = json.loads(cuerpo).get("mensaje", cuerpo)
            except json.JSONDecodeError:
                mensaje = cuerpo
            raise ValueError(f"HTTP {respuesta.status}: {mensaje}")

        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".dfsha-download-", dir=os.path.dirname(salida), delete=False
        ) as archivo:
            temporal = archivo.name
            while fragmento := respuesta.read(1024 * 1024):
                archivo.write(fragmento)
        os.replace(temporal, salida)
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)
        conexion.close()


def buscar_archivo(identificador, usuario, directorio_actual="/"):
    archivos = solicitar("GET", "/files?" + urlencode({"usuario": usuario}), usuario=usuario)["archivos"]
    for archivo in archivos:
        if archivo["file_id"] == identificador:
            return archivo
    ruta = ruta_remota(directorio_actual, identificador) if "/" in identificador else None
    if ruta:
        for archivo in archivos:
            if posixpath.join(archivo.get("directorio", "/"), archivo["nombre"]) == ruta:
                return archivo
    locales = [archivo for archivo in archivos if
               archivo["nombre"] == identificador and archivo.get("directorio", "/") == directorio_actual]
    if len(locales) == 1:
        return locales[0]
    globales = [archivo for archivo in archivos if archivo["nombre"] == identificador]
    if len(globales) == 1:
        return globales[0]
    if len(globales) > 1:
        raise ValueError("Nombre ambiguo; usa la ruta completa o el file_id")
    raise ValueError("Archivo no encontrado")


def comando_store(args):
    respuesta = subir_archivo_local(args.archivo, args.usuario, args.directorio)
    print(json.dumps(respuesta, indent=2, ensure_ascii=True))


def comando_list(args):
    respuesta = solicitar(
        "GET", "/files?" + urlencode({"usuario": args.usuario}), usuario=args.usuario
    )
    for archivo in respuesta["archivos"]:
        print(f"{archivo['nombre']} ({archivo['file_id']}) - {len(archivo['bloques'])} bloque(s)")


def comando_get(args):
    archivo = buscar_archivo(args.identificador, args.usuario, args.directorio)
    salida = args.salida or archivo["nombre"]
    descargar_archivo_remoto(archivo["file_id"], args.usuario, salida)
    print(f"Archivo recuperado: {salida}")


def comando_delete(args):
    archivo = buscar_archivo(args.identificador, args.usuario, args.directorio)
    respuesta = solicitar(
        "DELETE",
        f"/files/{archivo['file_id']}?" + urlencode({"usuario": args.usuario}),
        usuario=args.usuario,
    )
    print(respuesta["mensaje"])


def ruta_remota(actual, ruta):
    base = "/" if ruta.startswith("/") else actual
    resultado = posixpath.normpath(posixpath.join(base, ruta or "."))
    return resultado if resultado.startswith("/") else "/"


def comando_ls(args):
    path = urlencode({"path": args.ruta})
    contenido = solicitar("GET", "/directories?" + path, usuario=args.usuario)
    print(f"{contenido['ruta']}/")
    for nombre in contenido["directorios"]:
        print(f"{nombre}/")
    for archivo in contenido["archivos"]:
        print(f"{archivo['nombre']} ({archivo['file_id']})")


def comando_mkdir(args):
    respuesta = solicitar(
        "POST", "/directories", {"path": args.ruta, "usuario": args.usuario}, usuario=args.usuario
    )
    print(respuesta["ruta"])


def comando_rmdir(args):
    respuesta = solicitar(
        "DELETE", "/directories?" + urlencode({"path": args.ruta, "usuario": args.usuario}),
        usuario=args.usuario,
    )
    print(respuesta["mensaje"])


def comando_shell(args):
    actual = "/"
    print("Cliente interactivo DFSha. Escribe 'help' para ver los comandos.")
    while True:
        try:
            entrada = input(f"dfsha:{actual}$ ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        try:
            partes = shlex.split(entrada)
            if not partes:
                continue
            comando, *valores = partes
            if comando in {"exit", "quit"}:
                return
            if comando in {"help", "ayuda"}:
                print("""Comandos disponibles:
  pwd                         muestra la carpeta remota actual
  ls [ruta]                   lista carpetas y archivos
  cd <ruta>                   cambia la carpeta remota
  mkdir <ruta>                crea una carpeta remota
  rmdir <ruta>                elimina una carpeta vacía
  store <archivo_local>       sube un archivo a la carpeta actual
  get <nombre_o_id> [salida]  descarga un archivo
  rm <nombre_o_id>            elimina un archivo
  exit                        cierra el cliente""")
            if comando == "pwd":
                print(actual)
            elif comando == "ls":
                destino = ruta_remota(actual, valores[0] if valores else ".")
                contenido = solicitar("GET", "/directories?" + urlencode({"path": destino}), usuario=args.usuario)
                print(f"{contenido['ruta']}/")
                for nombre in contenido["directorios"]:
                    print(f"{nombre}/")
                for archivo in contenido["archivos"]:
                    print(f"{archivo['nombre']} ({archivo['file_id']})")
            elif comando == "cd":
                destino = ruta_remota(actual, valores[0] if valores else "/")
                solicitar("GET", "/directories?" + urlencode({"path": destino}), usuario=args.usuario)
                actual = destino
            elif comando == "mkdir" and valores:
                comando_mkdir(type("Args", (), {"ruta": ruta_remota(actual, valores[0]), "usuario": args.usuario})())
            elif comando == "rmdir" and valores:
                comando_rmdir(type("Args", (), {"ruta": ruta_remota(actual, valores[0]), "usuario": args.usuario})())
            elif comando == "store" and valores:
                print(json.dumps(subir_archivo_local(valores[0], args.usuario, actual), indent=2))
            elif comando == "get" and valores:
                archivo = buscar_archivo(valores[0], args.usuario, actual)
                salida = valores[1] if len(valores) > 1 else archivo["nombre"]
                descargar_archivo_remoto(archivo["file_id"], args.usuario, salida)
                print(f"Archivo recuperado: {salida}")
            elif comando in {"rm", "delete"} and valores:
                comando_delete(type("Args", (), {
                    "identificador": valores[0],
                    "usuario": args.usuario,
                    "directorio": actual,
                })())
            else:
                print("Comando inválido o faltan argumentos")
        except (HTTPError, ValueError, OSError, http.client.HTTPException, KeyError) as error:
            print(f"Error: {error}")


def crear_parser():
    parser = argparse.ArgumentParser(description="Cliente de consola de DFSha")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    store = subparsers.add_parser("store", aliases=["send"])
    store.add_argument("archivo")
    store.add_argument("--usuario", default=DEFAULT_USER)
    store.add_argument("--directorio", default="/")
    store.set_defaults(func=comando_store)

    listar = subparsers.add_parser("list")
    listar.add_argument("--usuario", default=DEFAULT_USER)
    listar.set_defaults(func=comando_list)

    ls = subparsers.add_parser("ls")
    ls.add_argument("--ruta", default="/")
    ls.add_argument("--usuario", default=DEFAULT_USER)
    ls.set_defaults(func=comando_ls)

    mkdir = subparsers.add_parser("mkdir")
    mkdir.add_argument("ruta")
    mkdir.add_argument("--usuario", default=DEFAULT_USER)
    mkdir.set_defaults(func=comando_mkdir)

    rmdir = subparsers.add_parser("rmdir")
    rmdir.add_argument("ruta")
    rmdir.add_argument("--usuario", default=DEFAULT_USER)
    rmdir.set_defaults(func=comando_rmdir)

    shell = subparsers.add_parser("shell")
    shell.add_argument("--usuario", default=DEFAULT_USER)
    shell.set_defaults(func=comando_shell)

    get = subparsers.add_parser("get", aliases=["receive"])
    get.add_argument("identificador")
    get.add_argument("--usuario", default=DEFAULT_USER)
    get.add_argument("--salida")
    get.add_argument("--directorio", default="/")
    get.set_defaults(func=comando_get)

    delete = subparsers.add_parser("delete", aliases=["rm"])
    delete.add_argument("identificador")
    delete.add_argument("--usuario", default=DEFAULT_USER)
    delete.add_argument("--directorio", default="/")
    delete.set_defaults(func=comando_delete)

    return parser


if __name__ == "__main__":
    try:
        argumentos = crear_parser().parse_args()
        argumentos.func(argumentos)
    except (HTTPError, ValueError, OSError, http.client.HTTPException) as error:
        print(f"Error: {error}")
        raise SystemExit(1)
