from __future__ import annotations

import shutil
import re
import time
from pathlib import Path
from typing import Any

import requests

from PyQt6.QtCore import QObject, QProcess, QRunnable, QSize, Qt, QThreadPool, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QProgressDialog, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QApplication, QVBoxLayout, QWidget,
)

from config import Config, DEFAULT_DOWNLOAD_DIR
from core.aria2_manager import Aria2Manager
from core.download_manager import DownloadManager
from core.public_catalog import search_catalog
from core.update_manager import APP_VERSION, ReleaseInfo, check_latest_release, download_release


class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class UpdateSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal()


class SearchWorker(QRunnable):
    def __init__(self, keyword: str, category: str = "all") -> None:
        super().__init__()
        self.keyword = keyword
        self.category = category
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.signals.result.emit(search_catalog(self.keyword, self.category))
        except Exception as exc:  # pylint: disable=broad-except
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class PrepareDownloadsWorker(QRunnable):
    def __init__(self, manager: DownloadManager, dramas: list[dict[str, Any]]) -> None:
        super().__init__()
        self.manager = manager
        self.dramas = dramas
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            added = 0
            for drama in self.dramas:
                count = max(1, int(drama.get("download_count") or 1))
                added += self.manager.add_drama(
                    str(drama.get("book_id") or ""),
                    str(drama.get("title") or "Untitled drama"),
                    f"1-{count}",
                )
            self.signals.result.emit(added)
        except Exception as exc:  # pylint: disable=broad-except
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class TelegramUploadWorker(QRunnable):
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024

    def __init__(self, token: str, chat_id: str, video_id: str, file_path: str) -> None:
        super().__init__()
        self.token = token
        self.chat_id = chat_id
        self.video_id = video_id
        self.file_path = file_path
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            path = Path(self.file_path)
            if not path.exists():
                raise RuntimeError("Downloaded video file was not found")
            if path.stat().st_size > self.MAX_UPLOAD_BYTES:
                raise RuntimeError("Video exceeds Telegram's 50 MB official Bot API upload limit")
            response = None
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    with path.open("rb") as video_file:
                        response = requests.post(
                            f"https://api.telegram.org/bot{self.token}/sendVideo",
                            data={"chat_id": self.chat_id, "caption": path.stem},
                            files={"video": (path.name, video_file, "video/mp4")},
                            timeout=(120, 600),
                        )
                    break
                except (requests.Timeout, requests.ConnectionError) as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(attempt * 2)
            if response is None:
                raise RuntimeError(f"Upload failed after 3 attempts: {last_error}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"Telegram returned HTTP {response.status_code}") from exc
            if not response.ok or not payload.get("ok"):
                raise RuntimeError(str(payload.get("description") or f"HTTP {response.status_code}"))
            self.signals.result.emit((self.video_id, path.name))
        except Exception as exc:  # pylint: disable=broad-except
            self.signals.error.emit(f"{self.video_id}|{exc}")
        finally:
            self.signals.finished.emit()


class UpdateCheckWorker(QRunnable):
    def __init__(self, repository: str) -> None:
        super().__init__()
        self.repository = repository
        self.signals = UpdateSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.signals.result.emit(check_latest_release(self.repository))
        except Exception as exc:  # pylint: disable=broad-except
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class UpdateDownloadWorker(QRunnable):
    def __init__(self, release: ReleaseInfo) -> None:
        super().__init__()
        self.release = release
        self.signals = UpdateSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            path = download_release(self.release, self.signals.progress.emit)
            self.signals.result.emit(str(path))
        except Exception as exc:  # pylint: disable=broad-except
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class MetricCard(QFrame):
    def __init__(self, caption: str, value: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        caption_label = QLabel(caption)
        caption_label.setObjectName("muted")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.value_label.setStyleSheet(f"color: {accent};")
        layout.addWidget(caption_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class ModernWindow(QMainWindow):
    def __init__(self, config: Config, download_manager: DownloadManager, aria2: Aria2Manager) -> None:
        super().__init__()
        self.config = config
        self.download_manager = download_manager
        self.aria2 = aria2
        self.results: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []
        self.thread_pool = QThreadPool.globalInstance()
        self.image_manager = QNetworkAccessManager(self)
        self.image_manager.finished.connect(self._thumbnail_finished)
        self.thumbnail_cache: dict[str, QPixmap] = {}
        self.pending_thumbnails: set[str] = set()
        self.thumbnail_labels: dict[str, list[QLabel]] = {}
        self.result_checks: list[QCheckBox] = []
        self.catalog_category = "all"
        self.telegram_uploading: set[str] = set()
        self.telegram_sent: set[str] = set()
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._apply_responsive_layout)
        self.setWindowTitle("DeepXII Tools")
        self.setMinimumSize(760, 560)
        self.resize(1280, 790)
        self._build_ui()
        self.download_manager.task_updated.connect(self._on_download_updated)
        self._show_page(0)
        QTimer.singleShot(150, self._start_search)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("content")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(30, 24, 30, 24)
        self.content_layout.setSpacing(18)
        self.content_layout.addWidget(self._build_header())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_discover_page())
        self.pages.addWidget(self._build_queue_page())
        self.pages.addWidget(self._build_settings_page())
        self.content_layout.addWidget(self.pages, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 24, 18, 20)
        layout.setSpacing(8)
        self.brand_logo = QLabel()
        self.brand_logo.setObjectName("brandLogo")
        self.brand_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        logo_path = Path(__file__).resolve().parent.parent / "resources" / "deepxii_logo.png"
        self.brand_logo_pixmap = QPixmap(str(logo_path))
        if self.brand_logo_pixmap.isNull():
            self.brand_logo.setText("DeepXII Tools")
        else:
            self.brand_logo.setPixmap(
                self.brand_logo_pixmap.scaled(
                    QSize(184, 72),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        subtitle = QLabel("Develop by Nava Seal Digital")
        subtitle.setObjectName("brandSub")
        layout.addWidget(self.brand_logo)
        layout.addWidget(subtitle)
        layout.addSpacing(28)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for text, index, role in (
            ("⌕  Discover", 0, "discover"),
            ("▤  My Queue", 1, "queue"),
            ("⚙  Settings", 2, "settings"),
        ):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setProperty("navRole", role)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.update_button = QPushButton(f"↻  Update Tools  ·  v{APP_VERSION}")
        self.update_button.setObjectName("updateButton")
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_button.clicked.connect(self._check_for_updates)
        layout.addWidget(self.update_button)
        layout.addSpacing(18)
        contact_label = QLabel("CONTACT")
        contact_label.setObjectName("contactLabel")
        layout.addWidget(contact_label)
        youtube = QPushButton("▶  YouTube")
        youtube.setObjectName("youtubeButton")
        youtube.setCursor(Qt.CursorShape.PointingHandCursor)
        youtube.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.youtube.com/@NavaSealDigital"))
        )
        telegram = QPushButton("➤  Telegram")
        telegram.setObjectName("telegramButton")
        telegram.setCursor(Qt.CursorShape.PointingHandCursor)
        telegram.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://t.me/NavasealDigital"))
        )
        donate = QPushButton("♥  Donate Admin")
        donate.setObjectName("donateButton")
        donate.setCursor(Qt.CursorShape.PointingHandCursor)
        donate.clicked.connect(self._show_donate_dialog)
        layout.addWidget(youtube)
        layout.addWidget(telegram)
        layout.addWidget(donate)
        layout.addStretch(1)

        info = QFrame()
        info.setObjectName("sideInfo")
        info_layout = QVBoxLayout(info)
        info_layout.addWidget(QLabel("PUBLIC CATALOGUE"))
        hint = QLabel("Live search is ready. Downloads activate with an authorized endpoint.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        info_layout.addWidget(hint)
        layout.addWidget(info)
        return sidebar

    def _check_for_updates(self) -> None:
        repository = self.config.github_repository.strip()
        self.update_button.setEnabled(False)
        self.update_button.setText("Checking for updates…")
        worker = UpdateCheckWorker(repository)
        worker.signals.result.connect(self._update_check_result)
        worker.signals.error.connect(self._update_error)
        worker.signals.finished.connect(self._update_check_finished)
        self.thread_pool.start(worker)

    @pyqtSlot(object)
    def _update_check_result(self, result: object) -> None:
        if result is None:
            QMessageBox.information(self, "Software Update", f"DeepXII Tools v{APP_VERSION} is up to date.")
            return
        if not isinstance(result, ReleaseInfo):
            return
        notes = result.notes.strip()
        if len(notes) > 1500:
            notes = notes[:1500] + "…"
        answer = QMessageBox.question(
            self,
            "Update available",
            f"DeepXII Tools v{result.version} is available.\n\n{notes}\n\nDownload and install now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._download_update(result)

    def _download_update(self, release: ReleaseInfo) -> None:
        self.update_progress = QProgressDialog("Downloading signed update…", "", 0, 100, self)
        self.update_progress.setWindowTitle("DeepXII Tools Update")
        self.update_progress.setCancelButton(None)
        self.update_progress.setAutoClose(False)
        self.update_progress.setValue(0)
        self.update_progress.show()
        worker = UpdateDownloadWorker(release)
        worker.signals.progress.connect(self.update_progress.setValue)
        worker.signals.result.connect(self._update_downloaded)
        worker.signals.error.connect(self._update_error)
        self.thread_pool.start(worker)

    @pyqtSlot(object)
    def _update_downloaded(self, value: object) -> None:
        if hasattr(self, "update_progress"):
            self.update_progress.close()
        installer = Path(str(value))
        answer = QMessageBox.question(
            self,
            "Update verified",
            "The installer passed SHA-256 verification. Open it now and close DeepXII Tools?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(installer.parent)))
            return
        if QProcess.startDetached(str(installer), []):
            QApplication.quit()
        else:
            QMessageBox.warning(self, "Software Update", "Windows could not start the installer.")

    @pyqtSlot(str)
    def _update_error(self, message: str) -> None:
        if hasattr(self, "update_progress"):
            self.update_progress.close()
        QMessageBox.warning(self, "Software Update", message)

    @pyqtSlot()
    def _update_check_finished(self) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText(f"↻  Update Tools  ·  v{APP_VERSION}")

    def _show_donate_dialog(self) -> None:
        qr_path = Path(__file__).resolve().parent.parent / "resources" / "donate_qr.png"
        dialog = QDialog(self)
        dialog.setWindowTitle("Donate Admin")
        dialog.setObjectName("donateDialog")
        dialog.setMinimumSize(440, 600)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        title = QLabel("Donate Admin")
        title.setObjectName("donateTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image = QLabel()
        image.setObjectName("donateImage")
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setWordWrap(True)

        def show_qr() -> bool:
            pixmap = QPixmap(str(qr_path))
            if pixmap.isNull():
                image.setText("QR image has not been selected yet.\nClick ‘Choose QR image’ below.")
                return False
            image.setText("")
            image.setPixmap(
                pixmap.scaled(
                    QSize(400, 520),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return True

        def choose_qr() -> None:
            selected, _ = QFileDialog.getOpenFileName(
                dialog,
                "Choose the original donation QR image",
                "",
                "Images (*.png *.jpg *.jpeg *.webp)",
            )
            if not selected:
                return
            try:
                qr_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(selected, qr_path)
            except OSError as exc:
                QMessageBox.warning(dialog, "QR code unavailable", f"Could not save the QR image:\n{exc}")
                return
            show_qr()

        show_qr()
        choose = QPushButton("Choose QR image" if not qr_path.exists() else "Replace QR image")
        choose.setObjectName("secondaryButton")
        choose.clicked.connect(choose_qr)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(title)
        layout.addWidget(image, 1)
        layout.addWidget(choose)
        layout.addWidget(close)
        dialog.exec()

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        title_box = QVBoxLayout()
        self.page_title = QLabel("Discover")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Explore the public Hongguo catalogue")
        self.page_subtitle.setObjectName("muted")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        layout.addLayout(title_box)
        layout.addStretch(1)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setToolTip("Switch between light and dark mode")
        self.theme_button.clicked.connect(self._toggle_theme)
        self._update_theme_button()
        layout.addWidget(self.theme_button)
        badge = QLabel("●  PUBLIC MODE")
        badge.setObjectName("statusBadge")
        layout.addWidget(badge)
        return header

    def _toggle_theme(self) -> None:
        self.config.theme = "dark" if self.config.theme == "light" else "light"
        self.config.save()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(app_stylesheet(self.config.theme))
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        self.theme_button.setText("☾  Dark" if self.config.theme == "light" else "☀  Light")

    def _build_discover_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        metrics = QHBoxLayout()
        self.results_card = MetricCard("SEARCH RESULTS", "0", "#ff2d75")
        self.queue_card = MetricCard("IN YOUR QUEUE", "0", "#00f5d4")
        metrics.addWidget(self.results_card)
        metrics.addWidget(self.queue_card)
        metrics.addWidget(MetricCard("CATALOGUE", "LIVE", "#b7ff2a"))
        layout.addLayout(metrics)

        search_card = QFrame()
        search_card.setObjectName("panel")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(18, 16, 18, 16)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search a Chinese drama title…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._start_search)
        self.search_button = QPushButton("Search catalogue")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self._start_search)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_button)
        layout.addWidget(search_card)

        catalog_widget = QWidget()
        catalog_widget.setObjectName("catalogBar")
        catalog_bar = QHBoxLayout(catalog_widget)
        catalog_bar.setContentsMargins(0, 0, 0, 0)
        catalog_title = QLabel("▤  CATALOG")
        catalog_title.setObjectName("catalogTitle")
        catalog_bar.addWidget(catalog_title)
        self.catalog_group = QButtonGroup(self)
        self.catalog_group.setExclusive(True)
        for label, category in (
            ("All", "all"), ("Modern", "modern"), ("Urban", "urban"),
            ("Historical", "historical"), ("Rural", "rural"),
            ("Fantasy", "fantasy"), ("Romance", "romance"),
            ("CEO", "ceo"), ("Rebirth", "rebirth"), ("Time Travel", "time travel"),
        ):
            chip = QPushButton(label)
            chip.setObjectName("catalogChip")
            chip.setCheckable(True)
            chip.setChecked(category == "all")
            chip.clicked.connect(lambda _checked=False, value=category: self._select_catalog(value))
            self.catalog_group.addButton(chip)
            catalog_bar.addWidget(chip)
        catalog_bar.addStretch(1)
        catalog_scroll = QScrollArea()
        catalog_scroll.setObjectName("catalogFilterScroll")
        catalog_scroll.setWidgetResizable(True)
        catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        catalog_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        catalog_scroll.setFixedHeight(49)
        catalog_scroll.setWidget(catalog_widget)
        layout.addWidget(catalog_scroll)

        self.results_scroll = QScrollArea()
        self.results_scroll.setObjectName("catalogScroll")
        self.results_scroll.setWidgetResizable(True)
        self.results_container = QWidget()
        self.results_container.setObjectName("catalogContainer")
        self.results_grid = QGridLayout(self.results_container)
        self.results_grid.setContentsMargins(10, 10, 10, 10)
        self.results_grid.setHorizontalSpacing(14)
        self.results_grid.setVerticalSpacing(18)
        self.results_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.results_scroll.setWidget(self.results_container)
        layout.addWidget(self.results_scroll, 1)

        footer = QHBoxLayout()
        self.search_status = QLabel("Enter a title, or leave it empty to show the latest catalogue.")
        self.search_status.setObjectName("muted")
        self.add_queue_button = QPushButton("＋ Add selected to queue")
        self.add_queue_button.setObjectName("secondaryButton")
        self.add_queue_button.clicked.connect(self._add_selected_to_queue)
        footer.addWidget(self.search_status)
        footer.addStretch(1)
        footer.addWidget(self.add_queue_button)
        layout.addLayout(footer)
        return page

    def _build_queue_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        notice = QFrame()
        notice.setObjectName("notice")
        notice_layout = QHBoxLayout(notice)
        notice_layout.addWidget(QLabel("ⓘ"))
        self.queue_notice = QLabel("Queue is ready. Public mode may provide preview episodes only; add an API key in Settings for full access.")
        self.queue_notice.setWordWrap(True)
        notice_layout.addWidget(self.queue_notice, 1)
        layout.addWidget(notice)

        telegram_panel = QFrame()
        telegram_panel.setObjectName("telegramPanel")
        telegram_layout = QGridLayout(telegram_panel)
        telegram_layout.setContentsMargins(16, 12, 16, 12)
        telegram_title = QLabel("➤  TELEGRAM AUTO UPLOAD")
        telegram_title.setObjectName("telegramTitle")
        telegram_layout.addWidget(telegram_title, 0, 0, 1, 2)
        create_bot = QPushButton("Open @BotFather")
        create_bot.setObjectName("telegramButton")
        create_bot.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://t.me/BotFather")))
        telegram_layout.addWidget(create_bot, 0, 2)
        telegram_layout.addWidget(QLabel("Bot Token"), 1, 0)
        self.queue_telegram_token = QLineEdit(self.config.telegram_bot_token)
        self.queue_telegram_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.queue_telegram_token.setPlaceholderText("Paste token from @BotFather")
        self.queue_telegram_token.setClearButtonEnabled(True)
        telegram_layout.addWidget(self.queue_telegram_token, 1, 1, 1, 2)
        telegram_layout.addWidget(QLabel("Group Link / Chat ID"), 2, 0)
        self.queue_telegram_group = QLineEdit(self.config.telegram_chat_id)
        self.queue_telegram_group.setPlaceholderText("https://t.me/groupname, @groupname, or -100…")
        telegram_layout.addWidget(self.queue_telegram_group, 2, 1, 1, 2)
        self.queue_telegram_auto = QCheckBox("Automatically send every completed video")
        self.queue_telegram_auto.setChecked(self.config.telegram_auto_send)
        telegram_layout.addWidget(self.queue_telegram_auto, 3, 1)
        save_telegram = QPushButton("Save Telegram")
        save_telegram.setObjectName("primaryButton")
        save_telegram.clicked.connect(self._save_queue_telegram)
        telegram_layout.addWidget(save_telegram, 3, 2)
        self.telegram_upload_status = QLabel("")
        self.telegram_upload_status.setObjectName("muted")
        telegram_layout.addWidget(self.telegram_upload_status, 4, 1, 1, 2)
        telegram_layout.setColumnStretch(1, 1)
        layout.addWidget(telegram_panel)

        self.queue_table = self._new_table(["Drama", "Episodes", "Download", "Series ID", "Progress", "Status", "Actions"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.queue_table.setColumnWidth(2, 105)
        self.queue_table.setColumnWidth(4, 180)
        self.queue_table.setColumnWidth(6, 190)
        layout.addWidget(self.queue_table, 1)
        controls = QHBoxLayout()
        clear_button = QPushButton("Clear queue")
        clear_button.clicked.connect(self._clear_queue)
        self.download_button = QPushButton("Download all")
        self.download_button.setObjectName("primaryButton")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._start_downloads)
        controls.addWidget(clear_button)
        controls.addStretch(1)
        controls.addWidget(self.download_button)
        layout.addLayout(controls)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer_layout = QVBoxLayout(page)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        settings_body = QWidget()
        layout = QVBoxLayout(settings_body)
        layout.setContentsMargins(0, 0, 6, 0)
        scroll.setWidget(settings_body)
        outer_layout.addWidget(scroll)
        card = QFrame()
        card.setObjectName("panel")
        grid = QGridLayout(card)
        grid.setContentsMargins(24, 24, 24, 24)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(16)
        grid.addWidget(self._field_label("Download folder"), 0, 0)
        self.folder_edit = QLineEdit(self.config.download_dir)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._choose_folder)
        grid.addWidget(self.folder_edit, 0, 1)
        grid.addWidget(browse, 0, 2)
        grid.addWidget(self._field_label("Concurrent episodes"), 1, 0)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.config.concurrent)
        grid.addWidget(self.concurrent_spin, 1, 1)
        grid.addWidget(self._field_label("Preferred quality"), 2, 0)
        quality = QLineEdit(self.config.level)
        quality.setReadOnly(True)
        grid.addWidget(quality, 2, 1)
        grid.addWidget(self._field_label("Authorized API key"), 3, 0)
        self.api_key_edit = QLineEdit(self.config.key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter a valid key for full episode access")
        self.api_key_edit.setClearButtonEnabled(True)
        grid.addWidget(self.api_key_edit, 3, 1, 1, 2)
        grid.addWidget(self._field_label("API status"), 4, 0)
        self.api_status = QLabel()
        self.api_status.setObjectName("warningText")
        self._update_api_status()
        grid.addWidget(self.api_status, 4, 1, 1, 2)
        grid.addWidget(self._field_label("Telegram Bot Token"), 5, 0)
        self.telegram_token_edit = QLineEdit(self.config.telegram_bot_token)
        self.telegram_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.telegram_token_edit.setPlaceholderText("Token from @BotFather")
        self.telegram_token_edit.setClearButtonEnabled(True)
        grid.addWidget(self.telegram_token_edit, 5, 1, 1, 2)
        grid.addWidget(self._field_label("Telegram Group"), 6, 0)
        self.telegram_group_edit = QLineEdit(self.config.telegram_chat_id)
        self.telegram_group_edit.setPlaceholderText("https://t.me/groupname, @groupname, or numeric chat ID")
        grid.addWidget(self.telegram_group_edit, 6, 1, 1, 2)
        grid.addWidget(self._field_label("Auto-send videos"), 7, 0)
        self.telegram_auto_check = QCheckBox("Send each completed download to Telegram")
        self.telegram_auto_check.setChecked(self.config.telegram_auto_send)
        grid.addWidget(self.telegram_auto_check, 7, 1, 1, 2)
        grid.addWidget(self._field_label("GitHub repository"), 8, 0)
        self.github_repository_edit = QLineEdit(self.config.github_repository)
        self.github_repository_edit.setPlaceholderText("owner/repository")
        grid.addWidget(self.github_repository_edit, 8, 1, 1, 2)
        save = QPushButton("Save preferences")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_settings)
        grid.addWidget(save, 9, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _new_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(48)
        return table

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _show_page(self, index: int) -> None:
        titles = [("Discover", "Explore the public Hongguo catalogue"),
                  ("My Queue", "Review dramas prepared for download"),
                  ("Settings", "Manage local preferences")]
        self.pages.setCurrentIndex(index)
        self.page_title.setText(titles[index][0])
        self.page_subtitle.setText(titles[index][1])
        self.nav_buttons[index].setChecked(True)

    def _start_search(self) -> None:
        self.search_button.setEnabled(False)
        self.search_button.setText("Searching…")
        self.search_status.setText("Reading the public catalogue…")
        worker = SearchWorker(self.search_input.text().strip(), self.catalog_category)
        worker.signals.result.connect(self._show_results)
        worker.signals.error.connect(self._show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.thread_pool.start(worker)

    def _select_catalog(self, category: str) -> None:
        self.catalog_category = category
        self._start_search()

    @pyqtSlot(object)
    def _show_results(self, results: object) -> None:
        self.results = list(results) if isinstance(results, list) else []
        while self.results_grid.count():
            grid_item = self.results_grid.takeAt(0)
            widget = grid_item.widget()
            if widget is not None:
                widget.deleteLater()
        self.result_checks.clear()
        self.thumbnail_labels.clear()
        columns = max(1, self.results_scroll.viewport().width() // 175)
        for index, item in enumerate(self.results):
            card = QFrame()
            card.setObjectName("dramaCard")
            card.setFixedWidth(155)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 5, 5, 7)
            card_layout.setSpacing(6)
            cover = QLabel("No image")
            cover.setObjectName("cardCover")
            cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover.setFixedSize(145, 204)
            card_layout.addWidget(cover)
            meta = QHBoxLayout()
            check = QCheckBox()
            check.setToolTip("Select this drama")
            episodes = QLabel(str(item.get("episode_total") or "Episodes unknown"))
            episodes.setObjectName("cardEpisodes")
            meta.addWidget(check)
            meta.addStretch(1)
            meta.addWidget(episodes)
            card_layout.addLayout(meta)
            title = QLabel(str(item.get("title") or "Untitled drama"))
            title.setObjectName("cardTitle")
            title.setWordWrap(True)
            title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            title.setFixedHeight(40)
            card_layout.addWidget(title)
            self.result_checks.append(check)
            cover_url = str(item.get("cover_url") or "")
            self.thumbnail_labels.setdefault(cover_url, []).append(cover)
            self._load_thumbnail(cover_url)
            self.results_grid.addWidget(card, index // columns, index % columns)
        self._reflow_catalog()
        self.results_card.set_value(str(len(self.results)))
        self.search_status.setText(f"Found {len(self.results)} matching dramas.")

    def _load_thumbnail(self, url: str) -> None:
        if not url:
            return
        cached = self.thumbnail_cache.get(url)
        if cached is not None:
            self._apply_thumbnail(url, cached)
            return
        if url in self.pending_thumbnails:
            return
        self.pending_thumbnails.add(url)
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"Mozilla/5.0")
        reply = self.image_manager.get(request)
        reply.setProperty("thumbnail_url", url)

    def _thumbnail_finished(self, reply: QNetworkReply) -> None:
        url = str(reply.property("thumbnail_url") or "")
        self.pending_thumbnails.discard(url)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(reply.readAll())):
                self.thumbnail_cache[url] = pixmap
                self._apply_thumbnail(url, pixmap)
        reply.deleteLater()

    def _apply_thumbnail(self, url: str, pixmap: QPixmap) -> None:
        for label in self.thumbnail_labels.get(url, []):
            try:
                label.setText("")
                label.setPixmap(
                    pixmap.scaled(
                        QSize(145, 204),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            except RuntimeError:
                continue

    def _reflow_catalog(self) -> None:
        if not hasattr(self, "results_grid"):
            return
        cards: list[QWidget] = []
        while self.results_grid.count():
            item = self.results_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                cards.append(widget)
        available = max(160, self.results_scroll.viewport().width() - 20)
        columns = max(1, available // 169)
        for index, card in enumerate(cards):
            self.results_grid.addWidget(card, index // columns, index % columns)

    def _apply_responsive_layout(self) -> None:
        if not hasattr(self, "sidebar"):
            return
        width = self.width()
        if width < 900:
            self.sidebar.setFixedWidth(170)
            self.content_layout.setContentsMargins(14, 14, 14, 14)
            self.content_layout.setSpacing(12)
        elif width < 1250:
            self.sidebar.setFixedWidth(195)
            self.content_layout.setContentsMargins(20, 18, 20, 18)
            self.content_layout.setSpacing(15)
        else:
            self.sidebar.setFixedWidth(220)
            self.content_layout.setContentsMargins(30, 24, 30, 24)
            self.content_layout.setSpacing(18)
        if hasattr(self, "brand_logo") and not self.brand_logo_pixmap.isNull():
            logo_width = max(120, self.sidebar.width() - 36)
            self.brand_logo.setPixmap(
                self.brand_logo_pixmap.scaled(
                    QSize(logo_width, 72),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._reflow_catalog()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.resize_timer.start(80)

    @pyqtSlot(str)
    def _show_search_error(self, message: str) -> None:
        self.search_status.setText("Catalogue request failed.")
        QMessageBox.warning(self, "Catalogue unavailable", message)

    @pyqtSlot()
    def _search_finished(self) -> None:
        self.search_button.setEnabled(True)
        self.search_button.setText("Search catalogue")

    def _add_selected_to_queue(self) -> None:
        selected = [
            item for item, check in zip(self.results, self.result_checks)
            if check.isChecked()
        ]
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select one or more dramas first.")
            return
        existing = {str(item.get("book_id")) for item in self.queue}
        self.queue.extend(item for item in selected if str(item.get("book_id")) not in existing)
        self._refresh_queue()
        self._show_page(1)

    def _refresh_queue(self) -> None:
        self.queue_table.setRowCount(len(self.queue))
        for row, item in enumerate(self.queue):
            self.queue_table.setItem(row, 0, QTableWidgetItem(str(item.get("title", "—"))))
            self.queue_table.setItem(row, 1, QTableWidgetItem(str(item.get("episode_total", "—"))))
            episode_match = re.search(r"(\d+)", str(item.get("episode_total") or ""))
            maximum = max(1, int(episode_match.group(1)) if episode_match else 1)
            if "download_count" not in item:
                item["download_count"] = maximum
            count_spin = QSpinBox()
            count_spin.setRange(1, maximum)
            count_spin.setValue(min(maximum, int(item.get("download_count") or maximum)))
            count_spin.setSuffix(" eps")
            count_spin.valueChanged.connect(
                lambda value, i=row: self.queue[i].__setitem__("download_count", value)
            )
            self.queue_table.setCellWidget(row, 2, count_spin)
            self.queue_table.setItem(row, 3, QTableWidgetItem(str(item.get("book_id", "—"))))
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(0)
            progress.setFormat("0%")
            self.queue_table.setCellWidget(row, 4, progress)
            tasks = [task for task in self.download_manager.get_tasks()
                     if task.book_id == str(item.get("book_id"))]
            done = sum(task.status == "done" for task in tasks)
            if tasks:
                percent = int(sum(task.progress for task in tasks) / len(tasks))
                progress.setValue(percent)
                progress.setFormat(f"{percent}%")
                status = f"Successful {done}/{len(tasks)}"
            else:
                status = "Ready to download"
            self.queue_table.setItem(row, 5, QTableWidgetItem(status))
            self._set_queue_actions(row, item, done > 0)
        self.queue_card.set_value(str(len(self.queue)))
        self.download_button.setEnabled(bool(self.queue))

    def _start_downloads(self) -> None:
        if not self.queue:
            return
        self.download_button.setEnabled(False)
        self.download_button.setText("Preparing episodes…")
        for row in range(self.queue_table.rowCount()):
            self.queue_table.setItem(row, 5, QTableWidgetItem("Loading episode list…"))
        worker = PrepareDownloadsWorker(self.download_manager, list(self.queue))
        worker.signals.result.connect(self._downloads_prepared)
        worker.signals.error.connect(self._download_prepare_error)
        worker.signals.finished.connect(self._download_prepare_finished)
        self.thread_pool.start(worker)

    @pyqtSlot(object)
    def _downloads_prepared(self, added: object) -> None:
        count = int(added) if isinstance(added, int) else 0
        if count <= 0:
            existing_tasks = self.download_manager.get_tasks()
            completed = [task for task in existing_tasks if task.status == "done" and task.save_path]
            startable = [task for task in existing_tasks if task.status in {"pending", "stopped"}]
            if completed or startable:
                self._refresh_queue()
                if startable:
                    self.download_manager.start_queue()
                if completed and self.config.telegram_auto_send:
                    self.telegram_upload_status.setText(
                        f"Telegram: preparing {len(completed)} downloaded video(s)…"
                    )
                for task in completed:
                    self._queue_telegram_upload(task.video_id, task.save_path)
                return
            QMessageBox.warning(
                self,
                "No episodes available",
                "The server returned no downloadable episodes. Add a valid API key in Settings or try another drama.",
            )
            self._refresh_queue()
            return
        self.download_manager.start_queue()

    @pyqtSlot(str)
    def _download_prepare_error(self, message: str) -> None:
        QMessageBox.warning(self, "Download unavailable", message)
        self._refresh_queue()

    @pyqtSlot()
    def _download_prepare_finished(self) -> None:
        self.download_button.setText("Download all")
        self.download_button.setEnabled(bool(self.queue))

    @pyqtSlot(str, str)
    def _on_download_updated(self, book_id: str, video_id: str) -> None:
        tasks = [task for task in self.download_manager.get_tasks() if task.book_id == book_id]
        if not tasks:
            return
        statuses = {task.status for task in tasks}
        done = sum(task.status == "done" for task in tasks)
        progress = sum(task.progress for task in tasks) / len(tasks)
        if "downloading" in statuses:
            text = f"Downloading · Successful {done}/{len(tasks)}"
        elif statuses == {"done"}:
            text = f"Completed · Successful {done}/{len(tasks)}"
        elif "error" in statuses:
            error = next((task.error_msg for task in tasks if task.error_msg), "Download failed")
            text = f"Error: {error}"
        else:
            text = f"Waiting · {len(tasks)} episodes"
        for row, drama in enumerate(self.queue):
            if str(drama.get("book_id")) == book_id:
                bar = self.queue_table.cellWidget(row, 4)
                if isinstance(bar, QProgressBar):
                    bar.setValue(int(progress))
                    bar.setFormat(f"{progress:.0f}%")
                self.queue_table.setItem(row, 5, QTableWidgetItem(text))
                self._set_queue_actions(row, drama, done > 0)
                break
        completed_task = next(
            (task for task in tasks if task.video_id == video_id and task.status == "done"),
            None,
        )
        if completed_task is not None:
            self._queue_telegram_upload(completed_task.video_id, completed_task.save_path)

    @staticmethod
    def _telegram_target(value: str) -> str:
        target = value.strip()
        for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
            if target.startswith(prefix):
                target = target[len(prefix):].split("?", 1)[0].strip("/")
                break
        if target.startswith("+") or target.startswith("joinchat/"):
            return ""
        if target and not target.startswith("@") and not target.lstrip("-").isdigit():
            target = f"@{target}"
        return target

    def _queue_telegram_upload(self, video_id: str, file_path: str) -> None:
        if not self.config.telegram_auto_send or not file_path:
            return
        if video_id in self.telegram_uploading or video_id in self.telegram_sent:
            return
        token = self.config.telegram_bot_token.strip()
        target = self._telegram_target(self.config.telegram_chat_id)
        if not token or not target:
            self.telegram_upload_status.setText("Telegram: configure a bot token and public @group/chat ID")
            return
        self.telegram_uploading.add(video_id)
        self.telegram_upload_status.setText(f"Telegram: uploading {Path(file_path).name}…")
        worker = TelegramUploadWorker(token, target, video_id, file_path)
        worker.signals.result.connect(self._telegram_upload_complete)
        worker.signals.error.connect(self._telegram_upload_error)
        self.thread_pool.start(worker)

    @pyqtSlot(object)
    def _telegram_upload_complete(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 2:
            return
        video_id, filename = str(result[0]), str(result[1])
        self.telegram_uploading.discard(video_id)
        self.telegram_sent.add(video_id)
        self.telegram_upload_status.setText(f"Telegram: sent {filename}")

    @pyqtSlot(str)
    def _telegram_upload_error(self, value: str) -> None:
        video_id, _, message = value.partition("|")
        self.telegram_uploading.discard(video_id)
        self.telegram_upload_status.setText(f"Telegram error: {message or value}")

    def _set_queue_actions(self, row: int, drama: dict[str, Any], can_view: bool) -> None:
        actions = QWidget()
        actions.setObjectName("tableActions")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(4, 2, 4, 2)
        action_layout.setSpacing(5)
        if can_view:
            view = QPushButton("View Folder")
            view.setObjectName("viewFolderButton")
            view.clicked.connect(
                lambda _checked=False, book_id=str(drama.get("book_id")): self._open_download_folder(book_id)
            )
            action_layout.addWidget(view)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda _checked=False, i=row: self._remove_queue_item(i))
        action_layout.addWidget(remove)
        self.queue_table.setCellWidget(row, 6, actions)

    def _open_download_folder(self, book_id: str) -> None:
        task = next(
            (task for task in self.download_manager.get_tasks()
             if task.book_id == book_id and task.save_path),
            None,
        )
        folder = Path(task.save_path).parent if task is not None else Path(self.config.download_dir)
        if not folder.exists():
            QMessageBox.information(self, "Folder unavailable", "No downloaded file is available yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _remove_queue_item(self, index: int) -> None:
        if 0 <= index < len(self.queue):
            self.queue.pop(index)
            self._refresh_queue()

    def _clear_queue(self) -> None:
        self.queue.clear()
        self._refresh_queue()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.download_manager.stop_all()
        self.aria2.stop()
        super().closeEvent(event)

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose download folder", self.folder_edit.text())
        if selected:
            self.folder_edit.setText(selected)

    def _save_queue_telegram(self) -> None:
        token = self.queue_telegram_token.text().strip()
        group = self.queue_telegram_group.text().strip()
        enabled = self.queue_telegram_auto.isChecked()
        if enabled and (not token or not group):
            QMessageBox.warning(
                self, "Telegram configuration", "Bot Token and Group Link / Chat ID are required."
            )
            return
        if enabled and not self._telegram_target(group):
            QMessageBox.warning(
                self,
                "Telegram configuration",
                "Private invite links are unsupported. Use a public @groupname or numeric chat ID.",
            )
            return
        self.config.telegram_bot_token = token
        self.config.telegram_chat_id = group
        self.config.telegram_auto_send = enabled
        self.config.save()
        self.telegram_token_edit.setText(token)
        self.telegram_group_edit.setText(group)
        self.telegram_auto_check.setChecked(enabled)
        self.telegram_upload_status.setText("Telegram settings saved")

    def _save_settings(self) -> None:
        folder = self.folder_edit.text().strip() or str(DEFAULT_DOWNLOAD_DIR)
        telegram_token = self.telegram_token_edit.text().strip()
        telegram_group = self.telegram_group_edit.text().strip()
        telegram_auto = self.telegram_auto_check.isChecked()
        github_repository = self.github_repository_edit.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", github_repository):
            QMessageBox.warning(self, "GitHub repository", "Use owner/repository format.")
            return
        if telegram_auto and (not telegram_token or not telegram_group):
            QMessageBox.warning(
                self, "Telegram configuration", "Bot Token and Telegram Group are required for auto-send."
            )
            return
        if telegram_auto and not self._telegram_target(telegram_group):
            QMessageBox.warning(
                self,
                "Telegram configuration",
                "Private invite links cannot be used by the Bot API. Enter the numeric chat ID instead.",
            )
            return
        self.config.download_dir = str(Path(folder).expanduser())
        self.config.concurrent = self.concurrent_spin.value()
        self.config.key = self.api_key_edit.text().strip()
        self.config.telegram_bot_token = telegram_token
        self.config.telegram_chat_id = telegram_group
        self.config.telegram_auto_send = telegram_auto
        self.config.github_repository = github_repository
        self.config.save()
        self.queue_telegram_token.setText(telegram_token)
        self.queue_telegram_group.setText(telegram_group)
        self.queue_telegram_auto.setChecked(telegram_auto)
        self._update_api_status()
        QMessageBox.information(self, "Saved", "Preferences saved successfully.")

    def _update_api_status(self) -> None:
        if not hasattr(self, "api_status"):
            return
        if self.config.is_key_set:
            self.api_status.setText("Authorized mode — full episodes depend on your key permissions")
            self.api_status.setStyleSheet("color: #149c57;")
            if hasattr(self, "queue_notice"):
                self.queue_notice.setText("Authorized mode is active. Episode availability follows your API key permissions.")
        else:
            self.api_status.setText("Public mode — only episodes opened by the website can be downloaded")
            self.api_status.setStyleSheet("")
            if hasattr(self, "queue_notice"):
                self.queue_notice.setText("Public mode can download only episodes opened by the website. Add an authorized API key in Settings for more access.")


def app_stylesheet(theme: str = "light") -> str:
    dark = """
    * { font-family: "Segoe UI", "Noto Sans"; font-size: 13px; color: #edfaff; }
    QMainWindow, QWidget#content { background: #080d1b; }
    QFrame#sidebar { background: #0c1326; border-right: 2px solid #00d9ff; }
    QLabel#brand { font-size: 19px; font-weight: 800; color: #ff2d75; }
    QLabel#brandSub { font-size: 9px; font-weight: 650; color: #00eaff; letter-spacing: 0.5px; }
    QLabel#contactLabel { color: #71809c; font-size: 10px; font-weight: 750; padding: 4px 12px; letter-spacing: 1px; }
    QLabel#pageTitle { font-size: 26px; font-weight: 750; color: #ffffff; }
    QLabel#muted { color: #8fa6c9; }
    QLabel#metricValue { font-size: 25px; font-weight: 800; }
    QLabel#fieldLabel { color: #c8d8f1; font-weight: 650; }
    QLabel#warningText { color: #ffd23f; }
    QLabel#coverThumbnail { background: #18223a; color: #71809c; border: 1px solid #2b3b59; border-radius: 7px; font-size: 10px; }
    QScrollArea#catalogScroll { background: transparent; border: none; }
    QScrollArea#catalogFilterScroll, QScrollArea#settingsScroll { background: transparent; border: none; }
    QWidget#catalogBar { background: transparent; }
    QWidget#catalogContainer { background: transparent; }
    QFrame#dramaCard { background: #111a31; border: 1px solid #263854; border-radius: 12px; }
    QFrame#dramaCard:hover { border: 2px solid #ff5b35; background: #15203a; }
    QLabel#cardCover { background: #18223a; color: #71809c; border: none; border-radius: 9px; font-size: 10px; }
    QLabel#cardTitle { font-weight: 650; padding: 0 2px; }
    QLabel#cardEpisodes { color: #b9c9df; font-size: 11px; font-weight: 700; }
    QLabel#catalogTitle { font-weight: 800; color: #ff7a45; margin-right: 6px; }
    QLabel#statusBadge { background: #073b3a; color: #b7ff2a; border: 1px solid #00f5d4;
        border-radius: 13px; padding: 6px 11px; font-size: 11px; font-weight: 750; }
    QFrame#metricCard, QFrame#panel { background: #111a31; border: 1px solid #1a8dac; border-radius: 12px; }
    QFrame#notice { background: #101c3b; border: 1px solid #7c3cff; border-radius: 10px; }
    QFrame#telegramPanel { background: #101c32; border: 1px solid #229ed9; border-radius: 11px; }
    QLabel#telegramTitle { color: #35bff3; font-weight: 800; letter-spacing: 0.5px; }
    QFrame#sideInfo { background: #111a31; border: 1px solid #244569; border-radius: 10px; }
    QPushButton { background: #16213d; border: 1px solid #176b8c; border-radius: 8px;
        padding: 9px 14px; font-weight: 650; }
    QPushButton:hover { background: #1b3155; border-color: #00eaff; }
    QPushButton:disabled { color: #53617b; background: #101629; border-color: #26324d; }
    QPushButton#navButton { text-align: left; padding: 11px 14px; border-radius: 10px;
        background: #090d19; color: #b8c2d8; border: 1px solid #283148; font-weight: 750; }
    QPushButton#navButton[navRole="discover"] { color: #ff557d; border-color: #8f2149; }
    QPushButton#navButton[navRole="queue"] { color: #bd78ff; border-color: #63389b; }
    QPushButton#navButton[navRole="settings"] { color: #43c7ff; border-color: #236e9c; }
    QPushButton#navButton[navRole="discover"]:hover { background: #2b1020; border-color: #ff2d75; color: #ffffff; }
    QPushButton#navButton[navRole="queue"]:hover { background: #211337; border-color: #a855f7; color: #ffffff; }
    QPushButton#navButton[navRole="settings"]:hover { background: #0d2134; border-color: #22b8f0; color: #ffffff; }
    QPushButton#navButton[navRole="discover"]:checked { background: #ff245f; color: #ffffff; border: 1px solid #ff8cad; }
    QPushButton#navButton[navRole="queue"]:checked { background: #7c3cff; color: #ffffff; border: 1px solid #c4a0ff; }
    QPushButton#navButton[navRole="settings"]:checked { background: #087fab; color: #ffffff; border: 1px solid #68dcff; }
    QPushButton#updateButton { text-align: left; padding: 10px 14px; border-radius: 10px;
        background: #0b211d; color: #42f5b0; border: 1px solid #168f6a; font-weight: 750; }
    QPushButton#updateButton:hover { background: #0f3a30; color: #ffffff; border-color: #42f5b0; }
    QPushButton#youtubeButton, QPushButton#telegramButton, QPushButton#donateButton { text-align: left; border: none; background: transparent; padding: 9px 14px; }
    QPushButton#youtubeButton { color: #ff4d5e; }
    QPushButton#telegramButton { color: #35bff3; }
    QPushButton#donateButton { color: #ff8a65; }
    QPushButton#youtubeButton:hover, QPushButton#telegramButton:hover, QPushButton#donateButton:hover { background: #122342; }
    QLabel#donateTitle { font-size: 22px; font-weight: 800; }
    QPushButton#primaryButton { background: #16d66b; color: #04120a; border: 1px solid #b7ff2a; padding: 11px 18px; }
    QPushButton#primaryButton:hover { background: #3bea82; border-color: #e5ff87; }
    QPushButton#primaryButton:disabled { color: #657089; background: #151c2d; border-color: #303a50; }
    QPushButton#secondaryButton { background: #141d3b; color: #00f5d4; border-color: #00b8d9; }
    QPushButton#catalogChip { border-radius: 14px; padding: 6px 11px; background: #151f36; color: #aebdd2; border-color: #34445e; }
    QPushButton#catalogChip:hover { border-color: #ff7a45; color: #ffffff; }
    QPushButton#catalogChip:checked { background: #ff6b24; color: #ffffff; border-color: #ff6b24; }
    QLineEdit, QSpinBox { background: #080e20; border: 1px solid #137c9b; border-radius: 8px;
        padding: 10px 12px; selection-background-color: #ff2d75; }
    QLineEdit:focus, QSpinBox:focus { border-color: #00eaff; }
    QTableWidget { background: #0d1529; alternate-background-color: #101b34; border: 1px solid #137c9b;
        border-radius: 10px; gridline-color: transparent; outline: none; }
    QTableWidget::item { border-bottom: 1px solid #1a2b49; padding: 7px; }
    QTableWidget::item:selected { background: #40225c; color: #ffffff; }
    QProgressBar { background: #0b1326; border: 1px solid #28506b; border-radius: 7px; text-align: center; min-height: 18px; }
    QProgressBar::chunk { background: #14cf70; border-radius: 6px; }
    QWidget#tableActions { background: transparent; }
    QPushButton#viewFolderButton { color: #00f5d4; border-color: #00a8c9; padding: 6px 9px; }
    QHeaderView::section { background: #ff245f; color: #ffffff; border: none;
        border-bottom: 2px solid #00eaff; padding: 11px 8px; font-size: 11px; font-weight: 750; }
    QScrollBar:vertical { background: #091126; width: 10px; }
    QScrollBar::handle:vertical { background: #00a8c9; border-radius: 5px; min-height: 30px; }
    """
    if theme == "dark":
        return dark
    return dark + """
    * { color: #172033; }
    QMainWindow, QWidget#content { background: #f4f7fb; }
    QFrame#sidebar { background: #ffffff; border-right-color: #16b8d4; }
    QLabel#brandSub { color: #087f9b; }
    QLabel#pageTitle { color: #101828; }
    QLabel#muted { color: #64748b; }
    QLabel#fieldLabel { color: #344054; }
    QLabel#warningText { color: #a15c00; }
    QLabel#contactLabel { color: #7a8699; }
    QLabel#coverThumbnail { background: #edf1f5; color: #7a8699; border-color: #cbd5e1; }
    QFrame#dramaCard { background: #ffffff; border-color: #d7cfc8; }
    QFrame#dramaCard:hover { background: #fffaf6; border-color: #ff6b35; }
    QLabel#cardCover { background: #edf1f5; color: #7a8699; }
    QLabel#cardEpisodes { color: #6c625b; }
    QLabel#catalogTitle { color: #e85d1f; }
    QLabel#statusBadge { background: #e8fff8; color: #087443; border-color: #18b981; }
    QFrame#metricCard, QFrame#panel { background: #ffffff; border-color: #9ccbd7; }
    QFrame#notice { background: #f3efff; border-color: #8b5cf6; }
    QFrame#telegramPanel { background: #f3fbff; border-color: #55acd2; }
    QLabel#telegramTitle { color: #1688bd; }
    QFrame#sideInfo { background: #f7faff; border-color: #c6d4e5; }
    QPushButton { background: #ffffff; border-color: #9cb3c9; }
    QPushButton:hover { background: #edf8fb; border-color: #0891b2; }
    QPushButton:disabled { color: #98a2b3; background: #eef1f5; border-color: #d0d5dd; }
    QPushButton#navButton { background: #111827; border-color: #344158; }
    QPushButton#navButton[navRole="discover"]:hover { background: #3a1225; }
    QPushButton#navButton[navRole="queue"]:hover { background: #281642; }
    QPushButton#navButton[navRole="settings"]:hover { background: #102a40; }
    QPushButton#updateButton { background: #eafff7; color: #08775a; border-color: #35b890; }
    QPushButton#updateButton:hover { background: #cffff0; color: #064c3c; border-color: #0aa978; }
    QPushButton#youtubeButton:hover, QPushButton#telegramButton:hover, QPushButton#donateButton:hover { background: #edf6fa; }
    QPushButton#primaryButton { background: #16c96a; color: #04120a; border-color: #0fa958; }
    QPushButton#primaryButton:hover { background: #31dc7d; border-color: #087443; }
    QPushButton#primaryButton:disabled { color: #98a2b3; background: #e4e7ec; border-color: #cbd2dc; }
    QPushButton#secondaryButton { background: #f0fffc; color: #087f72; border-color: #16a6b6; }
    QPushButton#catalogChip { background: #ffffff; color: #5f554f; border-color: #ddcec3; }
    QPushButton#catalogChip:hover { background: #fff8f2; color: #c94c13; border-color: #ff7a45; }
    QPushButton#catalogChip:checked { background: #ff6b24; color: #ffffff; border-color: #ff6b24; }
    QPushButton#themeButton { min-width: 78px; }
    QLineEdit, QSpinBox { background: #ffffff; border-color: #9cb3c9; }
    QLineEdit:focus, QSpinBox:focus { border-color: #0891b2; }
    QTableWidget { background: #ffffff; alternate-background-color: #f7f9fc; border-color: #9ccbd7; }
    QTableWidget::item { border-bottom-color: #e2e8f0; }
    QTableWidget::item:selected { background: #f4c5da; color: #31101f; }
    QProgressBar { background: #e9eef4; border-color: #a8bacb; color: #172033; }
    QProgressBar::chunk { background: #18c66c; }
    QPushButton#viewFolderButton { background: #effffc; color: #087f72; border-color: #16a6b6; }
    QHeaderView::section { background: #ff245f; color: #ffffff; border-bottom-color: #00b8d9; }
    QScrollBar:vertical { background: #edf2f7; }
    QScrollBar::handle:vertical { background: #52a9bc; }
    """
