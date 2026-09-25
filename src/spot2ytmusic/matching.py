"""Conservative song matching for YouTube Music search results."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .models import Candidate, Track

VERSION_WORDS = (
    "live",
    "karaoke",
    "instrumental",
    "acoustic",
    "remix",
    "radio edit",
    "sped up",
    "slowed",
    "cover",
    "edited",
    "clean",
)
FEATURE = re.compile(r"\s*[\[(](?:feat\.?|ft\.?|featuring)\s+[^)\]]+[)\]]", re.IGNORECASE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def core_title(title: str) -> str:
    title = FEATURE.sub("", title)
    title = re.sub(
        r"\s*[\[(](?:\d{4}\s+)?(?:remaster(?:ed)?|album version)[^\])]*[\])]", "", title, flags=re.IGNORECASE
    )
    return normalize(title)


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    a, b = set(left.split()), set(right.split())
    overlap = len(a & b) / len(a | b) if a | b else 0.0
    return max(ratio, 0.7 * overlap + 0.3 * ratio)


def version_flags(title: str) -> set[str]:
    text = normalize(title)
    return {word for word in VERSION_WORDS if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text)}


def _artist_score(source: str, candidate: str) -> float:
    source_names = [normalize(source)] + [
        normalize(part)
        for part in re.split(r"\s*(?:;|,| & | feat\.? | featuring )\s*", source, flags=re.IGNORECASE)
    ]
    candidate_names = [normalize(candidate)] + [
        normalize(part)
        for part in re.split(r"\s*(?:;|,| & | feat\.? | featuring )\s*", candidate, flags=re.IGNORECASE)
    ]
    return max((similarity(a, b) for a in source_names for b in candidate_names), default=0.0)


def score_result(track: Track, result: dict) -> Candidate | None:
    video_id = result.get("videoId")
    if not video_id or result.get("isAvailable") is False:
        return None
    title = str(result.get("title") or "")
    artists = result.get("artists") or []
    artist = ", ".join(str(item.get("name") or "") for item in artists if isinstance(item, dict))
    if not artist:
        artist = str(result.get("artist") or result.get("author") or "")
    album_value = result.get("album") or ""
    album = str(album_value.get("name") or "") if isinstance(album_value, dict) else str(album_value)
    duration = result.get("duration_seconds")
    if duration is None and result.get("duration"):
        from .csvio import parse_duration

        try:
            duration = parse_duration(str(result["duration"]))
        except ValueError:
            duration = None
    title_score = similarity(core_title(track.title), core_title(title))
    artist_score = _artist_score(track.artist, artist)
    duration_gap = (
        abs(track.duration_seconds - duration)
        if track.duration_seconds is not None and duration is not None
        else None
    )
    duration_score = max(0.0, 1 - duration_gap / 40) if duration_gap is not None else 0.5
    album_score = similarity(normalize(track.album), normalize(album)) if track.album and album else 0.5
    mismatch = version_flags(track.title) ^ version_flags(title)
    score = 0.53 * title_score + 0.27 * artist_score + 0.15 * duration_score + 0.05 * album_score
    if mismatch:
        score -= 0.16
    if result.get("resultType") == "song":
        score += 0.01
    reasons = []
    if mismatch:
        reasons.append("version words differ: " + ", ".join(sorted(mismatch)))
    if duration_gap is not None and duration_gap > 8:
        reasons.append(f"duration differs by {duration_gap}s")
    if artist_score < 0.8:
        reasons.append("artist differs")
    if title_score < 0.9:
        reasons.append("title differs")
    return Candidate(
        video_id=str(video_id),
        title=title,
        artist=artist,
        album=album,
        duration_seconds=duration,
        result_type=str(result.get("resultType") or ""),
        score=round(max(0.0, min(score, 1.0)), 4),
        reason="; ".join(reasons),
    )


def rank_results(track: Track, results: list[dict]) -> tuple[str, list[Candidate]]:
    candidates = [candidate for result in results if (candidate := score_result(track, result))]
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    if not candidates:
        return "missing", []
    top = candidates[0]
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    title_match = similarity(core_title(track.title), core_title(top.title)) >= 0.9
    artist_match = _artist_score(track.artist, top.artist) >= 0.8
    close_duration = (
        track.duration_seconds is not None
        and top.duration_seconds is not None
        and abs(track.duration_seconds - top.duration_seconds) <= 6
    )
    confident = (
        top.score >= 0.89
        and top.score - second_score >= 0.08
        and title_match
        and artist_match
        and close_duration
        and not (version_flags(track.title) ^ version_flags(top.title))
    )
    return ("auto" if confident else "review"), candidates[:5]
