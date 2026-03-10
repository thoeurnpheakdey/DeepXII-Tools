#!/usr/bin/env python3
"""红果短剧下载器 — 跨平台版本"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from config import Config
from core.api_client import HonguoClient
from core.aria2_manager import Aria2Manager
from core.download_manager import DownloadManager
from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("红果短剧下载器")
    app.setOrganizationName("HonguoDownloader")
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    config = Config.load()
    client = HonguoClient(config)
    aria2 = Aria2Manager(config)
    aria2_warning = ""
    try:
        started = aria2.start()
        if not started:
            aria2_warning = aria2.last_error() or "未能启动 aria2c，将改用直连下载。"
    except Exception as exc:  # pylint: disable=broad-except
        aria2_warning = str(exc)

    manager = DownloadManager(config, client, aria2)

    window = MainWindow(config, client, aria2, manager)
    window.show()

    if aria2_warning:
        window.show_aria2_warning(aria2_warning)

    exit_code = app.exec()
    aria2.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
