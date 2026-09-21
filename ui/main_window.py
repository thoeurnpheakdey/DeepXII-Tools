from __future__ import annotations

import threading
from typing import Callable, Tuple

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)

from config import Config
from core.api_client import HonguoClient
from core.aria2_manager import Aria2Manager
from core.download_manager import DownloadManager
from ui.queue_tab import QueueTab
from ui.search_tab import SearchTab
from ui.settings_dialog import SettingsDialog
from ui.settings_tab import SettingsTab


from version import APP_VERSION



class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: Config,
        client: HonguoClient,
        aria2: Aria2Manager,
        download_manager: DownloadManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.client = client
        self.aria2 = aria2
        self.download_manager = download_manager
        self._version_info: dict | None = None

        self.setWindowTitle("红果短剧下载器")
        self.resize(900, 650)
        self._center_on_screen()

        self._build_menu()
        self._build_status_bar()
        self._build_tabs()

        QTimer.singleShot(0, self._post_init)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        settings_menu = menu_bar.addMenu("设置")
        settings_action = QAction("授权码与设置", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

        about_menu = menu_bar.addMenu("关于")
        about_action = QAction("版本信息", self)
        about_action.triggered.connect(self._show_about)
        about_menu.addAction(about_action)

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.key_label = ClickableLabel()
        self.key_label.setCursor(Qt.PointingHandCursor)
        self.key_label.clicked.connect(self._open_settings)
        self.version_label = ClickableLabel(f"v{APP_VERSION}")
        self._update_url = ""
        self.version_label.clicked.connect(self._open_update_url)
        status_bar.addWidget(self.key_label)
        status_bar.addPermanentWidget(self.version_label)
        self._update_key_status()

    def _open_update_url(self) -> None:
        if self._update_url:
            QDesktopServices.openUrl(QUrl(self._update_url))

    def show_aria2_warning(self, msg: str) -> None:
        self.statusBar().showMessage(f"⚠️ {msg}  将使用直连下载", 12000)

    def _build_tabs(self) -> None:
        self.tab_widget = QTabWidget()
        self.search_tab = SearchTab(self.config, self.client, self.download_manager, self)
        self.queue_tab = QueueTab(self.config, self.download_manager, self)
        self.settings_tab = SettingsTab(self.config, self.client, self)
        self.settings_tab.settings_saved.connect(self._on_settings_saved)
        self.tab_widget.addTab(self.search_tab, "🔍 搜索")
        self.tab_widget.addTab(self.queue_tab, "📥 下载队列")
        self.tab_widget.addTab(self.settings_tab, "⚙️ 设置")
        self.setCentralWidget(self.tab_widget)

    def _post_init(self) -> None:
        self._check_version_async()

    def _update_key_status(self) -> None:
        if self.config.is_key_set:
            self.key_label.setText("🔑 已授权")
        else:
            self.key_label.setText("🆓 免费预览模式 — 点击设置授权码")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.client, self)
        if dialog.exec():
            self.queue_tab.set_concurrent_value(self.config.concurrent)
            self._update_key_status()

    def _on_settings_saved(self) -> None:
        self.queue_tab.set_concurrent_value(self.config.concurrent)
        self._update_key_status()

    def _show_about(self) -> None:
        info_lines = [f"版本：v{APP_VERSION}"]
        if self._version_info:
            info_lines.append(f"最新版本：{self._version_info.get('latest_version', '-')}")
            info_lines.append(f"联系邮箱：{self._version_info.get('contact_email', '-')}")
        QMessageBox.information(self, "关于", "\n".join(info_lines))

    def _check_version_async(self) -> None:
        def task() -> Tuple[bool, dict, str]:
            return self.client.check_version()

        self._start_worker(task, self._handle_version_result)

    def _handle_version_result(self, result: Tuple[bool, dict, str]) -> None:
        ok, data, msg = result
        if not ok:
            return
        self._version_info = data
        latest = str(data.get("latest_version") or "")
        download_url = str(data.get("download_url") or "")
        if latest and self._is_newer_version(latest, APP_VERSION):
            self._update_url = download_url
            self.version_label.setText(f"🆕 v{APP_VERSION} → {latest}  点击更新")
            self.version_label.setCursor(Qt.PointingHandCursor)
            self.statusBar().showMessage(f"发现新版本 {latest}，点击右下角更新", 8000)

    def _is_newer_version(self, remote: str, current: str) -> bool:
        def parse(ver: str) -> Tuple[int, ...]:
            parts = []
            for segment in ver.replace("v", "").split('.'):
                try:
                    parts.append(int(segment))
                except ValueError:
                    parts.append(0)
            return tuple(parts)

        return parse(remote) > parse(current)

    def _start_worker(
        self,
        func: Callable,
        callback_or_on_finished: Callable[[object], None],
        on_failed: Callable[[str], None] | None = None,
    ) -> None:
        def _run() -> None:
            try:
                result = func()
                QTimer.singleShot(0, self, lambda: callback_or_on_finished(result))
            except Exception as exc:  # pylint: disable=broad-except
                if on_failed is not None:
                    err = str(exc)
                    QTimer.singleShot(0, self, lambda: on_failed(err))

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _center_on_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geometry.center())
        self.move(frame.topLeft())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self.aria2.stop()
        finally:
            super().closeEvent(event)
