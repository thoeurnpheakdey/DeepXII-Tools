from __future__ import annotations

import base64
import re
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parent.parent
BOT_ENV = ROOT / "admin" / "bot.env"
LARAVEL_ENV = ROOT / "activation-server" / ".env"
PRIVATE_KEY = ROOT / "admin" / "license_private_key.pem"


def read_simple_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def replace(text: str, name: str, value: str) -> str:
    line = f"{name}={value}"
    pattern = re.compile(rf"^{re.escape(name)}=.*$", re.MULTILINE)
    return pattern.sub(line, text) if pattern.search(text) else text.rstrip() + "\n" + line + "\n"


if not BOT_ENV.exists() or not PRIVATE_KEY.exists() or not LARAVEL_ENV.exists():
    raise SystemExit("Missing bot.env, license_private_key.pem, or activation-server/.env")

bot = read_simple_env(BOT_ENV)
private_key = serialization.load_pem_private_key(PRIVATE_KEY.read_bytes(), password=None)
if not isinstance(private_key, Ed25519PrivateKey):
    raise SystemExit("The private key must be Ed25519")

seed = private_key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption(),
)
updates = {
    "APP_NAME": '"DeepXII Activation"',
    "APP_URL": "https://activate.goatplay.site",
    "TELEGRAM_USER_BOT_TOKEN": bot.get("DEEPXII_USER_BOT_TOKEN", ""),
    "TELEGRAM_ADMIN_BOT_TOKEN": bot.get("DEEPXII_ADMIN_BOT_TOKEN", ""),
    "TELEGRAM_ADMIN_ID": bot.get("DEEPXII_ADMIN_ID", ""),
    "TELEGRAM_USER_WEBHOOK_SECRET": secrets.token_urlsafe(32),
    "TELEGRAM_ADMIN_WEBHOOK_SECRET": secrets.token_urlsafe(32),
    "LICENSE_PRIVATE_KEY_SEED": base64.b64encode(seed).decode("ascii"),
}

text = LARAVEL_ENV.read_text(encoding="utf-8")
for key, value in updates.items():
    if not value:
        raise SystemExit(f"Missing required value: {key}")
    text = replace(text, key, value)
LARAVEL_ENV.write_text(text, encoding="utf-8")
print("Laravel activation secrets configured without displaying them.")
