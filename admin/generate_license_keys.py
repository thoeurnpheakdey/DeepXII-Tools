from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_KEY = Path(__file__).resolve().parent / "license_private_key.pem"
PUBLIC_KEY = ROOT / "resources" / "license_public_key.pem"


def main() -> None:
    if PRIVATE_KEY.exists():
        raise SystemExit(f"Private key already exists: {PRIVATE_KEY}")
    key = Ed25519PrivateKey.generate()
    PRIVATE_KEY.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Private key (keep secret): {PRIVATE_KEY}")
    print(f"Public key (bundle with app): {PUBLIC_KEY}")


if __name__ == "__main__":
    main()
