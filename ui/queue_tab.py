from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from config import Config
from core.download_manager import DownloadManager, DownloadTask


class QueueTab(QWidget):
    def __init__(self, config: Config, download_manager: DownloadManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.download_manager = download_manager
        self._row_map: Dict[str, int] = {}

        self._build_ui()
        self.refresh_table()

        self.download_manager.task_updated.connect(self._on_task_updated)  # type: ignore[attr-defined]
        self.download_manager.queue_changed.connect(self._on_queue_changed)  # type: ignore[attr-defined]

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.start_button = QPushButton("▶ 开始下载")
        self.start_button.clicked.connect(self.download_manager.start_queue)
        self.stop_button = QPushButton("⏹ 停止")
        self.stop_button.clicked.connect(self.download_manager.stop_all)
        self.clear_button = QPushButton("🗑 清空已完成")
        self.clear_button.clicked.connect(self._on_clear_done)
        self.count_label = QLabel("待下载: 0 | 下载中: 0 | 已完成: 0")
        self.concurrent_label = QLabel("并发数:")
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 16)
        self.concurrent_spin.setValue(self.config.concurrent)
        self.concurrent_spin.valueChanged.connect(self._on_concurrent_changed)

        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.clear_button)
        controls.addStretch(1)
        controls.addWidget(self.count_label)
        controls.addSpacing(10)
        controls.addWidget(self.concurrent_label)
        controls.addWidget(self.concurrent_spin)

        layout.addLayout(controls)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["剧名", "集数", "状态", "进度", "速度", "操作"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._open_context_menu)
        layout.addWidget(self.table, 1)

    def _on_concurrent_changed(self, value: int) -> None:
        self.config.concurrent = value
        self.config.save()

    def _on_clear_done(self) -> None:
        self.download_manager.clear_done()
        self.refresh_table()

    def refresh_table(self) -> None:
        tasks = self.download_manager.get_tasks()
        self.table.setRowCount(len(tasks))
        self._row_map.clear()
        for row, task in enumerate(tasks):
            self._populate_row(row, task)
        self._update_counts()

    def _populate_row(self, row: int, task: DownloadTask) -> None:
        self._row_map[task.video_id] = row
        title = QTableWidgetItem(task.title)
        episode_text = f"第{task.episode_num:02d}集 {task.episode_title}"
        episode_item = QTableWidgetItem(episode_text)
        status_item = QTableWidgetItem(self._format_status(task))
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(task.progress))
        speed_item = QTableWidgetItem(self._format_speed(task.speed))
        remove_button = QPushButton("移除")
        remove_button.clicked.connect(lambda _=False, vid=task.video_id: self._remove_task(vid))

        self.table.setItem(row, 0, title)
        self.table.setItem(row, 1, episode_item)
        self.table.setItem(row, 2, status_item)
        self.table.setCellWidget(row, 3, progress_bar)
        self.table.setItem(row, 4, speed_item)
        self.table.setCellWidget(row, 5, remove_button)

    def _format_status(self, task: DownloadTask) -> str:
        mapping = {
            "pending": "待下载",
            "downloading": "下载中",
            "done": "✅ 完成",
            "error": f"❌ 失败: {task.error_msg}" if task.error_msg else "❌ 失败",
            "stopped": "⏹ 已停止",
        }
        return mapping.get(task.status, task.status)

    def _format_speed(self, speed: float) -> str:
        if speed >= 1024 * 1024:
            return f"{speed / (1024 * 1024):.1f} MB/s"
        return f"{max(speed / 1024, 0):.0f} KB/s"

    def _remove_task(self, video_id: str) -> None:
        self.download_manager.remove_task(video_id)
        self.refresh_table()

    def _open_context_menu(self, pos: QPoint) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        video_id = self._find_video_id_by_row(row)
        if not video_id:
            return
        menu = QMenu(self)
        remove_action = QAction("移除", self)
        remove_action.triggered.connect(lambda: self._remove_task(video_id))
        menu.addAction(remove_action)
        open_action = QAction("打开文件夹", self)
        open_action.triggered.connect(lambda: self._open_folder(video_id))
        menu.addAction(open_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _find_video_id_by_row(self, row: int) -> Optional[str]:
        for video_id, mapped_row in self._row_map.items():
            if mapped_row == row:
                return video_id
        return None

    def _open_folder(self, video_id: str) -> None:
        task = next((t for t in self.download_manager.get_tasks() if t.video_id == video_id), None)
        if not task or not task.save_path:
            QMessageBox.information(self, "提示", "文件尚未下载完成。")
            return
        file_path = Path(task.save_path)
        if not file_path.exists():
            QMessageBox.warning(self, "提示", "文件不存在。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.parent)))

    def _on_task_updated(self, _book_id: str, video_id: str) -> None:
        row = self._row_map.get(video_id)
        if row is None:
            self.refresh_table()
            return
        task = next((t for t in self.download_manager.get_tasks() if t.video_id == video_id), None)
        if task is None:
            self.refresh_table()
            return
        title_item = self.table.item(row, 0)
        if title_item is None:
            title_item = QTableWidgetItem()
            self.table.setItem(row, 0, title_item)
        title_item.setText(task.title)

        episode_item = self.table.item(row, 1)
        if episode_item is None:
            episode_item = QTableWidgetItem()
            self.table.setItem(row, 1, episode_item)
        episode_item.setText(f"第{task.episode_num:02d}集 {task.episode_title}")

        status_item = self.table.item(row, 2)
        if status_item is None:
            status_item = QTableWidgetItem()
            self.table.setItem(row, 2, status_item)
        status_item.setText(self._format_status(task))

        progress_widget = self.table.cellWidget(row, 3)
        if isinstance(progress_widget, QProgressBar):
            progress_widget.setValue(int(task.progress))
        speed_item = self.table.item(row, 4)
        if speed_item is None:
            speed_item = QTableWidgetItem()
            self.table.setItem(row, 4, speed_item)
        speed_item.setText(self._format_speed(task.speed))
        self._update_counts()

    def _on_queue_changed(self) -> None:
        self.refresh_table()

    def _update_counts(self) -> None:
        counts = self.download_manager.task_count()
        text = f"待下载: {counts.get('pending', 0)} | 下载中: {counts.get('downloading', 0)} | 已完成: {counts.get('done', 0)}"
        self.count_label.setText(text)

    def set_concurrent_value(self, value: int) -> None:
        self.concurrent_spin.blockSignals(True)
        self.concurrent_spin.setValue(value)
        self.concurrent_spin.blockSignals(False)
