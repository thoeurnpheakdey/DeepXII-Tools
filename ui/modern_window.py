from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import requests

from PyQt6.QtCore import (QEasingCurve, QObject, QProcess, QPropertyAnimation, QRunnable,
                         QSize, Qt, QThreadPool, QTimer, QUrl, pyqtSignal, pyqtSlot)
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QComboBox,
    QProgressBar, QProgressDialog, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QApplication, QGraphicsOpacityEffect, QVBoxLayout, QWidget,
)

from config import Config, DEFAULT_DOWNLOAD_DIR
from core.aria2_manager import Aria2Manager
from core.download_manager import DownloadManager
from core.library_manager import LibraryDrama, scan_library, video_thumbnail
from core.public_catalog import search_catalog
from core.update_manager import APP_VERSION, ReleaseInfo, check_latest_release, download_release

KHMER_TRANSLATIONS = {
    "Discover": "ស្វែងរក",
    "My Queue": "បញ្ជីទាញយក",
    "My Library": "បណ្ណាល័យរបស់ខ្ញុំ",
    "Settings": "ការកំណត់",
    "Donate Admin": "ឧបត្ថម្ភ Admin",
    "Update Tools": "អាប់ដេតកម្មវិធី",
    "YouTube": "YouTube",
    "Facebook": "Facebook",
    "Telegram": "Telegram",
    "Website": "គេហទំព័រ",
    "CONTACT": "ទំនាក់ទំនង",
    "PUBLIC MODE": "របៀបសាធារណៈ",
    "PUBLIC CATALOGUE": "បញ្ជីរឿងសាធារណៈ",
    "Live search is ready. Downloads activate with an authorized endpoint.": "ការស្វែងរកបានត្រៀមរួច។ ការទាញយកអាស្រ័យលើសិទ្ធិ API។",
    "CATALOG": "បញ្ជីរឿង",
    "Explore the public Hongguo catalogue": "ស្វែងរករឿងក្នុងបញ្ជីសាធារណៈ Hongguo",
    "Review dramas prepared for download": "ពិនិត្យរឿងដែលត្រៀមទាញយក",
    "Browse and play downloaded videos": "មើល និងចាក់វីដេអូដែលបានទាញយក",
    "Manage local preferences": "គ្រប់គ្រងការកំណត់កម្មវិធី",
    "Support the development of DeepXII Tools": "គាំទ្រការអភិវឌ្ឍ DeepXII Tools",
    "Search catalogue": "ស្វែងរករឿង",
    "Search a Chinese drama title…": "ស្វែងរកចំណងជើងរឿងចិន…",
    "Add selected to queue": "បន្ថែមរឿងដែលបានជ្រើសទៅបញ្ជី",
    "Search downloaded dramas…": "ស្វែងរករឿងដែលបានទាញយក…",
    "Newest": "ថ្មីបំផុត",
    "Name": "ឈ្មោះ",
    "Most episodes": "ភាគច្រើនបំផុត",
    "Largest size": "ទំហំធំបំផុត",
    "Refresh": "ផ្ទុកឡើងវិញ",
    "Open download folder": "បើកថតទាញយក",
    "Download folder": "ថតទាញយក",
    "Concurrent episodes": "ចំនួនភាគទាញយកព្រមគ្នា",
    "Preferred quality": "គុណភាពវីដេអូ",
    "Authorized API key": "API Key ដែលបានអនុញ្ញាត",
    "API status": "ស្ថានភាព API",
    "Telegram Bot Token": "Telegram Bot Token",
    "Telegram Group": "ក្រុម Telegram",
    "Auto-send videos": "ផ្ញើវីដេអូដោយស្វ័យប្រវត្តិ",
    "GitHub repository": "GitHub repository",
    "Browse": "ជ្រើសរើស",
    "Save preferences": "រក្សាទុកការកំណត់",
    "Clear queue": "សម្អាតបញ្ជី",
    "Pause": "ផ្អាក",
    "Resume": "បន្ត",
    "Retry failed": "សាកល្បងឡើងវិញ",
    "Cancel": "បោះបង់",
    "Download all": "ទាញយកទាំងអស់",
    "Start": "ចាប់ផ្ដើម",
    "Remove": "ដកចេញ",
    "View Folder": "មើលថត",
    "COMPLETED VIDEOS": "វីដេអូដែលបានទាញយករួច",
    "File size": "ទំហំឯកសារ",
    "Completed": "រួចរាល់",
    "Drama": "រឿង",
    "Episodes": "ចំនួនភាគ",
    "Episode range": "ជួរភាគ",
    "Series ID": "លេខសម្គាល់រឿង",
    "Progress": "ដំណើរការ",
    "Status": "ស្ថានភាព",
    "Actions": "សកម្មភាព",
    "Folder": "ថត",
    "Delete": "លុប",
    "Play": "ចាក់",
    "Dark": "ងងឹត",
    "Light": "ភ្លឺ",
    "Support DeepXII Tools": "គាំទ្រ DeepXII Tools",
    "Scan the ABA PAY QR code below to donate to Nava Seal Digital.": "ស្កេន ABA PAY QR Code ខាងក្រោម ដើម្បីឧបត្ថម្ភ Nava Seal Digital។",
    "Language": "ភាសា",
    "English": "English",
    "Khmer": "ខ្មែរ",
    "Open @BotFather": "បើក @BotFather",
    "Save Telegram": "រក្សាទុក Telegram",
    "Automatically send every completed video": "ផ្ញើវីដេអូដែលទាញយករួចដោយស្វ័យប្រវត្តិ",
    "Send each completed download to Telegram": "ផ្ញើវីដេអូដែលទាញយករួចទៅ Telegram",
}


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
                start = max(1, int(drama.get("download_start") or 1))
                end = max(start, int(drama.get("download_end") or drama.get("download_count") or start))
                added += self.manager.add_drama(
                    str(drama.get("book_id") or ""),
                    str(drama.get("title") or "Untitled drama"),
                    f"{start}-{end}",
                )
            self.signals.result.emit(added)
        except Exception as exc:  # pylint: disable=broad-except
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class VideoThumbnailWorker(QRunnable):
    def __init__(self, video: Path, key: str) -> None:
        super().__init__()
        self.video = video
        self.key = key
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            thumbnail = video_thumbnail(self.video)
            self.signals.result.emit((self.key, str(thumbnail) if thumbnail else ""))
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


class QueueTable(QTableWidget):
    reorder_requested = pyqtSignal(int, int)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        source = self.currentRow()
        target = self.indexAt(event.position().toPoint()).row()
        if target < 0:
            target = self.rowCount() - 1
        if source >= 0 and target >= 0 and source != target:
            self.reorder_requested.emit(source, target)
            event.acceptProposedAction()
            return
        event.ignore()


class ModernWindow(QMainWindow):
    def _t(self, text: str) -> str:
        return KHMER_TRANSLATIONS.get(text, text) if self.config.language == "km" else text

    def __init__(self, config: Config, download_manager: DownloadManager, aria2: Aria2Manager) -> None:
        super().__init__()
        self.config = config
        self.download_manager = download_manager
        self.aria2 = aria2
        self.results: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []
        self.library_items: list[LibraryDrama] = []
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
        self.page_animation: QPropertyAnimation | None = None
        self.library_thumbnail_labels: dict[str, list[QLabel]] = {}
        self.library_thumbnail_pending: set[str] = set()
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._apply_responsive_layout)
        self.setWindowTitle("DeepXII Tools")
        self.setMinimumSize(760, 560)
        self.resize(1280, 790)
        self._build_ui()
        self.download_manager.task_updated.connect(self._on_download_updated)
        self.download_manager.queue_changed.connect(self._restore_persisted_queue)
        self._restore_persisted_queue()
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
        self.pages.addWidget(self._build_library_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(self._build_donate_page())
        self.content_layout.addWidget(self.pages, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _animate_page(self, page: QWidget) -> None:
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(200)
        animation.setStartValue(0.45)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.page_animation = animation
        animation.start()

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
        for icon, text, index, role in (
            ("⌕", "Discover", 0, "discover"),
            ("▤", "My Queue", 1, "queue"),
            ("▶", "My Library", 2, "library"),
            ("⚙", "Settings", 3, "settings"),
        ):
            button = QPushButton(f"{icon}  {self._t(text)}")
            button.setObjectName("navButton")
            button.setProperty("navRole", role)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.update_button = QPushButton(f"↻  {self._t('Update Tools')}  ·  v{APP_VERSION}")
        self.update_button.setObjectName("updateButton")
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_button.clicked.connect(self._check_for_updates)
        layout.addWidget(self.update_button)
        layout.addSpacing(18)
        contact_label = QLabel(self._t("CONTACT"))
        contact_label.setObjectName("contactLabel")
        layout.addWidget(contact_label)
        youtube = QPushButton(f"▶  {self._t('YouTube')}")
        youtube.setObjectName("youtubeButton")
        youtube.setCursor(Qt.CursorShape.PointingHandCursor)
        youtube.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.youtube.com/@NavaSealDigital"))
        )
        facebook = QPushButton(f"f  {self._t('Facebook')}")
        facebook.setObjectName("facebookButton")
        facebook.setCursor(Qt.CursorShape.PointingHandCursor)
        facebook.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://www.facebook.com/navasealSoftDeveloper")
            )
        )
        telegram = QPushButton(f"➤  {self._t('Telegram')}")
        telegram.setObjectName("telegramButton")
        telegram.setCursor(Qt.CursorShape.PointingHandCursor)
        telegram.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://t.me/NavasealDigital"))
        )
        website = QPushButton(f"◆  {self._t('Website')}")
        website.setObjectName("websiteButton")
        website.setCursor(Qt.CursorShape.PointingHandCursor)
        website.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://digital.navaseal.site"))
        )
        donate = QPushButton(f"♥  {self._t('Donate Admin')}")
        donate.setObjectName("donateButton")
        donate.setCursor(Qt.CursorShape.PointingHandCursor)
        donate.setCheckable(True)
        donate.clicked.connect(lambda _checked=False: self._show_page(4))
        self.nav_group.addButton(donate)
        self.nav_buttons.append(donate)
        layout.addWidget(youtube)
        layout.addWidget(facebook)
        layout.addWidget(telegram)
        layout.addWidget(website)
        layout.addWidget(donate)
        layout.addStretch(1)

        info = QFrame()
        info.setObjectName("sideInfo")
        info_layout = QVBoxLayout(info)
        info_layout.addWidget(QLabel(self._t("PUBLIC CATALOGUE")))
        hint = QLabel(self._t("Live search is ready. Downloads activate with an authorized endpoint."))
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
        self.update_button.setText(f"↻  {self._t('Update Tools')}  ·  v{APP_VERSION}")

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
        badge = QLabel(f"●  {self._t('PUBLIC MODE')}")
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
        self.theme_button.setText(
            f"☾  {self._t('Dark')}" if self.config.theme == "light" else f"☀  {self._t('Light')}"
        )

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
        self.search_input.setPlaceholderText(self._t("Search a Chinese drama title…"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._start_search)
        self.search_button = QPushButton(self._t("Search catalogue"))
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self._start_search)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_button)
        layout.addWidget(search_card)

        catalog_widget = QWidget()
        catalog_widget.setObjectName("catalogBar")
        catalog_bar = QHBoxLayout(catalog_widget)
        catalog_bar.setContentsMargins(0, 0, 0, 0)
        catalog_title = QLabel(f"▤  {self._t('CATALOG')}")
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
        self.add_queue_button = QPushButton(f"＋ {self._t('Add selected to queue')}")
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
        create_bot = QPushButton(self._t("Open @BotFather"))
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
        self.queue_telegram_auto = QCheckBox(self._t("Automatically send every completed video"))
        self.queue_telegram_auto.setChecked(self.config.telegram_auto_send)
        telegram_layout.addWidget(self.queue_telegram_auto, 3, 1)
        save_telegram = QPushButton(self._t("Save Telegram"))
        save_telegram.setObjectName("primaryButton")
        save_telegram.clicked.connect(self._save_queue_telegram)
        telegram_layout.addWidget(save_telegram, 3, 2)
        self.telegram_upload_status = QLabel("")
        self.telegram_upload_status.setObjectName("muted")
        telegram_layout.addWidget(self.telegram_upload_status, 4, 1, 1, 2)
        telegram_layout.setColumnStretch(1, 1)
        layout.addWidget(telegram_panel)

        headers = [self._t(text) for text in ("Drama", "Episodes", "Episode range", "Series ID", "Progress", "Status", "Actions")]
        self.queue_table = QueueTable(0, len(headers))
        self.queue_table.setHorizontalHeaderLabels(headers)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.verticalHeader().setDefaultSectionSize(48)
        self.queue_table.setDragEnabled(True)
        self.queue_table.setAcceptDrops(True)
        self.queue_table.setDropIndicatorShown(True)
        self.queue_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.queue_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.queue_table.reorder_requested.connect(self._reorder_queue)
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.queue_table.setColumnWidth(2, 175)
        self.queue_table.setColumnWidth(4, 180)
        self.queue_table.setColumnWidth(6, 270)
        self.queue_splitter = QSplitter(Qt.Orientation.Vertical)
        self.queue_splitter.setChildrenCollapsible(False)
        self.queue_splitter.addWidget(self.queue_table)
        completed_section = QWidget()
        completed_layout = QVBoxLayout(completed_section)
        completed_layout.setContentsMargins(0, 0, 0, 0)
        completed_layout.setSpacing(6)
        completed_title = QLabel(self._t("COMPLETED VIDEOS"))
        completed_title.setObjectName("completedTitle")
        completed_layout.addWidget(completed_title)
        self.completed_table = self._new_table([
            self._t("Drama"), self._t("Episodes"), self._t("File size"), self._t("Status"), self._t("Actions")
        ])
        self.completed_table.setObjectName("completedTable")
        self.completed_table.horizontalHeader().setObjectName("completedHeader")
        self.completed_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.completed_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.completed_table.setColumnWidth(2, 110)
        self.completed_table.setColumnWidth(3, 100)
        self.completed_table.setColumnWidth(4, 220)
        self.completed_table.verticalHeader().setDefaultSectionSize(58)
        self.completed_table.setMinimumHeight(150)
        completed_layout.addWidget(self.completed_table, 1)
        self.queue_splitter.addWidget(completed_section)
        self.queue_splitter.setStretchFactor(0, 3)
        self.queue_splitter.setStretchFactor(1, 2)
        self.queue_splitter.setSizes([260, 190])
        layout.addWidget(self.queue_splitter, 1)
        self.queue_summary = QLabel("")
        self.queue_summary.setObjectName("queueSummary")
        layout.addWidget(self.queue_summary)
        controls = QHBoxLayout()
        clear_button = QPushButton(self._t("Clear queue"))
        clear_button.setObjectName("dangerButton")
        clear_button.clicked.connect(self._clear_queue)
        self.pause_button = QPushButton(self._t("Pause"))
        self.pause_button.setObjectName("secondaryButton")
        self.pause_button.clicked.connect(self._pause_downloads)
        self.resume_button = QPushButton(self._t("Resume"))
        self.resume_button.setObjectName("primaryButton")
        self.resume_button.clicked.connect(self.download_manager.resume_all)
        self.retry_button = QPushButton(self._t("Retry failed"))
        self.retry_button.setObjectName("secondaryButton")
        self.retry_button.clicked.connect(self.download_manager.retry_failed)
        self.cancel_button = QPushButton(self._t("Cancel"))
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel_downloads)
        self.download_button = QPushButton(self._t("Download all"))
        self.download_button.setObjectName("primaryButton")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._start_downloads)
        controls.addWidget(clear_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.resume_button)
        controls.addWidget(self.retry_button)
        controls.addWidget(self.cancel_button)
        controls.addStretch(1)
        controls.addWidget(self.download_button)
        layout.addLayout(controls)
        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        toolbar = QFrame()
        toolbar.setObjectName("panel")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText(self._t("Search downloaded dramas…"))
        self.library_search.setClearButtonEnabled(True)
        self.library_search.textChanged.connect(self._render_library)
        self.library_sort = QComboBox()
        for mode in ("Newest", "Name", "Most episodes", "Largest size"):
            self.library_sort.addItem(self._t(mode), mode)
        self.library_sort.currentIndexChanged.connect(self._render_library)
        refresh = QPushButton(f"↻  {self._t('Refresh')}")
        refresh.setObjectName("secondaryButton")
        refresh.clicked.connect(self._refresh_library)
        open_root = QPushButton(self._t("Open download folder"))
        open_root.clicked.connect(lambda: self._open_path(Path(self.config.download_dir)))
        toolbar_layout.addWidget(self.library_search, 1)
        toolbar_layout.addWidget(self.library_sort)
        toolbar_layout.addWidget(refresh)
        toolbar_layout.addWidget(open_root)
        layout.addWidget(toolbar)

        self.library_summary = QLabel("No downloaded videos found.")
        self.library_summary.setObjectName("muted")
        layout.addWidget(self.library_summary)
        self.library_scroll = QScrollArea()
        self.library_scroll.setObjectName("catalogScroll")
        self.library_scroll.setWidgetResizable(True)
        self.library_container = QWidget()
        self.library_container.setObjectName("catalogContainer")
        self.library_grid = QGridLayout(self.library_container)
        self.library_grid.setContentsMargins(8, 8, 8, 8)
        self.library_grid.setHorizontalSpacing(14)
        self.library_grid.setVerticalSpacing(14)
        self.library_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.library_scroll.setWidget(self.library_container)
        layout.addWidget(self.library_scroll, 1)
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
        grid.addWidget(self._field_label(self._t("Download folder")), 0, 0)
        self.folder_edit = QLineEdit(self.config.download_dir)
        browse = QPushButton(self._t("Browse"))
        browse.clicked.connect(self._choose_folder)
        grid.addWidget(self.folder_edit, 0, 1)
        grid.addWidget(browse, 0, 2)
        grid.addWidget(self._field_label(self._t("Concurrent episodes")), 1, 0)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 16)
        self.concurrent_spin.setValue(self.config.concurrent)
        grid.addWidget(self.concurrent_spin, 1, 1)
        grid.addWidget(self._field_label(self._t("Preferred quality")), 2, 0)
        quality = QLineEdit(self.config.level)
        quality.setReadOnly(True)
        grid.addWidget(quality, 2, 1)
        grid.addWidget(self._field_label(self._t("Authorized API key")), 3, 0)
        self.api_key_edit = QLineEdit(self.config.key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter a valid key for full episode access")
        self.api_key_edit.setClearButtonEnabled(True)
        grid.addWidget(self.api_key_edit, 3, 1, 1, 2)
        grid.addWidget(self._field_label(self._t("API status")), 4, 0)
        self.api_status = QLabel()
        self.api_status.setObjectName("warningText")
        self._update_api_status()
        grid.addWidget(self.api_status, 4, 1, 1, 2)
        grid.addWidget(self._field_label(self._t("Telegram Bot Token")), 5, 0)
        self.telegram_token_edit = QLineEdit(self.config.telegram_bot_token)
        self.telegram_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.telegram_token_edit.setPlaceholderText("Token from @BotFather")
        self.telegram_token_edit.setClearButtonEnabled(True)
        grid.addWidget(self.telegram_token_edit, 5, 1, 1, 2)
        grid.addWidget(self._field_label(self._t("Telegram Group")), 6, 0)
        self.telegram_group_edit = QLineEdit(self.config.telegram_chat_id)
        self.telegram_group_edit.setPlaceholderText("https://t.me/groupname, @groupname, or numeric chat ID")
        grid.addWidget(self.telegram_group_edit, 6, 1, 1, 2)
        grid.addWidget(self._field_label(self._t("Auto-send videos")), 7, 0)
        self.telegram_auto_check = QCheckBox(self._t("Send each completed download to Telegram"))
        self.telegram_auto_check.setChecked(self.config.telegram_auto_send)
        grid.addWidget(self.telegram_auto_check, 7, 1, 1, 2)
        grid.addWidget(self._field_label(self._t("GitHub repository")), 8, 0)
        self.github_repository_edit = QLineEdit(self.config.github_repository)
        self.github_repository_edit.setPlaceholderText("owner/repository")
        grid.addWidget(self.github_repository_edit, 8, 1, 1, 2)
        grid.addWidget(self._field_label(self._t("Language")), 9, 0)
        self.language_combo = QComboBox()
        self.language_combo.addItem(self._t("English"), "en")
        self.language_combo.addItem(self._t("Khmer"), "km")
        self.language_combo.setCurrentIndex(1 if self.config.language == "km" else 0)
        grid.addWidget(self.language_combo, 9, 1, 1, 2)
        save = QPushButton(self._t("Save preferences"))
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_settings)
        grid.addWidget(save, 10, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_donate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("donatePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 22, 28, 22)
        panel_layout.setSpacing(10)
        heading = QLabel("ឧបត្ថម Admin សម្រាប់កាហ្វេ")
        heading.setObjectName("donateTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(self._t("Scan the ABA PAY QR code below to donate to Nava Seal Digital."))
        description.setObjectName("muted")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.donate_image = QLabel()
        self.donate_image.setObjectName("donateImage")
        self.donate_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.donate_image.setWordWrap(True)
        self.donate_image.setMinimumHeight(360)
        panel_layout.addWidget(heading)
        panel_layout.addWidget(description)
        panel_layout.addWidget(self.donate_image, 1)
        layout.addWidget(panel)
        QTimer.singleShot(0, self._refresh_donate_qr)
        return page

    @staticmethod
    def _donate_qr_path() -> Path:
        return Path(__file__).resolve().parent.parent / "resources" / "donate_qr.png"

    def _refresh_donate_qr(self) -> None:
        if not hasattr(self, "donate_image"):
            return
        pixmap = QPixmap(str(self._donate_qr_path()))
        if pixmap.isNull():
            self.donate_image.setPixmap(QPixmap())
            self.donate_image.setText("Donation QR image is unavailable.")
            return
        self.donate_image.setText("")
        width = max(260, min(560, self.donate_image.width() - 20))
        height = max(340, self.donate_image.height() - 10)
        self.donate_image.setPixmap(
            pixmap.scaled(QSize(width, height), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )

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
                  ("My Library", "Browse and play downloaded videos"),
                  ("Settings", "Manage local preferences"),
                  ("Donate Admin", "Support the development of DeepXII Tools")]
        self.pages.setCurrentIndex(index)
        self._animate_page(self.pages.widget(index))
        self.page_title.setText(self._t(titles[index][0]))
        self.page_subtitle.setText(self._t(titles[index][1]))
        self.nav_buttons[index].setChecked(True)
        if index == 2:
            self._refresh_library()
        elif index == 4:
            self._refresh_donate_qr()

    def _refresh_library(self, *_args: object) -> None:
        self.library_items = scan_library(self.config.download_dir)
        self._render_library()

    def _render_library(self, *_args: object) -> None:
        if not hasattr(self, "library_grid"):
            return
        while self.library_grid.count():
            item = self.library_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.library_thumbnail_labels.clear()
        query = self.library_search.text().strip().lower()
        items = [item for item in self.library_items if query in item.title.lower()]
        sort_mode = str(self.library_sort.currentData() or "Newest")
        if sort_mode == "Name":
            items.sort(key=lambda item: item.title.lower())
        elif sort_mode == "Most episodes":
            items.sort(key=lambda item: item.episode_count, reverse=True)
        elif sort_mode == "Largest size":
            items.sort(key=lambda item: item.total_bytes, reverse=True)
        else:
            items.sort(key=lambda item: item.modified_at, reverse=True)
        columns = max(1, (self.library_scroll.viewport().width() - 20) // 290)
        for index, drama in enumerate(items):
            card = QFrame()
            card.setObjectName("libraryCard")
            card.setFixedWidth(270)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(9, 9, 9, 10)
            card_layout.setSpacing(7)
            cover = QLabel("▶  VIDEO LIBRARY")
            cover.setObjectName("libraryCover")
            cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover.setFixedSize(250, 138)
            cover_path = drama.cover
            pixmap = QPixmap(str(cover_path)) if cover_path else QPixmap()
            if not pixmap.isNull():
                cover.setText("")
                cover.setPixmap(pixmap.scaled(cover.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
            elif drama.videos:
                key = str(drama.videos[0].resolve())
                self.library_thumbnail_labels.setdefault(key, []).append(cover)
                self._load_video_thumbnail(drama.videos[0], key)
            card_layout.addWidget(cover)
            title = QLabel(drama.title)
            title.setObjectName("libraryTitle")
            title.setWordWrap(True)
            title.setToolTip(str(drama.folder))
            card_layout.addWidget(title)
            info = QLabel(f"{drama.episode_count} episodes  ·  {self._human_bytes(drama.total_bytes)}  ·  {drama.modified_text}")
            info.setObjectName("muted")
            info.setWordWrap(True)
            card_layout.addWidget(info)
            episodes = QComboBox()
            for video in drama.videos:
                episodes.addItem(video.stem, str(video))
            card_layout.addWidget(episodes)
            actions = QHBoxLayout()
            play = QPushButton(f"▶ {self._t('Play')}")
            play.setObjectName("primaryButton")
            play.clicked.connect(lambda _checked=False, combo=episodes: self._play_selected_video(combo))
            folder = QPushButton(self._t("Folder"))
            folder.clicked.connect(lambda _checked=False, path=drama.folder: self._open_path(path))
            delete = QPushButton(self._t("Delete"))
            delete.setObjectName("dangerButton")
            delete.clicked.connect(lambda _checked=False, item=drama: self._delete_library_drama(item))
            actions.addWidget(play)
            actions.addWidget(folder)
            actions.addWidget(delete)
            card_layout.addLayout(actions)
            self.library_grid.addWidget(card, index // columns, index % columns)
        total_videos = sum(item.episode_count for item in items)
        total_size = sum(item.total_bytes for item in items)
        self.library_summary.setText(
            f"{len(items)} dramas · {total_videos} videos · {self._human_bytes(total_size)}"
            if items else "No downloaded videos found."
        )

    def _load_video_thumbnail(self, video: Path, key: str) -> None:
        cached = self.thumbnail_cache.get(key)
        if cached is not None:
            self._apply_library_thumbnail(key, cached)
            return
        if key in self.library_thumbnail_pending:
            return
        self.library_thumbnail_pending.add(key)
        worker = VideoThumbnailWorker(video, key)
        worker.signals.result.connect(self._video_thumbnail_ready)
        worker.signals.finished.connect(lambda value=key: self.library_thumbnail_pending.discard(value))
        self.thread_pool.start(worker)

    @pyqtSlot(object)
    def _video_thumbnail_ready(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 2 or not result[1]:
            return
        key, path = str(result[0]), str(result[1])
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self.thumbnail_cache[key] = pixmap
        self._apply_library_thumbnail(key, pixmap)

    def _apply_library_thumbnail(self, key: str, pixmap: QPixmap) -> None:
        for label in self.library_thumbnail_labels.get(key, []):
            label.setText("")
            label.setPixmap(pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                          Qt.TransformationMode.SmoothTransformation))

    def _play_selected_video(self, combo: QComboBox) -> None:
        value = combo.currentData()
        if value:
            self._open_path(Path(str(value)))

    def _open_path(self, path: Path) -> None:
        path = path.expanduser()
        if not path.exists():
            QMessageBox.information(self, "Unavailable", "The selected file or folder no longer exists.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _delete_library_drama(self, drama: LibraryDrama) -> None:
        answer = QMessageBox.warning(
            self,
            "Delete downloaded videos",
            f"Delete all {drama.episode_count} downloaded videos for ‘{drama.title}’?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        failures = []
        for video in drama.videos:
            try:
                video.unlink()
            except OSError as exc:
                failures.append(f"{video.name}: {exc}")
        try:
            if drama.folder.exists() and not any(drama.folder.iterdir()):
                drama.folder.rmdir()
        except OSError:
            pass
        self._refresh_library()
        if failures:
            QMessageBox.warning(self, "Some files were not deleted", "\n".join(failures[:5]))

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
        if hasattr(self, "library_grid") and self.pages.currentIndex() == 2:
            self._render_library()
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
        if hasattr(self, "pages") and self.pages.currentIndex() == 4:
            self._refresh_donate_qr()

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
        tasks = self.download_manager.get_tasks()
        grouped: dict[str, list] = {}
        for task in tasks:
            grouped.setdefault(task.book_id, []).append(task)
        active_items = []
        for queue_index, item in enumerate(self.queue):
            drama_tasks = grouped.get(str(item.get("book_id")), [])
            if drama_tasks and all(task.status == "done" for task in drama_tasks):
                continue
            active_items.append((queue_index, item, drama_tasks))
        self._active_queue_indices = [entry[0] for entry in active_items]
        self.queue_table.setRowCount(len(active_items))
        self.queue_table.setVisible(bool(active_items))
        if active_items:
            self.queue_splitter.setSizes([260, 190])
        for row, (queue_index, item, drama_tasks) in enumerate(active_items):
            self.queue_table.setItem(row, 0, QTableWidgetItem(str(item.get("title", "—"))))
            self.queue_table.setItem(row, 1, QTableWidgetItem(str(item.get("episode_total", "—"))))
            episode_match = re.search(r"(\d+)", str(item.get("episode_total") or ""))
            maximum = max(1, int(episode_match.group(1)) if episode_match else 1)
            item.setdefault("download_start", 1)
            item.setdefault("download_end", int(item.get("download_count") or maximum))
            range_widget = QWidget()
            range_layout = QHBoxLayout(range_widget)
            range_layout.setContentsMargins(2, 1, 2, 1)
            start_spin, end_spin = QSpinBox(), QSpinBox()
            for spin in (start_spin, end_spin):
                spin.setRange(1, maximum)
            start_spin.setValue(min(maximum, int(item.get("download_start") or 1)))
            end_spin.setValue(min(maximum, max(start_spin.value(), int(item.get("download_end") or maximum))))
            start_spin.setPrefix("EP ")
            end_spin.setPrefix("to ")
            start_spin.valueChanged.connect(lambda value, i=queue_index: self._set_episode_range(i, start=value))
            end_spin.valueChanged.connect(lambda value, i=queue_index: self._set_episode_range(i, end=value))
            range_layout.addWidget(start_spin)
            range_layout.addWidget(end_spin)
            self.queue_table.setCellWidget(row, 2, range_widget)
            self.queue_table.setItem(row, 3, QTableWidgetItem(str(item.get("book_id", "—"))))
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(0)
            progress.setFormat("0%")
            self.queue_table.setCellWidget(row, 4, progress)
            done = sum(task.status == "done" for task in drama_tasks)
            if drama_tasks:
                percent = int(sum(task.progress for task in drama_tasks) / len(drama_tasks))
                progress.setValue(percent)
                progress.setFormat(f"{percent}%")
                status = self._download_status_text(drama_tasks)
            else:
                status = "Ready to download"
            self.queue_table.setItem(row, 5, QTableWidgetItem(status))
            self._set_queue_actions(row, item, done > 0, queue_index)
        self._refresh_completed_table(tasks)
        self.queue_card.set_value(str(len(self.queue)))
        self.download_button.setEnabled(bool(active_items))
        self._update_queue_summary()

    def _reorder_queue(self, source: int, target: int) -> None:
        indices = getattr(self, "_active_queue_indices", [])
        if not (0 <= source < len(indices) and 0 <= target < len(indices)):
            return
        source_index, target_index = indices[source], indices[target]
        drama = self.queue.pop(source_index)
        self.queue.insert(target_index, drama)
        self._refresh_queue()
        self.queue_table.selectRow(target)

    def _refresh_completed_table(self, tasks: list) -> None:
        completed = [task for task in tasks if task.status == "done" and task.save_path]
        completed.sort(key=lambda task: (task.title.lower(), task.episode_num))
        self.completed_table.setRowCount(len(completed))
        for row, task in enumerate(completed):
            self.completed_table.setRowHeight(row, 58)
            path = Path(task.save_path)
            size = task.total_bytes
            if not size:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
            self.completed_table.setItem(row, 0, QTableWidgetItem(task.title))
            self.completed_table.setItem(row, 1, QTableWidgetItem(task.episode_title))
            self.completed_table.setItem(row, 2, QTableWidgetItem(self._human_bytes(size)))
            self.completed_table.setItem(row, 3, QTableWidgetItem(self._t("Completed")))
            actions = QWidget()
            actions.setObjectName("completedActions")
            actions.setMinimumHeight(56)
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(7, 7, 7, 7)
            action_layout.setSpacing(8)
            play = QPushButton(f"▶ {self._t('Play')}")
            play.setObjectName("primaryButton")
            play.setMinimumWidth(88)
            play.setFixedHeight(34)
            play.clicked.connect(lambda _checked=False, value=path: self._open_path(value))
            folder = QPushButton(self._t("Folder"))
            folder.setMinimumWidth(88)
            folder.setFixedHeight(34)
            folder.clicked.connect(lambda _checked=False, value=path.parent: self._open_path(value))
            action_layout.addWidget(play)
            action_layout.addWidget(folder)
            self.completed_table.setCellWidget(row, 4, actions)

    def _update_queue_summary(self) -> None:
        if not hasattr(self, "queue_summary"):
            return
        tasks = self.download_manager.get_tasks()
        active = [task for task in tasks if task.status in {"downloading", "retrying"}]
        waiting = sum(task.status in {"pending", "paused", "stopped"} for task in tasks)
        done = sum(task.status == "done" for task in tasks)
        failed = sum(task.status == "error" for task in tasks)
        speed = sum(task.speed for task in active)
        eta = max((task.eta_seconds for task in active), default=0)
        if self.config.language == "km":
            text = f"សកម្ម {len(active)} · រង់ចាំ {waiting} · រួចរាល់ {done} · បរាជ័យ {failed}"
            if speed:
                text += f" · ល្បឿន {self._human_bytes(speed)}/s"
            if eta:
                text += f" · ពេលនៅសល់ {self._human_time(eta)}"
        else:
            text = f"Active {len(active)} · Waiting {waiting} · Completed {done} · Failed {failed}"
            if speed:
                text += f" · Speed {self._human_bytes(speed)}/s"
            if eta:
                text += f" · ETA {self._human_time(eta)}"
        self.queue_summary.setText(text)

    def _set_episode_range(self, index: int, start: int | None = None, end: int | None = None) -> None:
        if not 0 <= index < len(self.queue):
            return
        if start is not None:
            self.queue[index]["download_start"] = start
            if start > int(self.queue[index].get("download_end") or start):
                self.queue[index]["download_end"] = start
        if end is not None:
            self.queue[index]["download_end"] = end
            if end < int(self.queue[index].get("download_start") or 1):
                self.queue[index]["download_start"] = end

    @staticmethod
    def _human_bytes(value: float) -> str:
        size = max(0.0, float(value))
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    @staticmethod
    def _human_time(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    def _download_status_text(self, tasks: list) -> str:
        done = sum(task.status == "done" for task in tasks)
        speed = sum(task.speed for task in tasks if task.status in {"downloading", "retrying"})
        downloaded = sum(task.downloaded_bytes for task in tasks)
        total = sum(task.total_bytes for task in tasks)
        eta = max((task.eta_seconds for task in tasks), default=0)
        states = {task.status for task in tasks}
        if "retrying" in states:
            prefix = "Retrying"
        elif "downloading" in states:
            prefix = "Downloading"
        elif states == {"done"}:
            prefix = "Completed"
        elif "paused" in states:
            prefix = "Paused"
        elif "error" in states:
            failed = sum(task.status == "error" for task in tasks)
            prefix = f"Failed {failed}"
        elif "cancelled" in states:
            prefix = "Cancelled"
        else:
            prefix = "Waiting"
        details = f"{prefix} · Successful {done}/{len(tasks)}"
        if total:
            details += f" · {self._human_bytes(downloaded)}/{self._human_bytes(total)}"
        if speed:
            details += f" · {self._human_bytes(speed)}/s"
        if eta:
            details += f" · ETA {self._human_time(eta)}"
        return details

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

    def _start_queue_drama(self, drama: dict[str, Any]) -> None:
        book_id = str(drama.get("book_id") or "")
        existing = [task for task in self.download_manager.get_tasks() if task.book_id == book_id]
        if existing:
            for task in existing:
                self.download_manager.start_task(task.video_id)
            return
        worker = PrepareDownloadsWorker(self.download_manager, [dict(drama)])
        worker.signals.result.connect(lambda _added, value=book_id: self._start_drama_tasks(value))
        worker.signals.error.connect(self._download_prepare_error)
        self.thread_pool.start(worker)

    def _start_drama_tasks(self, book_id: str) -> None:
        tasks = [task for task in self.download_manager.get_tasks() if task.book_id == book_id]
        if not tasks:
            QMessageBox.warning(self, "No episodes available", "The server returned no downloadable episodes.")
            return
        for task in tasks:
            self.download_manager.start_task(task.video_id)

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
        done = sum(task.status == "done" for task in tasks)
        progress = sum(task.progress for task in tasks) / len(tasks)
        text = self._download_status_text(tasks)
        active_indices = getattr(self, "_active_queue_indices", list(range(len(self.queue))))
        for row, queue_index in enumerate(active_indices):
            if not 0 <= queue_index < len(self.queue):
                continue
            drama = self.queue[queue_index]
            if str(drama.get("book_id")) == book_id:
                bar = self.queue_table.cellWidget(row, 4)
                if isinstance(bar, QProgressBar):
                    bar.setValue(int(progress))
                    bar.setFormat(f"{progress:.0f}%")
                self.queue_table.setItem(row, 5, QTableWidgetItem(text))
                self._set_queue_actions(row, drama, done > 0, queue_index)
                break
        self._update_queue_summary()
        completed_task = next(
            (task for task in tasks if task.video_id == video_id and task.status == "done"),
            None,
        )
        if completed_task is not None:
            if all(task.status == "done" for task in tasks):
                QTimer.singleShot(0, self._refresh_queue)
            else:
                self._refresh_completed_table(self.download_manager.get_tasks())
            self._queue_telegram_upload(completed_task.video_id, completed_task.save_path)
            if self.pages.currentIndex() == 2:
                QTimer.singleShot(100, self._refresh_library)

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

    def _set_queue_actions(
        self, row: int, drama: dict[str, Any], can_view: bool, queue_index: int | None = None
    ) -> None:
        actions = QWidget()
        actions.setObjectName("tableActions")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(4, 2, 4, 2)
        action_layout.setSpacing(5)
        start = QPushButton(self._t("Start"))
        start.setObjectName("startQueueButton")
        start.clicked.connect(lambda _checked=False, item=dict(drama): self._start_queue_drama(item))
        action_layout.addWidget(start)
        if can_view:
            view = QPushButton(self._t("View Folder"))
            view.setObjectName("viewFolderButton")
            view.clicked.connect(
                lambda _checked=False, book_id=str(drama.get("book_id")): self._open_download_folder(book_id)
            )
            action_layout.addWidget(view)
        remove = QPushButton(self._t("Remove"))
        remove.setObjectName("dangerButton")
        item_index = row if queue_index is None else queue_index
        remove.clicked.connect(lambda _checked=False, i=item_index: self._remove_queue_item(i))
        action_layout.addWidget(remove)
        self.queue_table.setCellWidget(row, 6, actions)

    def _pause_downloads(self) -> None:
        self.download_manager.pause_all()
        self.queue_notice.setText("Downloads paused. Partial files are preserved; click Resume to continue.")

    def _cancel_downloads(self) -> None:
        answer = QMessageBox.question(self, "Cancel downloads", "Cancel active downloads and delete partial files?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.download_manager.cancel_all()
        self.queue_notice.setText("Downloads cancelled. Completed videos were kept.")

    def _restore_persisted_queue(self) -> None:
        known = {str(item.get("book_id")) for item in self.queue}
        grouped: dict[str, list] = {}
        for task in self.download_manager.get_tasks():
            grouped.setdefault(task.book_id, []).append(task)
        for book_id, tasks in grouped.items():
            if book_id in known:
                continue
            numbers = [task.episode_num for task in tasks]
            self.queue.append({
                "book_id": book_id,
                "title": tasks[0].title,
                "episode_total": f"{max(numbers)} eps",
                "download_start": min(numbers),
                "download_end": max(numbers),
            })
        if hasattr(self, "queue_table"):
            self._refresh_queue()

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
            drama = self.queue.pop(index)
            self.download_manager.remove_drama(str(drama.get("book_id") or ""))
            self._refresh_queue()

    def _clear_queue(self) -> None:
        for drama in list(self.queue):
            self.download_manager.remove_drama(str(drama.get("book_id") or ""))
        self.queue.clear()
        self._refresh_queue()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.download_manager.shutdown(wait=True)
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
        previous_language = self.config.language
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
        self.config.language = str(self.language_combo.currentData() or "en")
        self.config.save()
        self.queue_telegram_token.setText(telegram_token)
        self.queue_telegram_group.setText(telegram_group)
        self.queue_telegram_auto.setChecked(telegram_auto)
        self._update_api_status()
        if previous_language != self.config.language:
            message = (
                "បានរក្សាទុកការកំណត់។ សូមបិទ និងបើកកម្មវិធីឡើងវិញ ដើម្បីប្រើភាសាថ្មី។"
                if self.config.language == "km"
                else "Preferences saved. Restart the application to use the new language."
            )
        else:
            message = "បានរក្សាទុកការកំណត់ដោយជោគជ័យ។" if self.config.language == "km" else "Preferences saved successfully."
        QMessageBox.information(self, "បានរក្សាទុក" if self.config.language == "km" else "Saved", message)

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
    QLabel#brandSub { font-size: 12px; font-weight: 700; color: #00eaff; letter-spacing: 0.3px; }
    QLabel#contactLabel { color: #71809c; font-size: 10px; font-weight: 750; padding: 4px 12px; letter-spacing: 1px; }
    QLabel#pageTitle { font-size: 26px; font-weight: 750; color: #ffffff; }
    QLabel#muted { color: #8fa6c9; }
    QLabel#queueSummary { color: #00d9ff; font-weight: 700; padding: 4px 8px; }
    QLabel#completedTitle { color: #62f5bd; font-size: 14px; font-weight: 800; padding: 6px 4px 2px 4px; }
    QLabel#metricValue { font-size: 25px; font-weight: 800; }
    QLabel#fieldLabel { color: #c8d8f1; font-weight: 650; }
    QLabel#warningText { color: #ffd23f; }
    QLabel#coverThumbnail { background: #18223a; color: #71809c; border: 1px solid #2b3b59; border-radius: 7px; font-size: 10px; }
    QScrollArea#catalogScroll { background: transparent; border: none; }
    QScrollArea#catalogFilterScroll, QScrollArea#settingsScroll { background: transparent; border: none; }
    QWidget#catalogBar { background: transparent; }
    QWidget#catalogContainer { background: transparent; }
    QFrame#dramaCard { background: #111a31; border: 1px solid #263854; border-radius: 12px; }
    QFrame#libraryCard { background: #111a31; border: 1px solid #263854; border-radius: 12px; }
    QFrame#libraryCard:hover { border-color: #00eaff; }
    QLabel#libraryCover { background: #0a1124; color: #71809c; border: 1px solid #263854; border-radius: 9px; font-weight: 800; }
    QLabel#libraryTitle { font-size: 15px; font-weight: 750; }
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
    QPushButton#navButton[navRole="library"] { color: #42f5b0; border-color: #168f6a; }
    QPushButton#navButton[navRole="settings"] { color: #43c7ff; border-color: #236e9c; }
    QPushButton#navButton[navRole="discover"]:hover { background: #2b1020; border-color: #ff2d75; color: #ffffff; }
    QPushButton#navButton[navRole="queue"]:hover { background: #211337; border-color: #a855f7; color: #ffffff; }
    QPushButton#navButton[navRole="library"]:hover { background: #0b2f28; border-color: #42f5b0; color: #ffffff; }
    QPushButton#navButton[navRole="settings"]:hover { background: #0d2134; border-color: #22b8f0; color: #ffffff; }
    QPushButton#navButton[navRole="discover"]:checked { background: #ff245f; color: #ffffff; border: 1px solid #ff8cad; }
    QPushButton#navButton[navRole="queue"]:checked { background: #7c3cff; color: #ffffff; border: 1px solid #c4a0ff; }
    QPushButton#navButton[navRole="library"]:checked { background: #0a9f70; color: #ffffff; border: 1px solid #72ffd1; }
    QPushButton#navButton[navRole="settings"]:checked { background: #087fab; color: #ffffff; border: 1px solid #68dcff; }
    QPushButton#updateButton { text-align: left; padding: 10px 14px; border-radius: 10px;
        background: #0b211d; color: #42f5b0; border: 1px solid #168f6a; font-weight: 750; }
    QPushButton#updateButton:hover { background: #0f3a30; color: #ffffff; border-color: #42f5b0; }
    QPushButton#youtubeButton, QPushButton#facebookButton, QPushButton#telegramButton, QPushButton#websiteButton, QPushButton#donateButton { text-align: left; border: none; background: transparent; padding: 9px 14px; }
    QPushButton#youtubeButton { color: #ff4d5e; }
    QPushButton#facebookButton { color: #5b9dff; }
    QPushButton#telegramButton { color: #35bff3; }
    QPushButton#websiteButton { color: #b879ff; }
    QPushButton#donateButton { color: #ff8a65; }
    QPushButton#youtubeButton:hover, QPushButton#facebookButton:hover, QPushButton#telegramButton:hover, QPushButton#websiteButton:hover, QPushButton#donateButton:hover { background: #122342; }
    QPushButton#donateButton:checked { background: #ff6b4a; color: #ffffff; border-radius: 8px; }
    QFrame#donatePanel { background: #111a31; border: 1px solid #263854; border-radius: 14px; }
    QLabel#donateTitle { font-size: 32px; font-weight: 800; padding: 6px; }
    QLabel#donateImage { background: #080e20; border: 1px solid #263854; border-radius: 12px; padding: 10px; }
    QPushButton#primaryButton { background: #16d66b; color: #04120a; border: 1px solid #b7ff2a; padding: 11px 18px; }
    QPushButton#primaryButton:hover { background: #3bea82; border-color: #e5ff87; }
    QPushButton#primaryButton:disabled { color: #657089; background: #151c2d; border-color: #303a50; }
    QPushButton#secondaryButton { background: #141d3b; color: #00f5d4; border-color: #00b8d9; }
    QPushButton#startQueueButton { background: #123d31; color: #62f5bd; border-color: #1aa979; padding: 6px 9px; }
    QPushButton#dangerButton { color: #ff718f; border-color: #a72b4c; padding: 7px 9px; }
    QPushButton#dangerButton:hover { background: #451427; border-color: #ff4775; color: #ffffff; }
    QPushButton#catalogChip { border-radius: 14px; padding: 6px 11px; background: #151f36; color: #aebdd2; border-color: #34445e; }
    QPushButton#catalogChip:hover { border-color: #ff7a45; color: #ffffff; }
    QPushButton#catalogChip:checked { background: #ff6b24; color: #ffffff; border-color: #ff6b24; }
    QLineEdit, QSpinBox { background: #080e20; border: 1px solid #137c9b; border-radius: 8px;
        padding: 10px 12px; selection-background-color: #ff2d75; }
    QComboBox { background: #080e20; border: 1px solid #137c9b; border-radius: 8px; padding: 8px 10px; }
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
    QHeaderView#completedHeader::section { background: #0a9f70; color: #ffffff; border-bottom-color: #42f5b0; }
    /* Logo button palette: red, green and yellow */
    QPushButton { background: #f5c400; color: #191500; border-color: #ffe36a; }
    QPushButton:hover { background: #ffdc32; color: #191500; border-color: #fff19a; }
    QPushButton:pressed { background: #d9aa00; }
    QPushButton#primaryButton, QPushButton#startQueueButton, QPushButton#viewFolderButton {
        background: #13a94b; color: #ffffff; border-color: #46dc7c; }
    QPushButton#primaryButton:hover, QPushButton#startQueueButton:hover, QPushButton#viewFolderButton:hover {
        background: #20c85d; color: #ffffff; border-color: #83f2aa; }
    QPushButton#secondaryButton, QPushButton#themeButton {
        background: #f5c400; color: #191500; border-color: #ffe36a; }
    QPushButton#dangerButton { background: #e32636; color: #ffffff; border-color: #ff6975; }
    QPushButton#dangerButton:hover { background: #ff3948; color: #ffffff; border-color: #ff9aa2; }
    QPushButton#navButton[navRole="discover"] { background: #3b1117; color: #ff5966; border-color: #e32636; }
    QPushButton#navButton[navRole="queue"], QPushButton#navButton[navRole="settings"] {
        background: #332a08; color: #ffd426; border-color: #d9aa00; }
    QPushButton#navButton[navRole="library"] { background: #0d3020; color: #45dc7d; border-color: #13a94b; }
    QPushButton#navButton[navRole="discover"]:checked { background: #e32636; color: #ffffff; border-color: #ff6975; }
    QPushButton#navButton[navRole="queue"]:checked, QPushButton#navButton[navRole="settings"]:checked {
        background: #f5c400; color: #191500; border-color: #ffe36a; }
    QPushButton#navButton[navRole="library"]:checked { background: #13a94b; color: #ffffff; border-color: #46dc7c; }
    QPushButton#updateButton { background: #13a94b; color: #ffffff; border-color: #46dc7c; }
    QPushButton#updateButton:hover { background: #20c85d; color: #ffffff; border-color: #83f2aa; }
    QPushButton#youtubeButton { color: #ff5966; }
    QPushButton#facebookButton { color: #4f8ff7; }
    QPushButton#telegramButton { color: #45dc7d; }
    QPushButton#websiteButton { color: #ffd426; }
    QPushButton#donateButton { color: #ff5966; }
    QPushButton#catalogChip { background: #332a08; color: #ffd426; border-color: #d9aa00; }
    QPushButton#catalogChip:checked { background: #e32636; color: #ffffff; border-color: #ff6975; }
    /* Neon capsule style inspired by the reference UI */
    QPushButton { border-radius: 15px; padding: 7px 15px; min-height: 18px; font-weight: 800; }
    QPushButton:hover { border: 2px solid #ffffff; padding: 6px 14px; }
    QPushButton#primaryButton, QPushButton#startQueueButton, QPushButton#viewFolderButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b84a, stop:1 #b7e400);
        color: #071408; border: 2px solid #79ff9f; }
    QPushButton#secondaryButton, QPushButton#themeButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffad00, stop:1 #ffe23b);
        color: #251800; border: 2px solid #fff09a; }
    QPushButton#dangerButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d8102f, stop:1 #ff4d51);
        color: #ffffff; border: 2px solid #ff8b91; }
    QPushButton#navButton { border-radius: 17px; border-width: 2px; padding: 10px 14px; }
    QPushButton#navButton[navRole="discover"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #39101a,stop:1 #711329); }
    QPushButton#navButton[navRole="queue"], QPushButton#navButton[navRole="settings"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3d2b00,stop:1 #705900); }
    QPushButton#navButton[navRole="library"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #07341d,stop:1 #08693a); }
    QPushButton#updateButton {
        border-radius: 16px; border-width: 2px;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00a647,stop:1 #a8d900); }
    QPushButton#youtubeButton, QPushButton#facebookButton, QPushButton#telegramButton, QPushButton#websiteButton, QPushButton#donateButton {
        background: #11182b; border-width: 1px; border-style: solid; border-radius: 14px; padding: 7px 13px; margin: 1px 0; }
    QPushButton#youtubeButton, QPushButton#donateButton { border-color: #ff4055; }
    QPushButton#facebookButton { border-color: #4f8ff7; }
    QPushButton#telegramButton { border-color: #31df7c; }
    QPushButton#websiteButton { border-color: #ffd426; }
    QPushButton#catalogChip { border-radius: 15px; border-width: 2px; padding: 5px 12px; }
    QWidget#tableActions QPushButton { border-radius: 12px; min-height: 16px; padding: 4px 10px; }
    QWidget#completedActions QPushButton { border-radius: 12px; min-height: 18px; max-height: 22px; padding: 3px 10px; }
    /* Reference neon palette: cyan, blue, pink, purple, lime, orange */
    QMainWindow, QWidget#content { background: #080b1d; }
    QFrame#sidebar { background: #0d1128; border-right-color: #00e5ff; }
    QFrame#metricCard, QFrame#panel, QFrame#telegramPanel {
        background: #151936; border-color: #00cfff; }
    QFrame#notice { background: #18143a; border-color: #8b5cff; }
    QLabel#telegramTitle, QLabel#queueSummary { color: #00e5ff; }
    QLabel#completedTitle { color: #7cff4f; }
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0077ff,stop:1 #00d9ff);
        color: #ffffff; border-color: #65f3ff; }
    QPushButton#primaryButton, QPushButton#startQueueButton, QPushButton#viewFolderButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00c96b,stop:1 #8cff00);
        color: #07150a; border-color: #aaff6b; }
    QPushButton#secondaryButton, QPushButton#themeButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff8a00,stop:1 #ffe23b);
        color: #251500; border-color: #fff08b; }
    QPushButton#dangerButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff176b,stop:1 #ff3d44);
        color: #ffffff; border-color: #ff8fb4; }
    QPushButton#navButton[navRole="discover"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #072d4e,stop:1 #005f7d);
        color: #56edff; border-color: #00d9ff; }
    QPushButton#navButton[navRole="queue"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2d155b,stop:1 #6836bd);
        color: #e1c8ff; border-color: #a768ff; }
    QPushButton#navButton[navRole="library"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #073821,stop:1 #087d45);
        color: #7cff9c; border-color: #35ef83; }
    QPushButton#navButton[navRole="settings"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #073462,stop:1 #096eb5);
        color: #75d8ff; border-color: #22b8ff; }
    QPushButton#navButton[navRole="discover"]:checked {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00a9d6,stop:1 #0077ff); }
    QPushButton#navButton[navRole="queue"]:checked {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7b2cff,stop:1 #d12dff); color: #ffffff; }
    QPushButton#navButton[navRole="library"]:checked {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00b95d,stop:1 #76e900); }
    QPushButton#navButton[navRole="settings"]:checked {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #006cd9,stop:1 #00cfff); }
    QPushButton#updateButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6d31e8,stop:1 #ff2da5);
        color: #ffffff; border-color: #ff76c9; }
    QPushButton#youtubeButton { color: #ff4f9a; border-color: #ff2d75; }
    QPushButton#facebookButton { color: #70a7ff; border-color: #347dff; }
    QPushButton#telegramButton { color: #39efff; border-color: #00d9ff; }
    QPushButton#websiteButton { color: #75aaff; border-color: #347dff; }
    QPushButton#donateButton {
        color: #ffffff; border-color: #ff9a4d;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff8a00,stop:1 #ff2d75); }
    QPushButton#donateButton:hover, QPushButton#donateButton:checked {
        color: #ffffff; border-color: #ffffff;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ffad20,stop:1 #ff4aa0); }
    QPushButton#catalogChip { background: #15264a; color: #5de9ff; border-color: #00bfe8; }
    QPushButton#catalogChip:checked {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff2d75,stop:1 #a72cff); border-color: #ff86c2; }
    QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00e5ff,stop:1 #77ff00); }
    QHeaderView::section {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff2169,stop:1 #a72cff);
        border-bottom-color: #00e5ff; }
    QHeaderView#completedHeader::section {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00a85a,stop:1 #00bfcf);
        border-bottom-color: #76ff80; }
    QLabel#statusBadge {
        color: #eafff7; border-color: #5dffd2;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #087d45,stop:1 #007f9e); }
    QScrollBar::handle:vertical { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #00d9ff,stop:1 #a72cff); }
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
    QLabel#queueSummary { color: #087f9b; }
    QLabel#completedTitle { color: #08775a; }
    QLabel#fieldLabel { color: #344054; }
    QLabel#warningText { color: #a15c00; }
    QLabel#contactLabel { color: #7a8699; }
    QLabel#coverThumbnail { background: #edf1f5; color: #7a8699; border-color: #cbd5e1; }
    QFrame#dramaCard { background: #ffffff; border-color: #d7cfc8; }
    QFrame#libraryCard { background: #ffffff; border-color: #cbd5e1; }
    QFrame#libraryCard:hover { border-color: #0891b2; }
    QLabel#libraryCover { background: #edf1f5; color: #64748b; border-color: #cbd5e1; }
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
    QPushButton#navButton[navRole="library"]:hover { background: #0b3028; }
    QPushButton#navButton[navRole="settings"]:hover { background: #102a40; }
    QPushButton#updateButton { background: #eafff7; color: #08775a; border-color: #35b890; }
    QPushButton#updateButton:hover { background: #cffff0; color: #064c3c; border-color: #0aa978; }
    QPushButton#youtubeButton:hover, QPushButton#facebookButton:hover, QPushButton#telegramButton:hover, QPushButton#websiteButton:hover, QPushButton#donateButton:hover { background: #edf6fa; }
    QPushButton#donateButton:checked { background: #ff7657; color: #ffffff; }
    QFrame#donatePanel { background: #ffffff; border-color: #b9d5e2; }
    QLabel#donateImage { background: #f7fafc; border-color: #cbd5e1; }
    QPushButton#primaryButton { background: #16c96a; color: #04120a; border-color: #0fa958; }
    QPushButton#primaryButton:hover { background: #31dc7d; border-color: #087443; }
    QPushButton#primaryButton:disabled { color: #98a2b3; background: #e4e7ec; border-color: #cbd2dc; }
    QPushButton#secondaryButton { background: #f0fffc; color: #087f72; border-color: #16a6b6; }
    QPushButton#startQueueButton { background: #e9fff6; color: #08775a; border-color: #35b890; }
    QPushButton#dangerButton { background: #fff1f3; color: #b42348; border-color: #f3a2b5; }
    QPushButton#catalogChip { background: #ffffff; color: #5f554f; border-color: #ddcec3; }
    QPushButton#catalogChip:hover { background: #fff8f2; color: #c94c13; border-color: #ff7a45; }
    QPushButton#catalogChip:checked { background: #ff6b24; color: #ffffff; border-color: #ff6b24; }
    QPushButton#themeButton { min-width: 78px; }
    QLineEdit, QSpinBox, QComboBox { background: #ffffff; border-color: #9cb3c9; }
    QLineEdit:focus, QSpinBox:focus { border-color: #0891b2; }
    QTableWidget { background: #ffffff; alternate-background-color: #f7f9fc; border-color: #9ccbd7; }
    QTableWidget::item { border-bottom-color: #e2e8f0; }
    QTableWidget::item:selected { background: #f4c5da; color: #31101f; }
    QProgressBar { background: #e9eef4; border-color: #a8bacb; color: #172033; }
    QProgressBar::chunk { background: #18c66c; }
    QPushButton#viewFolderButton { background: #effffc; color: #087f72; border-color: #16a6b6; }
    QHeaderView::section { background: #ff245f; color: #ffffff; border-bottom-color: #00b8d9; }
    QHeaderView#completedHeader::section { background: #12a66f; color: #ffffff; border-bottom-color: #08775a; }
    /* Light logo button palette */
    QPushButton { background: #ffd426; color: #211b00; border-color: #d9aa00; }
    QPushButton:hover { background: #ffe15a; color: #211b00; border-color: #b98f00; }
    QPushButton:pressed { background: #edbd00; }
    QPushButton#primaryButton, QPushButton#startQueueButton, QPushButton#viewFolderButton {
        background: #16b957; color: #ffffff; border-color: #07863b; }
    QPushButton#primaryButton:hover, QPushButton#startQueueButton:hover, QPushButton#viewFolderButton:hover {
        background: #20ce66; color: #ffffff; border-color: #087a39; }
    QPushButton#secondaryButton, QPushButton#themeButton {
        background: #ffd426; color: #211b00; border-color: #d9aa00; }
    QPushButton#dangerButton { background: #e32636; color: #ffffff; border-color: #b71523; }
    QPushButton#dangerButton:hover { background: #f43b49; color: #ffffff; border-color: #9e101c; }
    QPushButton#navButton[navRole="discover"] { background: #351116; color: #ff6571; border-color: #e32636; }
    QPushButton#navButton[navRole="queue"], QPushButton#navButton[navRole="settings"] {
        background: #3a3009; color: #ffe15a; border-color: #d9aa00; }
    QPushButton#navButton[navRole="library"] { background: #0c3320; color: #55e58a; border-color: #16b957; }
    QPushButton#navButton[navRole="discover"]:checked { background: #e32636; color: #ffffff; border-color: #b71523; }
    QPushButton#navButton[navRole="queue"]:checked, QPushButton#navButton[navRole="settings"]:checked {
        background: #ffd426; color: #211b00; border-color: #d9aa00; }
    QPushButton#navButton[navRole="library"]:checked { background: #16b957; color: #ffffff; border-color: #07863b; }
    QPushButton#updateButton { background: #16b957; color: #ffffff; border-color: #07863b; }
    QPushButton#updateButton:hover { background: #20ce66; color: #ffffff; border-color: #087a39; }
    QPushButton#youtubeButton { color: #e32636; }
    QPushButton#facebookButton { color: #1877f2; }
    QPushButton#telegramButton { color: #0c9c47; }
    QPushButton#websiteButton { color: #b18800; }
    QPushButton#donateButton { color: #e32636; }
    QPushButton#catalogChip { background: #fff7c7; color: #715800; border-color: #d9aa00; }
    QPushButton#catalogChip:checked { background: #e32636; color: #ffffff; border-color: #b71523; }
    /* Neon capsule style on the light surface */
    QPushButton { border-radius: 15px; padding: 7px 15px; min-height: 18px; font-weight: 800; }
    QPushButton:hover { border: 2px solid #ffffff; padding: 6px 14px; }
    QPushButton#primaryButton, QPushButton#startQueueButton, QPushButton#viewFolderButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0dbb50, stop:1 #b9e51a);
        color: #071408; border: 2px solid #07863b; }
    QPushButton#secondaryButton, QPushButton#themeButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffb000, stop:1 #ffe34d);
        color: #251800; border: 2px solid #c49400; }
    QPushButton#dangerButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d8102f, stop:1 #ff5156);
        color: #ffffff; border: 2px solid #a80e25; }
    QPushButton#navButton { border-radius: 17px; border-width: 2px; padding: 10px 14px; }
    QPushButton#navButton[navRole="discover"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2d1118,stop:1 #661126); }
    QPushButton#navButton[navRole="queue"], QPushButton#navButton[navRole="settings"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b2c04,stop:1 #6b5707); }
    QPushButton#navButton[navRole="library"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #08351e,stop:1 #087442); }
    QPushButton#updateButton {
        border-radius: 16px; border-width: 2px;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0bac4b,stop:1 #b4df19); }
    QPushButton#youtubeButton, QPushButton#facebookButton, QPushButton#telegramButton, QPushButton#websiteButton, QPushButton#donateButton {
        background: #ffffff; border-width: 1px; border-style: solid; border-radius: 14px; padding: 7px 13px; margin: 1px 0; }
    QPushButton#youtubeButton, QPushButton#donateButton { border-color: #e32636; }
    QPushButton#facebookButton { border-color: #1877f2; }
    QPushButton#telegramButton { border-color: #16a653; }
    QPushButton#websiteButton { border-color: #c79b00; }
    QPushButton#catalogChip { border-radius: 15px; border-width: 2px; padding: 5px 12px; }
    QWidget#tableActions QPushButton { border-radius: 12px; min-height: 16px; padding: 4px 10px; }
    QWidget#completedActions QPushButton { border-radius: 12px; min-height: 18px; max-height: 22px; padding: 3px 10px; }
    /* Reference neon colors retained on the light surface */
    QFrame#metricCard, QFrame#panel, QFrame#telegramPanel { border-color: #35bfe8; }
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #087bea,stop:1 #00cde8);
        color: #ffffff; border-color: #0067c6; }
    QPushButton#primaryButton, QPushButton#startQueueButton, QPushButton#viewFolderButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0abb59,stop:1 #83df00);
        color: #07150a; border-color: #07853e; }
    QPushButton#secondaryButton, QPushButton#themeButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff9700,stop:1 #ffdd35);
        color: #251500; border-color: #c37a00; }
    QPushButton#dangerButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #f31265,stop:1 #f43d43);
        color: #ffffff; border-color: #b90c43; }
    QPushButton#navButton[navRole="discover"] { background: #073d62; color: #63eaff; border-color: #00bfe8; }
    QPushButton#navButton[navRole="queue"] { background: #48237f; color: #e1c8ff; border-color: #9b5de5; }
    QPushButton#navButton[navRole="library"] { background: #075c32; color: #8cffae; border-color: #17bc65; }
    QPushButton#navButton[navRole="settings"] { background: #07558d; color: #8cddff; border-color: #159ddb; }
    QPushButton#navButton[navRole="discover"]:checked { background: #008dca; color: #ffffff; }
    QPushButton#navButton[navRole="queue"]:checked { background: #8a35df; color: #ffffff; }
    QPushButton#navButton[navRole="library"]:checked { background: #13aa54; color: #ffffff; }
    QPushButton#navButton[navRole="settings"]:checked { background: #087fc5; color: #ffffff; }
    QPushButton#updateButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7136df,stop:1 #f32b9c);
        color: #ffffff; border-color: #a62a94; }
    QPushButton#youtubeButton { color: #e91e63; border-color: #e91e63; }
    QPushButton#facebookButton { color: #1877f2; border-color: #1877f2; }
    QPushButton#telegramButton { color: #008eae; border-color: #00aeca; }
    QPushButton#websiteButton { color: #216bd5; border-color: #347dff; }
    QPushButton#donateButton {
        color: #ffffff; border-color: #dc6817;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff8a00,stop:1 #ec2876); }
    QPushButton#donateButton:hover, QPushButton#donateButton:checked {
        color: #ffffff; border-color: #b34e11;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ffa51f,stop:1 #f34491); }
    QPushButton#catalogChip { background: #e8faff; color: #087a9a; border-color: #00aeca; }
    QPushButton#catalogChip:checked { background: #ef2877; color: #ffffff; border-color: #a72cff; }
    QHeaderView::section {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #f51f67,stop:1 #9630df);
        color: #ffffff; border-bottom-color: #00bcd4; }
    QHeaderView#completedHeader::section {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0aa85c,stop:1 #00aebd);
        color: #ffffff; border-bottom-color: #08775a; }
    QLabel#statusBadge {
        color: #ffffff; border-color: #087f72;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #12a85d,stop:1 #0296a8); }
    QScrollBar:vertical { background: #edf2f7; }
    QScrollBar::handle:vertical { background: #52a9bc; }
    """
