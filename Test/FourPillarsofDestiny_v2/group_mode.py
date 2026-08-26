from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from ai_reporter import AIQuotaError, AIReportFormatError
from bazi_engine import profile_to_solar
from calendar_labels import (
    western_zodiac_from_date,
    zodiac_from_year_pillar,
)
from collector import (
    USER_FORCETELLER_MANIFEST,
    ensure_profiles_forceteller_charts,
    load_user_forceteller_chart,
)
from config import SETTINGS
from forceteller_parser import (
    compact_facts_for_ai,
    ensure_forceteller_facts,
)
from logging_utils import LOGGER
from models import BirthProfile, Chart
from scoring import score_compatibility
from storage import (
    profile_dir,
    profile_id,
    read_json,
    safe_filename_component,
    write_json,
)
from validation import validate_candidate_directory


_GROUP_MODES = {"lover", "friend"}
_GROUP_MODE_NAMES = {"lover": "연인", "friend": "친구"}
_GROUP_MODE_ALIASES = {
    "lover": "lover",
    "love": "lover",
    "l": "lover",
    "연인": "lover",
    "연애": "lover",
    "friend": "friend",
    "friendship": "friend",
    "f": "friend",
    "친구": "friend",
    "우정": "friend",
}


_GROUP_STEM_READING = {
    "甲": "갑목", "乙": "을목", "丙": "병화", "丁": "정화", "戊": "무토",
    "己": "기토", "庚": "경금", "辛": "신금", "壬": "임수", "癸": "계수",
}
_GROUP_BRANCH_READING = {
    "子": "자수", "丑": "축토", "寅": "인목", "卯": "묘목", "辰": "진토",
    "巳": "사화", "午": "오화", "未": "미토", "申": "신금", "酉": "유금",
    "戌": "술토", "亥": "해수",
}
_GROUP_HANJA_READING = {
    **_GROUP_STEM_READING,
    **_GROUP_BRANCH_READING,
    "木": "목", "火": "화", "土": "토", "金": "금", "水": "수",
}
_GROUP_HANJA_PATTERN = re.compile(r"[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥木火土金水]")


def _group_pillar_reading(value: str) -> str:
    if len(value) < 2:
        return value
    return (
        f"{value}("
        f"{_GROUP_HANJA_READING.get(value[0], value[0])}·"
        f"{_GROUP_HANJA_READING.get(value[1], value[1])})"
    )


def _group_annotate_hanja(value: object) -> str:
    text = str(value or "")
    return _GROUP_HANJA_PATTERN.sub(
        lambda m: (
            m.group(0)
            if re.match(r"^\([^)]*\)", text[m.end():])
            else f"{m.group(0)}({_GROUP_HANJA_READING[m.group(0)]})"
        ),
        text,
    )


def _normalize_group_mode(value: str) -> str:
    normalized = _GROUP_MODE_ALIASES.get(str(value or "").strip().lower())
    if normalized is None:
        raise ValueError(f"지원하지 않는 그룹 관계 모드입니다: {value!r}")
    return normalized


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", value.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:40] or "group"


def _hash_payload(value: object, length: int = 12) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def _group_root() -> Path:
    SETTINGS.groups_root.mkdir(parents=True, exist_ok=True)
    return SETTINGS.groups_root


def _group_path(group_id: str) -> Path:
    path = _group_root() / group_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _member_identity(profile: BirthProfile, name: str) -> dict[str, Any]:
    identity = {
        "name": name,
        "profile_id": profile_id(profile),
        "gender": profile.gender,
        "calendar_type": profile.calendar_type,
        "is_leap_month": profile.is_leap_month,
        "year": profile.year,
        "month": profile.month,
        "day": profile.day,
        "hour": profile.hour,
        "minute": profile.minute,
    }
    # 기존 출생시간 확정 그룹 ID는 유지한다.
    if not profile.birth_time_known:
        identity["hour"] = None
        identity["minute"] = None
        identity["birth_time_known"] = False
    return identity


def _build_group_id(
    group_name: str,
    relationship_mode: str,
    profiles: list[BirthProfile],
) -> str:
    identities = sorted(
        (_member_identity(profile, profile.name) for profile in profiles),
        key=lambda item: (
            item["name"],
            item["profile_id"],
        ),
    )
    digest = _hash_payload(
        {
            "mode": relationship_mode,
            "members": identities,
            "scoring_version": SETTINGS.scoring_version,
            "schema": SETTINGS.group_schema_version,
        }
    )
    return f"{_safe_slug(group_name)}_{relationship_mode}_{digest}"


def _member_id(index: int, profile: BirthProfile) -> str:
    return f"m{index:02d}_{profile_id(profile)}"


def _parse_gender(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "f": "F",
        "female": "F",
        "여": "F",
        "여성": "F",
        "여자": "F",
        "m": "M",
        "male": "M",
        "남": "M",
        "남성": "M",
        "남자": "M",
    }
    if normalized not in aliases:
        raise ValueError(f"성별은 F/M 또는 여성/남성으로 입력하세요: {value!r}")
    return aliases[normalized]


def _parse_calendar(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "s": "solar",
        "solar": "solar",
        "양": "solar",
        "양력": "solar",
        "l": "lunar",
        "lunar": "lunar",
        "음": "lunar",
        "음력": "lunar",
    }
    if normalized not in aliases:
        raise ValueError(f"달력은 S/L 또는 양력/음력으로 입력하세요: {value!r}")
    return aliases[normalized]


def _parse_bool(value: str, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized in {"y", "yes", "1", "true", "윤", "윤달"}:
        return True
    if normalized in {"n", "no", "0", "false", "평", "평달"}:
        return False
    raise ValueError(f"윤달 여부는 Y/N으로 입력하세요: {value!r}")


def _parse_birth_date(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(
        r"\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s*",
        str(value or ""),
    )
    if not match:
        raise ValueError(f"생년월일 형식은 YYYY-MM-DD입니다: {value!r}")
    year, month, day = map(int, match.groups())
    if not 1900 <= year <= 2100:
        raise ValueError(f"출생연도 범위는 1900~2100입니다: {year}")
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ValueError(f"유효하지 않은 생년월일입니다: {value!r}")
    return year, month, day


def _parse_birth_time(value: str) -> tuple[int, int, bool]:
    normalized = str(value or "").strip().lower()
    unknown_aliases = {
        "", "unknown", "unk", "none", "null", "?", "x",
        "모름", "미상", "모른다", "시간모름", "출생시간모름",
    }
    if normalized in unknown_aliases:
        # 날짜 변환용 안전한 임시값이다. 실제 궁합 계산에서는
        # 12개 시진 시나리오로 확장하므로 12:00을 확정 시각으로 쓰지 않는다.
        return 12, 0, False

    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        raise ValueError(
            "출생시간 형식은 HH:MM 또는 UNKNOWN/모름입니다: "
            f"{value!r}"
        )
    hour, minute = map(int, match.groups())
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"유효하지 않은 출생시간입니다: {value!r}")
    return hour, minute, True


def _build_profile_from_values(
    values: dict[str, str],
    relationship_mode: str,
) -> BirthProfile:
    name = str(values.get("name", "")).strip()
    if not name:
        raise ValueError("이름 또는 식별명이 비어 있습니다.")
    gender = _parse_gender(values.get("gender", ""))
    calendar_type = _parse_calendar(values.get("calendar_type", ""))
    year, month, day = _parse_birth_date(values.get("birth_date", ""))
    hour, minute, birth_time_known = _parse_birth_time(
        values.get("birth_time", "")
    )
    is_leap_month = (
        _parse_bool(values.get("is_leap_month", ""), False)
        if calendar_type == "lunar"
        else False
    )

    profile = BirthProfile(
        name=name,
        gender=gender,
        calendar_type=calendar_type,
        is_leap_month=is_leap_month,
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        location=SETTINGS.fixed_location_text,
        timezone="Asia/Seoul",
        partner_gender="M" if gender == "F" else "F",
        relationship_mode=relationship_mode,
        birth_time_known=birth_time_known,
    )

    # 음력 윤달과 날짜 오류를 가능한 한 입력 단계에서 확인한다.
    try:
        profile_to_solar(profile)
    except Exception as exc:
        raise ValueError(
            f"{name}의 양력/음력 생년월일시를 변환할 수 없습니다: {exc}"
        ) from exc
    return profile


_HEADER_ALIASES = {
    "name": {"name", "이름", "식별명", "성명"},
    "gender": {"gender", "성별"},
    "calendar_type": {"calendar", "calendar_type", "달력", "양음력"},
    "birth_date": {"birth_date", "date", "생년월일", "출생일"},
    "birth_time": {"birth_time", "time", "출생시간", "생시"},
    "is_leap_month": {"is_leap_month", "leap", "윤달", "윤달여부"},
}


def _header_key(value: str) -> str | None:
    normalized = str(value or "").strip().lower()
    for key, aliases in _HEADER_ALIASES.items():
        if normalized in aliases:
            return key
    return None


def _split_input_lines(lines: list[str]) -> list[list[str]]:
    meaningful = [line.strip() for line in lines if line.strip()]
    if not meaningful:
        return []
    first = meaningful[0]
    delimiter = "|"
    if "\t" in first:
        delimiter = "\t"
    elif "|" in first:
        delimiter = "|"
    elif "," in first:
        delimiter = ","
    reader = csv.reader(meaningful, delimiter=delimiter)
    return [[cell.strip() for cell in row] for row in reader]


def parse_group_profile_lines(
    lines: list[str],
    relationship_mode: str,
) -> list[BirthProfile]:
    mode = _normalize_group_mode(relationship_mode)
    rows = _split_input_lines(lines)
    if not rows:
        raise ValueError("입력된 구성원 정보가 없습니다.")

    header = [_header_key(cell) for cell in rows[0]]
    has_header = all(
        key in header
        for key in (
            "name",
            "gender",
            "calendar_type",
            "birth_date",
            "birth_time",
        )
    )

    profiles: list[BirthProfile] = []
    data_rows = rows[1:] if has_header else rows
    for row_number, row in enumerate(data_rows, 2 if has_header else 1):
        if not row:
            continue
        try:
            if has_header:
                values = {
                    key: row[index] if index < len(row) else ""
                    for index, key in enumerate(header)
                    if key is not None
                }
            else:
                if len(row) < 5:
                    raise ValueError(
                        "필드는 이름|성별|양력/음력|YYYY-MM-DD|HH:MM 또는 UNKNOWN"
                        "|윤달Y/N 순서이며 최소 5개가 필요합니다."
                    )
                values = {
                    "name": row[0],
                    "gender": row[1],
                    "calendar_type": row[2],
                    "birth_date": row[3],
                    "birth_time": row[4],
                    "is_leap_month": row[5] if len(row) > 5 else "N",
                }
            profiles.append(_build_profile_from_values(values, mode))
        except ValueError as exc:
            raise ValueError(f"{row_number}번째 입력 행 오류: {exc}") from exc

    if len(profiles) < 2:
        raise ValueError("서로 순위를 매기려면 최소 2명을 입력해야 합니다.")
    if len(profiles) > SETTINGS.group_max_members:
        raise ValueError(
            f"그룹 모드는 최대 {SETTINGS.group_max_members}명까지 지원합니다."
        )

    names = [profile.name for profile in profiles]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValueError(
            "구성원 이름·식별명은 서로 달라야 합니다: "
            + ", ".join(duplicate_names)
        )
    return profiles



def parse_single_profile_lines(
    lines: list[str],
    relationship_mode: str,
) -> BirthProfile:
    """1:1 지정 궁합의 상대방 한 명을 그룹 입력 형식으로 읽는다."""
    mode = _normalize_group_mode(relationship_mode)
    rows = _split_input_lines(lines)
    if not rows:
        raise ValueError("입력된 상대방 정보가 없습니다.")

    header = [_header_key(cell) for cell in rows[0]]
    has_header = all(
        key in header
        for key in (
            "name",
            "gender",
            "calendar_type",
            "birth_date",
            "birth_time",
        )
    )
    data_rows = rows[1:] if has_header else rows
    meaningful_rows = [row for row in data_rows if row]

    if len(meaningful_rows) != 1:
        raise ValueError(
            "지정 1인 궁합 모드에서는 상대방 정보를 정확히 한 명만 "
            "입력해야 합니다."
        )

    row = meaningful_rows[0]
    if has_header:
        values = {
            key: row[index] if index < len(row) else ""
            for index, key in enumerate(header)
            if key is not None
        }
    else:
        if len(row) < 5:
            raise ValueError(
                "필드는 이름|성별|양력/음력|YYYY-MM-DD|HH:MM 또는 UNKNOWN|윤달Y/N "
                "순서이며 최소 5개가 필요합니다."
            )
        values = {
            "name": row[0],
            "gender": row[1],
            "calendar_type": row[2],
            "birth_date": row[3],
            "birth_time": row[4],
            "is_leap_month": row[5] if len(row) > 5 else "N",
        }

    return _build_profile_from_values(values, mode)


def load_single_profile_file(
    path: Path,
    relationship_mode: str,
) -> BirthProfile:
    if not path.exists():
        raise ValueError(f"상대방 입력 파일이 없습니다: {path}")

    return parse_single_profile_lines(
        path.read_text(encoding="utf-8-sig").splitlines(),
        relationship_mode,
    )


def group_path(group_id: str) -> Path:
    """그룹·지정 1인 궁합 결과 폴더의 공개 접근 함수."""
    return _group_path(group_id)


def profiles_from_definition(
    definition: dict[str, Any],
) -> list[tuple[str, BirthProfile]]:
    """저장된 그룹/1:1 정의를 BirthProfile 목록으로 변환한다."""
    return _profiles_from_definition(definition)


def load_group_rankings(
    definition: dict[str, Any],
) -> dict[str, Any]:
    """그룹/1:1 궁합의 저장된 순위 결과를 읽는다."""
    return _load_group_rankings(definition)



def load_group_profiles_file(
    path: Path,
    relationship_mode: str,
) -> list[BirthProfile]:
    if not path.exists():
        raise ValueError(f"그룹 입력 파일이 없습니다: {path}")
    return parse_group_profile_lines(
        path.read_text(encoding="utf-8-sig").splitlines(),
        relationship_mode,
    )


def collect_group_profiles_interactive(
    relationship_mode: str,
) -> list[BirthProfile]:
    print("=== 다중 사주 입력 ===")
    print(
        "한 줄에 다음 순서로 입력하세요. 구분자는 |, 쉼표, 탭을 지원합니다."
    )
    print("이름|성별(F/M)|양력/음력(S/L)|YYYY-MM-DD|HH:MM|윤달(Y/N)")
    print("예: 배경은|F|S|1994-12-07|05:30|N")
    print("모두 입력한 뒤 END를 입력하세요.")

    lines: list[str] = []
    while True:
        raw = input().strip()
        if raw.upper() == "END":
            break
        if raw:
            lines.append(raw)
    return parse_group_profile_lines(lines, relationship_mode)


def create_group_definition(
    group_name: str,
    relationship_mode: str,
    profiles: list[BirthProfile],
) -> dict[str, Any]:
    mode = _normalize_group_mode(relationship_mode)
    group_id = _build_group_id(group_name, mode, profiles)
    members = [
        {
            "member_id": _member_id(index, profile),
            "profile_id": profile_id(profile),
            "profile": asdict(profile),
        }
        for index, profile in enumerate(profiles, 1)
    ]
    definition = {
        "group_id": group_id,
        "group_name": group_name.strip() or "다중 궁합",
        "relationship_mode": mode,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scoring_version": SETTINGS.scoring_version,
        "group_schema_version": SETTINGS.group_schema_version,
        "members": members,
    }
    write_json(_group_path(group_id) / "group.json", definition)
    return definition


def _profile_from_payload(payload: dict[str, Any]) -> BirthProfile:
    values = dict(payload)
    values["relationship_mode"] = _normalize_group_mode(
        values.get("relationship_mode", "lover")
    )
    values.setdefault(
        "partner_gender",
        "M" if values.get("gender", "F") == "F" else "F",
    )
    values.setdefault("birth_time_known", True)
    return BirthProfile(**values)


def load_group_definition(group_id: str | None = None) -> dict[str, Any]:
    if group_id:
        data = read_json(_group_root() / group_id / "group.json")
        if not isinstance(data, dict):
            raise RuntimeError(f"그룹 ID를 찾을 수 없습니다: {group_id}")
        return data

    candidates = list(_group_root().glob("*/group.json"))
    if not candidates:
        raise RuntimeError("저장된 그룹이 없습니다. 먼저 group 모드를 실행하세요.")
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    data = read_json(latest)
    if not isinstance(data, dict):
        raise RuntimeError(f"그룹 파일을 읽을 수 없습니다: {latest}")
    return data


def _profiles_from_definition(
    definition: dict[str, Any],
) -> list[tuple[str, BirthProfile]]:
    result: list[tuple[str, BirthProfile]] = []
    mode = _normalize_group_mode(definition.get("relationship_mode", ""))
    for item in definition.get("members", []):
        profile_data = item.get("profile")
        if not isinstance(profile_data, dict):
            raise RuntimeError("그룹 구성원 프로필 형식이 올바르지 않습니다.")
        profile_data = dict(profile_data)
        profile_data["relationship_mode"] = mode
        result.append((str(item["member_id"]), _profile_from_payload(profile_data)))
    if len(result) < 2:
        raise RuntimeError("그룹 구성원이 2명보다 적습니다.")
    return result


def _chart_dict(chart: Chart) -> dict[str, Any]:
    return asdict(chart)


def _facts_and_data_dir(profile: BirthProfile) -> tuple[dict[str, Any], Path]:
    manifest = read_json(profile_dir(profile) / USER_FORCETELLER_MANIFEST)
    if not isinstance(manifest, dict):
        raise RuntimeError(f"{profile.name}의 포스텔러 manifest가 없습니다.")
    data_dir = Path(str(manifest.get("data_dir", "")).strip())
    if not data_dir.exists():
        raise RuntimeError(f"{profile.name}의 포스텔러 원본 폴더가 없습니다.")
    quality = validate_candidate_directory(data_dir)
    if not quality.valid:
        raise RuntimeError(
            f"{profile.name}의 포스텔러 원본 검증 실패: "
            + ", ".join(quality.warnings)
        )
    return ensure_forceteller_facts(data_dir), data_dir


def _solar_date(profile: BirthProfile) -> date:
    solar = profile_to_solar(profile)
    return date(solar.getYear(), solar.getMonth(), solar.getDay())


def build_group_rankings(
    definition: dict[str, Any],
    charts_by_profile_id: dict[str, Chart],
) -> dict[str, Any]:
    members = _profiles_from_definition(definition)
    mode = _normalize_group_mode(definition["relationship_mode"])

    member_records: list[dict[str, Any]] = []
    chart_by_member: dict[str, Chart] = {}
    profile_by_member: dict[str, BirthProfile] = {}

    for member_id, profile in members:
        chart = charts_by_profile_id.get(profile_id(profile))
        if chart is None:
            raise RuntimeError(f"{profile.name}의 포스텔러 원국이 없습니다.")
        facts, data_dir = _facts_and_data_dir(profile)
        chart_by_member[member_id] = chart
        profile_by_member[member_id] = profile
        born = _solar_date(profile)
        member_records.append(
            {
                "member_id": member_id,
                "profile_id": profile_id(profile),
                "name": profile.name,
                "gender": profile.gender,
                "calendar_type": profile.calendar_type,
                "birth_datetime": (
                    f"{profile.year:04d}-{profile.month:02d}-{profile.day:02d} "
                    + (
                        f"{profile.hour:02d}:{profile.minute:02d}"
                        if profile.birth_time_known
                        else "UNKNOWN"
                    )
                ),
                "birth_time_known": profile.birth_time_known,
                "solar_birth_date": born.isoformat(),
                "chart": _chart_dict(chart),
                "zodiac": zodiac_from_year_pillar(chart.year_pillar),
                "western_zodiac": western_zodiac_from_date(born),
                "forceteller_data_dir": str(data_dir),
                "facts_summary": facts.get("summary", {}),
            }
        )

    rankings_by_user: list[dict[str, Any]] = []
    directed_scores: dict[tuple[str, str], float] = {}

    for user_id, user_profile in members:
        user_chart = chart_by_member[user_id]
        rankings: list[dict[str, Any]] = []

        for target_id, target_profile in members:
            if target_id == user_id:
                continue
            target_chart = chart_by_member[target_id]
            score, evidence = score_compatibility(
                user_chart,
                target_chart.year_pillar,
                target_chart.month_pillar,
                target_chart.day_pillar,
                target_chart.hour_pillar,
                user_profile.gender,
                mode,
                candidate_chart=target_chart,
            )
            directed_scores[(user_id, target_id)] = score.total
            rankings.append(
                {
                    "target_id": target_id,
                    "target_name": target_profile.name,
                    "score": asdict(score),
                    "evidence": [asdict(item) for item in evidence],
                    "brief_explanation": _brief_compatibility_explanation(
                        [asdict(item) for item in evidence],
                        mode,
                    ),
                }
            )

        rankings.sort(
            key=lambda item: (
                float(item["score"]["total"]),
                float(item["score"].get("internal_stability", 0.0)),
                item["target_name"],
            ),
            reverse=True,
        )
        for rank, item in enumerate(rankings, 1):
            item["rank"] = rank

        rankings_by_user.append(
            {
                "user_id": user_id,
                "user_name": user_profile.name,
                "rankings": rankings,
            }
        )

    mutual_pairs: list[dict[str, Any]] = []
    member_ids = [member_id for member_id, _ in members]
    name_by_id = {
        member_id: profile.name
        for member_id, profile in members
    }
    for left_index, left_id in enumerate(member_ids):
        for right_id in member_ids[left_index + 1:]:
            left_to_right = directed_scores[(left_id, right_id)]
            right_to_left = directed_scores[(right_id, left_id)]
            mutual_pairs.append(
                {
                    "left_id": left_id,
                    "left_name": name_by_id[left_id],
                    "right_id": right_id,
                    "right_name": name_by_id[right_id],
                    "left_to_right": left_to_right,
                    "right_to_left": right_to_left,
                    "average_score": round(
                        (left_to_right + right_to_left) / 2.0,
                        1,
                    ),
                    "lower_score": round(min(left_to_right, right_to_left), 1),
                    "direction_gap": round(abs(left_to_right - right_to_left), 1),
                }
            )
    mutual_pairs.sort(
        key=lambda item: (
            item["average_score"],
            item["lower_score"],
            -item["direction_gap"],
        ),
        reverse=True,
    )
    for rank, item in enumerate(mutual_pairs, 1):
        item["rank"] = rank

    result = {
        "group_id": definition["group_id"],
        "group_name": definition["group_name"],
        "relationship_mode": mode,
        "mode_name": _GROUP_MODE_NAMES[mode],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scoring_version": SETTINGS.scoring_version,
        "score_direction": (
            "각 구성원을 기준 사용자로 두고 다른 사람을 후보로 평가한 방향성 점수"
        ),
        "member_count": len(member_records),
        "members": member_records,
        "rankings_by_user": rankings_by_user,
        "mutual_pairs": mutual_pairs,
    }
    write_json(
        _group_path(definition["group_id"]) / "group_rankings.json",
        result,
    )
    return result


def _load_group_rankings(definition: dict[str, Any]) -> dict[str, Any]:
    data = read_json(
        _group_path(definition["group_id"]) / "group_rankings.json"
    )
    if not isinstance(data, dict):
        raise RuntimeError("그룹 순위 결과가 없습니다. 먼저 group 모드를 실행하세요.")
    if data.get("scoring_version") != SETTINGS.scoring_version:
        raise RuntimeError(
            "현재 점수 공식과 그룹 순위 파일의 버전이 다릅니다. "
            "group 모드를 다시 실행하세요."
        )
    return data



def _evidence_reason_text(item: dict[str, Any]) -> str:
    category = str(item.get("category", "관계 요소")).strip()
    relation = str(item.get("relation", "")).strip()
    evidence = str(item.get("evidence", "")).strip()
    core = f"{category}의 {relation}" if relation else category
    if evidence:
        core += f" ({evidence})"
    return _group_annotate_hanja(core)


def _brief_compatibility_explanation(
    evidence: list[dict[str, Any]],
    mode: str,
) -> str:
    positive, negative = _positive_negative_evidence(evidence)
    positive_text = ", ".join(
        _evidence_reason_text(item) for item in positive[:2]
    )
    negative_text = ", ".join(
        _evidence_reason_text(item) for item in negative[:2]
    )
    relation_word = "우정" if mode == "friend" else "관계"
    if positive_text:
        good = f"잘 맞는 이유는 {positive_text}가 긍정적으로 작용하기 때문입니다."
    else:
        good = f"{relation_word}을 강하게 끌어올리는 단일 가점보다는 전체 균형으로 평가됐습니다."
    if negative_text:
        caution = f"다만 {negative_text}에서는 속도나 표현 방식을 조율할 필요가 있습니다."
    else:
        caution = "뚜렷한 큰 충돌 근거는 적지만 실제 소통 방식은 별도로 확인하는 편이 좋습니다."
    return good + " " + caution


def _chart_html(chart: dict[str, Any]) -> str:
    rows = (
        ("연주", chart["year_pillar"]),
        ("월주", chart["month_pillar"]),
        ("일주", chart["day_pillar"]),
        ("시주", chart["hour_pillar"]),
    )
    cells = "".join(
        f"<div><span>{label}</span>"
        f"<strong>{html.escape(value)}</strong>"
        f"<small>{html.escape(_group_pillar_reading(value))}</small></div>"
        for label, value in rows
    )
    return f'<div class="chart-grid">{cells}</div>'


def _positive_negative_evidence(
    evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    positive = sorted(
        (item for item in evidence if float(item.get("score", 0)) > 0),
        key=lambda item: float(item.get("score", 0)),
        reverse=True,
    )[:3]
    negative = sorted(
        (item for item in evidence if float(item.get("score", 0)) < 0),
        key=lambda item: float(item.get("score", 0)),
    )[:3]
    return positive, negative


def _ai_index(ai_report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ai_report, dict):
        return {}
    return {
        str(item.get("member_id")): item
        for item in ai_report.get("users", [])
        if isinstance(item, dict)
    }


def write_group_reports(
    definition: dict[str, Any],
    rankings: dict[str, Any],
    ai_report: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    root = _group_path(definition["group_id"])
    mode_name = rankings["mode_name"]
    title = f"{rankings['group_name']} · {mode_name} 다중 궁합 순위"
    members = {
        item["member_id"]: item
        for item in rankings["members"]
    }
    ai_by_user = _ai_index(ai_report)

    markdown = [
        f"# {title}",
        "",
        f"- 그룹 ID: {definition['group_id']}",
        f"- 분석 모드: {mode_name}",
        f"- 구성원: {rankings['member_count']}명",
        "- 각 사람을 기준 사용자로 두고 나머지 입력 인원을 모두 순위화했습니다.",
        "- 점수는 포스텔러 공식 궁합점수가 아니라 동일 공식으로 비교한 내부 구조화 점수입니다.",
        "",
    ]
    if ai_report:
        markdown.extend([
            "## 그룹 요약",
            str(ai_report.get("group_summary", "")),
            "",
        ])

    markdown.extend(["## 상호 평균 궁합", ""])
    for pair in rankings["mutual_pairs"]:
        markdown.append(
            f"- {pair['rank']}위: {pair['left_name']} ↔ {pair['right_name']} "
            f"평균 {pair['average_score']:.1f} "
            f"({pair['left_name']}→{pair['right_name']} {pair['left_to_right']:.1f}, "
            f"반대 {pair['right_to_left']:.1f})"
        )

    for user_result in rankings["rankings_by_user"]:
        user_name = user_result["user_name"]
        markdown.extend(["", f"## {user_name}님 기준 순위", ""])
        ai_user = ai_by_user.get(user_result["user_id"], {})
        if ai_user.get("overview"):
            markdown.extend([_group_annotate_hanja(ai_user["overview"]), ""])
        ai_targets = {
            str(item.get("target_id")): item
            for item in ai_user.get("rankings", [])
            if isinstance(item, dict)
        }
        for item in user_result["rankings"]:
            markdown.append(
                f"### {item['rank']}위 · {item['target_name']}님 · "
                f"{item['score']['total']:.1f}/1000"
            )
            markdown.append(
                item.get("brief_explanation")
                or _brief_compatibility_explanation(
                    item.get("evidence", []),
                    rankings["relationship_mode"],
                )
            )
            ai_item = ai_targets.get(item["target_id"])
            if ai_item:
                markdown.append(_group_annotate_hanja(ai_item.get("summary", "")))
                strengths = ai_item.get("strengths", [])
                risks = ai_item.get("risks", [])
                if strengths:
                    markdown.append("- 장점: " + " / ".join(_group_annotate_hanja(value) for value in strengths))
                if risks:
                    markdown.append("- 주의: " + " / ".join(_group_annotate_hanja(value) for value in risks))
            markdown.append("")

    md_path = root / (
        "group_ai_report.md" if ai_report else "group_rankings.md"
    )
    md_path.write_text("\n".join(markdown), encoding="utf-8")

    pair_rows = "".join(
        f"<tr><td>{pair['rank']}</td>"
        f"<td>{html.escape(pair['left_name'])} ↔ {html.escape(pair['right_name'])}</td>"
        f"<td><strong>{pair['average_score']:.1f}</strong></td>"
        f"<td>{pair['left_to_right']:.1f} / {pair['right_to_left']:.1f}</td>"
        f"<td>{pair['direction_gap']:.1f}</td></tr>"
        for pair in rankings["mutual_pairs"]
    )

    member_sections: list[str] = []
    for user_result in rankings["rankings_by_user"]:
        user = members[user_result["user_id"]]
        ai_user = ai_by_user.get(user_result["user_id"], {})
        ai_targets = {
            str(item.get("target_id")): item
            for item in ai_user.get("rankings", [])
            if isinstance(item, dict)
        }
        ranking_rows: list[str] = []
        detail_blocks: list[str] = []
        for item in user_result["rankings"]:
            target = members[item["target_id"]]
            score = item["score"]
            ranking_rows.append(
                f"<tr><td>{item['rank']}</td>"
                f"<td>{html.escape(target['name'])}님</td>"
                f"<td><strong>{score['total']:.1f}</strong></td>"
                f"<td>{score.get('spouse_palace', 0):.1f}</td>"
                f"<td>{score.get('day_master', 0):.1f}</td>"
                f"<td>{score.get('branch_relations', 0):.1f}</td>"
                f"<td>{score.get('element_balance', 0):.1f}</td>"
                f"<td class='brief-cell'>{html.escape(item.get('brief_explanation') or _brief_compatibility_explanation(item.get('evidence', []), rankings['relationship_mode']))}</td></tr>"
            )
            positive, negative = _positive_negative_evidence(item["evidence"])
            ai_item = ai_targets.get(item["target_id"], {})
            ai_html = ""
            if ai_item:
                strengths = "".join(
                    f"<li>{html.escape(_group_annotate_hanja(value))}</li>"
                    for value in ai_item.get("strengths", [])
                )
                risks = "".join(
                    f"<li>{html.escape(_group_annotate_hanja(value))}</li>"
                    for value in ai_item.get("risks", [])
                )
                ai_html = (
                    f"<div class='ai-note'><h4>{html.escape(_group_annotate_hanja(ai_item.get('relationship_type', '관계 해설')))}</h4>"
                    f"<p>{html.escape(_group_annotate_hanja(ai_item.get('summary', '')))}</p>"
                    f"<div class='two-cols'><div><b>강점</b><ul>{strengths}</ul></div>"
                    f"<div><b>주의점</b><ul>{risks}</ul></div></div></div>"
                )
            positive_html = "".join(
                f"<li><b>{html.escape(_group_annotate_hanja(value['category']))}</b> · "
                f"{html.escape(_group_annotate_hanja(value['relation']))} ({float(value['score']):+.1f})</li>"
                for value in positive
            ) or "<li>두드러진 가점 근거 없음</li>"
            negative_html = "".join(
                f"<li><b>{html.escape(_group_annotate_hanja(value['category']))}</b> · "
                f"{html.escape(_group_annotate_hanja(value['relation']))} ({float(value['score']):+.1f})</li>"
                for value in negative
            ) or "<li>두드러진 감점 근거 없음</li>"
            brief = item.get("brief_explanation") or _brief_compatibility_explanation(
                item.get("evidence", []),
                rankings["relationship_mode"],
            )
            detail_blocks.append(
                f"<details><summary>{item['rank']}위 · {html.escape(target['name'])}님 · "
                f"{score['total']:.1f}점</summary>"
                f"<p class='brief-explanation'>{html.escape(brief)}</p>{ai_html}"
                f"<div class='two-cols'><div><h4>주요 긍정 근거</h4><ul>{positive_html}</ul></div>"
                f"<div><h4>주요 위험 근거</h4><ul>{negative_html}</ul></div></div></details>"
            )

        overview = ""
        if ai_user.get("overview"):
            overview = (
                "<div class='overview'><b>AI 요약</b><p>"
                + html.escape(_group_annotate_hanja(ai_user["overview"]))
                + "</p></div>"
            )
        member_sections.append(
            f"<section class='member-card' id='{html.escape(user_result['user_id'])}'>"
            f"<header><div><span class='mode-chip'>{mode_name} 모드</span>"
            f"<h2>{html.escape(user['name'])}님 기준 순위</h2>"
            f"<p>{html.escape(user['birth_datetime'])} · {html.escape(user['zodiac'])} · "
            f"{html.escape(user['western_zodiac'])}</p></div></header>"
            f"{_chart_html(user['chart'])}{overview}"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>순위</th><th>상대</th><th>총점</th><th>핵심 일지</th>"
            "<th>일간</th><th>지지 관계</th><th>오행</th><th>간략 해설</th>"
            f"</tr></thead><tbody>{''.join(ranking_rows)}</tbody></table></div>"
            f"<div class='details-list'>{''.join(detail_blocks)}</div></section>"
        )

    ai_summary = ""
    if ai_report:
        cautions = "".join(
            f"<li>{html.escape(_group_annotate_hanja(value))}</li>"
            for value in ai_report.get("cautions", [])
        )
        ai_summary = (
            "<section class='group-summary'><h2>그룹 AI 요약</h2>"
            f"<p>{html.escape(_group_annotate_hanja(ai_report.get('group_summary', '')))}</p>"
            f"<ul>{cautions}</ul></section>"
        )

    html_text = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#f5f3ef;--paper:#fff;--text:#292622;--muted:#756e67;--line:#e4ddd5;--accent:#8c5f48;--soft:#f8f3ee;--good:#eef7f1;--warn:#fff4e9}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:Arial,'Noto Sans KR',sans-serif;line-height:1.65}}
main{{max-width:1180px;margin:auto;padding:28px 18px 80px}} .hero,.member-card,.pair-section,.group-summary{{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:24px;margin-bottom:22px;box-shadow:0 8px 24px rgba(50,40,30,.05)}}
h1{{margin:0 0 8px;font-size:30px}} h2{{margin:0 0 10px}} .hero p,.member-card header p{{color:var(--muted);margin:4px 0}} .mode-chip{{display:inline-block;padding:4px 10px;border-radius:999px;background:#efe5de;color:var(--accent);font-size:12px;font-weight:800}}
.chart-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}} .chart-grid div{{padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--soft);text-align:center}} .chart-grid span{{display:block;color:var(--muted);font-size:12px}} .chart-grid strong{{font-size:22px}} .chart-grid small{{display:block;margin-top:4px;color:var(--muted);font-size:12px}}
.table-wrap{{overflow:auto}} table{{width:100%;border-collapse:collapse;min-width:720px}} th,td{{padding:11px 10px;border-bottom:1px solid var(--line);text-align:left}} th{{background:var(--soft);font-size:13px}} td:first-child{{width:60px}} details{{border:1px solid var(--line);border-radius:12px;margin-top:10px;background:#fcfbf9}} summary{{cursor:pointer;padding:13px 15px;font-weight:750}} details>div{{padding:0 15px 15px}} .two-cols{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .two-cols>div{{padding:12px;border-radius:10px;background:var(--soft)}} .ai-note{{padding:14px;margin:0 15px 12px;border-radius:12px;background:#f1f5fb}} .overview{{padding:14px;border-left:4px solid var(--accent);background:var(--soft);border-radius:10px;margin:14px 0}} .overview p{{margin:5px 0 0}} .brief-explanation{{margin:0 15px 12px;padding:12px 14px;background:#f8f3ee;border-left:4px solid var(--accent);border-radius:9px}} .brief-cell{{min-width:280px;line-height:1.5}} ul{{margin:7px 0;padding-left:20px}}
@media(max-width:720px){{.chart-grid,.two-cols{{grid-template-columns:1fr 1fr}} main{{padding:14px 10px 50px}} .hero,.member-card,.pair-section,.group-summary{{padding:17px}}}}
</style></head><body><main>
<section class="hero"><span class="mode-chip">{mode_name} 모드</span><h1>{html.escape(title)}</h1>
<p>입력한 {rankings['member_count']}명을 각각 기준 사용자로 두고 나머지 구성원을 모두 순위화했습니다.</p>
<p>방향성 점수이므로 A→B와 B→A 점수는 다를 수 있습니다. 포스텔러 공식 궁합점수가 아닌 내부 비교점수입니다.</p></section>
{ai_summary}
<section class="pair-section"><h2>상호 평균 궁합 순위</h2><div class="table-wrap"><table><thead><tr><th>순위</th><th>조합</th><th>평균</th><th>양방향 점수</th><th>방향 차이</th></tr></thead><tbody>{pair_rows}</tbody></table></div></section>
{''.join(member_sections)}
</main></body></html>"""
    if ai_report:
        html_path = root / "group_ai_report.html"
    else:
        group_report_basename = (
            f"{safe_filename_component(rankings['group_name'], '그룹')}_"
            f"{safe_filename_component(mode_name, '모드')}"
        )
        html_path = root / f"{group_report_basename}.html"

    html_path.write_text(html_text, encoding="utf-8")

    legacy_group_html = root / "group_rankings.html"
    if (
        not ai_report
        and legacy_group_html != html_path
        and legacy_group_html.exists()
    ):
        legacy_group_html.unlink()

    return md_path, html_path


def _group_ai_schema(member_count: int) -> dict[str, Any]:
    ranking_count = member_count - 1
    ranking_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "target_id",
            "relationship_type",
            "summary",
            "strengths",
            "risks",
            "why_ranked",
        ],
        "properties": {
            "target_id": {"type": "string"},
            "relationship_type": {"type": "string"},
            "summary": {"type": "string"},
            "strengths": {
                "type": "array",
                "maxItems": 2,
                "items": {"type": "string"},
            },
            "risks": {
                "type": "array",
                "maxItems": 2,
                "items": {"type": "string"},
            },
            "why_ranked": {"type": "string"},
        },
    }
    user_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["member_id", "overview", "rankings"],
        "properties": {
            "member_id": {"type": "string"},
            "overview": {"type": "string"},
            "rankings": {
                "type": "array",
                "minItems": ranking_count,
                "maxItems": ranking_count,
                "items": ranking_schema,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "group_summary", "cautions", "users"],
        "properties": {
            "title": {"type": "string"},
            "group_summary": {"type": "string"},
            "cautions": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "users": {
                "type": "array",
                "minItems": member_count,
                "maxItems": member_count,
                "items": user_schema,
            },
        },
    }


def _validate_group_sources(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    members = _profiles_from_definition(definition)
    expected_pair_count = len(members) * (len(members) - 1)
    actual_pair_count = sum(
        len(item.get("rankings", []))
        for item in rankings.get("rankings_by_user", [])
    )
    if actual_pair_count != expected_pair_count:
        errors.append(
            f"방향성 비교 수가 맞지 않습니다: 예상 {expected_pair_count}, "
            f"실제 {actual_pair_count}"
        )

    source_results: list[dict[str, Any]] = []
    for member_id, profile in members:
        result = {
            "member_id": member_id,
            "name": profile.name,
            "status": "failed",
        }
        try:
            chart = load_user_forceteller_chart(profile)
            if chart is None:
                raise RuntimeError("포스텔러 원국 캐시를 읽지 못했습니다.")
            facts, data_dir = _facts_and_data_dir(profile)
            if not facts.get("summary", {}).get("chart_found"):
                raise RuntimeError("포스텔러 facts에서 원국을 확정하지 못했습니다.")
            result.update({
                "status": "passed",
                "data_dir": str(data_dir),
                "chart": _chart_dict(chart),
            })
        except Exception as exc:
            result["error"] = str(exc)
            errors.append(f"{profile.name}: {exc}")
        source_results.append(result)

    manifest = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "status": "passed" if not errors else "failed",
        "api_call_authorized": not errors,
        "openai_api_called": False,
        "members": source_results,
        "errors": errors,
    }
    write_json(
        _group_path(definition["group_id"]) / "group_pre_ai_validation.json",
        manifest,
    )
    if errors:
        raise RuntimeError(
            "그룹 AI 호출 전 포스텔러 검증에 실패했습니다. "
            "OpenAI API는 호출되지 않았습니다: "
            + " | ".join(errors)
        )
    return manifest


def _group_ai_payload(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> dict[str, Any]:
    profiles = dict(_profiles_from_definition(definition))
    members_payload: list[dict[str, Any]] = []
    for member in rankings["members"]:
        member_id = member["member_id"]
        profile = profiles[member_id]
        facts, _ = _facts_and_data_dir(profile)
        members_payload.append({
            "member_id": member_id,
            "display_name": (
                profile.name if profile.name.endswith("님") else f"{profile.name}님"
            ),
            "gender": profile.gender,
            "birth_datetime": member["birth_datetime"],
            "zodiac": member["zodiac"],
            "western_zodiac": member["western_zodiac"],
            "forceteller_chart": member["chart"],
            "forceteller_facts": compact_facts_for_ai(facts),
        })

    ranking_payload = []
    for user_result in rankings["rankings_by_user"]:
        ranking_payload.append({
            "member_id": user_result["user_id"],
            "fixed_rankings": [
                {
                    "target_id": item["target_id"],
                    "rank": item["rank"],
                    "score_1000": item["score"]["total"],
                    "quality_scores": item["score"].get("quality_scores", {}),
                    "component_weights": item["score"].get("component_weights", {}),
                    "positive_evidence": [
                        evidence
                        for evidence in item["evidence"]
                        if float(evidence.get("score", 0)) > 0
                    ][:3],
                    "risk_evidence": [
                        evidence
                        for evidence in item["evidence"]
                        if float(evidence.get("score", 0)) < 0
                    ][:3],
                }
                for item in user_result["rankings"]
            ],
        })

    return {
        "group": {
            "group_id": definition["group_id"],
            "group_name": definition["group_name"],
            "relationship_mode": rankings["relationship_mode"],
            "mode_name": rankings["mode_name"],
            "member_count": rankings["member_count"],
            "scoring_version": rankings["scoring_version"],
            "ranking_rule": (
                "각 구성원을 기준 사용자로 두고 나머지 입력 구성원을 "
                "방향성 점수로 순위화함"
            ),
        },
        "members": members_payload,
        "rankings_by_user": ranking_payload,
        "mutual_pairs": rankings["mutual_pairs"],
    }


def _group_instructions(mode: str) -> str:
    common = """
포스텔러에서 확인한 여러 구성원의 원국과 Python이 확정한 방향성 궁합
순위를 바탕으로 한국어 다중 궁합 보고서를 작성한다.

- 각 구성원은 한 번씩 기준 사용자가 된다.
- fixed_rankings의 순서, rank, target_id를 절대로 변경하지 않는다.
- AI가 점수나 순위를 새로 만들지 않는다.
- 사주·신살·길성을 새로 계산하거나 추측하지 않는다.
- 각 사용자의 rankings에는 나머지 모든 구성원을 정확히 한 번씩 넣는다.
- 같은 두 사람이라도 A 기준과 B 기준 점수가 다를 수 있음을 자연스럽게 설명한다.
- 전문용어를 쓸 때는 실제 관계에서 어떤 모습인지 바로 풀어 쓴다.
- 한자를 쓸 때는 반드시 뜻음을 붙인다. 예: 丁(정화), 卯(묘목), 丁卯(정화·묘목).
- 구성원은 display_name으로 부른다.
- 출력은 간결하게 유지하되 순위 차이의 핵심 근거를 분명히 쓴다.
"""
    if mode == "friend":
        return common + """
[친구 모드]
- 연애 감정, 배우자, 결혼 가능성을 분석하거나 언급하지 않는다.
- 대화, 활동 리듬, 신뢰, 갈등 회복, 장기 우정 중심으로 설명한다.
"""
    return common + """
[연인 모드]
- 감정 표현, 애정 방식, 갈등, 생활 리듬, 장기 연애 관점으로 설명한다.
- 입력된 사람들만 비교 대상으로 삼고 성별을 이유로 임의 제외하지 않는다.
"""


def _inject_fixed_group_order(
    ai_data: dict[str, Any],
    rankings: dict[str, Any],
) -> dict[str, Any]:
    returned_users = {
        str(item.get("member_id")): item
        for item in ai_data.get("users", [])
        if isinstance(item, dict)
    }
    expected_users = [item["user_id"] for item in rankings["rankings_by_user"]]
    if set(returned_users) != set(expected_users):
        raise AIReportFormatError(
            "그룹 AI 응답의 구성원 ID가 요청과 다릅니다."
        )

    ordered_users = []
    for user_result in rankings["rankings_by_user"]:
        user_id = user_result["user_id"]
        user_ai = dict(returned_users[user_id])
        returned_targets = {
            str(item.get("target_id")): item
            for item in user_ai.get("rankings", [])
            if isinstance(item, dict)
        }
        expected_targets = [item["target_id"] for item in user_result["rankings"]]
        if set(returned_targets) != set(expected_targets):
            raise AIReportFormatError(
                f"{user_id} 기준 AI 응답의 후보 ID가 요청과 다릅니다."
            )
        ordered_rankings = []
        for fixed in user_result["rankings"]:
            item = dict(returned_targets[fixed["target_id"]])
            item["rank"] = fixed["rank"]
            item["score"] = fixed["score"]["total"]
            ordered_rankings.append(item)
        user_ai["rankings"] = ordered_rankings
        ordered_users.append(user_ai)
    ai_data["users"] = ordered_users
    return ai_data


def _group_cache_key(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> str:
    return _hash_payload({
        "group_id": definition["group_id"],
        "relationship_mode": rankings["relationship_mode"],
        "scoring_version": rankings["scoring_version"],
        "prompt_version": SETTINGS.group_prompt_version,
        "schema_version": SETTINGS.group_schema_version,
        "rankings": [
            {
                "user_id": user["user_id"],
                "targets": [
                    (item["target_id"], item["rank"], item["score"]["total"])
                    for item in user["rankings"]
                ],
            }
            for user in rankings["rankings_by_user"]
        ],
    }, 32)


def generate_group_ai_report(
    definition: dict[str, Any],
    rankings: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    member_count = int(rankings["member_count"])
    if member_count > SETTINGS.group_ai_max_members:
        raise RuntimeError(
            f"AI 단일 호출 그룹 보고서는 최대 {SETTINGS.group_ai_max_members}명까지 "
            f"지원합니다. 현재 {member_count}명입니다. 로컬 순위 HTML은 그대로 사용할 수 있습니다."
        )

    preflight = _validate_group_sources(definition, rankings)
    if not SETTINGS.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    root = _group_path(definition["group_id"])
    cache_path = root / "group_ai_report.json"
    cache_key = _group_cache_key(definition, rankings)
    if not force:
        cached = read_json(cache_path)
        if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
            LOGGER.info("그룹 AI 단일 호출 캐시 재사용")
            return dict(cached["report"])

    payload = _group_ai_payload(definition, rankings)
    write_json(root / "group_ai_request_manifest.json", {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "group_id": definition["group_id"],
        "relationship_mode": rankings["relationship_mode"],
        "member_count": member_count,
        "directed_comparison_count": member_count * (member_count - 1),
        "api_call_count_planned": 1,
        "preflight": preflight,
        "model": SETTINGS.openai_model,
        "max_output_tokens": SETTINGS.group_ai_max_output_tokens,
    })

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    response = None
    raw_text = ""
    try:
        LOGGER.info(
            "그룹 AI 단일 호출 시작: %s명, 방향성 비교 %s개",
            member_count,
            member_count * (member_count - 1),
        )
        response = client.responses.create(
            model=SETTINGS.openai_model,
            instructions=_group_instructions(rankings["relationship_mode"]),
            input=[{
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": (
                        "<source_data>\n"
                        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                        + "\n</source_data>"
                    ),
                }],
            }],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "multi_person_compatibility_rankings",
                    "strict": True,
                    "schema": _group_ai_schema(member_count),
                }
            },
            max_output_tokens=SETTINGS.group_ai_max_output_tokens,
            prompt_cache_key=f"four-pillars-{SETTINGS.group_prompt_version}",
            safety_identifier=hashlib.sha256(
                definition["group_id"].encode("utf-8")
            ).hexdigest()[:32],
            store=False,
        )
        raw_text = response.output_text or ""
        if str(getattr(response, "status", "") or "") == "incomplete" or getattr(
            response,
            "incomplete_details",
            None,
        ):
            raw_path = root / "group_ai_raw_incomplete.txt"
            raw_path.write_text(raw_text, encoding="utf-8")
            raise AIReportFormatError(
                "그룹 AI 단일 응답이 출력 한도 전에 완성되지 않았습니다. "
                f"자동 재호출하지 않았습니다. 원문: {raw_path}"
            )
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raw_path = root / "group_ai_raw_invalid_json.txt"
            raw_path.write_text(raw_text, encoding="utf-8")
            raise AIReportFormatError(
                f"그룹 AI 응답 JSON이 완성되지 않았습니다: {exc}. 원문: {raw_path}"
            ) from exc
        data = _inject_fixed_group_order(data, rankings)
        usage = getattr(response, "usage", None)
        write_json(cache_path, {
            "cache_key": cache_key,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "api_call_count": 1,
            "usage": {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
            "report": data,
        })
        LOGGER.info("그룹 AI 단일 호출 완료")
        return data
    except Exception as exc:
        text = str(exc).lower()
        if "insufficient_quota" in text or "exceeded your current quota" in text:
            raise AIQuotaError(
                "OpenAI API 크레딧 또는 결제 한도가 부족합니다."
            ) from exc
        if isinstance(exc, AIReportFormatError):
            raise
        if response is not None and raw_text:
            (root / "group_ai_raw_error.txt").write_text(raw_text, encoding="utf-8")
        raise


def load_cached_group_ai_report(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> dict[str, Any]:
    cache = read_json(
        _group_path(definition["group_id"]) / "group_ai_report.json"
    )
    if not isinstance(cache, dict):
        raise RuntimeError("저장된 그룹 AI 보고서가 없습니다.")
    if cache.get("cache_key") != _group_cache_key(definition, rankings):
        raise RuntimeError(
            "저장된 그룹 AI 보고서가 현재 구성원·모드·점수 순위와 다릅니다."
        )
    return dict(cache["report"])


def _choose_group_mode(value: str | None) -> str:
    if value:
        return _normalize_group_mode(value)
    while True:
        raw = input("그룹 분석 모드 L=연인 / F=친구 (기본 F): ").strip() or "F"
        try:
            return _normalize_group_mode(raw)
        except ValueError as exc:
            print(exc)


def _new_group_definition(args: Any) -> dict[str, Any]:
    mode = _choose_group_mode(getattr(args, "group_mode", None))
    group_name = (
        str(getattr(args, "group_name", "") or "").strip()
        or input("그룹 이름 또는 식별명: ").strip()
        or "다중 궁합"
    )
    file_value = getattr(args, "group_file", None)
    if file_value:
        profiles = load_group_profiles_file(Path(file_value), mode)
    else:
        profiles = collect_group_profiles_interactive(mode)
    return create_group_definition(group_name, mode, profiles)


def run_group_command(args: Any) -> None:
    mode = str(args.mode)
    if mode == "group" and not getattr(args, "group_id", None):
        definition = _new_group_definition(args)
    else:
        definition = load_group_definition(getattr(args, "group_id", None))

    group_id = definition["group_id"]
    print("그룹 ID:", group_id)
    print("그룹:", definition["group_name"])
    print("분석 모드:", _GROUP_MODE_NAMES[definition["relationship_mode"]])

    if mode == "group-status":
        rankings = read_json(_group_path(group_id) / "group_rankings.json")
        ai_cache = read_json(_group_path(group_id) / "group_ai_report.json")
        print("구성원 수:", len(definition.get("members", [])))
        print("순위 계산:", "완료" if isinstance(rankings, dict) else "미완료")
        print("AI 보고서:", "완료" if isinstance(ai_cache, dict) else "미완료")
        print("그룹 폴더:", _group_path(group_id))
        return

    if mode == "group":
        members = _profiles_from_definition(definition)
        profiles = [profile for _, profile in members]
        unknown_names = [
            profile.name
            for profile in profiles
            if not profile.birth_time_known
        ]
        if unknown_names:
            raise RuntimeError(
                "출생시간 미상 12시진 분석은 현재 지정 1인 궁합 모드에서 "
                "지원합니다. 그룹 모드 미상 구성원: "
                + ", ".join(unknown_names)
            )
        charts = ensure_profiles_forceteller_charts(profiles)
        rankings = build_group_rankings(definition, charts)
        md_path, html_path = write_group_reports(definition, rankings)
        print("그룹 순위 Markdown:", md_path)
        print("그룹 순위 HTML:", html_path)
        print(
            "AI 해설은 별도 1회 호출입니다: "
            f"python app.py group-report --group-id {group_id}"
        )
        return

    rankings = _load_group_rankings(definition)
    if mode == "group-report":
        report = generate_group_ai_report(
            definition,
            rankings,
            force=bool(getattr(args, "force_ai", False)),
        )
    elif mode == "group-render":
        report = load_cached_group_ai_report(definition, rankings)
    else:
        raise RuntimeError(f"지원하지 않는 그룹 명령입니다: {mode}")

    md_path, html_path = write_group_reports(
        definition,
        rankings,
        ai_report=report,
    )
    print("그룹 AI Markdown:", md_path)
    print("그룹 AI HTML:", html_path)
    print("OpenAI 호출 방식: 그룹 전체 1회")
