"""Command line entry point for a reviewed music migration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from functools import partial
from pathlib import Path

from requests import Session

from . import __version__
from .csvio import read_sources
from .download import download_playlists
from .planner import save_plan, save_review, scan
from .review_store import ReviewStore
from .transfer import apply_playlist, reviewed_video_ids, state_path_for


def _client(auth: Path | None = None, request_timeout: float | None = None):
    from ytmusicapi import OAuthCredentials, YTMusic

    session = None
    if request_timeout is not None:
        session = Session()
        session.request = partial(session.request, timeout=request_timeout)
    if auth is None:
        return YTMusic(requests_session=session)
    if not auth.is_file():
        raise ValueError(f"Authentication file not found: {auth}")
    client_id = os.environ.get("YTMUSIC_CLIENT_ID")
    client_secret = os.environ.get("YTMUSIC_CLIENT_SECRET")
    if auth.name.casefold().startswith("oauth"):
        if not client_id or not client_secret:
            raise ValueError("OAuth needs YTMUSIC_CLIENT_ID and YTMUSIC_CLIENT_SECRET environment variables")
        return YTMusic(
            str(auth), oauth_credentials=OAuthCredentials(client_id, client_secret), requests_session=session
        )
    return YTMusic(str(auth), requests_session=session)


def _select_tracks(paths: list[Path], playlists: list[str] | None) -> list:
    tracks = read_sources(paths)
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
        prog="spot2ytmusic", description="Review Spotify CSV matches before adding them to YouTube Music"
    )
    parser.add_argument("--version", action="version", version=f"Spot2YTMusic v{__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Show playlists and song counts in CSVs or ZIPs")
    inspect.add_argument("sources", nargs="+", type=Path)
    scan_command = commands.add_parser("scan", help="Search YouTube Music and create a review CSV")
    scan_command.add_argument("sources", nargs="+", type=Path)
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
    download_command = commands.add_parser("download", help="Save reviewed playlists as MP3 folders and M3U8 files")
    download_command.add_argument("plan", type=Path)
    download_command.add_argument("--playlist", action="append", dest="playlists", required=True)
    download_command.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            counts = Counter(track.collection for track in read_sources(args.sources))
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
            tracks = _select_tracks(args.sources, args.playlists)
            plan = scan(
                _client(),
                tracks,
                args.cache or args.plan.with_name("spot2ytmusic.cache.sqlite3"),
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
                args.state or state_path_for(args.plan, args.playlist),
                args.playlist_id,
                args.batch_size,
            )
            print(f"Done: https://music.youtube.com/playlist?list={playlist_id}")
            return 0
        if args.command == "download":
            store = ReviewStore(args.plan)
            report = download_playlists(
                store, args.playlists, args.output,
                progress=lambda done, total, message: print(message, flush=True),
                note=lambda message: print(message, flush=True),
            )
            print(
                f"Done: {report.saved} saved, {report.reused} already present, "
                f"{report.skipped} skipped, {len(report.failures)} failed"
            )
            return 1 if report.failures else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
