from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


private_key_path = Path(__file__).with_name("license_private_key.pem")
private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
if not isinstance(private_key, Ed25519PrivateKey):
    raise SystemExit("The license key is not Ed25519")

seed = private_key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption(),
)
print("LICENSE_PRIVATE_KEY_SEED=" + base64.b64encode(seed).decode("ascii"))
