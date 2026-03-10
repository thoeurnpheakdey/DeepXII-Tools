from __future__ import annotations

import re
import threading
from typing import Callable, List, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from core.api_client import HonguoClient
from core.download_manager import DownloadManager


class SearchTab(QWidget):
    def __init__(
        self,
        config: Config,
        client: HonguoClient,
        download_manager: DownloadManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.client = client
        self.download_manager = download_manager

        self._results: List[dict] = []
        self._page = 1
        self._last_query: str = ""
        self._last_mode: str = ""
        self._loading = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索剧名...")
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self._on_search_clicked)
        self.today_button = QPushButton("今日上新")
        self.today_button.clicked.connect(self._on_today_clicked)
        self.page_label = QLabel("")
        self.prev_button = QPushButton("◀ 上页")
        self.prev_button.clicked.connect(lambda: self._change_page(-1))
        self.next_button = QPushButton("下页 ▶")
        self.next_button.clicked.connect(lambda: self._change_page(1))

        top_bar.addWidget(self.search_input, 2)
        top_bar.addWidget(self.search_button)
        top_bar.addWidget(self.today_button)
        top_bar.addWidget(self.page_label)
        top_bar.addWidget(self.prev_button)
        top_bar.addWidget(self.next_button)
        layout.addLayout(top_bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "剧名", "集数", "类型", "更新时间", "简介"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        layout.addWidget(self.table, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addWidget(QLabel("集数范围:"))
        self.episode_mode = QComboBox()
        self.episode_mode.addItems(["全部", "前3集", "自定义"])
        bottom_bar.addWidget(self.episode_mode)
        self.episode_custom = QLineEdit()
        self.episode_custom.setPlaceholderText("如: 1-5 或 1,3,5")
        bottom_bar.addWidget(self.episode_custom, 1)
        self.add_button = QPushButton("加入下载队列")
        self.add_button.clicked.connect(self._on_add_clicked)
        bottom_bar.addWidget(self.add_button)
        layout.addLayout(bottom_bar)

    def _on_search_clicked(self) -> None:
        name = self.search_input.text().strip()
        if not name:
            QMessageBox.information(self, "提示", "请输入剧名后再搜索。")
            return
        self._page = 1
        self._last_query = name
        self._last_mode = "search"
        self._do_search(name, self._page)

    def _change_page(self, delta: int) -> None:
        if not self._last_mode:
            return
        new_page = max(1, self._page + delta)
        if new_page == self._page:
            return
        self._page = new_page
        self.page_label.setText(f"第 {self._page} 页")
        if self._last_mode == "search":
            self._do_search(self._last_query, self._page)
        elif self._last_mode == "today":
            self._do_today_new()

    def _on_today_clicked(self) -> None:
        self._page = 1
        self._last_mode = "today"
        self._last_query = ""
        self.page_label.setText("")
        self._do_today_new()

    def _do_search(self, name: str, page: int) -> None:
        if self._loading:
            return
        self._loading = True
        self._set_controls_enabled(False)

        def task() -> Tuple[bool, List[dict], str]:
            return self.client.search(name, page)

        self._start_worker(task, self._handle_search_result)

    def _do_today_new(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._set_controls_enabled(False)

        def task() -> Tuple[bool, List[dict], str]:
            return self.client.today_new()

        self._start_worker(task, self._handle_search_result)

    def _handle_search_result(self, result: Tuple[bool, List[dict], str]) -> None:
        self._loading = False
        self._set_controls_enabled(True)
        ok, data, msg = result
        if not ok:
            QMessageBox.warning(self, "提示", msg or "请求失败")
            return
        self._results = data
        if self._last_mode == "search":
            self.page_label.setText(f"第 {self._page} 页")
        else:
            self.page_label.setText("")
        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._results))
        for row, item in enumerate(self._results):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, check_item)

            title_item = QTableWidgetItem(str(item.get("title") or "未知剧名"))
            title_item.setData(Qt.UserRole, item)
            self.table.setItem(row, 1, title_item)

            episodes = str(item.get("episode_cnt") or "-")
            self.table.setItem(row, 2, QTableWidgetItem(episodes))
            type_str = re.sub(r"[·・]\d+集$", "", str(item.get("type") or "")).strip() or "-"
            self.table.setItem(row, 3, QTableWidgetItem(type_str))
            publish_time = str(item.get("publish_time") or "-")
            if len(publish_time) == 19:
                publish_time = publish_time[:16]
            self.table.setItem(row, 4, QTableWidgetItem(publish_time))

            intro = str(item.get("intro") or "")
            if len(intro) > 80:
                intro = intro[:80] + "..."
            self.table.setItem(row, 5, QTableWidgetItem(intro))
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(4, 130)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Stretch)

    def _on_add_clicked(self) -> None:
        selected_entries: List[dict] = []
        for row in range(self.table.rowCount()):
            item0 = self.table.item(row, 0)
            if item0 and item0.checkState() == Qt.Checked:
                item = self.table.item(row, 1)
                if item is None:
                    continue
                data = item.data(Qt.UserRole)
                if isinstance(data, dict):
                    selected_entries.append(data)
        if not selected_entries:
            QMessageBox.information(self, "提示", "请先选择要下载的剧集。")
            return
        episode_range = self._get_episode_range()
        self.add_button.setEnabled(False)

        def task() -> int:
            total = 0
            for entry in selected_entries:
                book_id = str(entry.get("book_id") or "")
                title = str(entry.get("title") or "未知剧名")
                total += self.download_manager.add_drama(book_id, title, episode_range)
            return total

        self._start_worker(task, self._handle_add_result, on_failed=self._handle_add_failed)

    def _handle_add_result(self, total: int) -> None:
        self.add_button.setEnabled(True)
        QMessageBox.information(self, "提示", f"已加入 {total} 部剧集到下载队列。")

    def _handle_add_failed(self, error: str) -> None:
        self.add_button.setEnabled(True)
        QMessageBox.warning(self, "错误", error)

    def _handle_worker_error(self, error: str) -> None:
        self._loading = False
        self._set_controls_enabled(True)
        QMessageBox.warning(self, "错误", error)

    def _get_episode_range(self) -> str:
        index = self.episode_mode.currentIndex()
        if index == 0:
            return "all"
        if index == 1:
            return "1-3"
        custom = self.episode_custom.text().strip()
        return custom if custom else "all"

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.search_button.setEnabled(enabled)
        self.today_button.setEnabled(enabled)
        self.prev_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)
        self.episode_mode.setEnabled(enabled)
        self.add_button.setEnabled(enabled)

    def _start_worker(
        self,
        func: Callable,
        callback: Callable[[object], None],
        on_failed: Callable[[str], None] | None = None,
    ) -> None:
        def _run() -> None:
            try:
                result = func()
                QTimer.singleShot(0, self, lambda: callback(result))
            except Exception as exc:  # pylint: disable=broad-except
                err = str(exc)
                if on_failed is not None:
                    QTimer.singleShot(0, self, lambda: on_failed(err))
                else:
                    QTimer.singleShot(0, self, lambda: self._handle_worker_error(err))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
