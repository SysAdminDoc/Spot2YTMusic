import threading
import time
from pathlib import Path

from ytmusicapi.exceptions import YTMusicServerError

from spot2ytmusic.models import Track
from spot2ytmusic.planner import ScanCancelled, _search_with_retry, save_review, scan
from spot2ytmusic.transfer import ReviewError, reviewed_video_ids


class SearchClient:
    def __init__(self):
        self.calls = 0

    def search(self, query, filter, limit):
        self.calls += 1
        return [
            {
                "videoId": "abcdefghijk",
                "title": "WE ON GO",
                "artists": [{"name": "BIA"}],
                "duration_seconds": 169,
                "resultType": "song",
                "isAvailable": True,
            }
        ]


def test_search_cache_avoids_repeated_requests(tmp_path: Path):
    client = SearchClient()
    track = Track("JogJams", 3, "WE ON GO", "BIA", duration_seconds=168)
    first = scan(client, [track], tmp_path / "cache.sqlite3", delay=0)
    second = scan(client, [track], tmp_path / "cache.sqlite3", delay=0)
    assert client.calls == 1
    assert first["entries"][0]["status"] == "auto"
    assert second["entries"][0]["selected_video_id"] == "abcdefghijk"


def test_review_must_resolve_ambiguous_rows(tmp_path: Path):
    track = Track("A", 1, "Unknown", "Artist")
    plan = {
        "entries": [
            {
                "track": track.to_dict(),
                "status": "review",
                "selected_video_id": "",
                "candidates": [],
                "note": "",
            }
        ]
    }
    review = tmp_path / "review.csv"
    save_review(review, plan)
    try:
        reviewed_video_ids(plan, review, "A")
    except ReviewError as exc:
        assert "choose use or skip" in str(exc)
    else:
        raise AssertionError("An unresolved song was accepted")


def test_transient_search_failure_retries(monkeypatch):
    class RetryClient:
        def __init__(self):
            self.calls = 0

        def search(self, query, filter, limit):
            self.calls += 1
            if self.calls == 1:
                raise YTMusicServerError("Server returned HTTP 429: Too Many Requests")
            return [{"videoId": "abcdefghijk"}]

    monkeypatch.setattr("spot2ytmusic.planner._wait_or_cancel", lambda seconds, cancelled: None)
    client = RetryClient()
    assert _search_with_retry(client, "song artist", "songs") == [{"videoId": "abcdefghijk"}]
    assert client.calls == 2


def test_retry_wait_stops_before_another_search():
    class RateLimitedClient:
        def __init__(self):
            self.calls = 0
            self.started = threading.Event()

        def search(self, query, filter, limit):
            self.calls += 1
            self.started.set()
            raise YTMusicServerError("Server returned HTTP 429: Too Many Requests")

    client = RateLimitedClient()
    stop = threading.Event()
    errors = []
    def run():
        try:
            _search_with_retry(client, "song artist", "songs", stop.is_set)
        except ScanCancelled as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert client.started.wait(1)
    time.sleep(0.05)
    stop.set()
    worker.join(1)
    assert not worker.is_alive()
    assert client.calls == 1
    assert errors and "stopped" in str(errors[0]).casefold()
