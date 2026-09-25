import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from spot2ytmusic import download
from spot2ytmusic.cli import main
from spot2ytmusic.models import PlanEntry, Track
from spot2ytmusic.planner import save_plan, save_review
from spot2ytmusic.review_store import ReviewStore


def make_store(tmp_path: Path) -> ReviewStore:
    entries = [
        PlanEntry(Track("Road/Trip", 1, "First Song", "Artist", "Album", 15), "auto", "abcdefghijk"),
        PlanEntry(Track("Road/Trip", 2, "First Song", "Artist", "Album", 15), "auto", "abcdefghijk"),
        PlanEntry(Track("Other", 1, "Second Song", "Singer", "Record", 20), "auto", "lmnopqrstuv"),
    ]
    plan = {"schema": 1, "entries": [entry.to_dict() for entry in entries]}
    path = tmp_path / "plan.json"
    save_plan(path, plan)
    save_review(path.with_suffix(".review.csv"), plan)
    return ReviewStore(path)


def media_tools(tmp_path: Path, monkeypatch) -> tuple[download.DownloadTools, list[str]]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg and ffprobe are needed for MP3 verification")
    fixture = tmp_path / "fixture.mp3"
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
         "-q:a", "5", str(fixture)], check=True, capture_output=True,
    )
    calls = []

    def fake_yt_dlp(args, cancelled):
        calls.append(args[-1])
        assert args[-1].startswith("https://www.youtube.com/watch?v=")
        shutil.copy2(fixture, Path(args[args.index("-o") + 1].replace("%(ext)s", "mp3")))

    monkeypatch.setattr(download, "_run_download", fake_yt_dlp)
    return download.DownloadTools("yt-dlp", ffmpeg, ffprobe, "deno"), calls


def test_download_reconstructs_order_tags_and_resumes(tmp_path: Path, monkeypatch):
    store = make_store(tmp_path)
    tools, calls = media_tools(tmp_path, monkeypatch)
    output = tmp_path / "MP3s"
    report = download.download_playlists(store, ["Road/Trip", "Other"], output, tools=tools)
    assert (report.total, report.saved, report.reused, report.skipped, report.failures) == (3, 3, 0, 0, [])
    assert len(calls) == 2
    first = report.folders[0]
    tracks = sorted(first.glob("*.mp3"))
    assert [path.name[:4] for path in tracks] == ["0001", "0002"]
    playlist = (first / "playlist.m3u8").read_text(encoding="utf-8")
    assert playlist.index(tracks[0].name) < playlist.index(tracks[1].name)
    assert playlist.count("#EXTINF:") == 2
    assert first.resolve().is_relative_to(output.resolve())
    probe = subprocess.run(
        [tools.ffprobe, "-v", "error", "-show_entries", "format_tags=title,artist,album,track",
         "-of", "json", str(tracks[0])], capture_output=True, text=True, check=True,
    )
    tags = json.loads(probe.stdout)["format"]["tags"]
    assert tags["title"] == "First Song"
    assert tags["artist"] == "Artist"
    assert tags["album"] == "Album"
    assert tags["track"] == "1"
    again = download.download_playlists(store, ["Road/Trip", "Other"], output, tools=tools)
    assert (again.saved, again.reused, len(calls)) == (0, 3, 2)


def test_stop_keeps_finished_tracks_and_playlist_can_resume(tmp_path: Path, monkeypatch):
    store = make_store(tmp_path)
    tools, calls = media_tools(tmp_path, monkeypatch)
    stopped = False

    def progress(done, total, message):
        nonlocal stopped
        stopped = done == 1

    with pytest.raises(download.DownloadCancelled, match="Completed MP3s"):
        download.download_playlists(
            store, ["Road/Trip"], tmp_path / "MP3s", tools=tools,
            progress=progress, cancelled=lambda: stopped,
        )
    folder = next((tmp_path / "MP3s").glob("Road Trip*"))
    assert len(list(folder.glob("*.mp3"))) == 1
    assert (folder / "playlist.m3u8").read_text().count("#EXTINF:") == 1
    resumed = download.download_playlists(store, ["Road/Trip"], tmp_path / "MP3s", tools=tools)
    assert (resumed.saved, resumed.reused, len(calls)) == (1, 1, 1)
    assert (folder / "playlist.m3u8").read_text().count("#EXTINF:") == 2


def test_review_required_and_names_are_safe(tmp_path: Path):
    store = make_store(tmp_path)
    key = store.plan["entries"][0]["track"]["key"]
    store.decide(key, "skip")
    chosen, skipped = download.selected_tracks(store, ["Road/Trip"])
    assert skipped == 1 and len(chosen["Road/Trip"]) == 1
    store.by_key[store.plan["entries"][1]["track"]["key"]]["Decision"] = ""
    with pytest.raises(ValueError, match="Review"):
        download.selected_tracks(store, ["Road/Trip"])
    with pytest.raises(ValueError, match="not found"):
        download.selected_tracks(store, ["Missing"])
    assert download.safe_name("../CON:<bad>|name? ") == "CON bad name"
    assert download.safe_name("NUL") == "_NUL"


def test_cli_download_does_not_need_account_auth(tmp_path: Path, monkeypatch, capsys):
    store = make_store(tmp_path)
    tools, calls = media_tools(tmp_path, monkeypatch)
    monkeypatch.setattr(download, "find_tools", lambda: tools)
    output = tmp_path / "Music"
    result = main(["download", str(store.plan_path), "--playlist", "Other", "--output", str(output)])
    assert result == 0
    assert len(calls) == 1
    assert next(output.glob("Other*/*.m3u8")).read_text().count("#EXTINF:") == 1
    assert "1 saved" in capsys.readouterr().out


def test_unavailable_video_does_not_block_other_playlists(tmp_path: Path, monkeypatch):
    store = make_store(tmp_path)
    tools, calls = media_tools(tmp_path, monkeypatch)
    fake_yt_dlp = download._run_download

    def fail_second(args, cancelled):
        if args[-1].endswith("lmnopqrstuv"):
            raise RuntimeError("Video unavailable")
        fake_yt_dlp(args, cancelled)

    monkeypatch.setattr(download, "_run_download", fail_second)
    output = tmp_path / "MP3s"
    report = download.download_playlists(store, ["Road/Trip", "Other"], output, tools=tools)
    assert (report.saved, len(report.failures)) == (2, 1)
    assert "Video unavailable" in report.failures[0]
    assert (report.folders[1] / "playlist.m3u8").read_text().count("#EXTINF:") == 0
    monkeypatch.setattr(download, "_run_download", fake_yt_dlp)
    retry = download.download_playlists(store, ["Road/Trip", "Other"], output, tools=tools)
    assert (retry.saved, retry.reused, retry.failures, len(calls)) == (1, 2, [], 2)


def test_stop_terminates_active_subprocess():
    stopped = threading.Event()
    timer = threading.Timer(0.2, stopped.set)
    timer.start()
    try:
        with pytest.raises(download.DownloadCancelled, match="stopped"):
            download._run_download(
                [sys.executable, "-u", "-c", "import time; time.sleep(10)"], stopped.is_set
            )
    finally:
        timer.cancel()
