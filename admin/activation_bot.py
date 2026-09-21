from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.license_manager import create_activation_code


def load_local_environment() -> None:
    env_file = Path(__file__).resolve().parent / "bot.env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


load_local_environment()
USER_BOT_TOKEN = os.environ.get("DEEPXII_USER_BOT_TOKEN", "").strip()
ADMIN_BOT_TOKEN = os.environ.get("DEEPXII_ADMIN_BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("DEEPXII_ADMIN_ID", "").strip()
USER_API = f"https://api.telegram.org/bot{USER_BOT_TOKEN}"
ADMIN_API = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}"
ROOT = Path(__file__).resolve().parent
PRIVATE_KEY = ROOT / "license_private_key.pem"
DATABASE = ROOT / "activation_bot.db"
MACHINE_PATTERN = re.compile(r"^[a-fA-F0-9]{32}$")
SESSION = requests.Session()
SESSION.trust_env = False


def call(api: str, method: str, **data):
    response = SESSION.post(f"{api}/{method}", json=data, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(str(payload))
    return payload.get("result")


def setup_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, user_id TEXT, username TEXT, machine_id TEXT, status TEXT)"
    )
    connection.commit()
    return connection


def request_activation(connection: sqlite3.Connection, message: dict) -> None:
    text = str(message.get("text") or "").strip()
    machine_id = text.split()[-1] if text else ""
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    user_id = str(chat.get("id") or "")
    if not MACHINE_PATTERN.fullmatch(machine_id):
        call(USER_API, "sendMessage", chat_id=user_id, text="Send your 32-character Machine ID to request activation.")
        return
    request_id = uuid.uuid4().hex[:12]
    username = str(user.get("username") or user.get("first_name") or "User")
    connection.execute(
        "INSERT INTO requests VALUES (?, ?, ?, ?, 'pending')", (request_id, user_id, username, machine_id.lower())
    )
    connection.commit()
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{request_id}"},
        {"text": "❌ Reject", "callback_data": f"reject:{request_id}"},
    ]]}
    call(ADMIN_API, "sendMessage", chat_id=ADMIN_ID,
         text=f"Activation request\nUser: @{username}\nMachine ID: `{machine_id}`",
         parse_mode="Markdown", reply_markup=keyboard)
    call(USER_API, "sendMessage", chat_id=user_id, text="Your activation request was sent. Please wait for Admin approval.")


def process_approval(connection: sqlite3.Connection, query: dict) -> None:
    admin_id = str((query.get("from") or {}).get("id") or "")
    if admin_id != ADMIN_ID:
        call(ADMIN_API, "answerCallbackQuery", callback_query_id=query["id"], text="Admin only", show_alert=True)
        return
    action, _, request_id = str(query.get("data") or "").partition(":")
    row = connection.execute(
        "SELECT user_id, username, machine_id, status FROM requests WHERE id=?", (request_id,)
    ).fetchone()
    if not row or row[3] != "pending":
        call(ADMIN_API, "answerCallbackQuery", callback_query_id=query["id"], text="Request already handled")
        return
    user_id, _username, machine_id, _status = row
    if action == "approve":
        code = create_activation_code(PRIVATE_KEY, machine_id, request_id)
        connection.execute("UPDATE requests SET status='approved' WHERE id=?", (request_id,))
        connection.commit()
        call(USER_API, "sendMessage", chat_id=user_id,
             text=f"✅ Approved\n\nCopy this Activation Code into DeepXII Tools:\n\n`{code}`",
             parse_mode="Markdown")
        result = "Approved and code sent"
    else:
        connection.execute("UPDATE requests SET status='rejected' WHERE id=?", (request_id,))
        connection.commit()
        call(USER_API, "sendMessage", chat_id=user_id, text="❌ Your activation request was rejected by Admin.")
        result = "Rejected"
    call(ADMIN_API, "answerCallbackQuery", callback_query_id=query["id"], text=result)


def main() -> None:
    if not USER_BOT_TOKEN or not ADMIN_BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("Set DEEPXII_USER_BOT_TOKEN, DEEPXII_ADMIN_BOT_TOKEN, and DEEPXII_ADMIN_ID first")
    if not PRIVATE_KEY.exists():
        raise SystemExit("Run admin/generate_license_keys.py first")
    connection = setup_database()
    user_offset = 0
    admin_offset = 0
    while True:
        try:
            user_updates = call(USER_API, "getUpdates", offset=user_offset, timeout=5, allowed_updates=["message"])
            for update in user_updates:
                user_offset = int(update["update_id"]) + 1
                if update.get("message"):
                    request_activation(connection, update["message"])
            admin_updates = call(
                ADMIN_API, "getUpdates", offset=admin_offset, timeout=5, allowed_updates=["callback_query"]
            )
            for update in admin_updates:
                admin_offset = int(update["update_id"]) + 1
                if update.get("callback_query"):
                    process_approval(connection, update["callback_query"])
        except (requests.RequestException, RuntimeError, sqlite3.Error) as exc:
            print(f"Bot error: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    main()
