from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from config import SETTINGS
from models import BirthProfile, Candidate


def _hash(data: dict[str, Any], length: int = 12) -> str:
    raw = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def profile_identity(profile: BirthProfile) -> dict[str, Any]:
    # 사용자 원국 캐시는 출생정보·성별·포스텔러 위치 기준으로 식별한다.
    return {
        "calendar_type": profile.calendar_type,
        "is_leap_month": profile.is_leap_month,
        "gender": profile.gender,
        "year": profile.year,
        "month": profile.month,
        "day": profile.day,
        "hour": profile.hour,
        "minute": profile.minute,
        "timezone": profile.timezone,
        "location_id": SETTINGS.fixed_location_id,
    }


def profile_id(profile: BirthProfile) -> str:
    digest = _hash(profile_identity(profile), 10)
    return (
        f"{profile.year:04d}-{profile.month:02d}-{profile.day:02d}_"
        f"{profile.hour:02d}{profile.minute:02d}_{profile.gender}_{digest}"
    )


def run_identity(profile: BirthProfile) -> dict[str, Any]:
    return {
        "profile_id": profile_id(profile),
        "partner_gender": profile.partner_gender,
        "scoring_version": SETTINGS.scoring_version,
        "run_schema_version": SETTINGS.run_schema_version,
        "candidate_selection_version": SETTINGS.candidate_selection_version,
        "max_older_years": SETTINGS.max_older_years,
        "max_younger_years": SETTINGS.max_younger_years,
        "full_range_time_scan": SETTINGS.full_range_time_scan,
        "location_id": SETTINGS.fixed_location_id,
        "location_longitude": SETTINGS.fixed_location_longitude,
        "standard_meridian_longitude": (
            SETTINGS.standard_meridian_longitude
        ),
        "solar_time_extra_minutes": SETTINGS.solar_time_extra_minutes,
        "location_correction_enabled": (
            SETTINGS.candidate_location_correction_enabled
        ),
        "strict_local_forceteller_chart_match": (
            SETTINGS.strict_local_forceteller_chart_match
        ),
        "collect_count": SETTINGS.collect_count,
        "ai_top_n": SETTINGS.ai_top_n,
    }


def run_id(profile: BirthProfile) -> str:
    return f"{profile.partner_gender}_{_hash(run_identity(profile), 12)}"


def profile_dir(profile: BirthProfile) -> Path:
    path = SETTINGS.profiles_root / profile_id(profile)
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_dir(profile: BirthProfile) -> Path:
    path = SETTINGS.runs_root / profile_id(profile) / run_id(profile)
    (path / "errors").mkdir(parents=True, exist_ok=True)
    return path


def candidate_key(
    profile: BirthProfile,
    candidate: Candidate,
) -> str:
    date_text = candidate.birth_date
    time_text = candidate.birth_time.replace(":", "")
    return (
        f"solar_{profile.partner_gender}_{date_text}_{time_text}_"
        f"{SETTINGS.fixed_location_id}"
    )


def candidate_dir(
    profile: BirthProfile,
    candidate: Candidate,
) -> Path:
    path = SETTINGS.candidates_root / candidate_key(profile, candidate)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
