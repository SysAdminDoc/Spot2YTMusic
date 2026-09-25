"""Read common Spotify exports without needing a Spotify developer account."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import Track

ALIASES = {
    "collection": ("collection", "playlist", "playlist name"),
    "position": ("position", "index", "number"),
    "title": ("song", "title", "track name", "track title", "name"),
    "artist": ("artist", "artists", "artist name", "artist name(s)", "artist(s)"),
    "album": ("album", "album name", "album title"),
    "duration": ("duration", "duration (ms)", "duration ms", "track duration (ms)"),
    "url": ("spotify track", "spotify url", "track url", "url", "uri"),
    "source_type": ("source type", "source_type"),
}


def _header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold().replace("_", " "))


def _find(headers: list[str], field: str) -> str | None:
    lookup = {_header(header): header for header in headers}
    for alias in ALIASES[field]:
        if alias in lookup:
            return lookup[alias]
    return None


def parse_duration(value: str, milliseconds: bool = False) -> int | None:
    value = value.strip()
    if not value:
        return None
    if ":" in value:
        parts = value.split(":")
        if len(parts) not in (2, 3) or any(not part.isdigit() for part in parts):
            raise ValueError(f"Invalid duration: {value}")
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds
    number = float(value)
    if number < 0:
        raise ValueError(f"Invalid duration: {value}")
    return round(number / 1000 if milliseconds else number)


def read_tracks(path: str | Path, playlist: str | None = None) -> list[Track]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        headers = list(reader.fieldnames or [])
        columns = {field: _find(headers, field) for field in ALIASES}
        if not columns["title"] or not columns["artist"]:
            raise ValueError(f"{path}: CSV needs song/title and artist columns")
        default_name = playlist or path.stem.replace("_", " ").replace("-", " ")
        seen: dict[str, set[int]] = {}
        next_position: dict[str, int] = {}
        tracks: list[Track] = []
        for row_number, row in enumerate(reader, 2):
            get = lambda field, current=row: (
                (current.get(columns[field], "") or "").strip() if columns[field] else ""
            )
            title = get("title")
            artist = get("artist")
            if not title and not artist:
                continue
            name = get("collection") or default_name
            number = get("position")
            try:
                position = int(number) if number else next_position.get(name, 0) + 1
                if position < 1 or position in seen.setdefault(name, set()):
                    raise ValueError("positions must be unique positive integers")
                duration_header = columns["duration"] or ""
                duration = parse_duration(get("duration"), "ms" in duration_header.casefold())
            except ValueError as exc:
                raise ValueError(f"{path}, row {row_number}: {exc}") from exc
            seen[name].add(position)
            next_position[name] = position
            tracks.append(
                Track(
                    collection=name,
                    position=position,
                    title=title,
                    artist=artist,
                    album=get("album"),
                    duration_seconds=duration,
                    spotify_url=get("url"),
                    source_type=get("source_type") or "Spotify catalog",
                )
            )
    return sorted(tracks, key=lambda item: (item.collection.casefold(), item.position))
