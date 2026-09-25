# Roadmap

Only incomplete work is listed. Evidence and rationale are in `RESEARCH.md`, dated 2026-09-25.

## Research-Driven Additions

### P0

- [ ] P0 — Re-download a track when its reviewed YouTube recording changes
  Why: A rerun currently treats the old MP3 as complete even after the user picks a different video.
  Evidence: `RESEARCH.md` Security, Privacy, and Reliability; `src/spot2ytmusic/download.py:_track_filename`, `download_playlists`; `tests/test_download.py`.
  Touches: `src/spot2ytmusic/download.py`, `tests/test_download.py`.
  Acceptance: A small manifest records source key, position, chosen video ID, and output filename. Reusing is allowed only when that identity and MP3 validation agree. A test changes one review choice, reruns, and observes exactly that position replaced while unchanged positions reuse audio and M3U8 order remains intact.
  Complexity: M

- [ ] P0 — Make exported review cells safe to open in spreadsheet apps
  Why: Imported song text can begin a formula, and CSV quoting alone does not neutralize it.
  Evidence: `RESEARCH.md` Security, Privacy, and Reliability; `src/spot2ytmusic/planner.py:save_review`; https://community.owasp.org/attacks/CSV_Injection.
  Touches: `src/spot2ytmusic/planner.py`, `src/spot2ytmusic/review_store.py`, `src/spot2ytmusic/transfer.py`, `tests/`.
  Acceptance: Formula-leading source and candidate fields, including `=`, `+`, `-`, `@`, leading control characters, and full-width variants, open as text in Excel-oriented output. Reopening and editing the review sheet preserves the original playlist/key mapping and decision round-trip. Tests include delimiter and quote payloads.
  Complexity: M

- [ ] P0 — Bound total CSV and ZIP import work
  Why: A ZIP can contain many 64 MiB members, and non-finite duration values escape the row-level error path.
  Evidence: `RESEARCH.md` Security, Privacy, and Reliability; `src/spot2ytmusic/csvio.py:read_sources`, `parse_duration`; https://docs.python.org/3/library/zipfile.html.
  Touches: `src/spot2ytmusic/csvio.py`, `tests/test_csvio.py`, GUI import error display in `src/spot2ytmusic/gui.py`.
  Acceptance: Enforce named limits of 1,000 CSV members, 256 MiB aggregate expanded CSV data, and 100,000 tracks across all selected inputs, both from ZIP metadata and bytes/rows actually read. Reject `nan` and infinite durations with file/row context. Tests cover each limit, corrupt ZIPs, and a normal Exportify bundle.
  Complexity: M

### P1

- [ ] P1 — Import Spotify account-data playlists and saved songs
  Why: Spotify's own download is JSON, while the app currently requires Exportify or custom CSV.
  Evidence: `RESEARCH.md` Product Map and Architecture Assessment; `src/spot2ytmusic/csvio.py`; https://support.spotify.com/us/article/understanding-your-data/.
  Touches: `src/spot2ytmusic/csvio.py`, `models.py`, `gui.py`, `cli.py`, `README.md`, `tests/`.
  Acceptance: The file picker and CLI accept a Spotify account-data JSON file or ZIP containing playlist and Your Library data. Saved songs appear as a selectable Liked Songs collection. Playlist order, duplicates, local/unavailable entries, and titles/artists/albums survive normalization. Malformed or unrelated JSON reports a specific error; Exportify input remains compatible. Tests use anonymized fixtures for each supported export shape.
  Complexity: L

- [ ] P1 — Match titles and artists in non-Latin scripts
  Why: ASCII-only normalization erases CJK and Cyrillic names before scoring.
  Evidence: `RESEARCH.md` Architecture Assessment; `src/spot2ytmusic/matching.py:normalize`; https://docs.python.org/3/library/unicodedata.html.
  Touches: `src/spot2ytmusic/matching.py`, `tests/test_matching.py`.
  Acceptance: Unicode letters and numbers survive normalization; accented Latin behavior remains stable. A fixture set with CJK, Cyrillic, diacritics, mixed scripts, punctuation, and live/remix collisions ranks the intended recording first without auto-accepting ambiguous versions.
  Complexity: M

- [ ] P1 — Recover transfers after playlist creation but before local state is saved
  Why: A disk write failure can leave a same-name empty remote playlist that the next automatic attempt refuses.
  Evidence: `RESEARCH.md` Security, Privacy, and Reliability; `src/spot2ytmusic/transfer.py:apply_playlist`, `_save_state`.
  Touches: `src/spot2ytmusic/transfer.py`, `gui.py`, `tests/test_transfer.py`.
  Acceptance: A fault-injection test fails the first state write after remote creation. The next run identifies the single empty destination and offers an explicit Adopt action in the GUI, then resumes without creating another playlist or duplicating tracks. Ambiguous or nonempty destinations still stop safely.
  Complexity: M

- [ ] P1 — Refresh selected search results and expire stale cache entries
  Why: Empty or obsolete results remain cached without an age marker or refresh control.
  Evidence: `RESEARCH.md` Architecture Assessment; `src/spot2ytmusic/planner.py:SearchCache`; https://ytmusicapi.readthedocs.io/en/stable/reference/search.html.
  Touches: `src/spot2ytmusic/planner.py`, `gui.py`, `tests/test_planner.py`.
  Acceptance: The cache stores creation time and schema version, expires negative results after 24 hours and positive results after 30 days, and supports refresh for chosen review rows without clearing unrelated entries. An old v0.2.0 cache migrates or rebuilds without crashing; tests use a fake clock and search client.
  Complexity: M

- [ ] P1 — Save a durable transfer and download result report
  Why: A 42-pixel log is an unreliable place to find failed songs after a large job.
  Evidence: `RESEARCH.md` Competitive Landscape; `src/spot2ytmusic/gui.py:_completed`; https://www.tunemymusic.com/features/transfer; https://github.com/spotDL/spotify-downloader/blob/master/docs/usage.md.
  Touches: `src/spot2ytmusic/gui.py`, `download.py`, `transfer.py`, `cli.py`, `tests/`.
  Acceptance: Every run writes a machine-readable result and a safe CSV with playlist, position, source, chosen video ID, outcome, and error. The GUI shows counts and an Open report action. Download retries revisit failed positions, transfer retries resume from the verified prefix, and neither alters completed tracks. Tests cover a mixed success/failure job and report reopen.
  Complexity: M

- [ ] P1 — Restrict and revoke saved YouTube Music browser authentication
  Why: The app writes reusable session headers to a predictable JSON file and has no in-app delete path.
  Evidence: `RESEARCH.md` Security, Privacy, and Reliability; `src/spot2ytmusic/gui.py:save_browser_auth`; https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html.
  Touches: `src/spot2ytmusic/gui.py`, auth helper module if needed, `README.md`, `tests/`.
  Acceptance: A saved auth file has a restricted Windows ACL for the current user and required system/admin principals, errors/logs redact header and cookie values, and a Disconnect action removes the app-created file and clears the GUI path. A permissions test verifies the file ACL without printing credentials. Existing user-created auth paths are never silently deleted.
  Complexity: M

- [ ] P1 — Check downloader tool versions before starting MP3 work
  Why: The app accepts any yt-dlp, FFmpeg, or JS runtime found on PATH, including obsolete binaries.
  Evidence: `RESEARCH.md` Security, Privacy, and Reliability; `src/spot2ytmusic/download.py:find_tools`; https://github.com/yt-dlp/yt-dlp/security; https://github.com/yt-dlp/yt-dlp/wiki/EJS.
  Touches: `src/spot2ytmusic/download.py`, `gui.py`, `README.md`, `tests/`.
  Acceptance: A preflight shows resolved paths and versions, rejects yt-dlp older than 2026.07.04, verifies FFmpeg/ffprobe, Deno 2.3+ or Node 22+, and yt-dlp EJS availability, then provides official download links. No tool is installed at runtime. Fake-tool tests cover missing, obsolete, and compatible sets; the release EXE passes the preflight on the build machine.
  Complexity: M

- [ ] P1 — Make the review workflow usable with assistive technology and compact windows
  Why: Source selection and failure details require scrolling or a tiny log, and control names are not explicitly audited.
  Evidence: `RESEARCH.md` Architecture Assessment; `src/spot2ytmusic/gui.py`, `docs/screenshots/desktop-compact.png`; https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html.
  Touches: `src/spot2ytmusic/gui.py`, `docs/screenshots/`, `tests/test_gui_workflow.py`.
  Acceptance: At 1080x700 and 125% DPI, import, selected-playlist scan, review, Stop, transfer, download, and Open report remain reachable without hidden horizontal overflow. Controls have meaningful accessible names/descriptions and a logical focus order. Verify with keyboard navigation and a Windows screen reader in an isolated display, then recapture dark, light, and compact screenshots.
  Complexity: M

### P2

- [ ] P2 — Show per-track download and conversion progress
  Why: The GUI reports a track only when it finishes, leaving long downloads looking idle.
  Evidence: `RESEARCH.md` Architecture Assessment; `src/spot2ytmusic/download.py:_run_download`; https://github.com/yt-dlp/yt-dlp/blob/master/README.md.
  Touches: `src/spot2ytmusic/download.py`, `gui.py`, `tests/test_download.py`, `tests/test_gui_workflow.py`.
  Acceptance: Use yt-dlp's `--progress-template` to report the active playlist, position, download percentage when known, and post-processing stage through the existing worker signal. Cancellation remains responsive and raw tool output does not fill the activity log. A fake-process test exercises download, conversion, failure, and Stop states.
  Complexity: S

- [ ] P2 — Preserve source recording identifiers through plans and local metadata
  Why: Exportify provides ISRC, but the importer discards it, limiting diagnostics and later reconciliation.
  Evidence: `RESEARCH.md` Architecture Assessment and Rejected Ideas; `src/spot2ytmusic/models.py:Track`, `csvio.py`; https://github.com/watsonbox/exportify; https://ytmusicapi.readthedocs.io/en/stable/reference/search.html.
  Touches: `src/spot2ytmusic/models.py`, `csvio.py`, `planner.py`, `download.py`, `review_store.py`, `tests/`.
  Acceptance: ISRC and explicitness survive Exportify import, saved plan, result report, and MP3 tags where supported. Missing identifiers remain optional. A v0.2.0 plan still opens, and tests confirm identifiers never force an exact YouTube Music match when the result lacks them.
  Complexity: M

- [ ] P2 — Calibrate automatic matching on a reviewed fixture corpus
  Why: The current 0.89 score, 0.08 margin, and six-second duration gate are hard-coded without a regression corpus.
  Evidence: `RESEARCH.md` Architecture Assessment; `src/spot2ytmusic/matching.py:rank_results`; https://github.com/spotDL/spotify-downloader/issues/2355; https://picard-docs.musicbrainz.org/en/latest/config/options_matching.html.
  Touches: `src/spot2ytmusic/matching.py`, `tests/test_matching.py`, fixture data under `tests/`.
  Acceptance: Add anonymized, reviewed examples covering exact tracks, remasters, live versions, lyric videos, duplicate titles, missing durations, and non-Latin names. Record precision and review rate before adjusting thresholds; no known wrong version becomes an automatic match. Keep uncertain cases for manual review.
  Complexity: M

- [ ] P2 — Verify plan and report compatibility across app upgrades
  Why: New source fields, cache timestamps, and download manifests will change persisted local data.
  Evidence: `RESEARCH.md` Architecture Assessment; `src/spot2ytmusic/planner.py:SCHEMA_VERSION`, `review_store.py`, `transfer.py:state_path_for`.
  Touches: `src/spot2ytmusic/planner.py`, `review_store.py`, `transfer.py`, `README.md`, `tests/`.
  Acceptance: Fixtures from v0.2.0 open in the current GUI and CLI after the new fields land. Unsupported future schemas fail with a clear backup-and-upgrade message. Migration is atomic, keeps review decisions and verified transfer counts, and has rollback tests for interrupted writes.
  Complexity: M
