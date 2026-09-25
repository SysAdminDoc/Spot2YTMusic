from playlist_bridge.matching import rank_results, score_result, version_flags
from playlist_bridge.models import Track


def track(title="WE ON GO", artist="BIA", seconds=168):
    return Track("JogJams", 3, title, artist, "", seconds)


def result(video_id, title, artist, seconds, kind="song"):
    return {
        "videoId": video_id,
        "title": title,
        "artists": [{"name": artist}],
        "duration_seconds": seconds,
        "resultType": kind,
        "isAvailable": True,
    }


def test_exact_song_is_automatic():
    status, candidates = rank_results(
        track(),
        [
            result("abcdefghijk", "WE ON GO", "BIA", 169),
            result("lmnopqrstuv", "We On Go", "Mir Bankz", 124),
        ],
    )
    assert status == "auto"
    assert candidates[0].video_id == "abcdefghijk"


def test_wrong_artist_and_duration_need_review():
    status, candidates = rank_results(track(), [result("lmnopqrstuv", "We On Go", "Mir Bankz", 124)])
    assert status == "review"
    assert "artist differs" in candidates[0].reason


def test_karaoke_and_live_versions_are_not_silent_matches():
    source = track("No Hands Karaoke", "No Hands Karaoke", 249)
    match = score_result(source, result("abcdefghijk", "No Hands", "Waka Flocka Flame", 249))
    assert match is not None
    assert "version words differ" in match.reason
    assert version_flags("Olive Tree") == set()


def test_unavailable_result_is_ignored():
    status, candidates = rank_results(
        track(), [{"videoId": "abcdefghijk", "title": "WE ON GO", "isAvailable": False}]
    )
    assert status == "missing"
    assert candidates == []
