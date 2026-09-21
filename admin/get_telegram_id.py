from __future__ import annotations

import os
from pathlib import Path

import requests


def load_env() -> None:
    path = Path(__file__).resolve().parent / "bot.env"
    if not path.exists():
        raise SystemExit("Create admin/bot.env from bot.env.example first")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env()
    token = os.environ.get("DEEPXII_ADMIN_BOT_TOKEN", "").strip()
    if not token or token.startswith("PASTE_"):
        raise SystemExit("Put the real DEEPXII_ADMIN_BOT_TOKEN in admin/bot.env first")
    session = requests.Session()
    session.trust_env = False
    response = session.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    response.raise_for_status()
    updates = response.json().get("result") or []
    identities: dict[str, str] = {}
    for update in updates:
        source = update.get("message") or update.get("callback_query") or {}
        user = source.get("from") or {}
        user_id = str(user.get("id") or "")
        if user_id:
            name = user.get("username") or user.get("first_name") or "Unknown"
            identities[user_id] = str(name)
    if not identities:
        raise SystemExit("No users found. Send /start to the Admin Approval Bot, then run this script again.")
    print("Telegram accounts found:")
    for user_id, name in identities.items():
        print(f"  ID: {user_id}  User: {name}")
    print("Copy your ID into DEEPXII_ADMIN_ID in admin/bot.env")


if __name__ == "__main__":
    main()
