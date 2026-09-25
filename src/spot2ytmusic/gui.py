"""Windows-friendly desktop workflow for reviewed playlist transfers."""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
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
QWidget { background-color: #0d1422; color: #dce6f5; font: 10pt 'Segoe UI'; }
QFrame#panel { background-color: #151f32; border: 1px solid #293750; border-radius: 10px; }
QFrame#soft { background-color: #1b2940; border: 1px solid #34445d; border-radius: 8px; }
QFrame#separator { background-color: #2b3952; border: 0; max-height: 1px; }
QLabel, QCheckBox { background-color: transparent; }
QLabel#brand { font-size: 24pt; font-weight: 700; color: #d4b8ff; }
QLabel#section { font-size: 11pt; font-weight: 700; color: #c7d5ff; }
QLabel#detailTitle { font-size: 18pt; font-weight: 700; color: #f2f5ff; }
QLabel#badge { background-color: #d5dcff; color: #122039; border-radius: 8px; font-weight: 700; }
QLabel#muted, QLabel#helper { color: #a6b7ce; }
QLabel#score { background-color: #255a48; color: #7af0b5; border-radius: 6px; padding: 5px 8px; font-weight: 700; }
QPushButton { background-color: #2b3850; border: 1px solid #35435d; border-radius: 6px; padding: 6px 11px; min-height: 26px; }
QPushButton:hover { background-color: #394b69; }
QPushButton:pressed { background-color: #425b81; }
QPushButton:disabled { background-color: #253147; color: #7b8ba5; border-color: #2d3a51; }
QPushButton#primary { background-color: #2774ee; color: #ffffff; border-color: #3681f4; font-weight: 700; }
QPushButton#primary:hover { background-color: #438bff; }
QPushButton#primary:disabled { background-color: #263954; color: #8294ad; border-color: #35445c; }
QPushButton#quiet { background: transparent; border-color: #35435d; color: #b9c9e1; }
QLineEdit, QComboBox, QListWidget, QPlainTextEdit, QTableView { background-color: #101a2b; color: #e1eafa; border: 1px solid #35435d; border-radius: 6px; padding: 5px; selection-background-color: #245eaf; }
QListWidget::item { min-height: 28px; padding: 3px 5px; }
QListWidget::item:selected { background-color: #234a82; }
QListView::indicator, QCheckBox::indicator { width: 16px; height: 16px; }
QListView::indicator:unchecked, QCheckBox::indicator:unchecked { background-color: #101a2b; border: 1px solid #8293ad; border-radius: 4px; }
QListView::indicator:checked, QCheckBox::indicator:checked { background-color: #2b7af0; border: 1px solid #6ba7ff; border-radius: 4px; }
QTableView { alternate-background-color: #172238; gridline-color: #2a3952; }
QTableView::item:selected { background-color: #245eaf; color: #ffffff; }
QHeaderView::section { background-color: #25334a; color: #d4dff1; padding: 8px; border: 0; border-right: 1px solid #34445d; }
QProgressBar { background-color: #2b3952; border: 0; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background-color: #46cc8e; border-radius: 5px; }
QStatusBar { color: #9eafc8; }
QSplitter::handle { background-color: #0d1422; }
QScrollArea { background-color: transparent; border: 0; }
"""
LIGHT = """
QWidget { background-color: #eef2fa; color: #27344b; font: 10pt 'Segoe UI'; }
QFrame#panel { background-color: #ffffff; border: 1px solid #cad5e6; border-radius: 10px; }
QFrame#soft { background-color: #f3f6fb; border: 1px solid #d1daea; border-radius: 8px; }
QFrame#separator { background-color: #d1daea; border: 0; max-height: 1px; }
QLabel, QCheckBox { background-color: transparent; }
QLabel#brand { font-size: 24pt; font-weight: 700; color: #6841b7; }
QLabel#section { font-size: 11pt; font-weight: 700; color: #33456c; }
QLabel#detailTitle { font-size: 18pt; font-weight: 700; color: #233049; }
QLabel#badge { background-color: #dce3ff; color: #264079; border-radius: 8px; font-weight: 700; }
QLabel#muted, QLabel#helper { color: #62738d; }
QLabel#score { background-color: #d5f4e2; color: #1d7449; border-radius: 6px; padding: 5px 8px; font-weight: 700; }
QPushButton { background-color: #e1e8f3; border: 1px solid #cbd6e6; border-radius: 6px; padding: 6px 11px; min-height: 26px; }
QPushButton:hover { background-color: #d3deee; }
QPushButton:disabled { background-color: #e9edf4; color: #98a5b8; border-color: #d9e1ed; }
QPushButton#primary { background-color: #246fdf; color: #ffffff; border-color: #246fdf; font-weight: 700; }
QPushButton#primary:hover { background-color: #4084ef; }
QPushButton#primary:disabled { background-color: #d9e3f0; color: #9aabc2; border-color: #ccd8e9; }
QPushButton#quiet { background: transparent; border-color: #cad5e6; color: #51637d; }
QLineEdit, QComboBox, QListWidget, QPlainTextEdit, QTableView { background-color: #ffffff; color: #27344b; border: 1px solid #c8d3e5; border-radius: 6px; padding: 5px; selection-background-color: #b4d1ff; }
QListWidget::item { min-height: 28px; padding: 3px 5px; }
QListWidget::item:selected { background-color: #d2e3ff; }
QListView::indicator, QCheckBox::indicator { width: 16px; height: 16px; }
QListView::indicator:unchecked, QCheckBox::indicator:unchecked { background-color: #ffffff; border: 1px solid #8293ad; border-radius: 4px; }
QListView::indicator:checked, QCheckBox::indicator:checked { background-color: #246fdf; border: 1px solid #246fdf; border-radius: 4px; }
QTableView { alternate-background-color: #f1f5fb; gridline-color: #d6dfed; }
QTableView::item:selected { background-color: #b4d1ff; color: #20334f; }
QHeaderView::section { background-color: #e4ebf5; color: #354765; padding: 8px; border: 0; border-right: 1px solid #d1daea; }
QProgressBar { background-color: #dbe4f0; border: 0; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background-color: #31ad72; border-radius: 5px; }
QSplitter::handle { background-color: #eef2fa; }
QScrollArea { background-color: transparent; border: 0; }
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
                    _client(request_timeout=10),
                    tracks,
                    cache,
                    progress=lambda done, total, entry: self.updated.emit(
                        done,
                        total,
                        f"{entry.track.collection} #{entry.track.position}: {entry.track.title} ({entry.status})",
                    ),
                    cancelled=self.stop_event.is_set,
                )
                if self.stop_event.is_set():
                    raise ScanCancelled("Scan stopped. Search results already found remain in the cache.")
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
                names = self.arguments["playlists"]
                if not names or any(name not in store.playlists for name in names):
                    raise ValueError("Choose playlists from the open plan")
                client = _client(self.arguments["auth"])
                total = sum(
                    len(reviewed_video_ids(store.plan, store.review_path, name)[0])
                    for name in names
                )
                done = 0
                results = []
                for name in names:
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
    COLUMNS = ("#", "Song", "Artist", "Match", "Status")

    def __init__(self) -> None:
        super().__init__()
        self.store: ReviewStore | None = None
        self.playlist = ""
        self.needs_review = False
        self.dark = True
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
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        track = entry["track"]
        row = self.store.by_key[track["key"]]
        match = entry["candidates"][0]["score"] if entry["candidates"] else None
        decision = (row["Decision"] or "").strip().casefold()
        status = "Ready" if decision == "use" else "Skipped" if decision == "skip" else "Review"
        if role == Qt.ForegroundRole:
            if index.column() == 3 and match is not None:
                return QColor(
                    ("#66dfa5" if match >= 0.9 else "#ffd36e")
                    if self.dark
                    else ("#137346" if match >= 0.9 else "#895b00")
                )
            if index.column() == 4:
                colors = (
                    {"Ready": "#66dfa5", "Review": "#ffd36e", "Skipped": "#9eafc8"}
                    if self.dark
                    else {"Ready": "#137346", "Review": "#895b00", "Skipped": "#62738d"}
                )
                return QColor(colors[status])
        if role == Qt.TextAlignmentRole and index.column() in (0, 3):
            return Qt.AlignCenter
        if role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        values = (
            track["position"],
            track["title"],
            track["artist"],
            f"{match:.0%}" if match is not None else "No match",
            status,
        )
        return str(values[index.column()])


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Spot2YTMusic v{__version__}")
        self.setMinimumSize(1080, 700)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(
            max(1080, min(1440, available.width() - 32)),
            max(700, min(900, available.height() - 32)),
        )
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

    def _section_heading(self, layout: QVBoxLayout, number: str | None, title: str, helper: str) -> None:
        heading = QHBoxLayout()
        heading.setSpacing(10)
        if number:
            badge = QLabel(number)
            badge.setObjectName("badge")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(29, 29)
            heading.addWidget(badge)
        label = QLabel(title)
        label.setObjectName("section")
        heading.addWidget(label)
        heading.addStretch()
        layout.addLayout(heading)
        explanation = QLabel(helper)
        explanation.setObjectName("helper")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

    def _build(self) -> None:
        content = QWidget()
        self.setCentralWidget(content)
        page = QVBoxLayout(content)
        page.setContentsMargins(12, 10, 12, 7)
        page.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(18)
        title = QLabel("Spot2YTMusic")
        title.setObjectName("brand")
        header.addWidget(title)
        subtitle = QLabel("Move your playlists with confidence")
        subtitle.setObjectName("muted")
        header.addWidget(subtitle)
        header.addStretch()
        export_button = self._button("Open Exportify", lambda: self._open_url(EXPORT_URL))
        export_button.setObjectName("quiet")
        header.addWidget(export_button)
        self.open_plan_button = self._button("Open saved plan", self._choose_plan)
        self.open_plan_button.setObjectName("quiet")
        header.addWidget(self.open_plan_button)
        self.theme_button = self._button("Light theme", self._toggle_theme)
        self.theme_button.setObjectName("quiet")
        header.addWidget(self.theme_button)
        page.addLayout(header)

        workspace = QSplitter(Qt.Horizontal)
        workspace.setChildrenCollapsible(False)
        workspace.setHandleWidth(8)

        sources = QFrame()
        sources.setObjectName("panel")
        sources.setMinimumHeight(548)
        source_layout = QVBoxLayout(sources)
        source_layout.setContentsMargins(15, 15, 15, 15)
        source_layout.setSpacing(9)
        self._section_heading(
            source_layout,
            "1",
            "IMPORT & SELECT",
            "Import your Spotify export, then choose which playlists to migrate.",
        )
        self.import_button = self._button("Import CSV or ZIP", self._choose_sources, True)
        self.import_button.setMinimumHeight(42)
        source_layout.addWidget(self.import_button)
        source_strip = QFrame()
        source_strip.setObjectName("soft")
        source_strip_layout = QHBoxLayout(source_strip)
        source_strip_layout.setContentsMargins(10, 7, 10, 7)
        self.sources_label = QLabel("No files selected")
        self.sources_label.setObjectName("muted")
        self.sources_label.setWordWrap(True)
        source_strip_layout.addWidget(self.sources_label)
        source_layout.addWidget(source_strip)
        self.playlists_label = QLabel("Playlists (0)")
        source_layout.addWidget(self.playlists_label)
        self.playlist_list = QListWidget()
        self.playlist_list.setMinimumHeight(122)
        self.playlist_list.setMaximumHeight(150)
        self.playlist_list.itemChanged.connect(lambda _item: self._update_buttons())
        source_layout.addWidget(self.playlist_list, 1)
        selection_buttons = QHBoxLayout()
        self.select_all_button = self._button("Select all", lambda: self._select_all_playlists(True))
        self.select_none_button = self._button("Select none", lambda: self._select_all_playlists(False))
        selection_buttons.addWidget(self.select_all_button)
        selection_buttons.addWidget(self.select_none_button)
        source_layout.addLayout(selection_buttons)
        divider = QFrame()
        divider.setObjectName("separator")
        divider.setFixedHeight(1)
        source_layout.addWidget(divider)
        source_layout.addWidget(QLabel("Save plan to"))
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(str(default_output()))
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self._button("Browse", self._choose_output))
        source_layout.addLayout(output_row)
        scan_row = QHBoxLayout()
        self.scan_button = self._button("Scan selected", self._start_scan, True)
        self.scan_button.setMinimumHeight(39)
        scan_row.addWidget(self.scan_button, 2)
        self.stop_scan_button = self._button("Stop scan", self._stop)
        self.stop_scan_button.setMinimumHeight(39)
        scan_row.addWidget(self.stop_scan_button, 1)
        source_layout.addLayout(scan_row)
        source_scroll = QScrollArea()
        source_scroll.setWidgetResizable(True)
        source_scroll.setMinimumWidth(245)
        source_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        source_scroll.setWidget(sources)
        workspace.addWidget(source_scroll)

        review = QFrame()
        review.setObjectName("panel")
        review.setMinimumWidth(470)
        review_layout = QVBoxLayout(review)
        review_layout.setContentsMargins(13, 15, 13, 13)
        review_layout.setSpacing(9)
        self._section_heading(
            review_layout,
            "2",
            "REVIEW MATCHES",
            "Check each match. Choose a playlist or show only songs that need a decision.",
        )
        review_bar = QHBoxLayout()
        review_bar.setSpacing(9)
        review_bar.addWidget(QLabel("Playlist"))
        self.playlist_combo = QComboBox()
        self.playlist_combo.currentTextChanged.connect(self._switch_playlist)
        review_bar.addWidget(self.playlist_combo, 1)
        self.only_review = QCheckBox("Needs review only")
        self.only_review.toggled.connect(self._filter_changed)
        review_bar.addWidget(self.only_review)
        review_layout.addLayout(review_bar)
        self.model = SongTable()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setMinimumHeight(41)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 44)
        self.table.setColumnWidth(2, 138)
        self.table.setColumnWidth(3, 84)
        self.table.setColumnWidth(4, 108)
        self.table.selectionModel().currentRowChanged.connect(self._show_song)
        review_layout.addWidget(self.table, 1)
        workspace.addWidget(review)

        detail = QFrame()
        detail.setObjectName("panel")
        detail.setMinimumHeight(455)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(14, 15, 14, 15)
        detail_layout.setSpacing(10)
        self._section_heading(
            detail_layout,
            None,
            "NOW REVIEWING",
            "Choose the best recording for this track.",
        )
        song_card = QFrame()
        song_card.setObjectName("soft")
        song_card_layout = QHBoxLayout(song_card)
        song_card_layout.setContentsMargins(10, 10, 10, 10)
        song_card_layout.setSpacing(12)
        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(102, 102)
        artwork = QPixmap(str(Path(__file__).resolve().parent / "assets" / "track-placeholder.png"))
        if artwork.isNull():
            raise FileNotFoundError("Track artwork is missing from the app package")
        self.artwork_label.setPixmap(artwork.scaled(102, 102, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        song_card_layout.addWidget(self.artwork_label)
        song_info = QVBoxLayout()
        self.song_label = QLabel("Choose a song")
        self.song_label.setObjectName("detailTitle")
        self.song_label.setWordWrap(True)
        song_info.addWidget(self.song_label)
        self.artist_label = QLabel("")
        song_info.addWidget(self.artist_label)
        self.origin_label = QLabel("")
        self.origin_label.setObjectName("muted")
        song_info.addWidget(self.origin_label)
        song_info.addStretch()
        song_card_layout.addLayout(song_info, 1)
        detail_layout.addWidget(song_card)

        candidate_card = QFrame()
        candidate_card.setObjectName("soft")
        candidate_layout = QVBoxLayout(candidate_card)
        candidate_layout.setContentsMargins(10, 10, 10, 10)
        candidate_head = QHBoxLayout()
        candidate_head.addWidget(QLabel("Suggested recording"))
        candidate_head.addStretch()
        self.candidate_score = QLabel("No match")
        self.candidate_score.setObjectName("score")
        candidate_head.addWidget(self.candidate_score)
        candidate_layout.addLayout(candidate_head)
        self.candidates = QComboBox()
        self.candidates.currentIndexChanged.connect(self._candidate_changed)
        candidate_body = QHBoxLayout()
        candidate_artwork = QLabel()
        candidate_artwork.setFixedSize(52, 52)
        candidate_artwork.setPixmap(artwork.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        candidate_body.addWidget(candidate_artwork)
        candidate_info = QVBoxLayout()
        candidate_info.addWidget(self.candidates)
        self.candidate_detail = QLabel("Choose a song to see suggestions")
        self.candidate_detail.setObjectName("muted")
        self.candidate_detail.setWordWrap(True)
        candidate_info.addWidget(self.candidate_detail)
        candidate_body.addLayout(candidate_info, 1)
        candidate_layout.addLayout(candidate_body)
        detail_layout.addWidget(candidate_card)
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
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setMinimumWidth(300)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        detail_scroll.setWidget(detail)
        workspace.addWidget(detail_scroll)
        workspace.setSizes([325, 715, 350])
        page.addWidget(workspace, 1)

        transfer = QFrame()
        transfer.setObjectName("panel")
        transfer_layout = QVBoxLayout(transfer)
        transfer_layout.setContentsMargins(15, 8, 15, 8)
        transfer_layout.setSpacing(5)
        transfer_heading = QHBoxLayout()
        transfer_badge = QLabel("3")
        transfer_badge.setObjectName("badge")
        transfer_badge.setAlignment(Qt.AlignCenter)
        transfer_badge.setFixedSize(29, 29)
        transfer_heading.addWidget(transfer_badge)
        transfer_title = QLabel("SEND TO YOUTUBE MUSIC")
        transfer_title.setObjectName("section")
        transfer_heading.addWidget(transfer_title)
        transfer_heading.addWidget(QLabel("Authenticate, then transfer the playlists you checked."))
        transfer_heading.addStretch()
        guide_button = self._button("Auth setup guide", lambda: self._open_url(AUTH_URL))
        guide_button.setObjectName("quiet")
        transfer_heading.addWidget(guide_button)
        paste_button = self._button("Paste browser headers", self._paste_auth)
        paste_button.setObjectName("quiet")
        transfer_heading.addWidget(paste_button)
        transfer_layout.addLayout(transfer_heading)
        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("YouTube Music auth file"))
        self.auth_edit = QLineEdit()
        self.auth_edit.setPlaceholderText("Choose your local browser.json")
        auth_row.addWidget(self.auth_edit, 1)
        auth_row.addWidget(self._button("Browse", self._choose_auth))
        self.transfer_button = self._button("Transfer selected", self._start_transfer, True)
        self.transfer_button.setMinimumWidth(210)
        auth_row.addWidget(self.transfer_button)
        transfer_layout.addLayout(auth_row)
        self.count_label = QLabel("Import files to begin")
        self.count_label.setObjectName("muted")
        transfer_layout.addWidget(self.count_label)

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("Ready to scan or transfer")
        progress_row.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        progress_row.addWidget(self.progress, 1)
        self.progress_count_label = QLabel("")
        self.progress_count_label.setObjectName("muted")
        progress_row.addWidget(self.progress_count_label)
        self.stop_button = self._button("Stop", self._stop)
        progress_row.addWidget(self.stop_button)
        transfer_layout.addLayout(progress_row)
        transfer_layout.addWidget(QLabel("Activity log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setFixedHeight(42)
        transfer_layout.addWidget(self.log)
        page.addWidget(transfer)
        self.statusBar().showMessage("Ready")
        self.statusBar().setFixedHeight(18)

    def _theme(self) -> None:
        self.setStyleSheet(DARK if self.dark else LIGHT)
        self.theme_button.setText("Light theme" if self.dark else "Dark theme")
        self.model.dark = self.dark
        if self.model.entries:
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(len(self.model.entries) - 1, len(self.model.COLUMNS) - 1),
                [Qt.ForegroundRole],
            )

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

    def _selected_playlists(self) -> list[str]:
        return [
            self.playlist_list.item(index).data(Qt.UserRole)
            for index in range(self.playlist_list.count())
            if self.playlist_list.item(index).checkState() == Qt.Checked
        ]

    def _populate_playlists(self, counts: Counter[str], selected: set[str] | None = None) -> None:
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        for name, count in counts.items():
            item = QListWidgetItem(f"{name}  ({count} songs)")
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if selected is None or name in selected else Qt.Unchecked)
            self.playlist_list.addItem(item)
        self.playlist_list.blockSignals(False)
        self.playlists_label.setText(f"Playlists ({self.playlist_list.count()})")
        self._update_buttons()

    def _select_all_playlists(self, checked: bool) -> None:
        self.playlist_list.blockSignals(True)
        for index in range(self.playlist_list.count()):
            self.playlist_list.item(index).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.playlist_list.blockSignals(False)
        self._update_buttons()

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

    def _load_plan(self, path: Path, from_scan: bool = False) -> None:
        try:
            store = ReviewStore(path)
        except (OSError, ValueError, KeyError) as exc:
            self._error(str(exc))
            return
        self.store = store
        self.model.store = store
        if from_scan:
            counts = Counter(track.collection for track in self.tracks)
            self._populate_playlists(counts, set(store.playlists))
        else:
            self.tracks = []
            self.sources = []
            self.sources_label.setText(f"Open plan: {path.name}")
            counts = Counter(entry["track"]["collection"] for entry in store.plan["entries"])
            self._populate_playlists(counts)
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
            self.song_label.setText(track["title"])
            self.artist_label.setText(track["artist"] or "Artist unavailable")
            self.origin_label.setText(f"From: {track['collection']}")
            for item in entry["candidates"]:
                self.candidates.addItem(
                    f"{item['title']}  |  {item['artist']}  |  {item['score']:.0%}",
                    item["video_id"],
                )
            self.video_edit.setText(
                self.store.by_key[track["key"]]["Chosen video ID"] or entry["selected_video_id"]
            )
            self._show_candidate_details(0)
        else:
            self.song_label.setText("Choose a song")
            self.artist_label.clear()
            self.origin_label.clear()
            self.candidate_score.setText("No match")
            self.candidate_detail.setText("Choose a song to see suggestions")
            self.video_edit.clear()
        self.candidates.blockSignals(False)
        self.use_button.setEnabled(bool(entry))
        self.skip_button.setEnabled(bool(entry))

    def _show_candidate_details(self, index: int) -> None:
        entry = self._current_entry()
        if not entry or not 0 <= index < len(entry["candidates"]):
            self.candidate_score.setText("No match")
            self.candidate_detail.setText("Search YouTube Music for this song")
            return
        candidate = entry["candidates"][index]
        self.candidate_score.setText(f"{candidate['score']:.0%} match")
        album = candidate["album"] or candidate["result_type"].capitalize()
        duration = candidate["duration_seconds"]
        timing = f"  |  {duration // 60}:{duration % 60:02d}" if duration else ""
        self.candidate_detail.setText(f"{candidate['artist']}  |  {album}{timing}")

    def _candidate_changed(self, index: int) -> None:
        if index >= 0:
            self.video_edit.setText(str(self.candidates.itemData(index)))
        self._show_candidate_details(index)

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
        selected = self._selected_playlists()
        selected_set = set(selected)
        self.import_button.setEnabled(not busy)
        self.open_plan_button.setEnabled(not busy)
        self.playlist_list.setEnabled(not busy)
        self.select_all_button.setEnabled(bool(self.playlist_list.count()) and not busy)
        self.select_none_button.setEnabled(bool(self.playlist_list.count()) and not busy)
        self.scan_button.setEnabled(bool(self.tracks and selected) and not busy)
        can_transfer = bool(
            self.store
            and selected
            and selected_set.issubset(self.store.playlists)
            and not self.store.unresolved(selected_set)
        )
        self.transfer_button.setEnabled(can_transfer and not busy)
        self.stop_button.setEnabled(busy and not self.job.stop_event.is_set())
        self.stop_scan_button.setEnabled(
            busy and self.job.kind == "scan" and not self.job.stop_event.is_set()
        )
        if self.store:
            if not selected:
                self.count_label.setText("Choose playlists to transfer")
            elif not selected_set.issubset(self.store.playlists):
                self.count_label.setText("Scan selected playlists to transfer them")
            else:
                counts = self.store.counts(selected_set)
                self.count_label.setText(
                    f"Selected: {counts['use']} ready, {counts['review']} to review, {counts['skip']} skipped"
                )
        else:
            self.count_label.setText(
                f"{len(selected)} of {self.playlist_list.count()} playlists selected"
                if self.playlist_list.count()
                else "Import files to begin"
            )

    def _start_scan(self) -> None:
        selected = set(self._selected_playlists())
        if not self.tracks or not selected:
            return
        tracks = [track for track in self.tracks if track.collection in selected]
        output = Path(self.output_edit.text().strip()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._error(str(exc))
            return
        self._log(f"Scanning {len(selected)} playlists, {len(tracks)} songs")
        self._launch(Job("scan", tracks=tracks, output=output))

    def _start_transfer(self) -> None:
        if not self.store:
            return
        selected = self._selected_playlists()
        if not selected or not set(selected).issubset(self.store.playlists):
            self._error("Choose playlists from the open plan")
            return
        if self.store.unresolved(set(selected)):
            self._error("Review the selected playlists before transferring")
            return
        auth = Path(self.auth_edit.text().strip())
        if not auth.is_file():
            self._error("Choose a local YouTube Music authentication JSON file")
            return
        self._log(f"Transferring {len(selected)} selected playlists")
        self._launch(Job("transfer", plan_path=self.store.plan_path, auth=auth, playlists=selected))

    def _launch(self, job: Job) -> None:
        self.job = job
        self.stop_button.setText(
            {"import": "Stop import", "scan": "Stop scan", "transfer": "Stop transfer"}[job.kind]
        )
        self.progress.setRange(0, 0 if job.kind == "import" else 100)
        if job.kind != "import":
            self.progress.setValue(0)
        self.progress_label.setText(
            {"import": "Importing playlists...", "scan": "Scanning YouTube Music...", "transfer": "Transferring to YouTube Music..."}[job.kind]
        )
        self.progress_count_label.clear()
        job.updated.connect(self._progress)
        job.note.connect(self._log)
        job.completed.connect(self._completed)
        job.failed.connect(self._failed)
        job.finished.connect(self._job_finished)
        job.start()
        self._update_buttons()

    def _progress(self, done: int, total: int, message: str) -> None:
        self.progress.setValue(round(100 * done / total) if total else 100)
        self.progress_count_label.setText(f"{done} / {total} tracks")
        self.statusBar().showMessage(message)
        if done == 1 or done == total or done % 25 == 0:
            self.log.appendPlainText(message)

    def _completed(self, result: object) -> None:
        if isinstance(result, dict) and result.get("kind") == "import":
            self.tracks = result["tracks"]
            self.sources = result["paths"]
            self.store = None
            self.model.store = None
            self.playlist_combo.clear()
            self.model.refresh()
            self._populate_playlists(Counter(track.collection for track in self.tracks))
            source_name = self.sources[0].name if len(self.sources) == 1 else f"{len(self.sources)} files"
            self.sources_label.setText(
                f"{source_name} · {len(self.tracks)} songs · "
                f"{len({track.collection for track in self.tracks})} playlists"
            )
            self._log("Imported " + self.sources_label.text())
        elif isinstance(result, Path):
            self._load_plan(result, from_scan=True)
            self._log("Scan finished. Check the uncertain matches, then transfer.")
        else:
            self._log(f"Transfer finished: {len(result)} playlists")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress_label.setText("Finished")

    def _failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        if "stopped" in message.casefold():
            self.progress_label.setText("Stopped")
            self._log(message)
        else:
            self.progress_label.setText("Needs attention")
            self._error(message)

    def _job_finished(self) -> None:
        self.job = None
        self.stop_button.setText("Stop")
        self.stop_scan_button.setText("Stop scan")
        self._update_buttons()

    def _stop(self) -> None:
        if self.job and not self.job.stop_event.is_set():
            self.job.stop_event.set()
            self.stop_button.setText("Stopping...")
            self.stop_button.setEnabled(False)
            self.stop_scan_button.setText("Stopping...")
            self.stop_scan_button.setEnabled(False)
            messages = {
                "scan": "Stopping scan after the current YouTube Music request...",
                "transfer": "Stopping transfer after the current verified batch...",
                "import": "Stopping import after the current file...",
            }
            self._log(messages[self.job.kind])

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
            _client(request_timeout=10)
        except Exception:
            LOGGER.exception("Packaged YouTube Music client startup failed")
            return 1
        QTimer.singleShot(100, app.quit)
    else:
        window.show()
    return app.exec()
