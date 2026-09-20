#!/usr/bin/env python3
"""DeepXII Tools — modern desktop interface."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtWidgets import QApplication

from config import Config
from core.api_client import HonguoClient
from core.aria2_manager import Aria2Manager
from core.download_manager import DownloadManager
from ui.modern_window import ModernWindow, app_stylesheet


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DeepXII Tools")
    app.setOrganizationName("Nava Seal Digital")
    app.setStyle("Fusion")
    config = Config.load()
    app.setStyleSheet(app_stylesheet(config.theme))

    client = HonguoClient(config)
    aria2 = Aria2Manager(config)
    download_manager = DownloadManager(config, client, aria2)
    window = ModernWindow(config, download_manager, aria2)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
