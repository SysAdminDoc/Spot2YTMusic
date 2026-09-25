"""Editable, durable decisions for the graphical review screen."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .transfer import VIDEO_ID, ReviewError


class ReviewStore:
    def __init__(self, plan_path: Path) -> None:
        self.plan_path = plan_path
        self.review_path = plan_path.with_suffix(".review.csv")
        self.plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if self.plan.get("schema") != 1 or not isinstance(self.plan.get("entries"), list):
            raise ReviewError("Unsupported plan format")
        with self.review_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            self.columns = list(reader.fieldnames or [])
            self.rows = list(reader)
        if not {"Key", "Decision", "Chosen video ID"}.issubset(self.columns):
            raise ReviewError("Review CSV is missing required columns")
        self.by_key = {row["Key"]: row for row in self.rows}
        plan_keys = {entry["track"]["key"] for entry in self.plan["entries"]}
        if (
            len(self.by_key) != len(self.rows)
            or len(plan_keys) != len(self.plan["entries"])
            or set(self.by_key) != plan_keys
        ):
            raise ReviewError("Review CSV keys do not match the plan")

    @property
    def playlists(self) -> list[str]:
        return list(dict.fromkeys(entry["track"]["collection"] for entry in self.plan["entries"]))

    @staticmethod
    def is_resolved(row: dict) -> bool:
        decision = (row["Decision"] or "").strip().casefold()
        return decision == "skip" or (
            decision == "use" and bool(VIDEO_ID.fullmatch((row["Chosen video ID"] or "").strip()))
        )

    def counts(self) -> Counter[str]:
        return Counter(
            (row["Decision"] or "").strip().casefold() if self.is_resolved(row) else "review"
            for row in self.rows
        )

    def unresolved(self) -> int:
        return sum(not self.is_resolved(row) for row in self.rows)

    def decide(self, key: str, decision: str, video_id: str = "") -> None:
        if key not in self.by_key:
            raise ReviewError("Song is missing from the review sheet")
        if decision not in {"use", "skip"}:
            raise ReviewError("Choose use or skip")
        if decision == "use" and not VIDEO_ID.fullmatch(video_id):
            raise ReviewError("Enter a valid 11-character YouTube video ID")
        row = self.by_key[key]
        old = (row["Decision"], row["Chosen video ID"])
        row["Decision"] = decision
        row["Chosen video ID"] = video_id if decision == "use" else ""
        temporary = self.review_path.with_suffix(self.review_path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8-sig", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=self.columns)
                writer.writeheader()
                writer.writerows(self.rows)
            temporary.replace(self.review_path)
        except OSError:
            row["Decision"], row["Chosen video ID"] = old
            temporary.unlink(missing_ok=True)
            raise
