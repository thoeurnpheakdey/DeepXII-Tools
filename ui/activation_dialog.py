from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from config import Config
from core.license_manager import verify_activation_code


LOGO_PATH = Path(__file__).resolve().parent.parent / "resources" / "activation_logo.png"


class ActivationDialog(QDialog):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("Activate DeepXII Tools")
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)

        logo = QLabel()
        logo.setObjectName("activationLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(LOGO_PATH))
        if pixmap.isNull():
            logo.setText("DeepXII Tools")
            logo.setObjectName("pageTitle")
        else:
            logo.setPixmap(
                pixmap.scaled(
                    430,
                    130,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            logo.setMinimumHeight(110)
        hint = QLabel(
            "1. Copy the Machine ID below and send it to the Admin.\n"
            "2. Admin generates an Activation Code for this computer.\n"
            "3. Paste the Activation Code below and click Activate."
        )
        hint.setWordWrap(True)
        layout.addWidget(logo)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Machine ID"))

        machine_row = QHBoxLayout()
        self.machine_edit = QLineEdit(config.machine_id)
        self.machine_edit.setReadOnly(True)
        copy_machine = QPushButton("Copy Machine ID")
        copy_machine.setObjectName("secondaryButton")
        copy_machine.clicked.connect(self._copy_machine_id)
        machine_row.addWidget(self.machine_edit, 1)
        machine_row.addWidget(copy_machine)
        layout.addLayout(machine_row)

        layout.addWidget(QLabel("Activation Code"))
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("DEEPXII-...")
        self.code_edit.setClearButtonEnabled(True)
        self.code_edit.returnPressed.connect(self._activate)
        layout.addWidget(self.code_edit)

        actions = QHBoxLayout()
        actions.addStretch(1)
        exit_button = QPushButton("Exit")
        exit_button.setObjectName("dangerButton")
        exit_button.clicked.connect(self.reject)
        activate_button = QPushButton("Activate")
        activate_button.setObjectName("primaryButton")
        activate_button.clicked.connect(self._activate)
        actions.addWidget(exit_button)
        actions.addWidget(activate_button)
        layout.addLayout(actions)

    def _copy_machine_id(self) -> None:
        QGuiApplication.clipboard().setText(self.config.machine_id)
        QMessageBox.information(self, "Machine ID", "Machine ID copied to clipboard.")

    def _activate(self) -> None:
        code = self.code_edit.text().strip()
        valid, info, message = verify_activation_code(code, self.config.machine_id)
        if not valid or info is None:
            QMessageBox.warning(self, "Activation failed", message)
            return
        self.config.activation_code = code
        self.config.save()
        QMessageBox.information(
            self,
            "Activated",
            f"DeepXII Tools activated successfully.\nLicense: {info.license_id}",
        )
        self.accept()
