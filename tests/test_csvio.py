from pathlib import Path
from zipfile import ZipFile

import pytest

from spot2ytmusic.csvio import parse_duration, read_sources, read_tracks


def test_reads_inventory_and_preserves_positions(tmp_path: Path):
    source = tmp_path / "spotify.csv"
    source.write_text(
        "\ufeffCollection,Position,Song,Artist,Album,Duration,Source type\n"
        'A,2,"Song, Two",Artist,Album,3:04,Local file\n'
        "A,1,First,Other,Record,2:01,Spotify catalog\n",
        encoding="utf-8",
    )
    tracks = read_tracks(source)
    assert [(track.position, track.title) for track in tracks] == [(1, "First"), (2, "Song, Two")]
    assert tracks[1].duration_seconds == 184
    assert tracks[1].source_type == "Local file"


def test_reads_exportify_columns_and_milliseconds(tmp_path: Path):
    source = tmp_path / "Liked_Songs.csv"
    source.write_text(
        "Track Name,Artist Name(s),Track Duration (ms)\nExample,One; Two,185000\n", encoding="utf-8"
    )
    track = read_tracks(source)[0]
    assert track.collection == "Liked Songs"
    assert track.artist == "One; Two"
    assert track.duration_seconds == 185


def test_rejects_duplicate_positions(tmp_path: Path):
    source = tmp_path / "songs.csv"
    source.write_text("Position,Title,Artist\n1,A,X\n1,B,Y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row 3"):
        read_tracks(source)


def test_duration_formats():
    assert parse_duration("1:02:03") == 3723
    assert parse_duration("185000", milliseconds=True) == 185
    assert parse_duration("") is None


def test_reads_export_all_zip_and_extra_csv(tmp_path: Path):
    archive_path = tmp_path / "all.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("Road_Trip.csv", "Track Name,Artist Name(s)\nFirst,Artist A\n")
        archive.writestr("Favorites.csv", "Track Name,Artist Name(s)\nSecond,Artist B\n")
        archive.writestr("__MACOSX/._noise.csv", "not,csv")
    extra = tmp_path / "New_Set.csv"
    extra.write_text("Title,Artist\nThird,Artist C\n", encoding="utf-8")
    tracks = read_sources([archive_path, extra])
    assert [(track.collection, track.title) for track in tracks] == [
        ("Favorites", "Second"),
        ("New Set", "Third"),
        ("Road Trip", "First"),
    ]


def test_rejects_duplicate_playlist_in_multiple_exports(tmp_path: Path):
    source = tmp_path / "Same.csv"
    source.write_text("Title,Artist\nA,X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate playlist position"):
        read_sources([source, source])
