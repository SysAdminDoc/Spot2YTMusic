"""Windows-friendly desktop workflow for reviewed playlist transfers."""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from ytmusicapi import setup
from ytmusicapi.exceptions import YTMusicError

from . import __version__
from .cli import _client
from .csvio import read_sources
from .planner import ScanCancelled, save_plan, save_review, scan
from .review_store import ReviewStore
from .transfer import TransferCancelled, apply_playlist, reviewed_video_ids, state_path_for

EXPORT_URL = "https://exportify.app/"
AUTH_URL = "https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html"
LOGGER = logging.getLogger("spot2ytmusic.gui")
EMPTY_INDEX = QModelIndex()
DARK = """
QWidget { background: #1e1e2e; color: #cdd6f4; font: 10pt 'Segoe UI'; }
QFrame#card { background: #252538; border: 1px solid #45475a; border-radius: 10px; }
QLabel#title { font-size: 22pt; font-weight: 700; color: #f5c2e7; }
QLabel#muted { color: #a6adc8; }
QPushButton { background: #45475a; border: 0; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { background: #585b70; }
QPushButton:pressed { background: #6c7086; }
QPushButton:disabled { color: #6c7086; background: #313244; }
QPushButton#primary { background: #b4befe; color: #11111b; font-weight: 700; }
QPushButton#primary:hover { background: #cba6f7; }
QLineEdit, QComboBox, QPlainTextEdit, QTableView { background: #181825; border: 1px solid #45475a; border-radius: 6px; padding: 5px; selection-background-color: #585b70; }
QTableView { alternate-background-color: #252538; }
QHeaderView::section { background: #313244; color: #cdd6f4; padding: 6px; border: 0; }
QProgressBar { background: #313244; border: 0; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #a6e3a1; border-radius: 5px; }
QStatusBar { color: #a6adc8; }
"""
LIGHT = """
QWidget { background: #eff1f5; color: #4c4f69; font: 10pt 'Segoe UI'; }
QFrame#card { background: #ffffff; border: 1px solid #ccd0da; border-radius: 10px; }
QLabel#title { font-size: 22pt; font-weight: 700; color: #8839ef; }
QLabel#muted { color: #6c6f85; }
QPushButton { background: #ccd0da; border: 0; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { background: #bcc0cc; }
QPushButton:disabled { color: #9ca0b0; background: #dce0e8; }
QPushButton#primary { background: #8839ef; color: white; font-weight: 700; }
QPushButton#primary:hover { background: #7287fd; }
QLineEdit, QComboBox, QPlainTextEdit, QTableView { background: #ffffff; border: 1px solid #ccd0da; border-radius: 6px; padding: 5px; selection-background-color: #acb0be; }
QTableView { alternate-background-color: #e6e9ef; }
QHeaderView::section { background: #dce0e8; padding: 6px; border: 0; }
QProgressBar { background: #ccd0da; border: 0; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #40a02b; border-radius: 5px; }
"""


def video_id_from(text: str) -> str:
    value = text.strip()
    if "youtu" not in value:
        return value
    parsed = urlparse(value)
    if parsed.netloc.lower().endswith("youtu.be"):
        return parsed.path.strip("/").split("/")[0]
    return parse_qs(parsed.query).get("v", [""])[0]


def default_output() -> Path:
    return Path.home() / "Documents" / "Spot2YTMusic"


def log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Spot2YTMusic"
    base.mkdir(parents=True, exist_ok=True)
    return base / "spot2ytmusic.log"


def save_browser_auth(headers: str, destination: Path) -> None:
    if not headers.strip():
        raise ValueError("Paste the request headers first")
    destination.parent.mkdir(parents=True, exist_ok=True)
    setup(str(destination), headers.strip())


class Job(QThread):
    updated = Signal(int, int, str)
    note = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, kind: str, **kwargs: object) -> None:
        super().__init__()
        self.kind = kind
        self.arguments = kwargs
        self.stop_event = threading.Event()

    def run(self) -> None:
        try:
            if self.kind == "import":
                paths = self.arguments["paths"]
                tracks = read_sources(paths)
                if self.stop_event.is_set():
                    raise ScanCancelled("Import stopped.")
                self.completed.emit({"kind": "import", "paths": paths, "tracks": tracks})
            elif self.kind == "scan":
                tracks = self.arguments["tracks"]
                output = self.arguments["output"]
                cache = output / "search-cache.sqlite3"
                self.note.emit("Searching YouTube Music. Results are cached as they arrive.")
                plan = scan(
                    _client(),
                    tracks,
                    cache,
                    progress=lambda done, total, entry: self.updated.emit(
                        done,
                        total,
                        f"{entry.track.collection} #{entry.track.position}: {entry.track.title} ({entry.status})",
                    ),
                    cancelled=self.stop_event.is_set,
                )
                stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                plan_path = output / f"transfer-{stamp}.json"
                suffix = 2
                while plan_path.exists():
                    plan_path = output / f"transfer-{stamp}-{suffix}.json"
                    suffix += 1
                save_plan(plan_path, plan)
                save_review(plan_path.with_suffix(".review.csv"), plan)
                self.completed.emit(plan_path)
            elif self.kind == "transfer":
                store = ReviewStore(self.arguments["plan_path"])
                client = _client(self.arguments["auth"])
                total = sum(
                    len(reviewed_video_ids(store.plan, store.review_path, name)[0])
                    for name in store.playlists
                )
                done = 0
                results = []
                for name in store.playlists:
                    if self.stop_event.is_set():
                        raise TransferCancelled("Transfer stopped. Run it again to resume.")
                    ids, skipped = reviewed_video_ids(store.plan, store.review_path, name)
                    if not ids:
                        self.note.emit(f"{name}: every song was skipped")
                        continue
                    self.note.emit(f"{name}: {len(ids)} to add, {skipped} skipped")
                    prefix = done
                    playlist_id = apply_playlist(
                        client,
                        name,
                        ids,
                        state_path_for(store.plan_path, name),
                        progress=lambda count, _total, label=name, start=prefix: self.updated.emit(
                            start + count, total, f"{label}: verified {count}/{_total} songs"
                        ),
                        cancelled=self.stop_event.is_set,
                    )
                    done += len(ids)
                    results.append((name, playlist_id))
                    self.note.emit(f"{name}: https://music.youtube.com/playlist?list={playlist_id}")
                self.completed.emit(results)
        except (ScanCancelled, TransferCancelled) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            LOGGER.exception("%s job failed", self.kind)
            self.failed.emit(f"{self.kind.capitalize()} failed: {exc or type(exc).__name__}")


class SongTable(QAbstractTableModel):
    COLUMNS = ("#", "Song", "Artist", "Match", "Decision")

    def __init__(self) -> None:
        super().__init__()
        self.store: ReviewStore | None = None
        self.playlist = ""
        self.needs_review = False
        self.entries: list[dict] = []

    def refresh(self) -> None:
        self.beginResetModel()
        self.entries = []
        if self.store:
            for entry in self.store.plan["entries"]:
                if entry["track"]["collection"] != self.playlist:
                    continue
                row = self.store.by_key[entry["track"]["key"]]
                if self.needs_review and self.store.is_resolved(row):
                    continue
                self.entries.append(entry)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: QModelIndex = EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        entry = self.entries[index.row()]
        track = entry["track"]
        row = self.store.by_key[track["key"]]
        match = entry["candidates"][0]["score"] if entry["candidates"] else None
        values = (
            track["position"],
            track["title"],
            track["artist"],
            f"{match:.0%}" if match is not None else "No match",
            row["Decision"] or "Needs review",
        )
        return str(values[index.column()])


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Spot2YTMusic v{__version__}")
        self.resize(1180, 780)
        self.tracks = []
        self.sources: list[Path] = []
        self.store: ReviewStore | None = None
        self.job: Job | None = None
        self.dark = True
        self._build()
        self._theme()
        self._update_buttons()

    def _button(self, label: str, handler, primary: bool = False) -> QPushButton:
        button = QPushButton(label)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(handler)
        return button

    def _build(self) -> None:
        content = QWidget()
        self.setCentralWidget(content)
        page = QVBoxLayout(content)
        page.setContentsMargins(20, 16, 20, 16)
        page.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Spot2YTMusic")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.theme_button = self._button("Light theme", self._toggle_theme)
        header.addWidget(self.theme_button)
        page.addLayout(header)
        intro = QLabel("Export your Spotify playlists, check the matches, then send them to YouTube Music.")
        intro.setObjectName("muted")
        page.addWidget(intro)

        actions = QFrame()
        actions.setObjectName("card")
        action_layout = QVBoxLayout(actions)
        first = QHBoxLayout()
        first.addWidget(self._button("1  Open Exportify", lambda: self._open_url(EXPORT_URL)))
        self.import_button = self._button("2  Import CSV or ZIP", self._choose_sources, True)
        first.addWidget(self.import_button)
        self.sources_label = QLabel("No files selected")
        self.sources_label.setObjectName("muted")
        first.addWidget(self.sources_label, 1)
        action_layout.addLayout(first)
        second = QHBoxLayout()
        second.addWidget(QLabel("Save plans in"))
        self.output_edit = QLineEdit(str(default_output()))
        second.addWidget(self.output_edit, 1)
        second.addWidget(self._button("Browse", self._choose_output))
        self.scan_button = self._button("3  Scan all", self._start_scan, True)
        second.addWidget(self.scan_button)
        self.open_plan_button = self._button("Open saved plan", self._choose_plan)
        second.addWidget(self.open_plan_button)
        action_layout.addLayout(second)
        page.addWidget(actions)

        review_bar = QHBoxLayout()
        review_bar.addWidget(QLabel("Playlist"))
        self.playlist_combo = QComboBox()
        self.playlist_combo.currentTextChanged.connect(self._switch_playlist)
        review_bar.addWidget(self.playlist_combo, 1)
        self.only_review = QCheckBox("Needs review only")
        self.only_review.toggled.connect(self._filter_changed)
        review_bar.addWidget(self.only_review)
        self.count_label = QLabel("Import files to begin")
        review_bar.addWidget(self.count_label)
        page.addLayout(review_bar)

        splitter = QSplitter(Qt.Horizontal)
        self.model = SongTable()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 52)
        self.table.setColumnWidth(1, 310)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 85)
        self.table.setColumnWidth(4, 120)
        self.table.selectionModel().currentRowChanged.connect(self._show_song)
        splitter.addWidget(self.table)

        detail = QFrame()
        detail.setObjectName("card")
        detail_layout = QVBoxLayout(detail)
        self.song_label = QLabel("Choose a song to review")
        self.song_label.setWordWrap(True)
        detail_layout.addWidget(self.song_label)
        self.candidates = QComboBox()
        self.candidates.currentIndexChanged.connect(self._candidate_changed)
        detail_layout.addWidget(QLabel("Suggested recordings"))
        detail_layout.addWidget(self.candidates)
        detail_layout.addWidget(QLabel("YouTube Music link or 11-character video ID"))
        self.video_edit = QLineEdit()
        self.video_edit.setPlaceholderText("Paste a YouTube Music song link or video ID")
        detail_layout.addWidget(self.video_edit)
        row = QHBoxLayout()
        row.addWidget(self._button("Search song", self._open_search))
        row.addWidget(self._button("Open candidate", self._open_candidate))
        detail_layout.addLayout(row)
        row = QHBoxLayout()
        self.use_button = self._button("Use recording", lambda: self._decide("use"), True)
        self.skip_button = self._button("Skip song", lambda: self._decide("skip"))
        row.addWidget(self.use_button)
        row.addWidget(self.skip_button)
        detail_layout.addLayout(row)
        detail_layout.addStretch()
        splitter.addWidget(detail)
        splitter.setSizes([760, 380])
        page.addWidget(splitter, 1)

        transfer = QFrame()
        transfer.setObjectName("card")
        transfer_layout = QHBoxLayout(transfer)
        transfer_layout.addWidget(self._button("Auth setup guide", lambda: self._open_url(AUTH_URL)))
        transfer_layout.addWidget(self._button("Paste browser headers", self._paste_auth))
        transfer_layout.addWidget(QLabel("YouTube Music auth"))
        self.auth_edit = QLineEdit()
        self.auth_edit.setPlaceholderText("Choose your local browser.json")
        transfer_layout.addWidget(self.auth_edit, 1)
        transfer_layout.addWidget(self._button("Browse", self._choose_auth))
        self.transfer_button = self._button("4  Transfer all", self._start_transfer, True)
        transfer_layout.addWidget(self.transfer_button)
        page.addWidget(transfer)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        progress_row.addWidget(self.progress, 1)
        self.stop_button = self._button("Stop", self._stop)
        progress_row.addWidget(self.stop_button)
        page.addLayout(progress_row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setFixedHeight(95)
        page.addWidget(self.log)
        self.statusBar().showMessage("Ready")

    def _theme(self) -> None:
        self.setStyleSheet(DARK if self.dark else LIGHT)
        self.theme_button.setText("Light theme" if self.dark else "Dark theme")

    def _toggle_theme(self) -> None:
        self.dark = not self.dark
        self._theme()

    def _log(self, message: str) -> None:
        self.log.appendPlainText(message)
        self.statusBar().showMessage(message, 8000)

    def _error(self, message: str) -> None:
        self._log("Error: " + message)
        QMessageBox.critical(self, "Spot2YTMusic", message)

    def _open_url(self, url: str) -> None:
        if not QDesktopServices.openUrl(QUrl(url)):
            self._error("Could not open the link in your browser")

    def _choose_sources(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose Spotify playlist exports",
            str(Path.home() / "Downloads"),
            "Playlist exports (*.csv *.zip)",
        )
        if not paths:
            return
        self._launch(Job("import", paths=[Path(path) for path in paths]))

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Save plans in", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def _choose_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a saved transfer plan", self.output_edit.text(), "Transfer plans (*.json)"
        )
        if path:
            self._load_plan(Path(path))

    def _choose_auth(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose YouTube Music authentication", str(Path.home()), "JSON (*.json)"
        )
        if path:
            self.auth_edit.setText(path)

    def _paste_auth(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Set up YouTube Music")
        dialog.resize(660, 450)
        layout = QVBoxLayout(dialog)
        directions = QLabel(
            "Sign in at music.youtube.com. Follow the auth guide to copy the request headers "
            "from your browser's developer tools, then paste them here. Keep these headers private."
        )
        directions.setWordWrap(True)
        layout.addWidget(directions)
        headers = QPlainTextEdit()
        headers.setPlaceholderText("Paste the copied request headers here")
        layout.addWidget(headers, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Open guide", lambda: self._open_url(AUTH_URL)))
        buttons.addStretch()

        def save() -> None:
            destination = log_path().with_name("browser.json")
            try:
                save_browser_auth(headers.toPlainText(), destination)
            except (OSError, ValueError, YTMusicError) as exc:
                self._error(str(exc) or type(exc).__name__)
                return
            headers.clear()
            self.auth_edit.setText(str(destination))
            self._log("YouTube Music auth saved locally")
            dialog.accept()

        buttons.addWidget(self._button("Save auth", save, True))
        layout.addLayout(buttons)
        dialog.exec()

    def _load_plan(self, path: Path) -> None:
        try:
            store = ReviewStore(path)
        except (OSError, ValueError, KeyError) as exc:
            self._error(str(exc))
            return
        self.store = store
        self.model.store = store
        self.playlist_combo.clear()
        self.playlist_combo.addItems(store.playlists)
        self._switch_playlist(self.playlist_combo.currentText())
        self._log(f"Opened {path.name}: {len(store.plan['entries'])} songs")
        self._update_buttons()

    def _switch_playlist(self, playlist: str) -> None:
        self.model.playlist = playlist
        self.model.refresh()
        if self.model.entries:
            self.table.selectRow(0)
        else:
            self._show_song(EMPTY_INDEX)
        self._update_buttons()

    def _filter_changed(self, checked: bool) -> None:
        self.model.needs_review = checked
        self._switch_playlist(self.playlist_combo.currentText())

    def _current_entry(self) -> dict | None:
        row = self.table.currentIndex().row()
        return self.model.entries[row] if 0 <= row < len(self.model.entries) else None

    def _show_song(self, index: QModelIndex, _previous: QModelIndex = EMPTY_INDEX) -> None:
        entry = (
            self.model.entries[index.row()]
            if index.isValid() and index.row() < len(self.model.entries)
            else None
        )
        self.candidates.blockSignals(True)
        self.candidates.clear()
        if entry:
            track = entry["track"]
            self.song_label.setText(
                f"{track['position']}. {track['title']}\n{track['artist']}\n{track['album']}\n{entry['note']}"
            )
            for item in entry["candidates"]:
                self.candidates.addItem(
                    f"{item['title']} | {item['artist']} | {item['score']:.0%} | "
                    f"{item['duration_seconds'] or '?'}s",
                    item["video_id"],
                )
            self.video_edit.setText(
                self.store.by_key[track["key"]]["Chosen video ID"] or entry["selected_video_id"]
            )
        else:
            self.song_label.setText("Choose a song to review")
            self.video_edit.clear()
        self.candidates.blockSignals(False)
        self.use_button.setEnabled(bool(entry))
        self.skip_button.setEnabled(bool(entry))

    def _candidate_changed(self, index: int) -> None:
        if index >= 0:
            self.video_edit.setText(str(self.candidates.itemData(index)))

    def _open_search(self) -> None:
        entry = self._current_entry()
        if entry:
            from urllib.parse import quote_plus

            track = entry["track"]
            self._open_url(
                "https://music.youtube.com/search?q=" + quote_plus(track["title"] + " " + track["artist"])
            )

    def _open_candidate(self) -> None:
        video_id = video_id_from(self.video_edit.text())
        if len(video_id) != 11:
            self._error("Choose a candidate or enter a valid YouTube Music link")
            return
        self._open_url("https://music.youtube.com/watch?v=" + video_id)

    def _decide(self, decision: str) -> None:
        entry = self._current_entry()
        if not entry or not self.store:
            return
        row = self.table.currentIndex().row()
        try:
            self.store.decide(
                entry["track"]["key"],
                decision,
                video_id_from(self.video_edit.text()) if decision == "use" else "",
            )
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return
        self._log(f"Saved {decision}: {entry['track']['title']}")
        self.model.refresh()
        if self.model.entries:
            self.table.selectRow(min(row, len(self.model.entries) - 1))
        self._update_buttons()

    def _update_buttons(self) -> None:
        busy = self.job is not None
        self.import_button.setEnabled(not busy)
        self.open_plan_button.setEnabled(not busy)
        self.scan_button.setEnabled(bool(self.tracks) and not busy)
        self.transfer_button.setEnabled(bool(self.store and not self.store.unresolved()) and not busy)
        self.stop_button.setEnabled(busy)
        if self.store:
            counts = self.store.counts()
            self.count_label.setText(
                f"{counts['use']} ready, {counts['review']} to review, {counts['skip']} skipped"
            )

    def _start_scan(self) -> None:
        if not self.tracks:
            return
        output = Path(self.output_edit.text().strip()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._error(str(exc))
            return
        self._launch(Job("scan", tracks=self.tracks, output=output))

    def _start_transfer(self) -> None:
        if not self.store:
            return
        if self.store.unresolved():
            self._error("Review every song before transferring")
            return
        auth = Path(self.auth_edit.text().strip())
        if not auth.is_file():
            self._error("Choose a local YouTube Music authentication JSON file")
            return
        self._launch(Job("transfer", plan_path=self.store.plan_path, auth=auth))

    def _launch(self, job: Job) -> None:
        self.job = job
        self.progress.setRange(0, 0 if job.kind == "import" else 100)
        if job.kind != "import":
            self.progress.setValue(0)
        job.updated.connect(self._progress)
        job.note.connect(self._log)
        job.completed.connect(self._completed)
        job.failed.connect(self._failed)
        job.finished.connect(self._job_finished)
        job.start()
        self._update_buttons()

    def _progress(self, done: int, total: int, message: str) -> None:
        self.progress.setValue(round(100 * done / total) if total else 100)
        self.statusBar().showMessage(message)
        if done == 1 or done == total or done % 25 == 0:
            self.log.appendPlainText(message)

    def _completed(self, result: object) -> None:
        if isinstance(result, dict) and result.get("kind") == "import":
            self.tracks = result["tracks"]
            self.sources = result["paths"]
            self.sources_label.setText(
                f"{len(self.sources)} file(s), {len(self.tracks)} songs, "
                f"{len({track.collection for track in self.tracks})} playlists"
            )
            self._log("Imported " + self.sources_label.text())
        elif isinstance(result, Path):
            self._load_plan(result)
            self._log("Scan finished. Check the uncertain matches, then transfer.")
        else:
            self._log(f"Transfer finished: {len(result)} playlists")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

    def _failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        if "stopped" in message.casefold():
            self._log(message)
        else:
            self._error(message)

    def _job_finished(self) -> None:
        self.job = None
        self._update_buttons()

    def _stop(self) -> None:
        if self.job:
            self.job.stop_event.set()
            self._log("Stopping after the current song or verified batch...")

    def closeEvent(self, event) -> None:
        if self.job:
            self._stop()
            event.ignore()
        else:
            event.accept()


def main() -> int:
    logging.basicConfig(
        filename=log_path(), level=logging.ERROR, format="%(asctime)s %(levelname)s %(message)s"
    )

    def _crash(kind, error, traceback) -> None:
        LOGGER.critical("Unhandled error", exc_info=(kind, error, traceback))
        QMessageBox.critical(
            None, "Spot2YTMusic", f"An unexpected error occurred.\n\n{error}\n\nDetails: {log_path()}"
        )

    sys.excepthook = _crash
    app = QApplication(sys.argv)
    window = MainWindow()
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer

        try:
            _client()
        except Exception:
            LOGGER.exception("Packaged YouTube Music client startup failed")
            return 1
        QTimer.singleShot(100, app.quit)
    else:
        window.show()
    return app.exec()
