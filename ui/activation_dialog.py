from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QVBoxLayout)

from config import Config
from core.license_manager import verify_activation_code


class ActivationDialog(QDialog):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("Activate DeepXII Tools")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)
        title = QLabel("Activate DeepXII Tools")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel(
            "1. Copy your Machine ID and send it to the Telegram Bot.\n"
            "2. Wait for Admin approval.\n"
            "3. Copy the Activation Code from the Bot and paste it below."
        )
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Machine ID"))
        machine_row = QHBoxLayout()
        self.machine_edit = QLineEdit(config.machine_id)
        self.machine_edit.setReadOnly(True)
        copy_machine = QPushButton("Copy Machine ID")
        copy_machine.setObjectName("secondaryButton")
        copy_machine.clicked.connect(lambda: QGuiApplication.clipboard().setText(config.machine_id))
        machine_row.addWidget(self.machine_edit, 1)
        machine_row.addWidget(copy_machine)
        layout.addLayout(machine_row)
        open_bot = QPushButton("Open Telegram Activation Bot")
        open_bot.setObjectName("primaryButton")
        open_bot.clicked.connect(self._open_bot)
        layout.addWidget(open_bot)
        layout.addWidget(QLabel("Activation Code"))
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Paste the code received from the Bot")
        self.code_edit.setClearButtonEnabled(True)
        layout.addWidget(self.code_edit)
        actions = QHBoxLayout()
        actions.addStretch(1)
        quit_button = QPushButton("Exit")
        quit_button.setObjectName("dangerButton")
        quit_button.clicked.connect(self.reject)
        activate = QPushButton("Activate")
        activate.setObjectName("primaryButton")
        activate.clicked.connect(self._activate)
        actions.addWidget(quit_button)
        actions.addWidget(activate)
        layout.addLayout(actions)

    def _open_bot(self) -> None:
        username = self.config.activation_bot_username.strip().lstrip("@")
        if not username:
            QMessageBox.information(self, "Telegram Bot", "Activation Bot username has not been configured yet.")
            return
        QDesktopServices.openUrl(QUrl(f"https://t.me/{username}?start={self.config.machine_id}"))

    def _activate(self) -> None:
        code = self.code_edit.text().strip()
        valid, info, message = verify_activation_code(code, self.config.machine_id)
        if not valid:
            QMessageBox.warning(self, "Activation failed", message)
            return
        self.config.activation_code = code
        self.config.save()
        QMessageBox.information(self, "Activated", f"DeepXII Tools activated successfully.\nLicense: {info.license_id}")
        self.accept()
