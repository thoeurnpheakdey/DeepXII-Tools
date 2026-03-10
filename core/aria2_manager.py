from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config

import aria2p
import psutil


class Aria2Manager:
    def __init__(self, config: Optional["Config"] = None, rpc_port: int = 6800) -> None:
        self.rpc_port = rpc_port
        self.rpc_host = "http://localhost"
        self.rpc_secret = ""
        self.config = config
        self._binary_path: Optional[Path] = self._detect_binary()
        self._process: Optional[subprocess.Popen] = None
        self._client: Optional[aria2p.Client] = None
        self._api: Optional[aria2p.API] = None
        self._last_error: str = ""

    def _detect_binary(self) -> Optional[Path]:
        project_root = Path(__file__).resolve().parent.parent
        mac_bin = project_root / "resources" / "aria2" / "mac" / "aria2c"
        win_bin = project_root / "resources" / "aria2" / "win" / "aria2c.exe"
        candidates = []
        if sys.platform.startswith("win"):
            candidates.extend([win_bin, mac_bin])
        else:
            candidates.extend([mac_bin, win_bin])
        which_path = shutil.which("aria2c")
        if which_path:
            candidates.append(Path(which_path))
        for candidate in candidates:
            if candidate and candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _get_api(self) -> aria2p.API:
        if self._api is None:
            self._client = aria2p.Client(
                host=self.rpc_host,
                port=self.rpc_port,
                secret=self.rpc_secret,
            )
            self._api = aria2p.API(self._client)
        return self._api

    def _rpc_alive(self) -> bool:
        try:
            api = self._get_api()
            api.get_stats()
            return True
        except ConnectionError:
            return False
        except Exception:
            return False

    def start(self) -> bool:
        if self._rpc_alive():
            return True
        binary = self._binary_path or self._detect_binary()
        if binary is None:
            self._last_error = "未找到 aria2c 可执行文件"
            return False
        self._binary_path = binary
        args = [
            str(binary),
            "--enable-rpc=true",
            f"--rpc-listen-port={self.rpc_port}",
            "--rpc-listen-all=false",
            "--max-connection-per-server=16",
            "--split=16",
            "--http-accept-gzip=true",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
        ]
        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._last_error = f"无法启动 aria2c: {exc}"
            return False
        if not self._wait_for_rpc_ready():
            self.stop()
            return False
        return True

    def _wait_for_rpc_ready(self, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._rpc_alive():
                return True
            time.sleep(0.2)
        return False

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            finally:
                self._process = None
        self._client = None
        self._api = None

    def is_running(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return True
        return self._rpc_alive()

    def add_download(self, url: str, save_dir: str, filename: str, ua: str) -> str:
        try:
            if not self.is_running() and not self.start():
                return ""
        except FileNotFoundError:
            self._last_error = "未找到 aria2c 可执行文件"
            return ""
        target_dir = Path(save_dir).expanduser()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return ""
        options = {
            "dir": str(target_dir),
            "user-agent": ua,
        }
        if filename:
            options["out"] = filename
        try:
            download = self._get_api().add_uris([url], options=options)
            return download.gid if download else ""
        except ConnectionError:
            return ""
        except Exception:
            return ""

    def get_status(self, gid: str) -> Dict[str, object]:
        status: Dict[str, object] = {
            "status": "unknown",
            "completed": 0,
            "total": 0,
            "speed": 0,
            "error_message": "",
        }
        try:
            download = self._get_api().get_download(gid)
        except ConnectionError:
            status["status"] = "error"
            status["error_message"] = "无法连接到 aria2 RPC"
            return status
        except Exception as exc:
            status["status"] = "error"
            status["error_message"] = str(exc)
            return status
        status.update(
            {
                "status": download.status,
                "completed": self._safe_int(download.completed_length),
                "total": self._safe_int(download.total_length),
                "speed": self._safe_int(download.download_speed),
                "error_message": download.error_message or "",
            }
        )
        return status

    def remove(self, gid: str) -> None:
        try:
            download = self._get_api().get_download(gid)
            self._get_api().remove([download], force=True, files=True)
        except ConnectionError:
            return
        except Exception:
            return

    def find_motrix(self) -> bool:
        try:
            for process in psutil.process_iter(["name"]):
                name = (process.info.get("name") or "").lower()
                if "motrix" in name:
                    return True
        except (psutil.Error, OSError):
            return False
        return False

    def last_error(self) -> str:
        return self._last_error

    @staticmethod
    def _safe_int(value: Optional[object]) -> int:
        try:
            return int(value) if value is not None else 0
        except (TypeError, ValueError):
            return 0
