"""Search, cache, and export a reviewable transfer plan."""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from requests.exceptions import RequestException
from ytmusicapi.exceptions import YTMusicServerError

from . import __version__
from .matching import rank_results
from .models import PlanEntry, Track

SCHEMA_VERSION = 1


class ScanCancelled(RuntimeError):
    """Raised when a user stops a scan between tracks."""


class SearchCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS searches (query TEXT NOT NULL, filter TEXT NOT NULL, "
            "results TEXT NOT NULL, PRIMARY KEY (query, filter))"
        )
        self.connection.commit()

    def get(self, query: str, filter_name: str) -> list[dict] | None:
        row = self.connection.execute(
            "SELECT results FROM searches WHERE query = ? AND filter = ?", (query, filter_name)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, query: str, filter_name: str, results: list[dict]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO searches VALUES (?, ?, ?)",
            (query, filter_name, json.dumps(results, ensure_ascii=False)),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def _search_with_retry(client: object, query: str, filter_name: str) -> list[dict]:
    waits = (3, 10, 30)
    for attempt in range(4):
        try:
            return client.search(query, filter=filter_name, limit=10)
        except (RequestException, YTMusicServerError) as exc:
            temporary = isinstance(exc, RequestException) or any(
                code in str(exc) for code in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")
            )
            if not temporary or attempt == len(waits):
                raise
            if sys.stderr is not None:
                print(
                    f"Search paused after a temporary YouTube Music error. Retrying in {waits[attempt]}s.",
                    file=sys.stderr,
                    flush=True,
                )
            time.sleep(waits[attempt])
    raise RuntimeError("Search retries exhausted")


def search_track(client: object, track: Track, cache: SearchCache, delay: float) -> PlanEntry:
    if track.source_type.casefold() == "unavailable" or track.title == "[Unavailable track]":
        return PlanEntry(track, "skip", note="Source track is unavailable on Spotify")
    if not track.title or not track.artist:
        return PlanEntry(track, "review", note="Source title or artist is missing")
    query = f"{track.title} {track.artist.split(';')[0]}"
    combined: list[dict] = []
    for filter_name in ("songs", "videos"):
        results = cache.get(query, filter_name)
        if results is None:
            results = _search_with_retry(client, query, filter_name)
            cache.put(query, filter_name, results)
            if delay:
                time.sleep(delay)
        combined.extend(results)
        status, candidates = rank_results(track, combined)
        if status == "auto":
            break
    unique = {result.get("videoId"): result for result in combined if result.get("videoId")}
    status, candidates = rank_results(track, list(unique.values()))
    return PlanEntry(
        track,
        status,
        candidates[0].video_id if candidates else "",
        candidates,
        "No YouTube Music match" if not candidates else "",
    )


def scan(
    client: object,
    tracks: list[Track],
    cache_path: Path,
    delay: float = 0.25,
    progress: Callable[[int, int, PlanEntry], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    cache = SearchCache(cache_path)
    entries: list[PlanEntry] = []
    try:
        for index, track in enumerate(tracks, 1):
            if cancelled and cancelled():
                raise ScanCancelled("Scan stopped. Search results already found remain in the cache.")
            entry = search_track(client, track, cache, delay)
            entries.append(entry)
            if progress:
                progress(index, len(tracks), entry)
            elif index == 1 or index % 25 == 0 or index == len(tracks) or entry.status != "auto":
                print(
                    f"{index}/{len(tracks)}  {track.collection} #{track.position}: {entry.status}  {track.title}",
                    flush=True,
                )
    finally:
        cache.close()
    return {
        "schema": SCHEMA_VERSION,
        "tool_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "entries": [entry.to_dict() for entry in entries],
    }


def save_plan(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def save_review(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.writer(destination)
        writer.writerow(
            [
                "Key",
                "Playlist",
                "Position",
                "Song",
                "Artist",
                "Album",
                "Spotify duration",
                "Source type",
                "Decision",
                "Chosen video ID",
                "Match score",
                "Search URL",
                "Candidate 1",
                "Candidate 2",
                "Candidate 3",
                "Candidate 4",
                "Candidate 5",
                "Note",
            ]
        )
        for item in plan["entries"]:
            source = item["track"]
            candidates = item["candidates"]
            displays = [
                f"{value['title']} | {value['artist']} | {value['duration_seconds'] or '?'}s | "
                f"{value['score']:.3f} | https://music.youtube.com/watch?v={value['video_id']}"
                for value in candidates[:5]
            ]
            writer.writerow(
                [
                    source["key"],
                    source["collection"],
                    source["position"],
                    source["title"],
                    source["artist"],
                    source["album"],
                    source["duration_seconds"] or "",
                    source["source_type"],
                    "use" if item["status"] == "auto" else "skip" if item["status"] == "skip" else "",
                    item["selected_video_id"],
                    candidates[0]["score"] if candidates else "",
                    "https://music.youtube.com/search?q="
                    + quote_plus(source["title"] + " " + source["artist"]),
                    *(displays + [""] * (5 - len(displays))),
                    item["note"],
                ]
            )
    temporary.replace(path)
