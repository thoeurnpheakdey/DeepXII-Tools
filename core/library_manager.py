from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
THUMBNAIL_DIR = Path.home() / ".hongguo" / "thumbnails"


@dataclass(frozen=True)
class LibraryDrama:
    title: str
    folder: Path
    videos: tuple[Path, ...]
    cover: Path | None
    total_bytes: int
    modified_at: float

    @property
    def episode_count(self) -> int:
        return len(self.videos)

    @property
    def modified_text(self) -> str:
        return datetime.fromtimestamp(self.modified_at).strftime("%Y-%m-%d %H:%M")


def _episode_number(path: Path) -> tuple[int, str]:
    match = re.match(r"\s*(\d+)", path.stem)
    return (int(match.group(1)) if match else 10**9, path.name.lower())


def scan_library(download_dir: str | Path) -> list[LibraryDrama]:
    root = Path(download_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    groups: dict[Path, list[Path]] = {}
    try:
        candidates = root.rglob("*")
        for path in candidates:
            try:
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and not path.name.endswith(".part"):
                    groups.setdefault(path.parent, []).append(path)
            except OSError:
                continue
    except OSError:
        return []

    library: list[LibraryDrama] = []
    for folder, videos in groups.items():
        videos.sort(key=_episode_number)
        total = 0
        modified = 0.0
        for video in videos:
            try:
                stat = video.stat()
                total += stat.st_size
                modified = max(modified, stat.st_mtime)
            except OSError:
                continue
        cover = None
        try:
            cover = next((item for item in folder.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS), None)
        except OSError:
            pass
        title = folder.name if folder != root else root.name
        library.append(LibraryDrama(title, folder, tuple(videos), cover, total, modified))
    library.sort(key=lambda item: item.modified_at, reverse=True)
    return library


def _ffmpeg_path() -> str | None:
    executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    roots = [Path(sys.executable).resolve().parent, Path(__file__).resolve().parent.parent]
    for root in roots:
        for candidate in (root / executable, root / "resources" / "ffmpeg" / executable):
            if candidate.is_file():
                return str(candidate)
    return shutil.which("ffmpeg")


def video_thumbnail(video: Path) -> Path | None:
    """Return a cached preview frame for a video, generating it with ffmpeg if needed."""
    try:
        stat = video.stat()
    except OSError:
        return None
    identity = f"{video.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    cache_name = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest() + ".jpg"
    thumbnail = THUMBNAIL_DIR / cache_name
    if thumbnail.is_file() and thumbnail.stat().st_size:
        return thumbnail
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return None
    temporary = thumbnail.with_suffix(".tmp.jpg")
    try:
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=500:-2", "-q:v", "3", "-y", str(temporary)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            timeout=30,
            check=False,
        )
        if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size:
            temporary.replace(thumbnail)
            return thumbnail
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass
    return None
