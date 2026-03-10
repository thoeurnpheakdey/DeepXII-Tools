from __future__ import annotations

import hashlib
import json
import platform
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

CONFIG_DIR_PATH = Path.home() / ".hongguo"
CONFIG_FILE_PATH = CONFIG_DIR_PATH / "config.json"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "红果下载"
DEFAULT_LEVEL = "1080P+"
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

    CONFIG_DIR: ClassVar[Path] = CONFIG_DIR_PATH
    CONFIG_FILE: ClassVar[Path] = CONFIG_FILE_PATH

    def __post_init__(self) -> None:
        self.machine_id = self.machine_id or _generate_machine_id()
        self.download_dir = _normalize_dir(self.download_dir)
        self.concurrent = _coerce_concurrent(self.concurrent)
        self.level = (self.level or DEFAULT_LEVEL).strip() or DEFAULT_LEVEL

    @property
    def is_key_set(self) -> bool:
        return bool(self.key.strip())

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
        )

        stored = {
            "key": data.get("key", ""),
            "machine_id": data.get("machine_id"),
            "download_dir": data.get("download_dir"),
            "concurrent": _coerce_concurrent(data.get("concurrent", 3)),
            "use_motrix": _coerce_bool(data.get("use_motrix")),
            "level": data.get("level") or DEFAULT_LEVEL,
        }
        if (
            needs_save
            or stored["machine_id"] != config.machine_id
            or stored["download_dir"] != config.download_dir
            or stored["concurrent"] != config.concurrent
            or stored["use_motrix"] != config.use_motrix
            or stored["level"] != config.level
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
        }
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.CONFIG_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise RuntimeError(f"无法写入配置文件: {exc}") from exc
