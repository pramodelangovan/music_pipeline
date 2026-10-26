import sys
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QFile, QIODevice, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QPlainTextEdit,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import DownloadManager, QueueItem, ResearchManager  # noqa: E402
from core.queue_manager import LOGS_DIR  # noqa: E402

WidgetT = TypeVar("WidgetT", bound=QWidget)


def _resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "resources"


def _logo_path() -> Path:
    """Shared logo: bundled into 'resources' in the exe, in <repo>/resources when run from source."""
    frozen_dir = Path(getattr(sys, "_MEIPASS", ""))
    return (frozen_dir / "resources" if hasattr(sys, "_MEIPASS") else ROOT_DIR / "resources") / "music-pipeline.svg"


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
        self._quitting = False

        self.setWindowTitle("Music Pipeline")
        self.logo_icon = QIcon(str(_logo_path()))
        self.setWindowIcon(self.logo_icon)
        self.resize(1200, 780)

        self._load_ui()
        self._wire_events()
        self._start_polling()

        self.load_settings()
        self.refresh_jobs()
        self.refresh_history()
        self._refresh_research()
        self._setup_tray()

    def _setup_tray(self) -> None:
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Music Pipeline")
        menu = QMenu(self)
        menu.addAction("Show", self._show_from_tray)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._notified_idle = True

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def has_active_work(self) -> bool:
        return self.manager.has_active_work() or self.research.is_active()

    def offer_resume(self) -> None:
        """On launch, offer to continue downloads/research interrupted by a previous close or crash."""
        pending_downloads = self.manager.has_active_work()
        pending_research = self.research.resumable
        if not (pending_downloads or pending_research):
            return
        parts = []
        if pending_downloads:
            parts.append("downloads")
        if pending_research:
            parts.append(f"research for '{self.research.artist}'")
        answer = QMessageBox.question(
            self,
            "Resume unfinished work",
            f"Unfinished {' and '.join(parts)} from the last session were found.\n\nContinue now?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if pending_downloads:
            self.start_queue()
        if pending_research and self.research.resume_interrupted():
            self.research_timer.start(1500)
            self._refresh_research()

    def _confirm_close(self) -> str:
        """Returns 'tray', 'quit' or 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Downloads or research in progress")
        box.setText(
            "Downloads or research are still running.\n\n"
            "Run in the system tray to keep them going in the background?\n"
            "If you quit, progress is saved and you can continue next time you open the app."
        )
        tray_btn = box.addButton("Run in Tray", QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton("Quit Anyway", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(tray_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is tray_btn:
            return "tray"
        if clicked is quit_btn:
            return "quit"
        return "cancel"

    def closeEvent(self, event) -> None:
        if self._quitting or not self.has_active_work():
            event.accept()
            QApplication.quit()
            return
        choice = self._confirm_close()
        if choice == "tray":
            event.ignore()
            self.hide()
            self._notified_idle = False
            self.tray.showMessage(
                "Music Pipeline", "Still running in the tray. Click the icon to reopen.",
                QSystemTrayIcon.MessageIcon.Information, 4000,
            )
        elif choice == "quit":
            self._quitting = True
            event.accept()
            QApplication.quit()
        else:
            event.ignore()

    def quit_app(self) -> None:
        if self.has_active_work():
            choice = QMessageBox.question(
                self,
                "Quit Music Pipeline",
                "Downloads or research are still running. Quit anyway?\n"
                "Progress is saved and can be continued next time.",
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        self._quitting = True
        self.tray.hide()
        QApplication.quit()

    def _load_ui(self) -> None:
        ui_file = QFile(str(_resource_dir() / "desktop.ui"))
        if not ui_file.open(QIODevice.ReadOnly):
            raise RuntimeError(f"Unable to open desktop UI file: {ui_file.errorString()}")
        loader = QUiLoader()
        try:
            self.ui_root = loader.load(ui_file, self)
        finally:
            ui_file.close()
        if self.ui_root is None:
            raise RuntimeError(f"Unable to load desktop UI XML: {loader.errorString()}")
        self.setCentralWidget(self.ui_root)
        self.setStatusBar(QStatusBar())

        self.active_jobs_label = self._widget(QLabel, "active_jobs_label")
        self.tabs = self._widget(QTabWidget, "tabs")
        self.add_row_btn = self._widget(QPushButton, "add_row_btn")
        self.queue_btn = self._widget(QPushButton, "queue_btn")
        self.start_queue_btn = self._widget(QPushButton, "start_queue_btn")
        self.pause_queue_btn = self._widget(QPushButton, "pause_queue_btn")
        self.clear_btn = self._widget(QPushButton, "clear_btn")
        self.clear_all_btn = self._widget(QPushButton, "clear_all_btn")
        self.retry_failed_btn = self._widget(QPushButton, "retry_failed_btn")
        self.queue_input_table = self._widget(QTableWidget, "queue_input_table")
        self.queue_status_table = self._widget(QTableWidget, "queue_status_table")
        self.output_edit = self._widget(QLineEdit, "output_edit")
        self.browse_folder_btn = self._widget(QPushButton, "browse_folder_btn")
        self.gap_spin = self._widget(QSpinBox, "gap_spin")
        self.save_settings_btn = self._widget(QPushButton, "save_settings_btn")
        self.pick_cookies_btn = self._widget(QPushButton, "pick_cookies_btn")
        self.cookies_file_label = self._widget(QLabel, "cookies_file_label")
        self.upload_cookies_btn = self._widget(QPushButton, "upload_cookies_btn")
        self.open_logs_btn = self._widget(QPushButton, "open_logs_btn")
        self.logs_path_label = self._widget(QLabel, "logs_path_label")
        self.logs_path_label.setText(str(LOGS_DIR))
        self.cookies_status_label = self._widget(QLabel, "cookies_status_label")
        self.research_name_edit = self._widget(QLineEdit, "research_name_edit")
        self.research_aliases_edit = self._widget(QLineEdit, "research_aliases_edit")
        self.research_albums_edit = self._widget(QLineEdit, "research_albums_edit")
        self.research_singles_check = self._widget(QCheckBox, "research_singles_check")
        self.research_unknown_check = self._widget(QCheckBox, "research_unknown_check")
        self.research_start_btn = self._widget(QPushButton, "research_start_btn")
        self.research_cancel_btn = self._widget(QPushButton, "research_cancel_btn")
        self.research_status_label = self._widget(QLabel, "research_status_label")
        self.research_log = self._widget(QPlainTextEdit, "research_log")
        self.research_table = self._widget(QTableWidget, "research_table")
        self.research_select_all_btn = self._widget(QPushButton, "research_select_all_btn")
        self.research_queue_btn = self._widget(QPushButton, "research_queue_btn")
        self.refresh_history_btn = self._widget(QPushButton, "refresh_history_btn")
        self.clear_history_btn = self._widget(QPushButton, "clear_history_btn")
        self.history_table = self._widget(QTableWidget, "history_table")

        self._configure_table_columns(
            self.queue_input_table,
            (QHeaderView.Stretch, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents),
        )
        self._configure_table_columns(
            self.queue_status_table,
            (
                QHeaderView.ResizeToContents,
                QHeaderView.ResizeToContents,
                QHeaderView.ResizeToContents,
                QHeaderView.Stretch,
                QHeaderView.Stretch,
            ),
        )
        self._configure_table_columns(
            self.research_table,
            (
                QHeaderView.ResizeToContents,
                QHeaderView.Stretch,
                QHeaderView.ResizeToContents,
                QHeaderView.Stretch,
                QHeaderView.ResizeToContents,
            ),
        )
        self._configure_table_columns(
            self.history_table,
            (
                QHeaderView.ResizeToContents,
                QHeaderView.ResizeToContents,
                QHeaderView.ResizeToContents,
                QHeaderView.ResizeToContents,
                QHeaderView.Stretch,
                QHeaderView.Stretch,
            ),
        )
        self.add_input_row()
        for button in self.ui_root.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_header_logo()

    def _add_header_logo(self) -> None:
        logo = QLabel()
        logo.setPixmap(self.logo_icon.pixmap(QSize(52, 43)))
        logo.setFixedSize(56, 46)
        header_layout = self._widget(QFrame, "Header").layout()
        header_layout.insertWidget(0, logo)
        header_layout.insertSpacing(1, 6)

    def _widget(self, widget_type: type[WidgetT], name: str) -> WidgetT:
        widget = self.ui_root.findChild(widget_type, name)
        if widget is None:
            raise RuntimeError(f"Desktop UI is missing required widget: {name}")
        return widget

    @staticmethod
    def _configure_table_columns(table: QTableWidget, modes: tuple) -> None:
        for index, mode in enumerate(modes):
            table.horizontalHeader().setSectionResizeMode(index, mode)

    def _wire_events(self) -> None:
        self.add_row_btn.clicked.connect(self.add_input_row)
        self.queue_btn.clicked.connect(self.queue_downloads)
        self.start_queue_btn.clicked.connect(self.start_queue)
        self.pause_queue_btn.clicked.connect(self.pause_queue)
        self.clear_btn.clicked.connect(self.clear_recent)
        self.clear_all_btn.clicked.connect(self.clear_all)
        self.retry_failed_btn.clicked.connect(self.retry_failed)
        self.pick_cookies_btn.clicked.connect(self.pick_cookies_file)
        self.upload_cookies_btn.clicked.connect(self.upload_cookies)
        self.open_logs_btn.clicked.connect(self.open_logs_folder)
        self.save_settings_btn.clicked.connect(self.save_settings)
        self.browse_folder_btn.clicked.connect(self.pick_download_folder)
        self.refresh_history_btn.clicked.connect(self.refresh_history)
        self.clear_history_btn.clicked.connect(self.clear_history)
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
        if not self.isVisible() and not self._notified_idle and not self.has_active_work():
            self._notified_idle = True
            self.tray.showMessage(
                "Music Pipeline", "All downloads and research are finished.",
                QSystemTrayIcon.MessageIcon.Information, 5000,
            )

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
            combo = QComboBox()
            combo.addItems(["audio", "video"])
            self.research_table.setCellWidget(row, 4, combo)
        if not running:
            self.research_timer.stop()

    def queue_research_selection(self) -> None:
        rows = sorted({index.row() for index in self.research_table.selectedIndexes()})
        if not rows:
            self._error("Select at least one result to queue.")
            return
        folder = self.research.snapshot()["folder_name"] or "research"
        items = [
            QueueItem(
                url=self.research_table.item(row, 3).text(),
                media_type=self.research_table.cellWidget(row, 4).currentText(),
                folder_name=folder,
            )
            for row in rows
        ]
        result = self.manager.submit(items)
        self.statusBar().showMessage(f"Queued {result['accepted']} research result(s) into '{folder}'", 5000)
        self.refresh_jobs(silent=True)

    def clear_recent(self) -> None:
        try:
            cleared = self.manager.clear_recent()
            self.statusBar().showMessage(f"Cleared {cleared} completed rows", 5000)
            self.refresh_jobs()
            self.refresh_history(silent=True)
        except Exception as exc:
            self._error(str(exc))

    def clear_all(self) -> None:
        try:
            cleared = self.manager.clear_all()
            self.statusBar().showMessage(f"Cleared {cleared} finished rows (queued/active kept)", 5000)
            self.refresh_jobs()
            self.refresh_history(silent=True)
        except Exception as exc:
            self._error(str(exc))

    def retry_failed(self) -> None:
        try:
            retried = self.manager.retry_failed()
            self.statusBar().showMessage(
                f"Re-queued {retried} failed download(s)" if retried else "No failed downloads to retry", 5000
            )
            self.refresh_jobs()
        except Exception as exc:
            self._error(str(exc))

    def clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear History",
            "Delete all completed and failed history? Active downloads will be kept.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            cleared = self.manager.clear_history()
            self.statusBar().showMessage(f"Deleted {cleared} completed/failed history rows", 5000)
            self.refresh_jobs(silent=True)
            self.refresh_history()
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

    def open_logs_folder(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS_DIR)))

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
    style_path = _resource_dir() / "style.qss"
    if not style_path.exists():
        return
    app.setStyleSheet(style_path.read_text(encoding="utf-8"))
