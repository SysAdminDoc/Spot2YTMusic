![Spot2YTMusic](docs/hero.svg)

[![Version](https://img.shields.io/badge/version-0.0.3-7659d6)](https://github.com/SysAdminDoc/Spot2YTMusic/releases/tag/v0.0.3) [![License](https://img.shields.io/badge/license-MIT-2680b8)](LICENSE) [![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-285f93)](#)

**Move Spotify playlists to YouTube Music and check the songs before they land.** Spot2YTMusic reads a CSV export, searches YouTube Music, and gives you a review sheet with candidate recordings. You choose what goes in. The transfer keeps the original order and repeated songs, then checks the destination after each batch.

This is a local command line tool. It needs no Spotify developer account because it starts with a CSV. Searching does not require a YouTube Music login; creating playlists does.

## Why use it

- **Review the recordings.** Song titles alone can hide a live take, cover, clean edit, or karaoke version. The review sheet links to candidates and leaves uncertain matches for you to decide.
- **Keep the playlist you made.** Original order and intentional duplicates carry over.
- **Resume with a check.** After an interruption, the tool compares the YouTube Music playlist with the reviewed plan before adding more songs.
- **Keep a local record.** The CSV, review sheet, and search cache stay on your computer. Search queries go to YouTube Music.

## Get a CSV

The file needs a song title and artist column. [Exportify](https://github.com/watsonbox/exportify) is one way to export Spotify playlists to CSV. Spot2YTMusic accepts its `Track Name`, `Artist Name(s)`, and `Track Duration (ms)` columns. A duration helps the matcher distinguish recordings.

You can also make a CSV yourself:

```csv
Collection,Position,Song,Artist,Album,Duration
Road Trip,1,Midnight City,M83,Hurry Up We're Dreaming,4:03
Road Trip,2,Kids,MGMT,Oracular Spectacular,5:02
```

`Album`, `Duration`, `Position`, and `Collection` are optional. With one playlist per file, the filename becomes the playlist name. A `Collection` column lets one file hold several playlists. Spotify's own [Download your data](https://support.spotify.com/us/article/understanding-your-data/) produces JSON, which this version does not read directly.

## Install

Install Python 3.11 or newer. On Windows:

```powershell
git clone https://github.com/SysAdminDoc/Spot2YTMusic.git
cd Spot2YTMusic
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

On macOS or Linux:

```sh
git clone https://github.com/SysAdminDoc/Spot2YTMusic.git
cd Spot2YTMusic
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Use `.venv/bin/spot2ytmusic` for the commands below. The [latest release](https://github.com/SysAdminDoc/Spot2YTMusic/releases/latest) also has an installable wheel.

## Search, review, transfer

Inspect the file, then search. This example assumes the file is named `Road_Trip.csv`:

```powershell
.\.venv\Scripts\spot2ytmusic inspect Road_Trip.csv
.\.venv\Scripts\spot2ytmusic scan Road_Trip.csv --plan plans\road-trip.json
```

Scanning writes `plans\road-trip.review.csv` and a JSON plan. It makes no changes to your YouTube Music account. Open the review CSV and check the candidate links. Strong matches are marked `use`; uncertain rows have a blank `Decision`. Set each row to `use` with the right 11-character `Chosen video ID`, or `skip` it. Keep the `Key` column intact. The transfer refuses unresolved rows.

Follow [ytmusicapi's browser authentication guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html) to make a local `browser.json` for the write step. Keep it private. OAuth also works through [ytmusicapi's setup guide](https://ytmusicapi.readthedocs.io/en/stable/setup/oauth.html); it needs `YTMUSIC_CLIENT_ID` and `YTMUSIC_CLIENT_SECRET` in your environment.

```powershell
.\.venv\Scripts\spot2ytmusic apply plans\road-trip.json --playlist "Road Trip" --auth browser.json
```

The tool creates a private playlist. If a playlist with that name exists, it stops. To use an existing empty playlist, pass its ID with `--playlist-id`. Run the same `apply` command after an interruption; the saved state and remote song order must agree before it continues. For a CSV with several playlists, add `--playlist "Name"` to `scan` for each one you want and run `apply` once per playlist.

## A few limits

Spot2YTMusic builds playlists from song metadata. It does not copy audio, set YouTube Music likes, or sync future Spotify changes. Some recordings may be missing from YouTube Music. The write step uses the unofficial [ytmusicapi](https://ytmusicapi.readthedocs.io/en/stable/) library, so changes to YouTube Music can interrupt a transfer.

Google also documents a [built-in transfer flow](https://support.google.com/youtubemusic/answer/14729358?hl=en). Spot2YTMusic is for CSV-based moves where you want to inspect the matches and keep the review sheet.

Your CSV, review sheet, cache, and authentication file stay local. Search requests include song titles and artists. Do not share `browser.json`, `oauth.json`, or a plan with private playlist names.

## Development

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check src tests
.\.venv\Scripts\python -m build
```

Released under the [MIT License](LICENSE). If this project saved you some time, [support it here](https://ko-fi.com/X8K126YVER).
