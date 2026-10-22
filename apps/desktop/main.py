import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QPlainTextEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import DownloadManager, QueueItem, ResearchManager  # noqa: E402


class DesktopApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.manager = DownloadManager()
        self.manager.start()
        self.research = ResearchManager(lambda: self.manager.cookies_path)
        self.research_timer = QTimer(self)
        self.research_timer.timeout.connect(self._refresh_research)
        self.cookies_file_path = ""
        self._active_count = 0

        self.setWindowTitle("Music Pipeline Desktop")
        self.resize(1200, 780)

        self._build_ui()
        self._wire_events()
        self._start_polling()

        self.load_settings()
        self.refresh_jobs()
        self.refresh_history()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)

        title_col = QVBoxLayout()
        header_title = QLabel("Queue Download Studio")
        header_title.setObjectName("HeaderTitle")
        header_meta = QLabel("PySide6 Desktop Client • Local Queue + History")
        header_meta.setObjectName("HeaderMeta")
        title_col.addWidget(header_title)
        title_col.addWidget(header_meta)

        self.active_jobs_label = QLabel("Active: 0")
        self.active_jobs_label.setObjectName("HeaderMeta")
        self.active_jobs_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header_layout.addLayout(title_col)
        header_layout.addWidget(self.active_jobs_label)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.queue_tab = self._build_queue_tab()
        self.settings_tab = self._build_settings_tab()
        self.history_tab = self._build_history_tab()
        self.research_tab = self._build_research_tab()

        self.tabs.addTab(self.queue_tab, "Queue")
        self.tabs.addTab(self.research_tab, "Research")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.history_tab, "History")

        self.setStatusBar(QStatusBar())

    def _build_queue_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        action_row = QHBoxLayout()
        self.add_row_btn = QPushButton("Add Row")
        self.queue_btn = QPushButton("Queue Downloads")
        self.start_queue_btn = QPushButton("Start Queue")
        self.pause_queue_btn = QPushButton("Pause Queue")
        self.pause_queue_btn.setObjectName("SecondaryButton")
        self.clear_btn = QPushButton("Clear Last Downloads")
        self.clear_btn.setObjectName("WarningButton")
        action_row.addWidget(self.add_row_btn)
        action_row.addWidget(self.queue_btn)
        action_row.addWidget(self.start_queue_btn)
        action_row.addWidget(self.pause_queue_btn)
        action_row.addStretch(1)
        action_row.addWidget(self.clear_btn)
        layout.addLayout(action_row)

        self.queue_input_table = QTableWidget(0, 3)
        self.queue_input_table.setHorizontalHeaderLabels(["URL", "Type", "Folder"])
        self.queue_input_table.setAlternatingRowColors(True)
        self.queue_input_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.queue_input_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.queue_input_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(QLabel("Download Inputs"))
        layout.addWidget(self.queue_input_table)

        self.queue_status_table = QTableWidget(0, 5)
        self.queue_status_table.setHorizontalHeaderLabels(["Status", "Type", "Folder", "URL", "Error"])
        self.queue_status_table.setAlternatingRowColors(True)
        self.queue_status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.queue_status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.queue_status_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.queue_status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.queue_status_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(QLabel("Queue Status"))
        layout.addWidget(self.queue_status_table)

        self.add_input_row()
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Download Folder"))
        self.output_edit = QLineEdit()
        folder_row.addWidget(self.output_edit, 1)
        self.browse_folder_btn = QPushButton("Browse...")
        self.browse_folder_btn.setObjectName("SecondaryButton")
        folder_row.addWidget(self.browse_folder_btn)
        layout.addLayout(folder_row)

        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("Gap Between Downloads (sec)"))
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 3600)
        self.gap_spin.setValue(12)
        gap_row.addWidget(self.gap_spin)
        self.save_settings_btn = QPushButton("Save Settings")
        gap_row.addWidget(self.save_settings_btn)
        gap_row.addStretch(1)
        layout.addLayout(gap_row)

        cookies_row = QHBoxLayout()
        self.pick_cookies_btn = QPushButton("Choose cookies.txt")
        self.pick_cookies_btn.setObjectName("SecondaryButton")
        self.cookies_file_label = QLabel("No file selected")
        self.upload_cookies_btn = QPushButton("Upload Cookies")
        cookies_row.addWidget(self.pick_cookies_btn)
        cookies_row.addWidget(self.cookies_file_label, 1)
        cookies_row.addWidget(self.upload_cookies_btn)
        layout.addLayout(cookies_row)

        self.cookies_status_label = QLabel("Cookies status: unknown")
        layout.addWidget(self.cookies_status_label)
        layout.addStretch(1)
        return tab

    def _build_research_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        form = QHBoxLayout()
        self.research_name_edit = QLineEdit()
        self.research_name_edit.setPlaceholderText("Artist name")
        self.research_aliases_edit = QLineEdit()
        self.research_aliases_edit.setPlaceholderText("Aliases (comma separated)")
        self.research_albums_edit = QLineEdit()
        self.research_albums_edit.setPlaceholderText("Known albums (comma separated)")
        form.addWidget(self.research_name_edit, 2)
        form.addWidget(self.research_aliases_edit, 2)
        form.addWidget(self.research_albums_edit, 3)
        layout.addLayout(form)

        options = QHBoxLayout()
        self.research_singles_check = QCheckBox("Find singles")
        self.research_singles_check.setChecked(True)
        self.research_unknown_check = QCheckBox("Find other albums")
        self.research_unknown_check.setChecked(True)
        self.research_start_btn = QPushButton("Start Research")
        self.research_cancel_btn = QPushButton("Cancel")
        self.research_cancel_btn.setObjectName("SecondaryButton")
        self.research_cancel_btn.setEnabled(False)
        self.research_status_label = QLabel("Idle")
        options.addWidget(self.research_singles_check)
        options.addWidget(self.research_unknown_check)
        options.addStretch(1)
        options.addWidget(self.research_status_label)
        options.addWidget(self.research_start_btn)
        options.addWidget(self.research_cancel_btn)
        layout.addLayout(options)

        self.research_log = QPlainTextEdit()
        self.research_log.setReadOnly(True)
        self.research_log.setMaximumHeight(150)
        layout.addWidget(self.research_log)

        self.research_table = QTableWidget(0, 4)
        self.research_table.setHorizontalHeaderLabels(["Type", "Title", "Duration", "URL"])
        self.research_table.setAlternatingRowColors(True)
        self.research_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.research_table.setSelectionMode(QTableWidget.ExtendedSelection)
        header = self.research_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.research_table)

        queue_row = QHBoxLayout()
        self.research_select_all_btn = QPushButton("Select All")
        self.research_select_all_btn.setObjectName("SecondaryButton")
        self.research_queue_btn = QPushButton("Queue Selected (Audio)")
        queue_row.addWidget(self.research_select_all_btn)
        queue_row.addStretch(1)
        queue_row.addWidget(self.research_queue_btn)
        layout.addLayout(queue_row)
        return tab

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Download History"))
        top_row.addStretch(1)
        self.refresh_history_btn = QPushButton("Refresh")
        self.refresh_history_btn.setObjectName("SecondaryButton")
        top_row.addWidget(self.refresh_history_btn)
        layout.addLayout(top_row)

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["Created", "Status", "Type", "Folder", "URL", "Error"])
        self.history_table.setAlternatingRowColors(True)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        layout.addWidget(self.history_table)

        return tab

    def _wire_events(self) -> None:
        self.add_row_btn.clicked.connect(self.add_input_row)
        self.queue_btn.clicked.connect(self.queue_downloads)
        self.start_queue_btn.clicked.connect(self.start_queue)
        self.pause_queue_btn.clicked.connect(self.pause_queue)
        self.clear_btn.clicked.connect(self.clear_recent)
        self.pick_cookies_btn.clicked.connect(self.pick_cookies_file)
        self.upload_cookies_btn.clicked.connect(self.upload_cookies)
        self.save_settings_btn.clicked.connect(self.save_settings)
        self.browse_folder_btn.clicked.connect(self.pick_download_folder)
        self.refresh_history_btn.clicked.connect(self.refresh_history)
        self.research_start_btn.clicked.connect(self.start_research)
        self.research_cancel_btn.clicked.connect(self.research.cancel)
        self.research_select_all_btn.clicked.connect(self.research_table.selectAll)
        self.research_queue_btn.clicked.connect(self.queue_research_selection)

    def _start_polling(self) -> None:
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(5000)

    def _poll(self) -> None:
        self.refresh_jobs(silent=True)
        if self.tabs.currentIndex() == 3:
            self.refresh_history(silent=True)

    def add_input_row(self) -> None:
        row = self.queue_input_table.rowCount()
        self.queue_input_table.insertRow(row)

        url_edit = QLineEdit()
        type_combo = QComboBox()
        type_combo.addItems(["audio", "video"])
        folder_edit = QLineEdit("youtube_playlist")

        self.queue_input_table.setCellWidget(row, 0, url_edit)
        self.queue_input_table.setCellWidget(row, 1, type_combo)
        self.queue_input_table.setCellWidget(row, 2, folder_edit)

    def queue_downloads(self) -> None:
        items = []
        for row in range(self.queue_input_table.rowCount()):
            url_w = self.queue_input_table.cellWidget(row, 0)
            type_w = self.queue_input_table.cellWidget(row, 1)
            folder_w = self.queue_input_table.cellWidget(row, 2)
            if not url_w or not type_w or not folder_w:
                continue
            url = url_w.text().strip()
            if not url:
                continue
            items.append(
                QueueItem(
                    url=url,
                    media_type=type_w.currentText(),
                    folder_name=folder_w.text().strip() or "youtube_playlist",
                )
            )

        if not items:
            self._error("Please add at least one valid URL.")
            return

        try:
            payload = self.manager.submit(items)
            self.statusBar().showMessage(f"Queued {payload.get('accepted', 0)} rows", 5000)
            self.refresh_jobs()
        except Exception as exc:
            self._error(str(exc))

    def start_queue(self) -> None:
        recovered = self.manager.resume()
        self._update_queue_state()
        self.refresh_jobs(silent=True)
        extra = f" ({recovered} queued job(s) reloaded)" if recovered else ""
        self.statusBar().showMessage(f"Queue started{extra}", 4000)

    def pause_queue(self) -> None:
        self.manager.pause()
        self._update_queue_state()
        self.statusBar().showMessage("Queue paused (current download will finish)", 4000)

    def _update_queue_state(self) -> None:
        paused = self.manager.paused
        self.start_queue_btn.setEnabled(True)
        self.pause_queue_btn.setEnabled(not paused)
        setup_message = self.manager.setup_message
        if setup_message:
            self.statusBar().showMessage(setup_message)
        label = f"Active: {self._active_count}"
        self.active_jobs_label.setText(f"{label} • PAUSED" if paused else label)

    @staticmethod
    def _split_csv(text: str) -> list:
        return [part.strip() for part in text.split(",") if part.strip()]

    def start_research(self) -> None:
        cfg = {
            "name": self.research_name_edit.text().strip(),
            "aliases": self._split_csv(self.research_aliases_edit.text()),
            "known_albums": self._split_csv(self.research_albums_edit.text()),
            "fetch_singles": self.research_singles_check.isChecked(),
            "fetch_unknown_albums": self.research_unknown_check.isChecked(),
        }
        try:
            self.research.start(cfg)
        except Exception as exc:
            self._error(str(exc))
            return
        self.research_table.setRowCount(0)
        self.research_log.clear()
        self.research_timer.start(1500)
        self._refresh_research()

    def _refresh_research(self) -> None:
        snap = self.research.snapshot()
        running = snap["status"] == "running"
        self.research_start_btn.setEnabled(not running)
        self.research_cancel_btn.setEnabled(running)
        self.research_status_label.setText(snap["status"].capitalize())

        self.research_log.setPlainText("\n".join(snap["log"]))
        self.research_log.verticalScrollBar().setValue(self.research_log.verticalScrollBar().maximum())

        items = snap["items"]
        for row in range(self.research_table.rowCount(), len(items)):
            item = items[row]
            self.research_table.insertRow(row)
            minutes, seconds = divmod(int(item.get("duration", 0)), 60)
            self._set_item(self.research_table, row, 0, item.get("type", ""))
            self._set_item(self.research_table, row, 1, item.get("title", ""))
            self._set_item(self.research_table, row, 2, f"{minutes}:{seconds:02d}")
            self._set_item(self.research_table, row, 3, item.get("url", ""))
        if not running:
            self.research_timer.stop()

    def queue_research_selection(self) -> None:
        rows = sorted({index.row() for index in self.research_table.selectedIndexes()})
        if not rows:
            self._error("Select at least one result to queue.")
            return
        folder = self.research.snapshot()["folder_name"] or "research"
        items = [
            QueueItem(url=self.research_table.item(row, 3).text(), media_type="audio", folder_name=folder)
            for row in rows
        ]
        result = self.manager.submit(items)
        self.statusBar().showMessage(f"Queued {result['accepted']} research result(s) into '{folder}'", 5000)
        self.refresh_jobs(silent=True)

    def clear_recent(self) -> None:
        try:
            cleared = self.manager.clear_recent()
            self.statusBar().showMessage(f"Cleared {cleared} completed/failed rows", 5000)
            self.refresh_jobs()
            self.refresh_history(silent=True)
        except Exception as exc:
            self._error(str(exc))

    def refresh_jobs(self, silent: bool = False) -> None:
        try:
            payload = self.manager.jobs_snapshot()
            rows = payload.get("jobs", [])
            self.queue_status_table.setRowCount(0)

            active_count = 0
            for item in rows:
                status = item.get("status", "")
                if status in ("queued", "downloading"):
                    active_count += 1

                row = self.queue_status_table.rowCount()
                self.queue_status_table.insertRow(row)
                self._set_item(self.queue_status_table, row, 0, status)
                self._set_item(self.queue_status_table, row, 1, item.get("media_type", ""))
                self._set_item(self.queue_status_table, row, 2, item.get("folder_name", ""))
                self._set_item(self.queue_status_table, row, 3, item.get("resolved_url", ""))
                self._set_item(self.queue_status_table, row, 4, item.get("error", ""))

            self._active_count = active_count
            self._update_queue_state()
        except Exception as exc:
            if not silent:
                self._error(str(exc))

    def refresh_history(self, silent: bool = False) -> None:
        try:
            rows = self.manager.list_history(limit=1000)
            self.history_table.setRowCount(0)
            for item in rows:
                row = self.history_table.rowCount()
                self.history_table.insertRow(row)
                created = (item.get("created_at") or "").replace("T", " ")[:19]
                self._set_item(self.history_table, row, 0, created)
                self._set_item(self.history_table, row, 1, item.get("status", ""))
                self._set_item(self.history_table, row, 2, item.get("media_type", ""))
                self._set_item(self.history_table, row, 3, item.get("folder_name", ""))
                self._set_item(self.history_table, row, 4, item.get("resolved_url", ""))
                self._set_item(self.history_table, row, 5, item.get("error", ""))
        except Exception as exc:
            if not silent:
                self._error(str(exc))

    def load_settings(self) -> None:
        try:
            payload = self.manager.get_settings()
            self.gap_spin.setValue(int(payload.get("gap_seconds", 12)))
            self.output_edit.setText(payload.get("output_base", ""))
            has_cookies = payload.get("cookies_exists", False)
            self.cookies_status_label.setText(f"Cookies status: {'ready' if has_cookies else 'missing'}")
        except Exception as exc:
            self._error(str(exc))

    def save_settings(self) -> None:
        try:
            payload = self.manager.update_settings(self.gap_spin.value(), self.output_edit.text())
            self.output_edit.setText(payload.get("output_base", ""))
            self.statusBar().showMessage(
                f"Saved: gap {payload.get('gap_seconds', self.gap_spin.value())} sec, "
                f"folder {payload.get('output_base', '')}",
                5000,
            )
        except Exception as exc:
            self._error(str(exc))

    def pick_download_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select download folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def pick_cookies_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select cookies.txt", "", "Text files (*.txt);;All files (*)")
        if not file_path:
            return
        self.cookies_file_path = file_path
        self.cookies_file_label.setText(Path(file_path).name)

    def upload_cookies(self) -> None:
        if not self.cookies_file_path:
            self._error("Please choose cookies.txt first.")
            return
        try:
            payload = self.manager.import_cookies_file(self.cookies_file_path)
            has_cookies = payload.get("cookies_exists", False)
            self.cookies_status_label.setText(f"Cookies status: {'ready' if has_cookies else 'missing'}")
            self.statusBar().showMessage("Cookies uploaded", 4000)
        except Exception as exc:
            self._error(str(exc))

    def _set_item(self, table: QTableWidget, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() ^ Qt.ItemIsEditable)
        table.setItem(row, col, item)

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)


def load_stylesheet(app: QApplication) -> None:
    style_path = Path(__file__).resolve().parent / "resources" / "style.qss"
    if not style_path.exists():
        return
    app.setStyleSheet(style_path.read_text(encoding="utf-8"))


def main() -> int:
    app = QApplication(sys.argv)
    load_stylesheet(app)
    window = DesktopApp()
    app.aboutToQuit.connect(window.research.cancel)
    app.aboutToQuit.connect(window.manager.stop)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
