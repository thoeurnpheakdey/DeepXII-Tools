"""Secure GitHub Releases updater for DeepXII Tools."""
from __future__ import annotations

import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from version import APP_VERSION


DEFAULT_GITHUB_REPOSITORY = "theournpheakdey/DeepXII-Tools"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    name: str
    notes: str
    page_url: str
    asset_name: str
    asset_url: str
    checksum_url: str


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = [int(part) for part in re.findall(r"\d+", value)]
    return tuple(numbers or [0])


def is_newer_version(remote: str, current: str = APP_VERSION) -> bool:
    return _version_tuple(remote) > _version_tuple(current)


def check_latest_release(repository: str) -> ReleaseInfo | None:
    repository = repository.strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise RuntimeError("GitHub repository must use owner/repository format")
    response = requests.get(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "DeepXII-Tools-Updater"},
        timeout=30,
    )
    if response.status_code == 404:
        raise RuntimeError("No published GitHub Release was found")
    response.raise_for_status()
    payload = response.json()
    version = str(payload.get("tag_name") or "").lstrip("vV")
    if not version or not is_newer_version(version):
        return None
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    exe_assets = [asset for asset in assets if str(asset.get("name") or "").lower().endswith(".exe")]
    if not exe_assets:
        raise RuntimeError("The latest Release has no Windows .exe asset")
    exe_assets.sort(key=lambda asset: ("setup" not in str(asset.get("name") or "").lower(),))
    selected = exe_assets[0]
    asset_name = str(selected.get("name") or "")
    checksum_names = {f"{asset_name}.sha256", "sha256sum.txt", "checksums.txt"}
    checksum = next(
        (asset for asset in assets if str(asset.get("name") or "").lower() in {name.lower() for name in checksum_names}),
        None,
    )
    if checksum is None:
        raise RuntimeError("Release is missing a SHA-256 checksum asset")
    return ReleaseInfo(
        version=version,
        name=str(payload.get("name") or f"Version {version}"),
        notes=str(payload.get("body") or "No release notes."),
        page_url=str(payload.get("html_url") or ""),
        asset_name=asset_name,
        asset_url=str(selected.get("browser_download_url") or ""),
        checksum_url=str(checksum.get("browser_download_url") or ""),
    )


def download_release(release: ReleaseInfo, progress: Callable[[int], None] | None = None) -> Path:
    target_dir = Path(tempfile.gettempdir()) / "DeepXIIToolsUpdates" / release.version
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / release.asset_name
    partial = destination.with_suffix(destination.suffix + ".part")
    with requests.get(release.asset_url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with partial.open("wb") as handle:
            for chunk in response.iter_content(1024 * 256):
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
                if progress and total > 0:
                    progress(min(99, int(downloaded * 100 / total)))
    checksum_response = requests.get(release.checksum_url, timeout=30)
    checksum_response.raise_for_status()
    expected_match = re.search(r"\b([a-fA-F0-9]{64})\b", checksum_response.text)
    if not expected_match:
        partial.unlink(missing_ok=True)
        raise RuntimeError("The Release checksum file is invalid")
    digest = hashlib.sha256()
    with partial.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_match.group(1).lower():
        partial.unlink(missing_ok=True)
        raise RuntimeError("Update checksum verification failed")
    partial.replace(destination)
    if progress:
        progress(100)
    return destination
