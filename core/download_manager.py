from __future__ import annotations

import contextlib
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from config import Config
from .api_client import HonguoClient
from .aria2_manager import Aria2Manager


API_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
POLL_INTERVAL = 0.5
CHUNK_SIZE = 65536
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


class _DownloadCancelled(Exception):
    """Internal sentinel to indicate a requested stop."""


class DownloadManager(QObject):
    task_updated = pyqtSignal(str, str)
    queue_changed = pyqtSignal()

    def __init__(self, config: Config, client: HonguoClient, aria2: Aria2Manager) -> None:
        super().__init__()
        self.config = config
        self.client = client
        self.aria2 = aria2
        self._tasks: List[DownloadTask] = []
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._cancelled: Set[str] = set()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_workers = 0
        self._futures: Dict[str, Future] = {}

    def add_drama(self, book_id: str, title: str, episode_range: str = "all") -> int:
        ok, episodes, msg = self.client.get_episodes(book_id)
        if not ok or not isinstance(episodes, list):
            return 0
        selected = self._parse_episode_range(episode_range)
        new_tasks: List[DownloadTask] = []
        with self._lock:
            existing_ids = {task.video_id for task in self._tasks}
        for idx, episode in enumerate(episodes, start=1):
            video_id = str(episode.get("video_id") or "")
            if not video_id or video_id in existing_ids:
                continue
            episode_num = self._safe_int(episode.get("episode_num"))
            if episode_num <= 0:
                title_str = str(episode.get("title") or "")
                m = re.search(r"(\d+)", title_str)
                episode_num = int(m.group(1)) if m else idx
            if selected is not None and episode_num not in selected:
                continue
            episode_title = str(episode.get("title") or f"第{episode_num:02d}集")
            task = DownloadTask(
                book_id=book_id,
                title=title.strip() or "未知剧目",
                video_id=video_id,
                episode_num=episode_num,
                episode_title=episode_title,
            )
            new_tasks.append(task)
            existing_ids.add(video_id)
        if not new_tasks:
            return 0
        with self._lock:
            self._tasks.extend(new_tasks)
        self.queue_changed.emit()
        for task in new_tasks:
            self.task_updated.emit(task.book_id, task.video_id)
        return len(new_tasks)

    def start_queue(self) -> None:
        with self._lock:
            startable = [
                task
                for task in self._tasks
                if task.status in {"pending", "stopped"} and task.video_id not in self._futures
            ]
        if not startable:
            return
        self._stop_flag.clear()
        self._ensure_executor()
        for task in startable:
            future = self._executor.submit(self._download_one, task)  # type: ignore[arg-type]
            self._futures[task.video_id] = future
            future.add_done_callback(lambda fut, vid=task.video_id: self._on_task_finished(vid, fut))

    def start_task(self, video_id: str) -> None:
        with self._lock:
            task = next((t for t in self._tasks if t.video_id == video_id), None)
            if task is None or task.status not in {"pending", "stopped"}:
                return
            if video_id in self._futures:
                return
        self._stop_flag.clear()
        self._ensure_executor()
        future = self._executor.submit(self._download_one, task)  # type: ignore[arg-type]
        self._futures[video_id] = future
        future.add_done_callback(lambda fut, vid=video_id: self._on_task_finished(vid, fut))

    def stop_all(self) -> None:
        self._stop_flag.set()
        tasks_snapshot: List[DownloadTask]
        with self._lock:
            tasks_snapshot = list(self._tasks)
        for task in tasks_snapshot:
            if task.gid:
                self.aria2.remove(task.gid)
        executor = self._executor
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None
            self._executor_workers = 0
        with self._lock:
            affected = [task for task in self._tasks if task.status in {"pending", "downloading"}]
        for task in affected:
            self._update_task(task, status="stopped", speed=0.0)
        self._stop_flag.clear()

    def remove_task(self, video_id: str) -> None:
        task = self._find_task(video_id)
        if task is None:
            return
        self._cancelled.add(video_id)
        if task.gid:
            self.aria2.remove(task.gid)
        future = self._futures.get(video_id)
        if future is not None:
            future.cancel()
        with self._lock:
            self._tasks = [t for t in self._tasks if t.video_id != video_id]
        self.queue_changed.emit()
        self.task_updated.emit(task.book_id, task.video_id)

    def clear_done(self) -> None:
        with self._lock:
            remaining = [task for task in self._tasks if task.status != "done"]
            if len(remaining) == len(self._tasks):
                return
            self._tasks = remaining
        self.queue_changed.emit()

    def get_tasks(self) -> List[DownloadTask]:
        with self._lock:
            return list(self._tasks)

    def task_count(self) -> Dict[str, int]:
        result = {"pending": 0, "downloading": 0, "done": 0, "error": 0, "stopped": 0, "total": 0}
        with self._lock:
            for task in self._tasks:
                if task.status in result:
                    result[task.status] += 1
            result["total"] = len(self._tasks)
        result.setdefault("error", 0)
        return result

    def _download_one(self, task: DownloadTask) -> None:
        if self._should_stop_task(task):
            self._update_task(task, status="stopped", speed=0.0)
            return
        try:
            ok, payload, msg = self.client.get_video_url(task.video_id, self.config.level)
            if not ok or not isinstance(payload, dict):
                self._update_task(task, status="error", error_msg=msg or "获取视频地址失败", speed=0.0)
                return
            url = str(payload.get("url") or "")
            if not url:
                self._update_task(task, status="error", error_msg="视频链接缺失", speed=0.0)
                return
            save_dir = Path(self.config.download_dir).expanduser() / self._safe_filename(task.title or "下载")
            filename = self._build_filename(task)
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._update_task(task, status="error", error_msg=str(exc), speed=0.0)
                return
            save_path = save_dir / filename
            self._update_task(task, save_path=str(save_path), error_msg="")
            if save_path.exists():
                self._update_task(task, status="done", progress=100.0, speed=0.0, gid="")
                return
            gid = self.aria2.add_download(url, str(save_dir), filename, API_USER_AGENT)
            if gid:
                self._update_task(task, gid=gid, status="downloading", progress=0.0, speed=0.0)
                handled = self._monitor_aria2(task, gid)
                if handled:
                    return
            if self._should_stop_task(task):
                self._update_task(task, status="stopped", speed=0.0)
                return
            self._update_task(task, status="downloading", gid="", error_msg="")
            success, stopped = self._download_direct(url, save_path, task)
            if stopped or success:
                return
        except Exception as exc:  # pylint: disable=broad-except
            self._update_task(task, status="error", error_msg=str(exc), speed=0.0)
        finally:
            if task.gid:
                self._update_task(task, gid="")

    def _monitor_aria2(self, task: DownloadTask, gid: str) -> bool:
        while True:
            if self._should_stop_task(task):
                self.aria2.remove(gid)
                self._update_task(task, status="stopped", speed=0.0, gid="")
                return True
            status = self.aria2.get_status(gid)
            state = str(status.get("status") or "")
            completed = self._safe_int(status.get("completed"))
            total = self._safe_int(status.get("total"))
            speed = float(status.get("speed") or 0.0)
            progress = task.progress
            if total > 0:
                progress = min(100.0, max(0.0, (completed / total) * 100.0))
            self._update_task(task, progress=progress, speed=max(0.0, speed))
            if state == "complete":
                self._update_task(task, status="done", progress=100.0, speed=0.0, gid="")
                return True
            if state in {"error", "removed"}:
                error_message = str(status.get("error_message") or "aria2 下载失败")
                if state == "removed" and self._should_stop_task(task):
                    self._update_task(task, status="stopped", speed=0.0, gid="")
                    return True
                self._update_task(task, status="error", error_msg=error_message, speed=0.0, gid="")
                return False
            time.sleep(POLL_INTERVAL)

    def _download_direct(self, url: str, save_path: Path, task: DownloadTask) -> Tuple[bool, bool]:
        headers = {"User-Agent": API_USER_AGENT}
        downloaded = 0
        start_time = time.time()
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(15, 30)) as response:
                response.raise_for_status()
                total = self._safe_int(response.headers.get("Content-Length"))
                with open(save_path, "wb") as file_handle:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if not chunk:
                            continue
                        if self._should_stop_task(task):
                            raise _DownloadCancelled
                        file_handle.write(chunk)
                        downloaded += len(chunk)
                        progress = (downloaded / total * 100.0) if total > 0 else 0.0
                        elapsed = max(time.time() - start_time, 0.001)
                        speed = downloaded / elapsed
                        self._update_task(task, progress=progress, speed=speed)
            self._update_task(task, status="done", progress=100.0, speed=0.0, error_msg="")
            return True, False
        except _DownloadCancelled:
            self._update_task(task, status="stopped", speed=0.0)
            with contextlib.suppress(FileNotFoundError, OSError):
                save_path.unlink()
            return False, True
        except requests.RequestException as exc:
            self._update_task(task, status="error", error_msg=f"直连下载失败: {exc}", speed=0.0)
            with contextlib.suppress(FileNotFoundError, OSError):
                save_path.unlink()
            return False, False

    def _ensure_executor(self) -> None:
        desired = max(1, self.config.concurrent)
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=desired, thread_name_prefix="hongguo-dl")
            self._executor_workers = desired
        elif self._executor_workers != desired and not self._futures:
            self._executor.shutdown(wait=False, cancel_futures=False)
            self._executor = ThreadPoolExecutor(max_workers=desired, thread_name_prefix="hongguo-dl")
            self._executor_workers = desired

    def _on_task_finished(self, video_id: str, future: Future) -> None:
        self._futures.pop(video_id, None)
        self._cancelled.discard(video_id)
        if not self._futures and self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=False)
            self._executor = None
            self._executor_workers = 0
        _ = future.exception()

    def _should_stop_task(self, task: DownloadTask) -> bool:
        return self._stop_flag.is_set() or task.video_id in self._cancelled

    def _find_task(self, video_id: str) -> Optional[DownloadTask]:
        with self._lock:
            for task in self._tasks:
                if task.video_id == video_id:
                    return task
        return None

    def _build_filename(self, task: DownloadTask) -> str:
        episode_title = self._safe_filename(task.episode_title or f"第{task.episode_num:02d}集")
        return f"{task.episode_num:02d}-{episode_title}.mp4"

    @staticmethod
    def _safe_filename(text: str) -> str:
        cleaned = _FILENAME_CLEANER.sub("_", text).strip()
        return cleaned or "episode"

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
            if not part:
                continue
            if "-" in part:
                start_str, end_str = part.split("-", 1)
                start = self._safe_int(start_str)
                end = self._safe_int(end_str)
                if start <= 0 or end <= 0:
                    continue
                if start > end:
                    start, end = end, start
                selected.update(range(start, end + 1))
            else:
                value = self._safe_int(part)
                if value > 0:
                    selected.add(value)
        return selected or None

    def _update_task(self, task: DownloadTask, **updates: object) -> None:
        with self._lock:
            for attr, value in updates.items():
                if attr == "progress":
                    try:
                        value = max(0.0, min(100.0, float(value)))
                    except (TypeError, ValueError):
                        value = task.progress
                elif attr == "speed":
                    try:
                        value = max(0.0, float(value))
                    except (TypeError, ValueError):
                        value = task.speed
                elif attr == "status":
                    value = str(value)
                elif attr == "error_msg":
                    value = str(value)
                elif attr == "gid":
                    value = str(value)
                elif attr == "save_path":
                    value = str(value)
                setattr(task, attr, value)
        self.task_updated.emit(task.book_id, task.video_id)
