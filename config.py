from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

CONFIG_DIR_PATH = Path.home() / ".hongguo"
CONFIG_FILE_PATH = CONFIG_DIR_PATH / "config.json"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "红果下载"
DEFAULT_LEVEL = "1080P+"
DEFAULT_THEME = "light"
DEFAULT_LANGUAGE = "en"
DEFAULT_ACTIVATION_BOT_USERNAME = "deepxiiactivate_bot"
MIN_CONCURRENT = 1
MAX_CONCURRENT = 10


def _generate_machine_id() -> str:
    raw = uuid.getnode().to_bytes(6, "big") + platform.node().encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:32]


def _coerce_concurrent(value: Any) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = 3
    return max(MIN_CONCURRENT, min(MAX_CONCURRENT, numeric))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _normalize_dir(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return str(Path(value).expanduser())
    return str(DEFAULT_DOWNLOAD_DIR)


@dataclass
class Config:
    key: str = ""
    machine_id: str = field(default_factory=_generate_machine_id)
    download_dir: str = field(default_factory=lambda: str(DEFAULT_DOWNLOAD_DIR))
    concurrent: int = 3
    use_motrix: bool = False
    level: str = DEFAULT_LEVEL
    theme: str = DEFAULT_THEME
    language: str = DEFAULT_LANGUAGE
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_auto_send: bool = False
    github_repository: str = "thoeurnpheakdey/DeepXII-Tools"
    activation_code: str = ""
    activation_bot_username: str = DEFAULT_ACTIVATION_BOT_USERNAME

    CONFIG_DIR: ClassVar[Path] = CONFIG_DIR_PATH
    CONFIG_FILE: ClassVar[Path] = CONFIG_FILE_PATH

    def __post_init__(self) -> None:
        self.machine_id = self.machine_id or _generate_machine_id()
        self.download_dir = _normalize_dir(self.download_dir)
        self.concurrent = _coerce_concurrent(self.concurrent)
        self.level = (self.level or DEFAULT_LEVEL).strip() or DEFAULT_LEVEL
        self.theme = str(self.theme or DEFAULT_THEME).strip().lower()
        if self.theme not in {"light", "dark"}:
            self.theme = DEFAULT_THEME
        self.language = str(self.language or DEFAULT_LANGUAGE).strip().lower()
        if self.language not in {"en", "km"}:
            self.language = DEFAULT_LANGUAGE

    @property
    def is_key_set(self) -> bool:
        return bool(self.effective_key)

    @property
    def effective_key(self) -> str:
        """Prefer the environment key without ever persisting it to disk."""
        return str(os.environ.get("HONGGUO_KEY") or self.key).strip()

    @classmethod
    def load(cls) -> "Config":
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        needs_save = False
        if cls.CONFIG_FILE.exists():
            try:
                data = json.loads(cls.CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
                needs_save = True
        else:
            needs_save = True

        config = cls(
            key=str(data.get("key", "")),
            machine_id=str(data.get("machine_id") or _generate_machine_id()),
            download_dir=data.get("download_dir") or str(DEFAULT_DOWNLOAD_DIR),
            concurrent=data.get("concurrent", 3),
            use_motrix=_coerce_bool(data.get("use_motrix")),
            level=data.get("level") or DEFAULT_LEVEL,
            theme=data.get("theme") or DEFAULT_THEME,
            language=data.get("language") or DEFAULT_LANGUAGE,
            telegram_bot_token=str(data.get("telegram_bot_token", "")),
            telegram_chat_id=str(data.get("telegram_chat_id", "")),
            telegram_auto_send=_coerce_bool(data.get("telegram_auto_send")),
            github_repository=str(data.get("github_repository") or "thoeurnpheakdey/DeepXII-Tools"),
            activation_code=str(data.get("activation_code", "")),
            activation_bot_username=str(data.get("activation_bot_username") or DEFAULT_ACTIVATION_BOT_USERNAME),
        )

        stored = {
            "key": data.get("key", ""),
            "machine_id": data.get("machine_id"),
            "download_dir": data.get("download_dir"),
            "concurrent": _coerce_concurrent(data.get("concurrent", 3)),
            "use_motrix": _coerce_bool(data.get("use_motrix")),
            "level": data.get("level") or DEFAULT_LEVEL,
            "theme": data.get("theme") or DEFAULT_THEME,
            "language": data.get("language") or DEFAULT_LANGUAGE,
            "telegram_bot_token": data.get("telegram_bot_token", ""),
            "telegram_chat_id": data.get("telegram_chat_id", ""),
            "telegram_auto_send": _coerce_bool(data.get("telegram_auto_send")),
            "github_repository": data.get("github_repository") or "thoeurnpheakdey/DeepXII-Tools",
            "activation_code": data.get("activation_code", ""),
            "activation_bot_username": data.get("activation_bot_username") or DEFAULT_ACTIVATION_BOT_USERNAME,
        }
        if (
            needs_save
            or stored["machine_id"] != config.machine_id
            or stored["download_dir"] != config.download_dir
            or stored["concurrent"] != config.concurrent
            or stored["use_motrix"] != config.use_motrix
            or stored["level"] != config.level
            or stored["theme"] != config.theme
            or stored["language"] != config.language
            or stored["telegram_bot_token"] != config.telegram_bot_token
            or stored["telegram_chat_id"] != config.telegram_chat_id
            or stored["telegram_auto_send"] != config.telegram_auto_send
            or stored["github_repository"] != config.github_repository
            or stored["activation_code"] != config.activation_code
            or stored["activation_bot_username"] != config.activation_bot_username
        ):
            config.save()
        return config

    def save(self) -> None:
        payload = {
            "key": self.key,
            "machine_id": self.machine_id,
            "download_dir": self.download_dir,
            "concurrent": self.concurrent,
            "use_motrix": self.use_motrix,
            "level": self.level,
            "theme": self.theme,
            "language": self.language,
            "telegram_bot_token": self.telegram_bot_token,
            "telegram_chat_id": self.telegram_chat_id,
            "telegram_auto_send": self.telegram_auto_send,
            "github_repository": self.github_repository,
            "activation_code": self.activation_code,
            "activation_bot_username": self.activation_bot_username,
        }
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.CONFIG_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise RuntimeError(f"无法写入配置文件: {exc}") from exc
