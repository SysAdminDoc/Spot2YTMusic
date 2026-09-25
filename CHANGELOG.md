# Changelog

## v0.1.3

- Rebuild the desktop layout around playlist selection, match review, recording details, and transfer status.
- Refresh the dark theme and improve the light theme, including clearer selection and match states.
- Add a generic track artwork tile and keep the review controls visible beside the track list.

## v0.1.2

- Choose individual playlists from an imported CSV or Exportify ZIP before scanning.
- Transfer selected playlists from a plan without reviewing unrelated playlists first.
- Stop scans during a retry wait or after the current search request. Search requests use a 10-second network timeout, and completed results stay cached.

## v0.1.1

- Include YouTube Music language files in the Windows EXE so scanning starts after an Exportify import.
- Check the frozen app's YouTube Music client during every Windows build.
- Label background errors by the step that failed.

## v0.1.0

- Add a Windows desktop app for export, batch scan, match review, and playlist transfer.
- Import several Spotify CSVs or an Exportify Export All ZIP without unpacking it.
- Save review decisions in the existing CSV and resume verified transfers from the app.
- Create a local YouTube Music auth file from browser headers pasted into the app.
- Package a single-file Windows EXE with a dark and light theme.

## v0.0.3

- Rewrite the README around reviewed matches, CSV setup, privacy, and recovery.
- Add an evergreen header and keep the original and alternate artwork in the concept archive.
- Add package links and search terms for people finding the project on GitHub.

## v0.0.2

- Rename the project, Python package, and command to Spot2YTMusic.
- Publish the source and installable package on GitHub.

## v0.0.1

- Read Spotify playlist CSV files without a Spotify developer account.
- Search YouTube Music and score title, artist, duration, album, and version clues.
- Produce a review CSV before making account changes.
- Transfer reviewed songs in order, including repeated songs, and verify every batch.
- Resume a stopped transfer after checking the destination against the saved plan.
- Retry temporary search failures and handle newly created empty playlists.
