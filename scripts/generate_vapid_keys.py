"""Gera um par VAPID para Web Push sem gravar a chave privada em arquivo."""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


private_key = ec.generate_private_key(ec.SECP256R1())
private_der = private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
)
public_raw = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)

print("Copie os valores abaixo para a Vercel. Não envie a chave privada a ninguém.\n")
print(f"VAPID_PUBLIC_KEY={base64url(public_raw)}")
print(f"VAPID_PRIVATE_KEY={base64url(private_der)}")
print("VAPID_CLAIMS_EMAIL=seu-email@dominio.com")
