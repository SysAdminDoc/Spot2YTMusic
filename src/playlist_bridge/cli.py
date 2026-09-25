"""Command line entry point for a reviewed music migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .csvio import read_tracks
from .planner import save_plan, save_review, scan
from .transfer import apply_playlist, reviewed_video_ids


def _client(auth: Path | None = None):
    from ytmusicapi import OAuthCredentials, YTMusic

    if auth is None:
        return YTMusic()
    if not auth.is_file():
        raise ValueError(f"Authentication file not found: {auth}")
    client_id = os.environ.get("YTMUSIC_CLIENT_ID")
    client_secret = os.environ.get("YTMUSIC_CLIENT_SECRET")
    if auth.name.casefold().startswith("oauth"):
        if not client_id or not client_secret:
            raise ValueError("OAuth needs YTMUSIC_CLIENT_ID and YTMUSIC_CLIENT_SECRET environment variables")
        return YTMusic(str(auth), oauth_credentials=OAuthCredentials(client_id, client_secret))
    return YTMusic(str(auth))


def _select_tracks(path: Path, playlists: list[str] | None) -> list:
    tracks = read_tracks(path)
    if playlists:
        available = {track.collection for track in tracks}
        missing = set(playlists) - available
        if missing:
            raise ValueError("Playlist not found in CSV: " + ", ".join(sorted(missing)))
        tracks = [track for track in tracks if track.collection in playlists]
    if not tracks:
        raise ValueError("No songs found")
    return tracks


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playlist-bridge", description="Review Spotify CSV matches before adding them to YouTube Music"
    )
    parser.add_argument("--version", action="version", version=f"Playlist Bridge v{__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Show playlists and song counts in a CSV")
    inspect.add_argument("csv", type=Path)
    scan_command = commands.add_parser("scan", help="Search YouTube Music and create a review CSV")
    scan_command.add_argument("csv", type=Path)
    scan_command.add_argument(
        "--playlist", action="append", dest="playlists", help="Include this playlist, repeat for several"
    )
    scan_command.add_argument("--plan", type=Path, required=True)
    scan_command.add_argument("--review", type=Path)
    scan_command.add_argument("--cache", type=Path)
    scan_command.add_argument("--delay", type=float, default=0.25, help="Seconds between uncached searches")
    scan_command.add_argument(
        "--overwrite", action="store_true", help="Replace an existing plan and review CSV"
    )
    apply_command = commands.add_parser("apply", help="Transfer one reviewed playlist")
    apply_command.add_argument("plan", type=Path)
    apply_command.add_argument("--review", type=Path)
    apply_command.add_argument("--playlist", required=True)
    apply_command.add_argument(
        "--auth", type=Path, required=True, help="ytmusicapi browser.json or oauth.json"
    )
    apply_command.add_argument("--state", type=Path)
    apply_command.add_argument("--playlist-id", help="Use an existing empty YouTube Music playlist")
    apply_command.add_argument("--batch-size", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            counts = Counter(track.collection for track in read_tracks(args.csv))
            if not counts:
                raise ValueError("No songs found")
            for name, count in sorted(counts.items()):
                print(f"{name}: {count} songs")
            return 0
        if args.command == "scan":
            if args.delay < 0:
                raise ValueError("Delay must be nonnegative")
            review_path = args.review or args.plan.with_suffix(".review.csv")
            if not args.overwrite and (args.plan.exists() or review_path.exists()):
                raise ValueError("Plan or review file exists. Choose another path or pass --overwrite")
            tracks = _select_tracks(args.csv, args.playlists)
            plan = scan(
                _client(),
                tracks,
                args.cache or args.plan.with_name("playlist-bridge.cache.sqlite3"),
                args.delay,
            )
            save_plan(args.plan, plan)
            save_review(review_path, plan)
            counts = Counter(item["status"] for item in plan["entries"])
            print(f"Saved {args.plan} and {review_path}. Matches: {dict(counts)}")
            return 0
        if args.command == "apply":
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if plan.get("schema") != 1:
                raise ValueError("Unsupported plan format")
            review_path = args.review or args.plan.with_suffix(".review.csv")
            video_ids, skipped = reviewed_video_ids(plan, review_path, args.playlist)
            print(f"Reviewed {args.playlist}: {len(video_ids)} songs to add, {skipped} skipped")
            playlist_id = apply_playlist(
                _client(args.auth),
                args.playlist,
                video_ids,
                args.state
                or args.plan.with_name(
                    args.plan.stem
                    + "."
                    + hashlib.sha256(args.playlist.encode("utf-8")).hexdigest()[:8]
                    + ".state.json"
                ),
                args.playlist_id,
                args.batch_size,
            )
            print(f"Done: https://music.youtube.com/playlist?list={playlist_id}")
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
