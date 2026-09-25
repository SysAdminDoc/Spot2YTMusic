"""Read common Spotify exports without needing a Spotify developer account."""

from __future__ import annotations

import csv
import re
from io import TextIOWrapper
from pathlib import Path, PurePosixPath
from typing import TextIO
from zipfile import BadZipFile, ZipFile

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


def _parse_tracks(source: TextIO, default_name: str, label: str) -> list[Track]:
    reader = csv.DictReader(source)
    headers = list(reader.fieldnames or [])
    columns = {field: _find(headers, field) for field in ALIASES}
    if not columns["title"] or not columns["artist"]:
        raise ValueError(f"{label}: CSV needs song/title and artist columns")
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
            raise ValueError(f"{label}, row {row_number}: {exc}") from exc
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


def read_tracks(path: str | Path, playlist: str | None = None) -> list[Track]:
    path = Path(path)
    default_name = playlist or path.stem.replace("_", " ").replace("-", " ")
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return _parse_tracks(source, default_name, str(path))


def read_sources(paths: list[Path]) -> list[Track]:
    """Read CSV files or Exportify ZIPs without extracting the archive."""
    if not paths:
        raise ValueError("Choose at least one CSV or ZIP file")
    tracks: list[Track] = []
    for path in paths:
        if path.suffix.casefold() == ".csv":
            tracks.extend(read_tracks(path))
        elif path.suffix.casefold() == ".zip":
            try:
                with ZipFile(path) as archive:
                    members = sorted(
                        (
                            item
                            for item in archive.infolist()
                            if not item.is_dir()
                            and item.filename.casefold().endswith(".csv")
                            and not item.filename.startswith("__MACOSX/")
                        ),
                        key=lambda item: item.filename.casefold(),
                    )
                    if not members:
                        raise ValueError(f"{path}: ZIP contains no CSV files")
                    for member in members:
                        if member.file_size > 64 * 1024 * 1024:
                            raise ValueError(f"{path}!{member.filename}: CSV is too large")
                        name = PurePosixPath(member.filename).stem.replace("_", " ").replace("-", " ")
                        with (
                            archive.open(member) as raw,
                            TextIOWrapper(raw, encoding="utf-8-sig", newline="") as source,
                        ):
                            tracks.extend(_parse_tracks(source, name, f"{path}!{member.filename}"))
            except BadZipFile as exc:
                raise ValueError(f"{path}: invalid ZIP file") from exc
        else:
            raise ValueError(f"{path}: choose a CSV or ZIP file")
    if not tracks:
        raise ValueError("No songs found in the selected files")
    seen: set[tuple[str, int]] = set()
    for track in tracks:
        key = (track.collection.casefold(), track.position)
        if key in seen:
            raise ValueError(f"Duplicate playlist position: {track.collection} #{track.position}")
        seen.add(key)
    return sorted(tracks, key=lambda item: (item.collection.casefold(), item.position))
