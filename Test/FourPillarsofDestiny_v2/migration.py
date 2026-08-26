from __future__ import annotations

import shutil
from pathlib import Path

from config import SETTINGS
from logging_utils import LOGGER
from storage import read_json

REQUIRED = ("result.png", "result.html", "result.txt", "network.json", "metadata.json")


def _completeness(path: Path) -> int:
    return sum((path / name).exists() for name in REQUIRED)


def migrate_legacy_output() -> dict[str, int]:
    """기존 output/<프로필>/candidates 자료를 전역 data/candidates로 병합한다."""
    stats = {"found": 0, "copied": 0, "merged": 0, "skipped": 0}
    root = SETTINGS.legacy_output_root
    if not root.exists():
        return stats

    for old_candidate in root.glob("*/candidates/*"):
        if not old_candidate.is_dir():
            continue
        stats["found"] += 1
        metadata = read_json(old_candidate / "metadata.json") or {}
        birth_date = metadata.get("birth_date")
        birth_time = str(metadata.get("birth_time", "")).replace(":", "")
        gender = metadata.get("gender", "M")
        location_id = metadata.get("location_id", SETTINGS.fixed_location_id)
        if not birth_date or not birth_time:
            LOGGER.warning("마이그레이션 건너뜀(메타데이터 부족): %s", old_candidate)
            stats["skipped"] += 1
            continue
        key = f"solar_{gender}_{birth_date}_{birth_time}_{location_id}"
        target = SETTINGS.candidates_root / key
        if not target.exists():
            shutil.copytree(old_candidate, target)
            stats["copied"] += 1
            continue
        # 기존 전역 폴더가 있으면 없는 파일만 병합한다.
        changed = False
        for source_file in old_candidate.iterdir():
            if not source_file.is_file():
                continue
            target_file = target / source_file.name
            if not target_file.exists() or source_file.stat().st_size > target_file.stat().st_size:
                shutil.copy2(source_file, target_file)
                changed = True
        stats["merged" if changed else "skipped"] += 1
    LOGGER.info("기존 데이터 마이그레이션 결과: %s", stats)
    return stats


if __name__ == "__main__":
    print(migrate_legacy_output())
