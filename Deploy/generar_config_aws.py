"""Genera secretos locales para el despliegue distribuido en AWS."""

import argparse
import base64
import json
import secrets
from pathlib import Path


def secreto_base64():
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def escribir(ruta, valores):
    ruta.write_text("\n".join(f"{clave}={valor}" for clave, valor in valores.items()) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-host", required=True, help="dominio público del Gateway")
    parser.add_argument("--nodes", required=True, help="tres IP privadas separadas por coma")
    parser.add_argument("--output-dir", default="Deploy/aws", help="directorio local de secretos")
    args = parser.parse_args()

    nodos = [ip.strip() for ip in args.nodes.split(",") if ip.strip()]
    if len(nodos) != 3:
        raise SystemExit("--nodes debe contener exactamente tres IP privadas")

    salida = Path(args.output_dir)
    salida.mkdir(parents=True, exist_ok=True)
    passwords = {"admin": secrets.token_urlsafe(18), "demo": secrets.token_urlsafe(18)}
    token_interno = secreto_base64()
    gateway = {
        "DFS_PUBLIC_HOST": args.public_host,
        "DFS_USER_PASSWORDS": "'" + json.dumps(passwords, separators=(",", ":")) + "'",
        "DFS_USER_ROLES": "'{\"admin\":\"admin\",\"demo\":\"usuario\"}'",
        "DFS_ADMIN_TOKEN": secreto_base64(),
        "DFS_NODE_TOKEN": token_interno,
        "DFS_NODES": ",".join(f"{ip}:50051" for ip in nodos),
    }
    escribir(salida / "gateway.env", gateway)
    for indice, ip in enumerate(nodos, start=1):
        escribir(salida / f"node{indice}.env", {
            "DFS_NODE_ID": f"{ip}:50051",
            "DFS_NODE_TOKEN": token_interno,
            "DFS_STORAGE_KEY": secreto_base64(),
        })
    print(f"Configuración creada en {salida.resolve()}")
    print(f"Contraseña admin: {passwords['admin']}")
    print(f"Contraseña demo:  {passwords['demo']}")
    print("Guarda las contraseñas ahora; los archivos generados contienen secretos.")


if __name__ == "__main__":
    main()
