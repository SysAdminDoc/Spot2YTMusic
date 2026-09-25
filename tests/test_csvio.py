from pathlib import Path

import pytest

from spot2ytmusic.csvio import parse_duration, read_tracks


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
