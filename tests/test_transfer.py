import hashlib
import json
from pathlib import Path

import pytest

from playlist_bridge.transfer import RemoteStateError, apply_playlist


class MusicClient:
    def __init__(self):
        self.items = []
        self.add_calls = 0
        self.fail_after_add_once = False

    def get_library_playlists(self, limit=None):
        return []

    def create_playlist(self, name, description, privacy_status):
        assert privacy_status == "PRIVATE"
        return "PLexample"

    def get_playlist(self, playlist_id, limit=None):
        return {"tracks": [{"videoId": item} for item in self.items]}

    def add_playlist_items(self, playlist_id, videoIds, duplicates):
        assert duplicates is True
        self.add_calls += 1
        self.items.extend(videoIds)
        if self.fail_after_add_once:
            self.fail_after_add_once = False
            raise RuntimeError("Response was lost")
        return "STATUS_SUCCEEDED"


def test_transfer_preserves_order_and_duplicates(tmp_path: Path):
    client = MusicClient()
    ids = ["abcdefghijk", "lmnopqrstuv", "abcdefghijk"]
    state = tmp_path / "state.json"
    assert apply_playlist(client, "A", ids, state, batch_size=2) == "PLexample"
    assert client.items == ids
    assert json.loads(state.read_text())["verified_count"] == 3
    assert apply_playlist(client, "A", ids, state, batch_size=2) == "PLexample"
    assert client.add_calls == 2


def test_recovers_a_successful_add_with_lost_reply(tmp_path: Path):
    client = MusicClient()
    client.fail_after_add_once = True
    ids = ["abcdefghijk", "lmnopqrstuv", "mnopqrstuvw"]
    apply_playlist(client, "A", ids, tmp_path / "state.json", batch_size=2)
    assert client.items == ids


def test_stops_if_remote_order_changed(tmp_path: Path):
    client = MusicClient()
    ids = ["abcdefghijk", "lmnopqrstuv"]
    client.items = [ids[1]]
    fingerprint = hashlib.sha256(json.dumps(["A", ids]).encode("utf-8")).hexdigest()
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {"playlist": "A", "playlist_id": "PLexample", "fingerprint": fingerprint, "verified_count": 0}
        ),
        encoding="utf-8",
    )
    with pytest.raises(RemoteStateError, match="differs"):
        apply_playlist(client, "A", ids, state)
    assert client.add_calls == 0


def test_new_empty_playlist_can_be_verified(tmp_path: Path):
    class EmptyPlaylistClient(MusicClient):
        def __init__(self):
            super().__init__()
            self.created = False

        def create_playlist(self, name, description, privacy_status):
            self.created = True
            return super().create_playlist(name, description, privacy_status)

        def get_library_playlists(self, limit=None):
            return (
                [{"playlistId": "PLexample", "title": "A", "count": "0"}]
                if self.created and not self.items
                else []
            )

        def get_playlist(self, playlist_id, limit=None):
            if not self.items:
                raise KeyError("contents")
            return super().get_playlist(playlist_id, limit)

    client = EmptyPlaylistClient()
    ids = ["abcdefghijk", "lmnopqrstuv"]
    assert apply_playlist(client, "A", ids, tmp_path / "state.json") == "PLexample"
    assert client.items == ids
