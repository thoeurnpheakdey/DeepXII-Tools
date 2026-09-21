from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


PUBLIC_KEY_PATH = Path(__file__).resolve().parent.parent / "resources" / "license_public_key.pem"


@dataclass(frozen=True)
class LicenseInfo:
    machine_id: str
    license_id: str
    issued_at: str
    plan: str


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_activation_code(code: str, machine_id: str) -> tuple[bool, LicenseInfo | None, str]:
    try:
        payload_text, signature_text = code.strip().split(".", 1)
        payload_bytes = _decode(payload_text)
        signature = _decode(signature_text)
        public_key = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
        if not isinstance(public_key, Ed25519PublicKey):
            return False, None, "Invalid activation public key"
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
    except (ValueError, TypeError, json.JSONDecodeError, InvalidSignature):
        return False, None, "Invalid activation code"
    except OSError as exc:
        return False, None, f"Could not read activation data: {exc}"


def create_activation_code(private_key_path: Path, machine_id: str, license_id: str, plan: str = "lifetime") -> str:
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    payload = {
        "machine_id": machine_id.strip().lower(),
        "license_id": license_id,
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": plan,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = private_key.sign(payload_bytes)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"{encode(payload_bytes)}.{encode(signature)}"
