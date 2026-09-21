from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


PUBLIC_KEY_PATH = Path(__file__).resolve().parent.parent / "resources" / "license_public_key.pem"
CODE_PREFIX = "DEEPXII-"


@dataclass(frozen=True)
class LicenseInfo:
    machine_id: str
    license_id: str
    issued_at: str
    plan: str


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _machine_message(machine_id: str) -> bytes:
    return f"DEEPXII:{machine_id.strip().lower()}".encode("ascii")


def verify_activation_code(code: str, machine_id: str) -> tuple[bool, LicenseInfo | None, str]:
    if not code.strip():
        return False, None, "Activation code is required"
    try:
        public_key = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
        if not isinstance(public_key, Ed25519PublicKey):
            return False, None, "Invalid activation public key"

        normalized = code.strip().upper()
        if normalized.startswith(CODE_PREFIX):
            encoded_signature = normalized[len(CODE_PREFIX):]
            signature = base64.b32decode(
                encoded_signature + "=" * (-len(encoded_signature) % 8)
            )
            if len(signature) != 64:
                return False, None, "Invalid activation code"
            licensed_machine = machine_id.strip().lower()
            public_key.verify(signature, _machine_message(licensed_machine))
            info = LicenseInfo(
                machine_id=licensed_machine,
                license_id=hashlib.sha256(signature).hexdigest()[:12].upper(),
                issued_at="",
                plan="lifetime",
            )
            return True, info, "Activated"

        # Continue accepting the previous signed-payload format so existing
        # customers are not locked out after upgrading the application.
        payload_text, signature_text = code.strip().split(".", 1)
        payload_bytes = _decode(payload_text)
        signature = _decode(signature_text)
        public_key.verify(signature, payload_bytes)
        payload = json.loads(payload_bytes.decode("utf-8"))
        licensed_machine = str(payload.get("machine_id") or "").lower()
        if licensed_machine != machine_id.strip().lower():
            return False, None, "This activation code belongs to another computer"
        info = LicenseInfo(
            machine_id=licensed_machine,
            license_id=str(payload.get("license_id") or ""),
            issued_at=str(payload.get("issued_at") or ""),
            plan=str(payload.get("plan") or "lifetime"),
        )
        if not info.license_id:
            return False, None, "Activation code is missing its license ID"
        return True, info, "Activated"
    except FileNotFoundError:
        return False, None, "Activation public key is missing"
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, InvalidSignature):
        return False, None, "Invalid activation code"
    except OSError as exc:
        return False, None, f"Could not read activation data: {exc}"


def create_activation_code(
    private_key_path: Path, machine_id: str, license_id: str, plan: str = "lifetime"
) -> str:
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("The activation private key must be an Ed25519 key")
    # The Machine ID is already known by the app, so it does not need to be
    # repeated inside the code. Keeping only the signature makes the code much
    # shorter while retaining full Ed25519 verification strength.
    del license_id, plan
    signature = private_key.sign(_machine_message(machine_id))
    encoded_signature = base64.b32encode(signature).decode("ascii").rstrip("=")
    return f"{CODE_PREFIX}{encoded_signature}"
