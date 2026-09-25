# Research — Spot2YTMusic

Date: 2026-09-25. This replaces all prior research.

## Executive Summary

Spot2YTMusic v0.2.0 is a local Windows app that reads Spotify playlist exports, searches YouTube Music, holds uncertain matches for review, then creates private playlists or numbered MP3 folders. Its strongest feature is the review decision shared by both destinations, with ordered transfer verification and resumable work (`README.md`, `src/spot2ytmusic/transfer.py`, `src/spot2ytmusic/download.py`). Basic transfer is crowded: [YouTube Music has an in-app transfer path](https://support.google.com/youtubemusic/answer/14729358?hl=en), while [Tune My Music](https://www.tunemymusic.com/features/transfer) and [Soundiiz](https://soundiiz.com/pricing) handle large catalogs. The best direction is to make local, reviewed migration trustworthy across source formats, languages, retries, and downloads.

| Order | Opportunity | Tier | Impact / effort | Confidence |
| --- | --- | --- | --- | --- |
| 1 | Tie each reused MP3 to the chosen YouTube video ID. Changing a review decision currently keeps the old recording (`src/spot2ytmusic/download.py:_track_filename`, `download_playlists`). | Now | 5/5, M | Verified |
| 2 | Neutralize spreadsheet formulas in the review CSV and cap total import work, not just each ZIP member (`src/spot2ytmusic/planner.py:save_review`, `src/spot2ytmusic/csvio.py:read_sources`; [OWASP](https://community.owasp.org/attacks/CSV_Injection)). | Now | 5/5, M | Verified |
| 3 | Read Spotify's own playlist and saved-song JSON, preserving order and unavailable/local entries (`src/spot2ytmusic/csvio.py`; [Spotify export guide](https://support.spotify.com/us/article/understanding-your-data/)). | Next | 5/5, L | Verified |
| 4 | Match non-Latin titles and artists without collapsing them to empty strings (`src/spot2ytmusic/matching.py:normalize`; [Python Unicode data](https://docs.python.org/3/library/unicodedata.html)). | Next | 4/5, M | Verified |
| 5 | Let users refresh stale search results and leave every transfer or download with a durable failures report (`src/spot2ytmusic/planner.py:SearchCache`, `src/spot2ytmusic/gui.py:_completed`; [Tune My Music report](https://www.tunemymusic.com/features/transfer)). | Next | 4/5, M | Verified |
| 6 | Recover a created YouTube Music playlist when its local state file was never saved (`src/spot2ytmusic/transfer.py:apply_playlist`). | Next | 4/5, M | Likely; needs fault-injection validation |
| 7 | Protect locally saved browser headers and reject obsolete yt-dlp binaries before use (`src/spot2ytmusic/gui.py:save_browser_auth`, `src/spot2ytmusic/download.py:find_tools`; [ytmusicapi auth](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html), [yt-dlp advisories](https://github.com/yt-dlp/yt-dlp/security)). | Next | 4/5, M | Verified |
| 8 | Make review, progress, and failures accessible at compact window sizes (`src/spot2ytmusic/gui.py`, `docs/screenshots/desktop-compact.png`; [Qt accessibility](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html)). | Next | 3/5, M | Likely; needs isolated GUI validation |
| 9 | Show the active track's download and conversion stage, not only completed-track counts (`src/spot2ytmusic/download.py:_run_download`, `src/spot2ytmusic/gui.py:_progress`; [yt-dlp progress output](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)). | Later | 3/5, S | Verified |

## Product Map

- **Workflows.** Import Exportify CSVs or ZIPs; select playlists; scan and cache song/video candidates; review uncertain matches; transfer selected playlists or download selected MP3s (`src/spot2ytmusic/csvio.py`, `planner.py`, `review_store.py`, `transfer.py`, `download.py`).
- **Users.** Spotify leavers who want a YouTube Music library, and collectors who also want a local MP3/M3U8 copy (`README.md`). Single-user, local operation is the present design (`src/spot2ytmusic/gui.py`, `pyproject.toml`).
- **Platform.** Python 3.11+, PySide6 Essentials GUI, PyInstaller Windows single-file EXE, and a CLI. Downloads use external yt-dlp, FFmpeg/ffprobe, and Deno or Node (`pyproject.toml`, `scripts/build_windows.ps1`, `src/spot2ytmusic/download.py:find_tools`).
- **Data flow.** Export files remain local; title/artist queries reach YouTube Music; a browser-header JSON authenticates transfers; reviewed video IDs feed yt-dlp for MP3s. The plan, review sheet, SQLite search cache, transfer journal, and audio are local. An existing plan can be reviewed without another scan, while transfers and downloads require network access (`README.md`, `src/spot2ytmusic/gui.py`, `planner.py`, `transfer.py`, `download.py`).
- **Platform constraint.** The [YouTube Data API](https://developers.google.com/youtube/v3/docs/playlistItems/insert) exists, but playlist insertion has quota costs. This app uses [ytmusicapi's unofficial YouTube Music interface](https://ytmusicapi.readthedocs.io/en/stable/reference/playlists.html), so service changes remain a reliability risk (`src/spot2ytmusic/planner.py`, `transfer.py`).

## Competitive Landscape

| Product | Does well | Learn | Avoid |
| --- | --- | --- | --- |
| [YouTube Music transfer](https://support.google.com/youtubemusic/answer/14729358?hl=en) | In-app path to outside transfers. | Explain when reviewed matches and MP3 copies justify this app. | Competing on an undifferentiated copy button. |
| [Tune My Music](https://www.tunemymusic.com/features/transfer) | File imports, alternate-version matching, ordered transfers, unmatched CSV. | Leave a portable, per-track result and retry list. | A cloud account dependency for local work. |
| [Soundiiz](https://soundiiz.com/pricing) | Batch transfer, export, add/replace sync; free transfers select up to 200 tracks per playlist. | Make selection and destination behavior explicit. | Building a broad sync service before reliability is sound. |
| [SongShift](https://www.songshift.com/pro) | Review, batch setup, JSON/TXT import and export. | Keep manual correction quick for large libraries. | A subscription or hosted workflow. |
| [spotDL](https://github.com/spotDL/spotify-downloader) | Tagged downloads, M3U8, resume, save-errors option. | Treat error reports and asset identity as first-class data. | Replacing a user's chosen recording with a fresh automatic match; [wrong-song report](https://github.com/spotDL/spotify-downloader/issues/2355). |
| [spotify_to_ytmusic](https://github.com/linsomniac/spotify_to_ytmusic) | Liked-song and playlist migration with a GUI. | Include saved songs in the source model. | Fragile setup and auth assumptions seen in [GUI issue #252](https://github.com/linsomniac/spotify_to_ytmusic/issues/252) and [OAuth issue #248](https://github.com/linsomniac/spotify_to_ytmusic/issues/248). |
| [Sideload](https://github.com/marctorrelles/sideload) | Read-back verification, review queue, explicit missing-items list. | Keep verifying destination state and expose what failed. | Moving this single-user Windows app to hosted infrastructure. |
| [Spotify2MP3](https://github.com/angall1/Spotify2MP3) | Exportify CSV to MP3 and M3U for portable players. | Keep the local-playlist output understandable and easy to reopen. | Assuming a filename proves the audio is the reviewed recording. |
| [Playlift](https://github.com/idodoron11/Playlift) | Cross-service/local playlist comparison and multilingual matching. | Test Unicode names and portable M3U paths. | Adding several services without a user-backed migration need. |
| [Exportify](https://github.com/watsonbox/exportify) | UTF-8 CSV/ZIP export with artist, album, duration, and ISRC. | Preserve useful source identifiers. | Making Exportify the only source; Spotify provides its own JSON. |
| [MusicBrainz Picard](https://picard-docs.musicbrainz.org/en/latest/config/options_fingerprinting.html) | Separates metadata matching from optional acoustic fingerprint lookup. | Consider fingerprints only for post-download verification. | Calling a metadata score proof of audio identity. |

Additional OSS checked: [spotify-ytmusic-tools](https://github.com/alharari01/spotify-ytmusic-tools), [streamhop](https://github.com/sytelus/streamhop), [SpotTransfer](https://github.com/pushan2005/spottransfer), [spotify-playlister](https://github.com/jtsternberg/spotify-playlister), [SpotifyDownloader](https://github.com/PrathamRanka/SpotifyDownloader), [zipify-tunes](https://github.com/akhileshthite/zipify-tunes), [MusicMigrator](https://github.com/Steven-S-Francis/MusicMigrator), [playlist-porter](https://github.com/nikhil-thomas-a/playlist-porter), and [spotify-to-ytmusic](https://github.com/SuluMeloNNN/spotify-to-ytmusic). Their useful patterns overlap with the items above: compare before writing, resume after failures, surface missing tracks, and preserve metadata.

## Reported Issues

The repository's GitHub tracker is enabled but had no open or closed issues, no open PRs, and no discussions on 2026-09-25 (`https://github.com/SysAdminDoc/Spot2YTMusic/issues`, `https://github.com/SysAdminDoc/Spot2YTMusic/pulls`). The earlier user reports about Exportify ZIP import, individual playlist selection, and stopping a scan are addressed in `CHANGELOG.md` v0.1.0 and v0.1.2. They are not roadmap duplicates. Outside reports of wrong song versions and setup failures are directional evidence, not verified Spot2YTMusic defects ([spotDL #2355](https://github.com/spotDL/spotify-downloader/issues/2355), [spotify_to_ytmusic #252](https://github.com/linsomniac/spotify_to_ytmusic/issues/252), [YouTube Music discussion](https://www.reddit.com/r/YoutubeMusic/comments/1ljkiu8/shifting_from_spotify/)).

## Security, Privacy, and Reliability

- **Verified:** `download_playlists` reuses a valid destination MP3 by source track key and position, while the reviewed `video_id` can change. A corrected review can therefore retain the wrong audio. Existing tests cover unchanged resumes but not a changed candidate (`src/spot2ytmusic/download.py`, `tests/test_download.py`).
- **Verified:** `save_review` writes untrusted track and candidate text into a CSV opened by spreadsheet programs. `csv.writer` quotes delimiters but does not neutralize formula-leading cells. Because the review CSV is also programmatic input, the fix must round-trip decisions without changing track identity (`src/spot2ytmusic/planner.py`, `review_store.py`; [OWASP](https://community.owasp.org/attacks/CSV_Injection)).
- **Verified:** ZIP import limits each CSV member to 64 MiB but not the archive's total expanded bytes, member count, or track count. `parse_duration` does not reject non-finite numbers. Bound all work before a hostile export can exhaust memory or strand import (`src/spot2ytmusic/csvio.py`; [Python zipfile](https://docs.python.org/3/library/zipfile.html)).
- **Verified:** Browser authentication is stored as reusable headers in a JSON file under the Windows profile, with no file-specific access restriction or in-app disconnect/delete path (`src/spot2ytmusic/gui.py:save_browser_auth`; [ytmusicapi browser auth](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)). The existing README correctly tells users to keep it private (`README.md`).
- **Verified:** `find_tools` accepts any yt-dlp on PATH. Its own command uses `--ignore-config` and `--no-plugin-dirs`, which limits inherited behavior, but a stale executable remains possible. [2026 yt-dlp advisories](https://github.com/yt-dlp/yt-dlp/security) were patched before [2026.08.19](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19). The pinned PyInstaller 6.22.3 is above the 6.22.1 fix for [GHSA-9fxf-4qw3-ghmr](https://github.com/pyinstaller/pyinstaller/security/advisories/GHSA-9fxf-4qw3-ghmr), so that advisory does not call for a version bump (`pyproject.toml`).
- **Likely:** `apply_playlist` creates a remote playlist before `_save_state`. A local write failure then leaves an empty playlist with the target name, and the next automatic attempt refuses that name. Test this fault path before changing recovery behavior (`src/spot2ytmusic/transfer.py:apply_playlist`).
- **Needs live validation:** No authenticated end-to-end transfer or YouTube media download was run for this research. The 33 local tests passed on 2026-09-25, including fake-client transfer and fake-downloader MP3 coverage (`tests/`, `src/spot2ytmusic/transfer.py`, `tests/test_download.py`).
- **Policy constraint:** [YouTube's terms](https://www.youtube.com/t/terms) restrict downloads and automated access without specified permission. `README.md` already discloses this. New downloader work should stay focused on correctness and user transparency, without proposing access-control bypasses.

## Architecture Assessment

- `Track` has no ISRC or explicitness field even though [Exportify exports ISRC](https://github.com/watsonbox/exportify). `csvio.py` is the right boundary for a second reader for [Spotify's official JSON](https://support.spotify.com/us/article/understanding-your-data/). Keep one normalized `Track` representation (`src/spot2ytmusic/models.py`, `csvio.py`).
- `matching.py:normalize` retains only `[a-z0-9]`, so CJK and Cyrillic names become empty; `rank_results` then cannot make a confident match. Use Unicode letters/numbers and a multilingual fixture set. [ytmusicapi search](https://ytmusicapi.readthedocs.io/en/stable/reference/search.html) exposes title, artists, album, duration, type, and availability, but no ISRC in documented song results, so exact cross-service ISRC matching is not currently justified (`src/spot2ytmusic/matching.py`).
- `SearchCache` uses only query/filter as a primary key, with no age or schema marker. An empty result can persist indefinitely; a review screen needs targeted refresh without deleting the whole cache (`src/spot2ytmusic/planner.py:SearchCache`).
- The transfer journal verifies a remote prefix after each batch. Preserve that safeguard while recovering state-file loss. The MP3 side needs an equally durable manifest mapping output path, source key, reviewed video ID, and content validity (`src/spot2ytmusic/transfer.py`, `download.py`).
- The GUI has worker threads, cancellation, a status bar, and a crash log. The 42-pixel activity log and compact screenshot make multi-song failures hard to inspect; no explicit accessible names were found in `gui.py`. Test with Windows screen reader and an isolated compact display before finalizing a layout (`src/spot2ytmusic/gui.py`, `docs/screenshots/desktop-compact.png`; [Qt widget accessibility](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html)).
- `_run_download` consumes yt-dlp output only for the final error, so a long recording has no in-track progress in the GUI. [yt-dlp recommends `--progress-template`](https://github.com/yt-dlp/yt-dlp/blob/master/README.md) for integrations instead of parsing normal stdout (`src/spot2ytmusic/download.py:_run_download`, `src/spot2ytmusic/gui.py:_progress`).
- The release script builds an offscreen-smoked Windows EXE, wheel, source archive, ZIP, and checksums; the EXE is unsigned and download tools are separate. Keep the version preflight and install guidance ahead of wider distribution. Signing depends on obtaining a certificate (`scripts/build_windows.ps1`, `README.md`).
- `pyproject.toml` pins ytmusicapi 1.12.3 and PySide6 Essentials 6.11.2, which match their published releases on 2026-09-25 ([ytmusicapi](https://pypi.org/project/ytmusicapi/1.12.3/), [PySide6 Essentials](https://pypi.org/project/PySide6-Essentials/)). Keep a tested dependency upgrade path and an older-plan fixture rather than upgrading just for novelty (`src/spot2ytmusic/review_store.py`, `tests/`).

## Rejected Ideas

- **Exact ISRC match against YouTube Music:** Exportify provides ISRC, but [documented ytmusicapi search results](https://ytmusicapi.readthedocs.io/en/stable/reference/search.html) do not. Preserve the identifier; do not label a text match as exact.
- **Automatic fingerprints before selection:** [Picard](https://picard-docs.musicbrainz.org/en/latest/config/options_fingerprinting.html) fingerprints an audio file. This app has no candidate audio until after selection and download (`src/spot2ytmusic/download.py`). Post-download checking may be useful later if a reliable reference recording is available.
- **Cloud hosting, multi-user accounts, mobile client, or plugin framework:** [Sideload](https://github.com/marctorrelles/sideload) and [Tune My Music](https://www.tunemymusic.com/features/transfer) already cover hosted transfer. Spot2YTMusic's documented local Windows workflow and privacy model would gain little from those costs (`README.md`, `scripts/build_windows.ps1`).
- **Bidirectional auto-sync or destructive replacement:** [Soundiiz](https://soundiiz.com/pricing) sells sync, but this product currently promises one-way migration and local copies. Ongoing sync would require separate source credentials and conflict rules (`README.md`, `src/spot2ytmusic/transfer.py`).
- **Bundling a downloader that bypasses service restrictions:** [YouTube terms](https://www.youtube.com/t/terms) and [yt-dlp's own documentation](https://github.com/yt-dlp/yt-dlp) make permission and maintenance material. Offer clear tool checks and keep user control (`src/spot2ytmusic/download.py`).
- **A mandatory code-signing task before a certificate exists:** `README.md` already discloses the unsigned EXE. `scripts/build_windows.ps1` can gain signing once a certificate is available; the present actionable distribution work is tool preflight and release verification.

## Sources

**Project and source formats**

- https://github.com/SysAdminDoc/Spot2YTMusic
- https://github.com/watsonbox/exportify
- https://support.spotify.com/us/article/understanding-your-data/
- https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide
- https://developers.google.com/youtube/v3/docs/playlistItems/insert
- https://support.google.com/youtubemusic/answer/14729358?hl=en
- https://ytmusicapi.readthedocs.io/en/stable/reference/search.html
- https://ytmusicapi.readthedocs.io/en/stable/reference/playlists.html

**Competitors and adjacent tools**

- https://www.tunemymusic.com/features/transfer
- https://soundiiz.com/pricing
- https://www.songshift.com/pro
- https://freeyourmusic.com/pricing
- https://github.com/spotDL/spotify-downloader
- https://github.com/linsomniac/spotify_to_ytmusic
- https://github.com/marctorrelles/sideload
- https://github.com/angall1/Spotify2MP3
- https://github.com/idodoron11/Playlift
- https://github.com/alharari01/spotify-ytmusic-tools
- https://github.com/sytelus/streamhop
- https://github.com/pushan2005/spottransfer
- https://github.com/jtsternberg/spotify-playlister
- https://github.com/PrathamRanka/SpotifyDownloader
- https://github.com/akhileshthite/zipify-tunes
- https://github.com/Steven-S-Francis/MusicMigrator
- https://github.com/nikhil-thomas-a/playlist-porter
- https://github.com/SuluMeloNNN/spotify-to-ytmusic
- https://github.com/topics/playlist-transfer
- https://github.com/awesome-selfhosted/awesome-selfhosted
- https://picard-docs.musicbrainz.org/en/latest/config/options_fingerprinting.html

**Community, engineering, and security**

- https://github.com/spotDL/spotify-downloader/issues/2355
- https://github.com/linsomniac/spotify_to_ytmusic/issues/252
- https://www.reddit.com/r/YoutubeMusic/comments/1ljkiu8/shifting_from_spotify/
- https://arxiv.org/abs/1407.3191
- https://musicbrainz.org/doc/MusicBrainz_API
- https://community.owasp.org/attacks/CSV_Injection
- https://docs.python.org/3/library/zipfile.html
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html
- https://github.com/yt-dlp/yt-dlp/wiki/EJS
- https://github.com/yt-dlp/yt-dlp/blob/master/README.md
- https://github.com/yt-dlp/yt-dlp/security
- https://github.com/pyinstaller/pyinstaller/security/advisories/GHSA-9fxf-4qw3-ghmr
- https://www.youtube.com/t/terms

## Open Questions

- **Needs live validation:** Do changed review choices, session expiry, and server-side playlist lag behave as the code paths imply on a real account? The fixes can be implemented with fault-injection tests first, then verified with a small permissioned account and recording (`src/spot2ytmusic/download.py`, `transfer.py`).
- **Needs live validation:** What minimum tool versions work reliably with the exact shipped Windows EXE and current YouTube extraction? Publish only versions tested together (`scripts/build_windows.ps1`, `src/spot2ytmusic/download.py:find_tools`).
