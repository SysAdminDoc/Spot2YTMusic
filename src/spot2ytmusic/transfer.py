"""Apply a reviewed plan with remote-prefix checks after every batch."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class ReviewError(ValueError):
    pass


class RemoteStateError(RuntimeError):
    pass


class TransferCancelled(RuntimeError):
    """Raised after the last verified batch when a user stops a transfer."""


def state_path_for(plan_path: Path, playlist: str) -> Path:
    digest = hashlib.sha256(playlist.encode("utf-8")).hexdigest()[:8]
    return plan_path.with_name(f"{plan_path.stem}.{digest}.state.json")


def reviewed_video_ids(plan: dict, review_path: Path, playlist: str) -> tuple[list[str], int]:
    entries = [item for item in plan["entries"] if item["track"]["collection"] == playlist]
    if not entries:
        raise ReviewError(f"No tracks for playlist: {playlist}")
    entries.sort(key=lambda item: item["track"]["position"])
    with review_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    by_key = {row.get("Key", ""): row for row in rows}
    if len(by_key) != len(rows):
        raise ReviewError("The review CSV has duplicate or blank keys")
    selected: list[str] = []
    skipped = 0
    for item in entries:
        key = item["track"]["key"]
        if key not in by_key:
            raise ReviewError(f"Review CSV is missing {playlist} #{item['track']['position']}")
        row = by_key[key]
        decision = (row.get("Decision") or "").strip().casefold()
        if decision == "skip":
            skipped += 1
            continue
        if decision != "use":
            raise ReviewError(f"Review {playlist} #{item['track']['position']}: choose use or skip")
        video_id = (row.get("Chosen video ID") or "").strip()
        if not VIDEO_ID.fullmatch(video_id):
            raise ReviewError(f"Review {playlist} #{item['track']['position']}: invalid YouTube video ID")
        selected.append(video_id)
    return selected, skipped


def _save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def _remote_ids(client: object, playlist_id: str) -> list[str]:
    try:
        details = client.get_playlist(playlist_id, limit=None)
    except KeyError as exc:
        # ytmusicapi 1.12.3 cannot parse a newly created empty playlist.
        entries = client.get_library_playlists(limit=None)
        empty = any(
            item.get("playlistId") == playlist_id and str(item.get("count")).strip() == "0"
            for item in entries
        )
        if empty:
            return []
        raise RemoteStateError("YouTube Music did not return playlist contents") from exc
    if not isinstance(details, dict) or not isinstance(details.get("tracks"), list):
        raise RemoteStateError("YouTube Music did not return the full playlist")
    ids = [track.get("videoId") for track in details["tracks"]]
    if any(not video_id for video_id in ids):
        raise RemoteStateError("Playlist includes an item without a video ID")
    return ids


def _checked_prefix(client: object, playlist_id: str, expected: list[str], minimum: int = 0) -> int:
    for attempt in range(3):
        remote = _remote_ids(client, playlist_id)
        if len(remote) > len(expected) or remote != expected[: len(remote)]:
            raise RemoteStateError(
                "YouTube Music playlist differs from the reviewed order. No further songs were added."
            )
        if len(remote) >= minimum:
            return len(remote)
        if attempt < 2:
            time.sleep(1 + attempt)
    raise RemoteStateError("Added songs are not visible in YouTube Music yet. Rerun after they appear.")


def apply_playlist(
    client: object,
    playlist: str,
    video_ids: list[str],
    state_path: Path,
    playlist_id: str | None = None,
    batch_size: int = 20,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    if not video_ids:
        raise ReviewError("No reviewed songs to transfer")
    if not 1 <= batch_size <= 50:
        raise ValueError("Batch size must be 1 to 50")
    fingerprint = hashlib.sha256(json.dumps([playlist, video_ids]).encode("utf-8")).hexdigest()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("fingerprint") != fingerprint or state.get("playlist") != playlist:
            raise RemoteStateError("Reviewed song list changed since transfer started. Use a new state file.")
        if playlist_id and state["playlist_id"] != playlist_id:
            raise RemoteStateError("State file belongs to a different YouTube Music playlist")
        playlist_id = state["playlist_id"]
    else:
        if playlist_id:
            if _remote_ids(client, playlist_id):
                raise RemoteStateError("The chosen destination is not empty. Supply a new empty playlist.")
        else:
            existing = [
                item for item in client.get_library_playlists(limit=None) if item.get("title") == playlist
            ]
            if existing:
                raise RemoteStateError(
                    f"A playlist named {playlist!r} already exists. Choose an empty playlist with --playlist-id."
                )
            playlist_id = client.create_playlist(
                playlist, "Transferred from Spotify", privacy_status="PRIVATE"
            )
            if not isinstance(playlist_id, str) or not playlist_id:
                raise RemoteStateError(f"Could not create the destination playlist: {playlist_id}")
        state = {
            "playlist": playlist,
            "playlist_id": playlist_id,
            "fingerprint": fingerprint,
            "verified_count": 0,
        }
        _save_state(state_path, state)
    position = _checked_prefix(client, playlist_id, video_ids)
    if position < state["verified_count"]:
        raise RemoteStateError("Previously verified songs are missing from the destination playlist")
    state["verified_count"] = position
    _save_state(state_path, state)
    if progress:
        progress(position, len(video_ids))
    while position < len(video_ids):
        if cancelled and cancelled():
            raise TransferCancelled(f"Transfer stopped after {position} verified songs. It can resume.")
        batch = video_ids[position : position + batch_size]
        try:
            client.add_playlist_items(playlist_id, videoIds=batch, duplicates=True)
        except Exception:
            # A request can succeed remotely and fail before its reply reaches us.
            recovered = _checked_prefix(client, playlist_id, video_ids)
            if recovered <= position:
                raise
            position = recovered
        else:
            position = _checked_prefix(client, playlist_id, video_ids, minimum=position + len(batch))
        state["verified_count"] = position
        _save_state(state_path, state)
        if progress:
            progress(position, len(video_ids))
        else:
            print(f"{playlist}: verified {position}/{len(video_ids)} songs", flush=True)
    return playlist_id
