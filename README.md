![Playlist Bridge](docs/hero.svg)

[![Version](https://img.shields.io/badge/version-0.0.1-7659d6)](#) [![License](https://img.shields.io/badge/license-MIT-2680b8)](LICENSE) [![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-285f93)](#)

Playlist Bridge moves songs from a Spotify CSV into a private YouTube Music playlist. It searches first, writes a review sheet, and only adds songs you approve. It keeps repeated songs and their order. A stopped transfer checks the remote playlist before it resumes.

## Set up

Install Python 3.11 or newer. In the project folder:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
~~~

On macOS or Linux, use the matching commands under .venv/bin.

## Prepare a CSV

A file needs a song title and artist column. Playlist Bridge also reads playlist name, position, album, duration, Spotify track URL, and source type when present. It accepts the CSV saved by Spotify inventory tools and common exports with Track Name and Artist Name(s) columns. If there is no playlist column, the filename becomes the playlist name.

Example:

~~~csv
Collection,Position,Song,Artist,Album,Duration
Road Trip,1,Midnight City,M83,Hurry Up We're Dreaming,4:03
Road Trip,2,Kids,MGMT,Oracular Spectacular,5:02
~~~

The CSV lists metadata, not audio files. Local Spotify files can be searched by title and artist, but a matching recording may not exist on YouTube Music.

## Inspect and search

~~~powershell
.\.venv\Scripts\playlist-bridge inspect data\spotify.csv
.\.venv\Scripts\playlist-bridge scan data\spotify.csv --playlist "Road Trip" --plan plans\road-trip.json
~~~

Search uses YouTube Music's public catalog. No account login is needed for this step. Results are cached beside the plan, so a second scan can reuse completed searches. Temporary server errors get a bounded retry. Use a new plan filename for another scan, or pass --overwrite if you intend to replace its review sheet. The review sheet is written as plans/road-trip.review.csv.

Open the review CSV and check each row. Decision is prefilled with use only for a strong match. For other songs, inspect the candidate links or the search link. Enter use with the correct 11-character YouTube video ID, or skip. The apply command refuses blank decisions. Keep the Key column intact.

## Transfer

The write step uses [ytmusicapi](https://ytmusicapi.readthedocs.io/en/stable/), an unofficial YouTube Music library. Follow its [browser authentication guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html) to make a local browser.json file, or use its [OAuth guide](https://ytmusicapi.readthedocs.io/en/stable/setup/oauth.html). Keep that file private. OAuth also needs YTMUSIC_CLIENT_ID and YTMUSIC_CLIENT_SECRET in your environment.

~~~powershell
.\.venv\Scripts\playlist-bridge apply plans\road-trip.json --playlist "Road Trip" --auth browser.json
~~~

Playlist Bridge creates a private playlist. If a playlist with that name already exists, it stops. You can pass --playlist-id with an existing empty playlist ID. It never clears or replaces an existing playlist.

After each batch, it reads the destination and checks the full song order against the reviewed plan. Run the same apply command again after an interruption. The state file and remote playlist must agree before more songs are added.

## Privacy and limits

Your CSV, review sheet, search cache, and account credentials stay on your computer. Search queries containing song titles and artists go to YouTube Music. No separate migration service receives your playlists. Do not share browser.json, oauth.json, or a plan containing private playlist names.

This project avoids a Spotify developer account by starting from CSV. Spotify's development API currently limits who can use an app, which makes a public direct-login migrator harder to distribute. YouTube Music has no supported public API for searching its music catalog and writing native music playlists, so this tool depends on an unofficial library. Site changes may interrupt a transfer; the saved state makes it safe to inspect before retrying.

## Verify the project

~~~powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check src tests
.\.venv\Scripts\python -m build
~~~

The transfer does not download or copy audio. It finds corresponding YouTube Music entries and builds a playlist from those links.
