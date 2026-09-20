#!/usr/bin/env python3
"""红果短剧下载器命令行界面"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import os
import queue
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config, MAX_CONCURRENT, MIN_CONCURRENT  # noqa: E402
from core.api_client import HonguoClient  # noqa: E402
from core.aria2_manager import Aria2Manager  # noqa: E402
from core.public_catalog import search_catalog  # noqa: E402


POLL_INTERVAL = 0.5
CHUNK_SIZE = 65536
BAR_WIDTH = 12
_FILENAME_CLEANER = re.compile(r"[\\/:*?\"<>|]")


class DownloadCancelled(Exception):
    """Raised when a download is interrupted."""


@dataclass
class EpisodeTask:
    book_id: str
    video_id: str
    episode_num: int
    episode_title: str
    order: int = 0

    @property
    def label(self) -> str:
        title = self.episode_title.strip() or f"第{self.episode_num:02d}集"
        return title


@dataclass
class ProgressEvent:
    kind: str
    index: int
    progress: float = 0.0
    speed: float = 0.0
    status: str = ""
    message: str = ""
    path: str = ""


@dataclass
class EpisodeProgressState:
    title: str
    status: str = "等待"
    progress: float = 0.0
    speed: float = 0.0
    message: str = ""
    path: str = ""


class ProgressRenderer:
    def __init__(self, tasks: Sequence[EpisodeTask]):
        self.states: List[EpisodeProgressState] = [
            EpisodeProgressState(title=f"{task.label}") for task in tasks
        ]
        self.total = len(self.states)
        self.rendered_lines = 0
        self.supports_redraw = sys.stdout.isatty() and _enable_ansi_escape()

    def handle(self, event: ProgressEvent) -> None:
        if event.index <= 0 or event.index > len(self.states):
            return
        state = self.states[event.index - 1]
        if event.kind == "start":
            state.status = event.status or "准备"
            state.message = event.message
        elif event.kind == "progress":
            if event.status:
                state.status = event.status
            state.progress = max(0.0, min(100.0, event.progress))
            state.speed = max(0.0, event.speed)
            state.message = event.message
        elif event.kind == "done":
            state.status = "完成"
            state.progress = 100.0
            state.speed = 0.0
            state.message = event.message
            state.path = event.path
        elif event.kind == "error":
            state.status = "失败"
            state.speed = 0.0
            state.message = event.message or "发生错误"
        elif event.kind == "skip":
            state.status = "已存在"
            state.progress = 100.0
            state.speed = 0.0
            state.message = event.message
        elif event.kind == "cancel":
            state.status = "已取消"
            state.speed = 0.0
            state.message = event.message
        self.render()

    def render(self) -> None:
        lines = []
        for idx, state in enumerate(self.states, start=1):
            prefix = f"[{idx:02d}/{self.total:02d}]"
            bar = _progress_bar(state.progress)
            percent = f"{state.progress:5.1f}%"
            speed = _format_speed(state.speed)
            status = state.status
            message = state.message
            line = f"{prefix} {state.title} {bar} {percent} | {speed} | {status}"
            if message:
                line = f"{line} - {message}"
            lines.append(line)
        block = "\n".join(lines)
        if self.supports_redraw and self.rendered_lines:
            sys.stdout.write(f"\x1b[{self.rendered_lines}F")
        sys.stdout.write(block + "\n")
        sys.stdout.flush()
        self.rendered_lines = len(lines)

    def finalize(self) -> None:
        if self.supports_redraw:
            sys.stdout.write("\n")
            sys.stdout.flush()


@dataclass
class DownloadContext:
    config: Config
    client: HonguoClient
    aria2: Optional[Aria2Manager]
    aria2_enabled: bool
    quality: str
    output_dir: Path
    stop_event: threading.Event
    progress_queue: "queue.Queue[ProgressEvent]"


def main(argv: Optional[Sequence[str]] = None) -> int:
    _configure_console_encoding()
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\n操作已取消")
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="红果短剧下载器 CLI")
    subparsers = parser.add_subparsers(dest="command")

    search_parser = subparsers.add_parser("search", help="搜索剧目")
    search_parser.add_argument("keyword", help="关键词")
    search_parser.add_argument("--page", type=int, default=1, help="页码 (默认 1)")
    search_parser.set_defaults(handler=_command_search)

    today_parser = subparsers.add_parser("today", help="今日更新")
    today_parser.set_defaults(handler=_command_today)

    episodes_parser = subparsers.add_parser("episodes", help="查看剧集列表")
    episodes_parser.add_argument("book_id", help="book_id")
    episodes_parser.set_defaults(handler=_command_episodes)

    download_parser = subparsers.add_parser("download", help="下载剧集")
    download_parser.add_argument("book_id", help="book_id")
    download_parser.add_argument("--title", help="剧名-可选")
    download_parser.add_argument(
        "--episodes",
        default="all",
        help="选择剧集，示例: all 或 1,3,5-10",
    )
    download_parser.add_argument(
        "--quality",
        choices=["1080P+", "720P", "480P"],
        help="清晰度",
    )
    download_parser.add_argument("--dir", help="保存目录，默认读取配置")
    download_parser.add_argument(
        "--concurrent",
        type=int,
        help="并发任务数 (默认使用配置)",
    )
    download_parser.set_defaults(handler=_command_download)

    batch_parser = subparsers.add_parser("batch", help="批量下载多个剧目")
    batch_parser.add_argument("book_ids", nargs="*", help="一个或多个 book_id")
    batch_parser.add_argument(
        "--file",
        help="批量文件；每行格式为 book_id|剧名|集数（剧名和集数可省略）",
    )
    batch_parser.add_argument(
        "--episodes",
        default="all",
        help="命令行 book_id 的剧集范围，例如 all 或 1,3,5-10",
    )
    batch_parser.add_argument("--quality", choices=["1080P+", "720P", "480P"], help="清晰度")
    batch_parser.add_argument("--dir", help="保存目录，默认读取配置")
    batch_parser.add_argument("--concurrent", type=int, help="每个剧目的并发任务数")
    batch_parser.set_defaults(handler=_command_batch)

    config_parser = subparsers.add_parser("config", help="查看或更新配置")
    config_parser.add_argument("--key", help="授权 Key")
    config_parser.add_argument("--dir", help="下载目录")
    config_parser.add_argument("--level", choices=["1080P+", "720P", "480P"], help="默认清晰度")
    config_parser.add_argument("--concurrent", type=int, help="默认并发数")
    config_parser.set_defaults(handler=_command_config)

    return parser


def _command_search(args: argparse.Namespace) -> int:
    try:
        all_results = search_catalog(args.keyword)
    except RuntimeError as exc:
        print(f"搜索失败: {exc}")
        return 1
    page = max(1, args.page)
    page_size = 50
    results = all_results[(page - 1) * page_size:page * page_size]
    if not results:
        print("未找到匹配剧目。")
        return 0
    rows = []
    for idx, item in enumerate(results, start=1):
        title = str(item.get("title") or item.get("book_name") or item.get("name") or "-")
        drama_type = str(item.get("type") or item.get("tags") or "-")
        episode_total = str(item.get("episode") or item.get("episode_total") or item.get("ji") or "-")
        book_id = str(item.get("book_id") or item.get("id") or "-")
        rows.append([
            f"{idx:02d}",
            title,
            drama_type,
            str(episode_total),
            book_id,
        ])
    _print_table(["序号", "剧名", "类型", "集数", "book_id"], rows)
    return 0


def _command_today(args: argparse.Namespace) -> int:  # pylint: disable=unused-argument
    config = Config.load()
    client = HonguoClient(config)
    ok, results, msg = client.today_new()
    if not ok:
        print(f"获取失败: {msg}")
        return 1
    if not results:
        print("今日暂无更新。")
        return 0
    rows = []
    for idx, item in enumerate(results, start=1):
        title = str(item.get("title") or item.get("book_name") or item.get("name") or "-")
        drama_type = str(item.get("type") or item.get("tags") or "-")
        episode_total = str(item.get("episode") or item.get("episode_total") or item.get("ji") or "-")
        book_id = str(item.get("book_id") or item.get("id") or "-")
        rows.append([
            f"{idx:02d}",
            title,
            drama_type,
            str(episode_total),
            book_id,
        ])
    _print_table(["序号", "剧名", "类型", "集数", "book_id"], rows)
    return 0


def _command_episodes(args: argparse.Namespace) -> int:
    config = Config.load()
    client = HonguoClient(config)
    ok, episodes, msg = client.get_episodes(args.book_id)
    if not ok:
        print(f"获取剧集失败: {msg}")
        return 1
    if not episodes:
        print("未找到任何剧集。")
        return 0
    rows = []
    for idx, episode in enumerate(episodes, start=1):
        episode_num = _extract_episode_num(episode, idx)
        title = str(episode.get("title") or episode.get("name") or f"第{episode_num:02d}集")
        video_id = str(episode.get("video_id") or "-")
        rows.append([f"{episode_num:02d}", title, video_id])
    _print_table(["集数", "标题", "video_id"], rows)
    return 0


def _command_config(args: argparse.Namespace) -> int:
    config = Config.load()
    updated = False
    if args.key is not None:
        config.key = args.key.strip()
        updated = True
    if args.dir is not None:
        config.download_dir = str(Path(args.dir).expanduser())
        updated = True
    if args.level is not None:
        config.level = args.level
        updated = True
    if args.concurrent is not None:
        config.concurrent = _clamp_concurrent(args.concurrent)
        updated = True
    if updated:
        config.save()
        print("配置已更新。")
    masked_key = "****" if config.is_key_set else "(未设置)"
    print("当前配置：")
    print(f"- 授权 Key: {masked_key}")
    print(f"- 下载目录: {config.download_dir}")
    print(f"- 默认清晰度: {config.level}")
    print(f"- 并发任务: {config.concurrent}")
    print(f"- Machine ID: {config.machine_id}")
    return 0


def _command_download(args: argparse.Namespace) -> int:
    config = Config.load()
    client = HonguoClient(config)
    aria2 = Aria2Manager(config)
    concurrency = _clamp_concurrent(args.concurrent if args.concurrent else config.concurrent)
    quality = args.quality or config.level or "1080P+"
    selection = _parse_episode_selection(args.episodes)

    ok, episodes, msg = client.get_episodes(args.book_id)
    if not ok:
        print(f"获取剧集失败: {msg}")
        return 1
    if not episodes:
        print("没有可下载的剧集。")
        return 1

    drama_title = (args.title or _guess_drama_title(episodes) or args.book_id).strip() or args.book_id
    tasks = _build_tasks(args.book_id, episodes, selection)
    if not tasks:
        print("未匹配到任何需要下载的剧集。")
        return 1

    download_root = Path(args.dir or config.download_dir).expanduser()
    target_dir = download_root / _safe_filename(drama_title)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"创建目录失败: {exc}")
        return 1

    aria2_enabled = False
    try:
        aria2_enabled = aria2.start()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"提示: 无法启动 aria2 ({exc})，将使用直连下载。")
    if not aria2_enabled and aria2.last_error():
        print(f"提示: {aria2.last_error()}，将使用直连下载。")

    stop_event = threading.Event()
    progress_queue: "queue.Queue[ProgressEvent]" = queue.Queue()
    renderer = ProgressRenderer(tasks)
    renderer.render()

    ctx = DownloadContext(
        config=config,
        client=client,
        aria2=aria2 if aria2_enabled else None,
        aria2_enabled=aria2_enabled,
        quality=quality,
        output_dir=target_dir,
        stop_event=stop_event,
        progress_queue=progress_queue,
    )

    futures: List[Future[DownloadResult]] = []
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="hongguo-cli") as executor:
        for task in tasks:
            future = executor.submit(_download_worker, task, ctx)
            futures.append(future)

        pending = set(futures)
        try:
            while pending:
                _drain_progress(progress_queue, renderer)
                done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                _drain_progress(progress_queue, renderer)
        except KeyboardInterrupt:
            stop_event.set()
            print("\n正在取消下载...")
            for future in pending:
                future.cancel()
            while pending:
                done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            _drain_progress(progress_queue, renderer)
            renderer.finalize()
            aria2.stop()
            raise

    stop_event.set()
    _drain_progress(progress_queue, renderer)
    renderer.finalize()
    aria2.stop()

    results = [future.result() for future in futures if future.done()]
    success = sum(1 for result in results if result.success)
    errors = [result for result in results if not result.success]

    print(f"已完成 {success}/{len(tasks)} 集下载。")
    print(f"保存位置: {target_dir}")
    if errors:
        print("以下剧集下载失败：")
        for result in errors:
            print(f"- {result.label}: {result.message}")
        return 1
    return 0


@dataclass
class BatchItem:
    book_id: str
    title: Optional[str] = None
    episodes: str = "all"


def _command_batch(args: argparse.Namespace) -> int:
    try:
        items = _load_batch_items(args.book_ids, args.file, args.episodes)
    except (OSError, ValueError) as exc:
        print(f"读取批量任务失败: {exc}")
        return 2

    if not items:
        print("请提供至少一个 book_id，或使用 --file 指定批量文件。")
        return 2

    failures: List[str] = []
    print(f"准备下载 {len(items)} 个剧目。")
    for index, item in enumerate(items, start=1):
        print(f"\n=== [{index}/{len(items)}] {item.title or item.book_id} ===")
        download_args = argparse.Namespace(
            book_id=item.book_id,
            title=item.title,
            episodes=item.episodes,
            quality=args.quality,
            dir=args.dir,
            concurrent=args.concurrent,
        )
        if _command_download(download_args) != 0:
            failures.append(item.book_id)

    succeeded = len(items) - len(failures)
    print(f"\n批量任务完成: {succeeded}/{len(items)} 个剧目成功。")
    if failures:
        print("失败的 book_id: " + ", ".join(failures))
        return 1
    return 0


def _load_batch_items(
    book_ids: Sequence[str],
    file_path: Optional[str],
    default_episodes: str,
) -> List[BatchItem]:
    items = [
        BatchItem(book_id=value.strip(), episodes=default_episodes)
        for value in book_ids
        if value.strip()
    ]
    if file_path:
        path = Path(file_path).expanduser()
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("|", 2)]
            if not parts[0]:
                raise ValueError(f"第 {line_number} 行缺少 book_id")
            title = parts[1] if len(parts) > 1 and parts[1] else None
            episodes = parts[2] if len(parts) > 2 and parts[2] else default_episodes
            items.append(BatchItem(parts[0], title, episodes))

    # Preserve the first occurrence so a repeated ID is not downloaded twice.
    unique: List[BatchItem] = []
    seen: Set[str] = set()
    for item in items:
        if item.book_id not in seen:
            seen.add(item.book_id)
            unique.append(item)
    return unique


@dataclass
class DownloadResult:
    success: bool
    label: str
    path: Optional[Path] = None
    message: str = ""


def _download_worker(task: EpisodeTask, ctx: DownloadContext) -> DownloadResult:
    label = f"第{task.episode_num:02d}集"
    ctx.progress_queue.put(ProgressEvent("start", task.order, status="准备", message="等待获取链接"))
    try:
        if ctx.stop_event.is_set():
            raise DownloadCancelled
        ok, payload, msg = ctx.client.get_video_url(task.video_id, ctx.quality)
        if not ok or not isinstance(payload, dict):
            raise RuntimeError(msg or "无法获取播放链接")
        url = str(payload.get("url") or "")
        if not url:
            raise RuntimeError("视频链接缺失")
        filename = _build_filename(task)
        save_path = ctx.output_dir / filename
        if save_path.exists():
            ctx.progress_queue.put(ProgressEvent("skip", task.order, message="已存在，跳过"))
            return DownloadResult(True, label, save_path)
        if ctx.aria2_enabled and ctx.aria2 is not None:
            success = _download_via_aria2(task, url, save_path.parent, filename, ctx)
            if success:
                ctx.progress_queue.put(ProgressEvent("done", task.order, message="下载完成", path=str(save_path)))
                return DownloadResult(True, label, save_path)
        success = _download_direct(task, url, save_path, ctx)
        if success:
            ctx.progress_queue.put(ProgressEvent("done", task.order, message="下载完成", path=str(save_path)))
            return DownloadResult(True, label, save_path)
        raise RuntimeError("下载失败")
    except DownloadCancelled:
        ctx.progress_queue.put(ProgressEvent("cancel", task.order, message="已取消"))
        return DownloadResult(False, label, message="用户取消")
    except Exception as exc:  # pylint: disable=broad-except
        ctx.progress_queue.put(ProgressEvent("error", task.order, message=str(exc)))
        return DownloadResult(False, label, message=str(exc))


def _download_via_aria2(
    task: EpisodeTask,
    url: str,
    save_dir: Path,
    filename: str,
    ctx: DownloadContext,
) -> bool:
    if ctx.aria2 is None:
        return False
    gid = ctx.aria2.add_download(url, str(save_dir), filename, HonguoClient.UA)
    if not gid:
        return False
    while True:
        if ctx.stop_event.is_set():
            ctx.aria2.remove(gid)
            raise DownloadCancelled
        status = ctx.aria2.get_status(gid)
        state = str(status.get("status") or "")
        completed = _safe_int(status.get("completed"))
        total = _safe_int(status.get("total"))
        speed = float(status.get("speed") or 0.0)
        progress = (completed / total * 100.0) if total > 0 else 0.0
        ctx.progress_queue.put(
            ProgressEvent("progress", task.order, progress=max(0.0, progress), speed=speed, status="aria2")
        )
        if state == "complete":
            return True
        if state in {"error", "removed"}:
            return False
        time.sleep(POLL_INTERVAL)


def _download_direct(task: EpisodeTask, url: str, save_path: Path, ctx: DownloadContext) -> bool:
    headers = {"User-Agent": HonguoClient.UA}
    downloaded = 0
    start_time = time.time()
    try:
        with requests.get(url, headers=headers, stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            total = _safe_int(response.headers.get("Content-Length"))
            with open(save_path, "wb") as file_handle:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if ctx.stop_event.is_set():
                        raise DownloadCancelled
                    if not chunk:
                        continue
                    file_handle.write(chunk)
                    downloaded += len(chunk)
                    progress = (downloaded / total * 100.0) if total > 0 else 0.0
                    elapsed = max(time.time() - start_time, 0.001)
                    speed = downloaded / elapsed
                    ctx.progress_queue.put(
                        ProgressEvent(
                            "progress",
                            task.order,
                            progress=progress,
                            speed=speed,
                            status="直连",
                        )
                    )
        return True
    except DownloadCancelled:
        with contextlib.suppress(FileNotFoundError, OSError):
            save_path.unlink()
        raise
    except requests.RequestException as exc:
        with contextlib.suppress(FileNotFoundError, OSError):
            save_path.unlink()
        ctx.progress_queue.put(ProgressEvent("error", task.order, message=f"直连失败: {exc}"))
        return False


def _drain_progress(progress_queue: "queue.Queue[ProgressEvent]", renderer: ProgressRenderer) -> None:
    while True:
        try:
            event = progress_queue.get_nowait()
        except queue.Empty:
            break
        renderer.handle(event)


def _build_tasks(book_id: str, episodes: Sequence[Dict[str, object]], selection: Optional[Set[int]]) -> List[EpisodeTask]:
    tasks: List[EpisodeTask] = []
    for idx, episode in enumerate(episodes, start=1):
        video_id = str(episode.get("video_id") or "")
        if not video_id:
            continue
        episode_num = _extract_episode_num(episode, idx)
        if selection is not None and episode_num not in selection:
            continue
        title = str(episode.get("title") or episode.get("name") or f"第{episode_num:02d}集")
        tasks.append(EpisodeTask(book_id=book_id, video_id=video_id, episode_num=episode_num, episode_title=title))
    tasks.sort(key=lambda item: item.episode_num)
    for order, task in enumerate(tasks, start=1):
        task.order = order
    return tasks


def _guess_drama_title(episodes: Sequence[Dict[str, object]]) -> str:
    for episode in episodes:
        for key in ("book_name", "drama_name", "title", "name"):
            value = str(episode.get(key) or "").strip()
            if value and not value.startswith("第"):
                return value
    return ""


def _parse_episode_selection(raw: Optional[str]) -> Optional[Set[int]]:
    if not raw or raw.strip().lower() == "all":
        return None
    selected: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = _safe_int(start_str)
            end = _safe_int(end_str)
            if start <= 0 or end <= 0:
                continue
            if start > end:
                start, end = end, start
            selected.update(range(start, end + 1))
        else:
            value = _safe_int(part)
            if value > 0:
                selected.add(value)
    return selected or None


def _extract_episode_num(data: Dict[str, object], fallback: int) -> int:
    value = _safe_int(data.get("episode_num"))
    if value > 0:
        return value
    title = str(data.get("title") or data.get("name") or "")
    match = re.search(r"(\d+)", title)
    if match:
        return int(match.group(1))
    return fallback


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    widths = [_display_width(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], _display_width(str(cell)))

    def fmt_row(values: Sequence[str]) -> str:
        parts = []
        for idx, value in enumerate(values):
            text = str(value)
            pad = widths[idx] - _display_width(text)
            parts.append(text + " " * max(0, pad))
        return " | ".join(parts)

    print(fmt_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(fmt_row(row))


def _build_filename(task: EpisodeTask) -> str:
    safe_title = _safe_filename(task.episode_title or f"第{task.episode_num:02d}集")
    return f"{task.episode_num:02d}-{safe_title}.mp4"


def _safe_filename(text: str) -> str:
    cleaned = _FILENAME_CLEANER.sub("_", text).strip()
    return cleaned or "episode"


def _format_speed(speed: float) -> str:
    if speed <= 0:
        return "0 B/s"
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    value = speed
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}"


def _progress_bar(progress: float) -> str:
    filled = int(max(0.0, min(100.0, progress)) / 100 * BAR_WIDTH)
    filled = min(BAR_WIDTH, max(0, filled))
    return "█" * filled + "─" * (BAR_WIDTH - filled)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in {"F", "W"}:
            width += 2
        else:
            width += 1
    return width


def _clamp_concurrent(value: int) -> int:
    if value is None:
        return MIN_CONCURRENT
    return max(MIN_CONCURRENT, min(MAX_CONCURRENT, value))


def _enable_ansi_escape() -> bool:
    if os.name != "nt":
        return True
    if not sys.stdout.isatty():
        return False
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        if handle == 0:
            return False
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        new_mode = mode.value | 0x0004
        if not kernel32.SetConsoleMode(handle, new_mode):
            return False
        return True
    except Exception:  # pylint: disable=broad-except
        return False


def _configure_console_encoding() -> None:
    """Keep Chinese titles and status messages printable on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass


if __name__ == "__main__":
    sys.exit(main())
