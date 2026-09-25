"""Save reviewed YouTube recordings as tagged MP3 playlist folders."""

from __future__ import annotations

import hashlib
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .review_store import ReviewStore
from .transfer import ReviewError

INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAME = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


class DownloadCancelled(RuntimeError):
    """The user stopped a download; completed files remain usable."""


@dataclass(frozen=True)
class DownloadTools:
    yt_dlp: str
    ffmpeg: str
    ffprobe: str
    js_runtime: str


@dataclass(frozen=True)
class DownloadTrack:
    playlist: str
    position: int
    title: str
    artist: str
    album: str
    duration_seconds: int | None
    video_id: str
    key: str


@dataclass
class DownloadReport:
    total: int = 0
    saved: int = 0
    reused: int = 0
    skipped: int = 0
    failures: list[str] = field(default_factory=list)
    folders: list[Path] = field(default_factory=list)


def safe_name(value: str, limit: int = 90) -> str:
    clean = " ".join(INVALID_NAME.sub(" ", value).split()).strip(" .")[:limit].rstrip(" .")
    if not clean:
        clean = "Untitled"
    if RESERVED_NAME.match(clean):
        clean = "_" + clean
    return clean


def selected_tracks(store: ReviewStore, playlists: Sequence[str]) -> tuple[dict[str, list[DownloadTrack]], int]:
    if not playlists or len(set(playlists)) != len(playlists):
        raise ReviewError("Choose one or more playlists from the open plan")
    missing = set(playlists) - set(store.playlists)
    if missing:
        raise ReviewError("Playlist not found in plan: " + ", ".join(sorted(missing)))
    chosen: dict[str, list[DownloadTrack]] = {name: [] for name in playlists}
    skipped = 0
    for entry in store.plan["entries"]:
        track = entry["track"]
        name = track["collection"]
        if name not in chosen:
            continue
        row = store.by_key[track["key"]]
        decision = (row["Decision"] or "").strip().casefold()
        if decision == "skip":
            skipped += 1
            continue
        if not store.is_resolved(row):
            raise ReviewError(f"Review {name} #{track['position']} before downloading")
        chosen[name].append(
            DownloadTrack(
                name, int(track["position"]), track["title"], track["artist"],
                track.get("album") or "", track.get("duration_seconds"),
                row["Chosen video ID"].strip(), track["key"],
            )
        )
    for tracks in chosen.values():
        tracks.sort(key=lambda item: item.position)
    return chosen, skipped


def _find_tool(name: str) -> str | None:
    suffix = ".exe" if os.name == "nt" else ""
    local = Path(sys.executable).resolve().parent / (name + suffix)
    if local.is_file():
        return str(local)
    return shutil.which(name)


def find_tools() -> DownloadTools:
    names = {name: _find_tool(name) for name in ("yt-dlp", "ffmpeg", "ffprobe")}
    missing = [name for name, path in names.items() if not path]
    if missing:
        raise RuntimeError(
            "Install " + ", ".join(missing) + " and make them available on PATH or beside the app. "
            "See the Download MP3s section in the README."
        )
    deno = _find_tool("deno")
    node = _find_tool("node")
    runtime = f"deno:{deno}" if deno else f"node:{node}" if node else ""
    if not runtime:
        raise RuntimeError("Install Deno or Node.js for yt-dlp's YouTube support, then try again")
    return DownloadTools(names["yt-dlp"], names["ffmpeg"], names["ffprobe"], runtime)


def _valid_mp3(path: Path, tools: DownloadTools) -> bool:
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        return False
    result = subprocess.run(
        [tools.ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    return result.returncode == 0 and result.stdout.strip() == "mp3"


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_download(args: list[str], cancelled: Callable[[], bool]) -> None:
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(
        args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, **flags,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.strip())
        lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    recent: list[str] = []
    try:
        while True:
            if cancelled():
                raise DownloadCancelled("Download stopped. Completed MP3s remain in the playlist folders.")
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is not None and not reader.is_alive():
                    break
                continue
            if line is None:
                break
            if line:
                recent.append(line)
                recent = recent[-8:]
        code = process.wait(timeout=5)
        if code:
            error = next((line for line in reversed(recent) if "ERROR:" in line), None)
            raise RuntimeError("yt-dlp failed: " + (error or (recent[-1] if recent else f"exit code {code}")))
    finally:
        _stop_process(process)
        reader.join(timeout=2)


def _download_video(video_id: str, cache: Path, tools: DownloadTools, cancelled: Callable[[], bool]) -> Path:
    target = cache / f"{video_id}.mp3"
    if _valid_mp3(target, tools):
        return target
    target.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=cache) as directory:
        work = Path(directory)
        command = [
            tools.yt_dlp, "--ignore-config", "--no-plugin-dirs", "--no-playlist",
            "--no-colors", "--newline", "--retries", "3", "--fragment-retries", "3",
            "--ffmpeg-location", str(Path(tools.ffmpeg).parent),
            "-f", "bestaudio/best", "--extract-audio", "--audio-format", "mp3",
            "--audio-quality", "0", "-o", str(work / "audio.%(ext)s"),
        ]
        command.extend(("--js-runtimes", tools.js_runtime))
        command.append(f"https://www.youtube.com/watch?v={video_id}")
        _run_download(command, cancelled)
        result = work / "audio.mp3"
        if not _valid_mp3(result, tools):
            raise RuntimeError("yt-dlp did not produce a valid MP3")
        result.replace(target)
    return target


def _tag_copy(source: Path, target: Path, track: DownloadTrack, tools: DownloadTools) -> None:
    staged = target.with_name(target.name + ".part.mp3")
    staged.unlink(missing_ok=True)
    command = [
        tools.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source), "-map", "0:a:0", "-c:a", "copy", "-id3v2_version", "3",
        "-metadata", f"title={track.title}", "-metadata", f"artist={track.artist}",
        "-metadata", f"album={track.album}", "-metadata", f"track={track.position}", str(staged),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        if result.returncode or not _valid_mp3(staged, tools):
            raise RuntimeError("Could not tag MP3: " + (result.stderr.strip()[-300:] or "invalid output"))
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)


def _playlist_folder(root: Path, name: str) -> Path:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    folder = root / f"{safe_name(name, 75)} [{digest}]"
    if folder.is_symlink():
        raise ValueError(f"Playlist folder is a link: {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Playlist folder escaped the output directory: {folder}")
    return folder


def _track_filename(track: DownloadTrack) -> str:
    label = safe_name(f"{track.artist} - {track.title}", 80)
    return f"{track.position:04d} - {label} [{track.key[:8]}].mp3"


def _write_playlist(folder: Path, tracks: list[tuple[DownloadTrack, Path]]) -> None:
    lines = ["#EXTM3U"]
    for track, path in tracks:
        artist = " ".join(track.artist.split())
        title = " ".join(track.title.split())
        lines.append(f"#EXTINF:{track.duration_seconds or -1},{artist} - {title}")
        lines.append(path.name)
    temporary = folder / "playlist.m3u8.tmp"
    temporary.unlink(missing_ok=True)
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(folder / "playlist.m3u8")


def download_playlists(
    store: ReviewStore,
    playlists: Sequence[str],
    output: Path,
    progress: Callable[[int, int, str], None] | None = None,
    note: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    tools: DownloadTools | None = None,
) -> DownloadReport:
    chosen, skipped = selected_tracks(store, playlists)
    tools = tools or find_tools()
    cancelled = cancelled or (lambda: False)
    root = output.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    cache = root / ".spot2ytmusic-cache"
    if cache.is_symlink():
        raise ValueError(f"Download cache is a link: {cache}")
    cache.mkdir(exist_ok=True)
    report = DownloadReport(total=sum(map(len, chosen.values())), skipped=skipped)
    done = 0
    for playlist, tracks in chosen.items():
        folder = _playlist_folder(root, playlist)
        report.folders.append(folder)
        completed: list[tuple[DownloadTrack, Path]] = []
        if note:
            note(f"{playlist}: saving {len(tracks)} songs to {folder}")
        try:
            for track in tracks:
                if cancelled():
                    raise DownloadCancelled("Download stopped. Completed MP3s remain in the playlist folders.")
                target = folder / _track_filename(track)
                try:
                    if target.is_symlink():
                        raise ValueError(f"Track destination is a link: {target}")
                    if _valid_mp3(target, tools):
                        report.reused += 1
                    else:
                        target.unlink(missing_ok=True)
                        if shutil.disk_usage(root).free < 100 * 1024 * 1024:
                            raise RuntimeError("Less than 100 MB free in the download destination")
                        media = _download_video(track.video_id, cache, tools, cancelled)
                        if cancelled():
                            raise DownloadCancelled("Download stopped. Completed MP3s remain in the playlist folders.")
                        _tag_copy(media, target, track, tools)
                        report.saved += 1
                    completed.append((track, target))
                except DownloadCancelled:
                    raise
                except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                    failure = f"{playlist} #{track.position} {track.title}: {exc}"
                    report.failures.append(failure)
                    if note:
                        note(failure)
                done += 1
                if progress:
                    progress(done, report.total, f"{playlist}: {done}/{report.total} songs checked")
        finally:
            _write_playlist(folder, completed)
    return report
