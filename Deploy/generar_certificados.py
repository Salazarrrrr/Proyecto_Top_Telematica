"""Crea certificados de laboratorio TLS para Compose (no para producción)."""

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import argparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def crear_llave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def serializar_llave(llave):
    return llave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def emitir_certificado(nombre, llave_publica, ca_cert, ca_key, sans, ahora):
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nombre)])
    return (
        x509.CertificateBuilder()
        .subject_name(sujeto)
        .issuer_name(ca_cert.subject)
        .public_key(llave_publica)
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(ahora + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(llave_publica), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
                ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="reemplaza solamente los certificados de laboratorio ya generados",
    )
    parser.add_argument(
        "--gateway-host", default="localhost",
        help="nombre DNS o dirección IP con la que los clientes accederán al Gateway",
    )
    args = parser.parse_args()
    destino = Path(__file__).resolve().parent / "certs"
    destino.mkdir(parents=True, exist_ok=True)
    nombres_esperados = {
        "ca.key", "ca.crt", "nodes.key", "nodes.crt", "gateway.key", "gateway.crt"
    }
    existentes = {p.name for p in destino.iterdir() if p.is_file()} & nombres_esperados
    if existentes:
        if args.force:
            for nombre in existentes:
                (destino / nombre).unlink()
            existentes.clear()
    if existentes:
        faltantes = nombres_esperados - existentes
        if faltantes:
            raise SystemExit("Conjunto de certificados incompleto; no reemplazo llaves existentes")
        print(f"Certificados ya existentes preservados en {destino}")
        return

    ahora = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DFSha-Lab-CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(ahora + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    nodos_key = crear_llave()
    nodos_cert = emitir_certificado(
        "dfsha-nodes", nodos_key.public_key(), ca_cert, ca_key,
        [x509.DNSName(host) for host in ("node1", "node2", "node3", "localhost")]
        + [x509.IPAddress(ip_address("127.0.0.1"))], ahora,
    )
    try:
        gateway_san = x509.IPAddress(ip_address(args.gateway_host))
    except ValueError:
        gateway_san = x509.DNSName(args.gateway_host)
    gateway_key = crear_llave()
    gateway_cert = emitir_certificado(
        args.gateway_host, gateway_key.public_key(), ca_cert, ca_key,
        [x509.DNSName("localhost"), x509.DNSName("gateway"),
         x509.IPAddress(ip_address("127.0.0.1")), gateway_san], ahora,
    )

    artefactos = {
        "ca.key": serializar_llave(ca_key),
        "ca.crt": ca_cert.public_bytes(serialization.Encoding.PEM),
        "nodes.key": serializar_llave(nodos_key),
        "nodes.crt": nodos_cert.public_bytes(serialization.Encoding.PEM),
        "gateway.key": serializar_llave(gateway_key),
        "gateway.crt": gateway_cert.public_bytes(serialization.Encoding.PEM),
    }
    for nombre, contenido in artefactos.items():
        (destino / nombre).write_bytes(contenido)
    print(f"Certificados TLS de laboratorio creados en {destino}")
    print("No uses esta CA ni sus certificados en producción.")


if __name__ == "__main__":
    main()
