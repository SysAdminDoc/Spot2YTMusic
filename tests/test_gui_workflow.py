import os
import time
from pathlib import Path
from zipfile import ZipFile

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from spot2ytmusic.gui import MainWindow, save_browser_auth


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
    monkeypatch.setattr("spot2ytmusic.gui._client", lambda auth=None: fake)
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


def test_browser_headers_create_local_auth_without_terminal(tmp_path: Path):
    destination = tmp_path / "auth" / "browser.json"
    with pytest.raises(ValueError, match="Paste"):
        save_browser_auth("", destination)
    assert not destination.exists()
    save_browser_auth("Cookie: test_cookie\nx-goog-authuser: 0", destination)
    assert destination.exists()
    assert "test_cookie" in destination.read_text(encoding="utf-8")
