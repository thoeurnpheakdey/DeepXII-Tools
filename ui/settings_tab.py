from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import Config, DEFAULT_DOWNLOAD_DIR
from core.api_client import HonguoClient


_TEST_BOOK_ID = "7598544138262301720"


class SettingsTab(QWidget):
    settings_saved = Signal()

    def __init__(self, config: Config, client: HonguoClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.client = client
        self._status_timer: QTimer | None = None

        self._build_ui()
        self._load_config()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        hint_label = QLabel("授权码可选 — 无授权码将使用免费预览模式（部分集数可能受限）")
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", hint_label)

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("请输入授权码")
        self.verify_button = QPushButton("验证")
        self.verify_button.clicked.connect(self._on_verify_clicked)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key_edit, 1)
        key_layout.addWidget(self.verify_button)
        form.addRow("授权码", key_row)
        self.verify_label = QLabel("")
        form.addRow("", self.verify_label)

        self.dir_edit = QLineEdit()
        self.browse_button = QPushButton("浏览")
        self.browse_button.clicked.connect(self._on_browse)
        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.addWidget(self.dir_edit, 1)
        dir_layout.addWidget(self.browse_button)
        form.addRow("下载目录", dir_row)

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 16)
        form.addRow("并发数", self.concurrent_spin)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["1080P+", "2160p"])
        form.addRow("清晰度", self.level_combo)

        self.motrix_check = QCheckBox("启用")
        form.addRow("使用 Motrix", self.motrix_check)

        self.buy_button = QPushButton("购买授权码")
        self.buy_button.clicked.connect(self._open_buy_page)
        form.addRow("", self.buy_button)

        self.save_button = QPushButton("💾 保存设置")
        self.save_button.clicked.connect(self._save)
        form.addRow("", self.save_button)

        self.status_label = QLabel("")
        form.addRow("", self.status_label)

    def _load_config(self) -> None:
        self.key_edit.setText(self.config.key)
        self.dir_edit.setText(self.config.download_dir)
        self.concurrent_spin.setValue(self.config.concurrent)
        level_index = self.level_combo.findText(self.config.level)
        self.level_combo.setCurrentIndex(level_index if level_index >= 0 else 0)
        self.motrix_check.setChecked(self.config.use_motrix)

    def _save(self) -> None:
        self.config.key = self.key_edit.text().strip()
        download_dir = self.dir_edit.text().strip() or str(DEFAULT_DOWNLOAD_DIR)
        self.config.download_dir = str(Path(download_dir).expanduser())
        self.config.concurrent = self.concurrent_spin.value()
        self.config.level = self.level_combo.currentText()
        self.config.use_motrix = self.motrix_check.isChecked()
        self.config.save()
        self._show_status("✅ 已保存")
        self.settings_saved.emit()

    def _show_status(self, text: str) -> None:
        self.status_label.setText(text)
        if self._status_timer is not None:
            self._status_timer.stop()
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self.status_label.clear)
        self._status_timer.start(3000)

    def _on_browse(self) -> None:
        current = self.dir_edit.text() or self.config.download_dir or str(DEFAULT_DOWNLOAD_DIR)
        directory = QFileDialog.getExistingDirectory(self, "选择下载目录", current)
        if directory:
            self.dir_edit.setText(directory)

    def _open_buy_page(self) -> None:
        QDesktopServices.openUrl(QUrl("https://orz.icic.icu/auth/hg/"))

    def _on_verify_clicked(self) -> None:
        key_value = self.key_edit.text().strip()
        if not key_value:
            QMessageBox.warning(self, "提示", "请先输入授权码。")
            return
        self.verify_button.setEnabled(False)
        self.verify_label.setText("⌛ 正在验证...")

        def task() -> Tuple[bool, str]:
            original = self.config.key
            self.config.key = key_value
            try:
                ok, _data, msg = self.client.get_episodes(_TEST_BOOK_ID)
            finally:
                self.config.key = original
            if ok:
                return True, msg or "授权码有效"
            return False, msg or "验证失败"

        self._start_worker(
            task,
            on_finished=lambda result: self._handle_verify_result(result, key_value),
            on_failed=self._handle_verify_error,
        )

    def _handle_verify_result(self, result: Tuple[bool, str], key_value: str) -> None:
        ok, message = result
        if ok:
            self.verify_label.setText(f"✅ 授权码有效：{message}")
            self.config.key = key_value
            self.config.save()
        else:
            self.verify_label.setText(f"❌ 授权码无效：{message}")
        self.verify_button.setEnabled(True)

    def _handle_verify_error(self, error: str) -> None:
        self.verify_label.setText(f"❌ 验证失败：{error}")
        self.verify_button.setEnabled(True)

    def _start_worker(
        self,
        func: Callable,
        on_finished: Callable[[object], None],
        on_failed: Callable[[str], None],
    ) -> None:
        def _run() -> None:
            try:
                result = func()
                QTimer.singleShot(0, self, lambda: on_finished(result))
            except Exception as exc:  # pylint: disable=broad-except
                err = str(exc)
                QTimer.singleShot(0, self, lambda: on_failed(err))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
