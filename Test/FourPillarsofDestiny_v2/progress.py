from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from storage import read_json, write_json


class ProgressTracker:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = read_json(path) or {
            "stage": "not_started",
            "updated_at": None,
            "candidates": {},
        }

    def set_stage(self, stage: str) -> None:
        self.data["stage"] = stage
        self._save()

    def mark(self, candidate_id: str, status: str, **extra: Any) -> None:
        record = self.data.setdefault("candidates", {}).setdefault(candidate_id, {})
        record.update({"status": status, "updated_at": datetime.now().isoformat(timespec="seconds"), **extra})
        self._save()

    def status(self, candidate_id: str) -> str | None:
        return self.data.get("candidates", {}).get(candidate_id, {}).get("status")

    def failed_ids(self) -> list[str]:
        return [
            candidate_id
            for candidate_id, value in self.data.get("candidates", {}).items()
            if value.get("status") == "failed"
        ]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in self.data.get("candidates", {}).values():
            status = value.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _save(self) -> None:
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        write_json(self.path, self.data)
