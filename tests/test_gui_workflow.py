import os
import threading
import time
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from spot2ytmusic.cli import _client
from spot2ytmusic.gui import MainWindow, save_browser_auth
from spot2ytmusic.models import Track


class FakeMusic:
    def __init__(self):
        self.items = []

    def search(self, query, filter, limit):
        return [
            {
                "videoId": "abcdefghijk",
                "title": "Other recording",
                "artists": [{"name": "Other artist"}],
                "duration_seconds": 193,
                "resultType": "song",
                "isAvailable": True,
            }
        ]

    def get_library_playlists(self, limit=None):
        return []

    def create_playlist(self, name, description, privacy_status):
        assert name == "Road Trip"
        assert privacy_status == "PRIVATE"
        return "PLexample"

    def get_playlist(self, playlist_id, limit=None):
        return {"tracks": [{"videoId": item} for item in self.items]}

    def add_playlist_items(self, playlist_id, videoIds, duplicates):
        self.items.extend(videoIds)
        return "STATUS_SUCCEEDED"


def wait_for_job(app: QApplication, window: MainWindow) -> None:
    deadline = time.monotonic() + 10
    while window.job and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert window.job is None


def test_offscreen_scan_review_transfer_from_export_all(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    archive_path = tmp_path / "Export_All.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("Road_Trip.csv", "Track Name,Artist Name(s)\nExample,Artist\n")
    fake = FakeMusic()
    monkeypatch.setattr("spot2ytmusic.gui._client", lambda auth=None, request_timeout=None: fake)
    monkeypatch.setattr(
        "spot2ytmusic.gui.QFileDialog.getOpenFileNames",
        lambda *args: ([str(archive_path)], ""),
    )
    window = MainWindow()
    window.import_button.click()
    wait_for_job(app, window)
    assert len(window.tracks) == 1
    window.output_edit.setText(str(tmp_path / "plans"))
    window._update_buttons()
    window.scan_button.click()
    wait_for_job(app, window)
    assert window.store is not None
    assert window.store.unresolved() == 1
    window.table.selectRow(0)
    window.video_edit.setText("https://music.youtube.com/watch?v=abcdefghijk")
    window.use_button.click()
    assert window.store.unresolved() == 0
    auth = tmp_path / "browser.json"
    auth.write_text("{}", encoding="utf-8")
    window.auth_edit.setText(str(auth))
    window.transfer_button.click()
    wait_for_job(app, window)
    assert fake.items == ["abcdefghijk"]
    assert "Transfer finished" in window.log.toPlainText()
    window.close()


def test_scan_only_checked_playlists(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    archive_path = tmp_path / "Export_All.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("Morning.csv", "Track Name,Artist Name(s)\nFirst,Artist\n")
        archive.writestr("Road_Trip.csv", "Track Name,Artist Name(s)\nSecond,Artist\n")
    fake = FakeMusic()
    monkeypatch.setattr("spot2ytmusic.gui._client", lambda auth=None, request_timeout=None: fake)
    monkeypatch.setattr(
        "spot2ytmusic.gui.QFileDialog.getOpenFileNames",
        lambda *args: ([str(archive_path)], ""),
    )
    window = MainWindow()
    window.import_button.click()
    wait_for_job(app, window)
    assert window.playlist_list.count() == 2
    window.select_none_button.click()
    assert not window.scan_button.isEnabled()
    window.select_all_button.click()
    assert window.scan_button.isEnabled()
    window.playlist_list.item(0).setCheckState(Qt.Unchecked)
    window.output_edit.setText(str(tmp_path / "plans"))
    window.scan_button.click()
    wait_for_job(app, window)
    assert window.store.playlists == ["Road Trip"]
    assert len(window.store.plan["entries"]) == 1
    assert window._selected_playlists() == ["Road Trip"]
    window.close()


def test_scan_client_limits_each_request_to_ten_seconds():
    client = _client(request_timeout=10)
    assert client._session.request.keywords["timeout"] == 10
    client._session.close()


def test_transfer_selected_does_not_require_review_of_other_playlists(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    fake = FakeMusic()
    monkeypatch.setattr("spot2ytmusic.gui._client", lambda auth=None, request_timeout=None: fake)
    window = MainWindow()
    window.tracks = [Track("Road Trip", 1, "First", "Artist"), Track("Morning", 1, "Second", "Artist")]
    window._populate_playlists(Counter(track.collection for track in window.tracks))
    window.output_edit.setText(str(tmp_path))
    window.scan_button.click()
    wait_for_job(app, window)
    assert window.store.unresolved() == 2
    window.playlist_list.item(1).setCheckState(Qt.Unchecked)
    window.playlist_combo.setCurrentText("Road Trip")
    window.table.selectRow(0)
    window.video_edit.setText("abcdefghijk")
    window.use_button.click()
    assert window.transfer_button.isEnabled()
    assert "Selected: 1 ready, 0 to review" in window.count_label.text()
    auth = tmp_path / "browser.json"
    auth.write_text("{}", encoding="utf-8")
    window.auth_edit.setText(str(auth))
    window.transfer_button.click()
    wait_for_job(app, window)
    assert fake.items == ["abcdefghijk"]
    assert "Transfer finished: 1 playlists" in window.log.toPlainText()
    window.close()


def test_stop_scan_prevents_a_second_request(tmp_path: Path, monkeypatch):
    class SlowMusic(FakeMusic):
        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()
            self.calls = 0

        def search(self, query, filter, limit):
            self.calls += 1
            self.started.set()
            assert self.release.wait(5)
            return []

    app = QApplication.instance() or QApplication([])
    fake = SlowMusic()
    monkeypatch.setattr("spot2ytmusic.gui._client", lambda auth=None, request_timeout=None: fake)
    window = MainWindow()
    window.tracks = [Track("Road Trip", 1, "First", "Artist")]
    window._populate_playlists(Counter(track.collection for track in window.tracks))
    window.output_edit.setText(str(tmp_path))
    window.scan_button.click()
    deadline = time.monotonic() + 5
    while not fake.started.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert fake.started.is_set()
    assert window.stop_scan_button.isEnabled()
    window.stop_scan_button.click()
    assert window.stop_scan_button.text() == "Stopping..."
    fake.release.set()
    wait_for_job(app, window)
    assert fake.calls == 1
    assert "Scan stopped" in window.log.toPlainText()
    assert not window.stop_button.isEnabled()
    assert window.store is None
    window.close()


def test_browser_headers_create_local_auth_without_terminal(tmp_path: Path):
    destination = tmp_path / "auth" / "browser.json"
    with pytest.raises(ValueError, match="Paste"):
        save_browser_auth("", destination)
    assert not destination.exists()
    save_browser_auth("Cookie: test_cookie\nx-goog-authuser: 0", destination)
    assert destination.exists()
    assert "test_cookie" in destination.read_text(encoding="utf-8")
