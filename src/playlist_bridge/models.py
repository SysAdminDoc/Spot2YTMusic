"""Small, serializable records used by the transfer plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256


@dataclass(frozen=True)
class Track:
    collection: str
    position: int
    title: str
    artist: str
    album: str = ""
    duration_seconds: int | None = None
    spotify_url: str = ""
    source_type: str = "Spotify catalog"

    @property
    def key(self) -> str:
        raw = "\x1f".join(
            (
                self.collection,
                str(self.position),
                self.title,
                self.artist,
                self.album,
                str(self.duration_seconds),
                self.spotify_url,
            )
        )
        return sha256(raw.encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> dict:
        return asdict(self) | {"key": self.key}


@dataclass(frozen=True)
class Candidate:
    video_id: str
    title: str
    artist: str
    album: str
    duration_seconds: int | None
    result_type: str
    score: float
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanEntry:
    track: Track
    status: str
    selected_video_id: str = ""
    candidates: list[Candidate] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "track": self.track.to_dict(),
            "status": self.status,
            "selected_video_id": self.selected_video_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "note": self.note,
        }
