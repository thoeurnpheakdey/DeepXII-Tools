from __future__ import annotations

import contextlib
import json
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from config import Config
from .api_client import HonguoClient
from .aria2_manager import Aria2Manager

API_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.1"
POLL_INTERVAL = 0.5
CHUNK_SIZE = 1024 * 1024
MAX_RETRIES = 3
_FILENAME_CLEANER = re.compile(r"[\\/:*?\"<>|]")


@dataclass
class DownloadTask:
    book_id: str
    title: str
    video_id: str
    episode_num: int
    episode_title: str
    status: str = "pending"
    progress: float = 0.0
    speed: float = 0.0
    save_path: str = ""
    gid: str = ""
    error_msg: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    eta_seconds: int = 0
    retry_count: int = 0
    max_retries: int = MAX_RETRIES


class _DownloadStopped(Exception):
    pass


class DownloadManager(QObject):
    task_updated = pyqtSignal(str, str)
    queue_changed = pyqtSignal()

    def __init__(self, config: Config, client: HonguoClient, aria2: Aria2Manager) -> None:
        super().__init__()
        self.config, self.client, self.aria2 = config, client, aria2
        self._tasks: List[DownloadTask] = []
        self._lock = threading.RLock()
        self._stop_flag, self._pause_flag = threading.Event(), threading.Event()
        self._cancelled: Set[str] = set()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_workers = 0
        self._futures: Dict[str, Future] = {}
        self._queue_file = Config.CONFIG_DIR / "download_queue.json"
        self._last_persist = 0.0
        self._load_queue()

    def add_drama(self, book_id: str, title: str, episode_range: str = "all") -> int:
        ok, episodes, _ = self.client.get_episodes(book_id)
        if not ok or not isinstance(episodes, list):
            return 0
        selected, new_tasks = self._parse_episode_range(episode_range), []
        with self._lock:
            existing = {task.video_id for task in self._tasks}
        for index, episode in enumerate(episodes, 1):
            video_id = str(episode.get("video_id") or "")
            if not video_id or video_id in existing:
                continue
            number = self._safe_int(episode.get("episode_num"))
            if number <= 0:
                match = re.search(r"(\d+)", str(episode.get("title") or ""))
                number = int(match.group(1)) if match else index
            if selected is not None and number not in selected:
                continue
            new_tasks.append(DownloadTask(book_id, title.strip() or "Untitled drama", video_id, number,
                                          str(episode.get("title") or f"Episode {number:02d}")))
            existing.add(video_id)
        if not new_tasks:
            return 0
        with self._lock:
            self._tasks.extend(new_tasks)
        self._persist_queue(True)
        self.queue_changed.emit()
        return len(new_tasks)

    def start_queue(self) -> None:
        self._pause_flag.clear()
        self._stop_flag.clear()
        with self._lock:
            tasks = [task for task in self._tasks if task.status in {"pending", "paused", "stopped", "error"}
                     and task.video_id not in self._futures]
        self._ensure_executor()
        for task in tasks:
            self._submit(task)

    def start_task(self, video_id: str) -> None:
        task = self._find_task(video_id)
        if task and task.status in {"pending", "paused", "stopped", "error"} and video_id not in self._futures:
            self._pause_flag.clear()
            self._stop_flag.clear()
            self._ensure_executor()
            self._submit(task)

    def pause_all(self) -> None:
        self._pause_flag.set()
        for task in self.get_tasks():
            if task.gid:
                self.aria2.remove(task.gid, delete_files=False)
            if task.status in {"pending", "downloading", "retrying"}:
                self._update_task(task, status="paused", speed=0, eta_seconds=0, gid="")
        self._persist_queue(True)

    def resume_all(self) -> None:
        self.start_queue()

    def retry_failed(self) -> None:
        for task in self.get_tasks():
            if task.status == "error":
                self._update_task(task, status="pending", error_msg="", retry_count=0)
        self.start_queue()

    def cancel_all(self) -> None:
        self._stop_flag.set()
        for task in self.get_tasks():
            self._cancelled.add(task.video_id)
            if task.gid:
                self.aria2.remove(task.gid, delete_files=True)
            self._delete_partial(task)
            if task.status != "done":
                self._update_task(task, status="cancelled", speed=0, eta_seconds=0, gid="")
        self._persist_queue(True)

    def stop_all(self) -> None:
        self._stop_flag.set()
        for task in self.get_tasks():
            if task.gid:
                self.aria2.remove(task.gid, delete_files=False)
            if task.status in {"pending", "downloading", "retrying"}:
                self._update_task(task, status="stopped", speed=0, eta_seconds=0, gid="")
        self._persist_queue(True)

    def shutdown(self, wait: bool = True) -> None:
        """Stop active transfers and release worker threads during application exit."""
        self.stop_all()
        executor = self._executor
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)
            self._executor = None
            self._executor_workers = 0
        self._persist_queue(True)

    def remove_task(self, video_id: str) -> None:
        task = self._find_task(video_id)
        if not task:
            return
        self._cancelled.add(video_id)
        if task.gid:
            self.aria2.remove(task.gid, delete_files=True)
        self._delete_partial(task)
        with self._lock:
            self._tasks = [item for item in self._tasks if item.video_id != video_id]
        self._persist_queue(True)
        self.queue_changed.emit()

    def remove_drama(self, book_id: str) -> None:
        removed = [item for item in self.get_tasks() if item.book_id == book_id]
        for task in removed:
            self._cancelled.add(task.video_id)
            if task.gid:
                self.aria2.remove(task.gid, delete_files=True)
            self._delete_partial(task)
        with self._lock:
            self._tasks = [item for item in self._tasks if item.book_id != book_id]
        self._persist_queue(True)
        self.queue_changed.emit()

    def clear_done(self) -> None:
        with self._lock:
            self._tasks = [task for task in self._tasks if task.status != "done"]
        self._persist_queue(True)
        self.queue_changed.emit()

    def get_tasks(self) -> List[DownloadTask]:
        with self._lock:
            return list(self._tasks)

    def task_count(self) -> Dict[str, int]:
        result = {name: 0 for name in ("pending", "downloading", "retrying", "paused", "done", "error", "stopped", "cancelled")}
        tasks = self.get_tasks()
        for task in tasks:
            if task.status in result:
                result[task.status] += 1
        result["total"] = len(tasks)
        return result

    def _submit(self, task: DownloadTask) -> None:
        if self._executor is None:
            return
        future = self._executor.submit(self._download_one, task)
        self._futures[task.video_id] = future
        future.add_done_callback(lambda item, video_id=task.video_id: self._finished(video_id, item))

    def _download_one(self, task: DownloadTask) -> None:
        last_error = "Download failed"
        for attempt in range(task.retry_count, task.max_retries + 1):
            if self._should_stop(task):
                self._mark_interrupted(task)
                return
            self._update_task(task, retry_count=attempt, status="downloading" if attempt == 0 else "retrying")
            try:
                if self._download_attempt(task):
                    return
                last_error = task.error_msg or last_error
            except _DownloadStopped:
                self._mark_interrupted(task)
                return
            except Exception as exc:  # pylint: disable=broad-except
                last_error = str(exc)
            if attempt < task.max_retries and not self._should_stop(task):
                self._update_task(task, status="retrying", error_msg=f"Retry {attempt + 1}/{task.max_retries}: {last_error}")
                time.sleep(2 * (attempt + 1))
        self._update_task(task, status="error", error_msg=last_error, speed=0, eta_seconds=0, gid="")

    def _download_attempt(self, task: DownloadTask) -> bool:
        ok, payload, message = self.client.get_video_url(task.video_id, self.config.level)
        if not ok or not isinstance(payload, dict):
            raise RuntimeError(message or "Unable to resolve video URL")
        url = str(payload.get("url") or "")
        if not url:
            raise RuntimeError("Video URL is missing")
        folder = Path(self.config.download_dir).expanduser() / self._safe_filename(task.title)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / self._build_filename(task)
        self._update_task(task, save_path=str(path), error_msg="")
        if path.exists() and path.stat().st_size:
            size = path.stat().st_size
            self._update_task(task, status="done", progress=100, downloaded_bytes=size, total_bytes=size, speed=0, eta_seconds=0)
            return True
        gid = self.aria2.add_download(url, str(folder), path.name, API_USER_AGENT)
        if gid:
            self._update_task(task, gid=gid, status="downloading")
            if self._monitor_aria2(task, gid):
                return True
        if self._should_stop(task):
            raise _DownloadStopped
        self._update_task(task, gid="", status="downloading")
        return self._download_direct(url, path, task)

    def _monitor_aria2(self, task: DownloadTask, gid: str) -> bool:
        while True:
            if self._should_stop(task):
                self.aria2.remove(gid, delete_files=False)
                raise _DownloadStopped
            data = self.aria2.get_status(gid)
            completed, total = self._safe_int(data.get("completed")), self._safe_int(data.get("total"))
            speed = max(0, self._safe_int(data.get("speed")))
            progress = completed / total * 100 if total else task.progress
            eta = int((total - completed) / speed) if total > completed and speed else 0
            self._update_task(task, progress=progress, speed=speed, downloaded_bytes=completed, total_bytes=total, eta_seconds=eta)
            state = str(data.get("status") or "")
            if state == "complete":
                self._update_task(task, status="done", progress=100, speed=0, eta_seconds=0, gid="", error_msg="")
                return True
            if state in {"error", "removed"}:
                if state == "removed" and self._should_stop(task):
                    raise _DownloadStopped
                self._update_task(task, gid="", error_msg=str(data.get("error_message") or "aria2 download failed"))
                return False
            time.sleep(POLL_INTERVAL)

    def _download_direct(self, url: str, path: Path, task: DownloadTask) -> bool:
        partial = Path(f"{path}.part")
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": API_USER_AGENT}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        started, current = time.time(), 0
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(20, 60)) as response:
                response.raise_for_status()
                resumed = offset > 0 and response.status_code == 206
                if offset and not resumed:
                    offset = 0
                length = self._safe_int(response.headers.get("Content-Length"))
                total = offset + length if length else 0
                with open(partial, "ab" if resumed else "wb") as output:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if not chunk:
                            continue
                        if self._should_stop(task):
                            raise _DownloadStopped
                        output.write(chunk)
                        current += len(chunk)
                        completed = offset + current
                        speed = current / max(time.time() - started, 0.001)
                        progress = completed / total * 100 if total else 0
                        eta = int((total - completed) / speed) if total > completed and speed else 0
                        self._update_task(task, progress=progress, speed=speed, downloaded_bytes=completed,
                                          total_bytes=total, eta_seconds=eta)
            partial.replace(path)
            size = path.stat().st_size
            self._update_task(task, status="done", progress=100, speed=0, downloaded_bytes=size,
                              total_bytes=size, eta_seconds=0, error_msg="")
            return True
        except _DownloadStopped:
            raise
        except (requests.RequestException, OSError) as exc:
            self._update_task(task, error_msg=f"Direct download failed: {exc}", speed=0, eta_seconds=0)
            return False

    def _mark_interrupted(self, task: DownloadTask) -> None:
        state = "cancelled" if task.video_id in self._cancelled else ("paused" if self._pause_flag.is_set() else "stopped")
        self._update_task(task, status=state, speed=0, eta_seconds=0, gid="")

    def _delete_partial(self, task: DownloadTask) -> None:
        if task.save_path:
            for candidate in (Path(f"{task.save_path}.part"), Path(f"{task.save_path}.aria2")):
                with contextlib.suppress(OSError):
                    candidate.unlink()

    def _ensure_executor(self) -> None:
        workers = max(1, self.config.concurrent)
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="deepxii-dl")
            self._executor_workers = workers
        elif self._executor_workers != workers and not self._futures:
            self._executor.shutdown(wait=False)
            self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="deepxii-dl")
            self._executor_workers = workers

    def _finished(self, video_id: str, future: Future) -> None:
        with self._lock:
            self._futures.pop(video_id, None)
            self._cancelled.discard(video_id)
        with contextlib.suppress(Exception):
            future.result()
        self._persist_queue(True)

    def _should_stop(self, task: DownloadTask) -> bool:
        return self._stop_flag.is_set() or self._pause_flag.is_set() or task.video_id in self._cancelled

    def _find_task(self, video_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return next((task for task in self._tasks if task.video_id == video_id), None)

    def _build_filename(self, task: DownloadTask) -> str:
        return f"{task.episode_num:02d}-{self._safe_filename(task.episode_title)}.mp4"

    @staticmethod
    def _safe_filename(text: str) -> str:
        return _FILENAME_CLEANER.sub("_", text).strip() or "episode"

    @staticmethod
    def _safe_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _parse_episode_range(self, raw: str) -> Optional[Set[int]]:
        if not raw or raw.strip().lower() == "all":
            return None
        selected: Set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                left, right = part.split("-", 1)
                start, end = self._safe_int(left), self._safe_int(right)
                if start > 0 and end > 0:
                    selected.update(range(min(start, end), max(start, end) + 1))
            elif self._safe_int(part) > 0:
                selected.add(self._safe_int(part))
        return selected or None

    def _update_task(self, task: DownloadTask, **updates: object) -> None:
        with self._lock:
            for name, value in updates.items():
                if name == "progress":
                    value = max(0.0, min(100.0, float(value)))
                elif name == "speed":
                    value = max(0.0, float(value))
                elif name in {"downloaded_bytes", "total_bytes", "eta_seconds", "retry_count", "max_retries"}:
                    value = max(0, self._safe_int(value))
                elif name in {"status", "error_msg", "gid", "save_path"}:
                    value = str(value)
                setattr(task, name, value)
        self._persist_queue()
        self.task_updated.emit(task.book_id, task.video_id)

    def _load_queue(self) -> None:
        if not self._queue_file.exists():
            return
        try:
            payload = json.loads(self._queue_file.read_text(encoding="utf-8"))
            allowed = {item.name for item in fields(DownloadTask)}
            for raw in payload if isinstance(payload, list) else []:
                if isinstance(raw, dict):
                    task = DownloadTask(**{key: value for key, value in raw.items() if key in allowed})
                    if task.status in {"downloading", "retrying"}:
                        task.status, task.speed, task.eta_seconds, task.gid = "stopped", 0, 0, ""
                    self._tasks.append(task)
        except (OSError, ValueError, TypeError):
            self._tasks = []

    def _persist_queue(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_persist < 1:
            return
        self._last_persist = now
        with self._lock:
            payload = [asdict(task) for task in self._tasks]
        try:
            self._queue_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._queue_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self._queue_file)
        except OSError:
            pass
