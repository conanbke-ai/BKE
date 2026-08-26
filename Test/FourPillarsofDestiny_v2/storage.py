from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import logging

from config import SETTINGS
from models import BirthProfile, Candidate

LOGGER = logging.getLogger(__name__)


def _hash(data: dict[str, Any], length: int = 12) -> str:
    raw = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def profile_identity(profile: BirthProfile) -> dict[str, Any]:
    """사용자 원국 캐시의 고유 식별값.

    이름이나 후보 선정 전략은 원국 자체를 바꾸지 않으므로 제외한다.
    """
    time_known = bool(getattr(profile, "birth_time_known", True))
    identity = {
        "calendar_type": profile.calendar_type,
        "is_leap_month": profile.is_leap_month,
        "gender": profile.gender,
        "year": profile.year,
        "month": profile.month,
        "day": profile.day,
        "hour": profile.hour if time_known else None,
        "minute": profile.minute if time_known else None,
        "timezone": profile.timezone,
        "location_id": SETTINGS.fixed_location_id,
    }
    # 기존 출생시간 확정 프로필의 해시를 바꾸지 않는다.
    if not time_known:
        identity["birth_time_known"] = False
    return identity


def profile_id(profile: BirthProfile) -> str:
    digest = _hash(profile_identity(profile), 10)
    if bool(getattr(profile, "birth_time_known", True)):
        time_text = f"{profile.hour:02d}{profile.minute:02d}"
    else:
        time_text = "UNKNOWN"
    return (
        f"{profile.year:04d}-{profile.month:02d}-{profile.day:02d}_"
        f"{time_text}_{profile.gender}_{digest}"
    )


def safe_filename_component(
    value: object,
    default: str = "item",
    max_length: int = 60,
) -> str:
    """Windows에서도 안전한 디렉터리·파일명 구성요소를 만든다."""
    text = str(value or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip(" ._")
    if not text:
        text = default
    return text[:max_length].rstrip(" ._") or default


def profile_storage_name(profile: BirthProfile) -> str:
    """논리 ID는 유지하면서 실제 폴더명 앞에 사용자명을 붙인다."""
    user_name = safe_filename_component(
        profile.name,
        default="사용자",
        max_length=30,
    )
    return f"{user_name}_{profile_id(profile)}"


def _move_directory(
    legacy: Path,
    named: Path,
) -> Path:
    """
    기존 폴더를 새 이름으로 옮긴다.

    Windows에서 직접 rename이 막히면 복사한 뒤 원본 삭제까지 시도한다.
    """
    if named.exists():
        return named
    if not legacy.exists():
        named.mkdir(parents=True, exist_ok=True)
        return named

    named.parent.mkdir(parents=True, exist_ok=True)
    try:
        legacy.rename(named)
        return named
    except OSError:
        shutil.copytree(
            legacy,
            named,
            dirs_exist_ok=True,
        )
        try:
            shutil.rmtree(legacy)
        except OSError as exc:
            LOGGER.warning(
                "기존 디렉터리 삭제 실패: %s (%s)",
                legacy,
                exc,
            )
        return named


def _named_profile_root(
    root: Path,
    profile: BirthProfile,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    named = root / profile_storage_name(profile)
    legacy = root / profile_id(profile)
    return _move_directory(legacy, named)


def _mode_name_from_run_dir(run_name: str) -> str | None:
    if run_name.startswith("lover_"):
        return "연인"
    if run_name.startswith("friend_"):
        return "친구"
    return None


def migrate_existing_personal_report_names(
    profile: BirthProfile,
) -> None:
    """기존 top10_ai_report.html도 새 이름으로 즉시 이전한다."""
    runs_root = _named_profile_root(
        SETTINGS.runs_root,
        profile,
    )
    safe_name = safe_filename_component(
        profile.name,
        default="사용자",
    )
    for run_root in runs_root.iterdir():
        if not run_root.is_dir():
            continue
        mode_name = _mode_name_from_run_dir(run_root.name)
        if mode_name is None:
            continue
        legacy = run_root / "top10_ai_report.html"
        named = run_root / f"{safe_name}_{mode_name}.html"
        if legacy.exists() and not named.exists():
            legacy.replace(named)
        elif legacy.exists() and named.exists():
            legacy.unlink()



def migrate_user_candidate_cache(
    profile: BirthProfile,
) -> None:
    """
    forceteller_profile.json이 가리키는 기존 사용자 원국 캐시 폴더도
    앱 시작 시 <사용자명>_<생년월일>... 형식으로 즉시 이전한다.
    """
    profile_root = _named_profile_root(
        SETTINGS.profiles_root,
        profile,
    )
    manifest_path = profile_root / "forceteller_profile.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return

    data_dir_text = str(
        manifest.get("data_dir", "")
    ).strip()
    if not data_dir_text:
        return

    legacy = Path(data_dir_text)
    birth_date = str(
        manifest.get("birth_date", "")
    ).strip()
    birth_time = str(
        manifest.get("birth_time", "")
    ).strip().replace(":", "")
    gender = str(
        manifest.get("gender", profile.gender)
    ).strip().upper()

    if not birth_date or not birth_time:
        return

    named = (
        SETTINGS.candidates_root
        / (
            f"{safe_filename_component(profile.name, '사용자', 30)}_"
            f"{birth_date}_{birth_time}_{gender}_"
            f"{SETTINGS.fixed_location_id}"
        )
    )

    if legacy != named:
        named = _move_directory(legacy, named)
        manifest["data_dir"] = str(named)
        manifest["forceteller_facts_path"] = str(
            named / "forceteller_facts.json"
        )
        write_json(manifest_path, manifest)



def migrate_profile_roots(
    profile: BirthProfile,
) -> None:
    """
    프로필 목록만 열어도 profiles/runs 이름과 기존 개인 HTML 이름을
    사용자명 기반으로 정리한다.
    """
    _named_profile_root(SETTINGS.profiles_root, profile)
    _named_profile_root(SETTINGS.runs_root, profile)
    migrate_user_candidate_cache(profile)
    migrate_existing_personal_report_names(profile)


def _legacy_candidate_key(
    profile: BirthProfile,
    candidate: Candidate,
) -> str:
    date_text = candidate.birth_date
    time_text = candidate.birth_time.replace(":", "")
    return (
        f"solar_{profile.partner_gender}_{date_text}_{time_text}_"
        f"{SETTINGS.fixed_location_id}"
    )


def candidate_storage_name(
    profile: BirthProfile,
    candidate: Candidate,
) -> str:
    """
    실제 포스텔러 조회 대상의 이름이 생년월일 앞에 오도록 한다.
    """
    name = safe_filename_component(
        profile.name,
        default="사용자",
        max_length=30,
    )
    date_text = candidate.birth_date
    time_text = candidate.birth_time.replace(":", "")
    return (
        f"{name}_{date_text}_{time_text}_"
        f"{profile.partner_gender}_{SETTINGS.fixed_location_id}"
    )


def _update_user_manifest_candidate_path(
    profile: BirthProfile,
    legacy: Path,
    named: Path,
) -> None:
    manifest_path = (
        _named_profile_root(SETTINGS.profiles_root, profile)
        / "forceteller_profile.json"
    )
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return

    old_data_dir = str(manifest.get("data_dir", "")).strip()
    if old_data_dir and Path(old_data_dir) == legacy:
        manifest["data_dir"] = str(named)
        manifest["forceteller_facts_path"] = str(
            named / "forceteller_facts.json"
        )
        write_json(manifest_path, manifest)



def run_identity(profile: BirthProfile) -> dict[str, Any]:
    """현재 적응형 후보 선정 실행을 식별하는 값.

    같은 출생정보라도 연인 모드와 친구 모드는 점수와 HTML 조건이
    다르므로 별도 실행 디렉터리와 AI 캐시를 사용한다.
    """
    return {
        "profile_id": profile_id(profile),
        "partner_gender": profile.partner_gender,
        "relationship_mode": profile.relationship_mode,
        "scoring_version": SETTINGS.scoring_version,
        "run_schema_version": SETTINGS.run_schema_version,
        "candidate_selection_version": SETTINGS.candidate_selection_version,
        "age_range_policy_version": SETTINGS.age_range_policy_version,
        "dynamic_age_range_enabled": SETTINGS.dynamic_age_range_enabled,
        "parser_version": SETTINGS.parser_version,
        "collector_version": SETTINGS.collector_version,
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
        "adaptive_initial_count": SETTINGS.adaptive_initial_count,
        "adaptive_step_count": SETTINGS.adaptive_step_count,
        "adaptive_max_count": SETTINGS.adaptive_max_count,
        "adaptive_stability_rounds": (
            SETTINGS.adaptive_stability_rounds
        ),
        "adaptive_require_stability": (
            SETTINGS.adaptive_require_stability
        ),
        "ai_top_n": SETTINGS.ai_top_n,
    }


def run_id(profile: BirthProfile) -> str:
    return (
        f"{profile.relationship_mode}_{profile.partner_gender}_"
        f"{_hash(run_identity(profile), 12)}"
    )


def profile_dir(profile: BirthProfile) -> Path:
    path = _named_profile_root(
        SETTINGS.profiles_root,
        profile,
    )
    _named_profile_root(
        SETTINGS.runs_root,
        profile,
    )
    migrate_existing_personal_report_names(profile)
    return path


def project_dir(profile: BirthProfile) -> Path:
    migrate_profile_roots(profile)
    profile_root = _named_profile_root(
        SETTINGS.runs_root,
        profile,
    )
    path = profile_root / run_id(profile)
    (path / "errors").mkdir(parents=True, exist_ok=True)
    return path


def candidate_key(
    profile: BirthProfile,
    candidate: Candidate,
) -> str:
    return candidate_storage_name(profile, candidate)


def candidate_dir(
    profile: BirthProfile,
    candidate: Candidate,
) -> Path:
    named = (
        SETTINGS.candidates_root
        / candidate_storage_name(profile, candidate)
    )
    legacy = (
        SETTINGS.candidates_root
        / _legacy_candidate_key(profile, candidate)
    )
    path = _move_directory(legacy, named)
    _update_user_manifest_candidate_path(
        profile,
        legacy,
        named,
    )
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
