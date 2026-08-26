from __future__ import annotations

from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from lunar_python import Lunar, Solar

from config import SETTINGS
from models import BirthProfile, Chart, PartialChart


BAZI_ENGINE_VERSION = "forceteller-compatible-local-v2"
DAY_BOUNDARY_SECT = 2

ELEMENTS = ("木", "火", "土", "金", "水")
STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}
VALID_STEMS = frozenset(STEM_ELEMENT)
VALID_BRANCHES = frozenset(BRANCH_ELEMENT)

# 위치 보정이 적용된 태양시 기준 12시진의 안전한 중앙값.
# 경계(23:00, 01:00, 03:00...)가 아니라 중앙값을 쓰므로
# 동일 시진 내부에서는 분 단위가 달라도 네 기둥이 동일하다.
_TRUE_SOLAR_CENTERS = (
    ("자시", 0, 0),
    ("축시", 2, 0),
    ("인시", 4, 0),
    ("묘시", 6, 0),
    ("진시", 8, 0),
    ("사시", 10, 0),
    ("오시", 12, 0),
    ("미시", 14, 0),
    ("신시", 16, 0),
    ("유시", 18, 0),
    ("술시", 20, 0),
    ("해시", 22, 0),
)


def _lunar_python_version() -> str:
    try:
        return version("lunar_python")
    except PackageNotFoundError:
        return "unknown"


def profile_to_solar(profile: BirthProfile) -> Solar:
    if profile.calendar_type == "solar":
        return Solar.fromYmdHms(
            profile.year,
            profile.month,
            profile.day,
            profile.hour,
            profile.minute,
            0,
        )

    lunar_month = -profile.month if profile.is_leap_month else profile.month
    return Lunar.fromYmdHms(
        profile.year,
        lunar_month,
        profile.day,
        profile.hour,
        profile.minute,
        0,
    ).getSolar()


def candidate_location_correction_minutes() -> int:
    """후보 로컬 계산에 사용하는 경도 기반 평균태양시 보정값."""
    if not SETTINGS.candidate_location_correction_enabled:
        return 0

    longitude_minutes = round(
        (
            SETTINGS.fixed_location_longitude
            - SETTINGS.standard_meridian_longitude
        )
        * 4
    )
    return longitude_minutes + SETTINGS.solar_time_extra_minutes


def adjusted_candidate_datetime(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    local_datetime = datetime(year, month, day, hour, minute)
    return local_datetime + timedelta(
        minutes=candidate_location_correction_minutes()
    )


def _local_input_for_true_solar_center(
    true_hour: int,
    true_minute: int,
) -> tuple[int, int]:
    total = (
        true_hour * 60
        + true_minute
        - candidate_location_correction_minutes()
    ) % (24 * 60)
    return divmod(total, 60)


DOUBLE_HOURS = [
    (
        label,
        *_local_input_for_true_solar_center(true_hour, true_minute),
    )
    for label, true_hour, true_minute in _TRUE_SOLAR_CENTERS
]


def _elements(
    stems: list[str],
    branches: list[str],
) -> tuple[dict[str, int], dict[str, float]]:
    counts = {element: 0 for element in ELEMENTS}

    for stem in stems:
        counts[STEM_ELEMENT[stem]] += 1
    for branch in branches:
        counts[BRANCH_ELEMENT[branch]] += 1

    total = sum(counts.values())
    percentages = {
        element: round(counts[element] / total * 100, 1)
        for element in ELEMENTS
    }
    return counts, percentages


def _validate_pillar(pillar: str, label: str) -> None:
    if len(pillar) != 2:
        raise ValueError(f"{label} 길이가 올바르지 않습니다: {pillar!r}")
    if pillar[0] not in VALID_STEMS:
        raise ValueError(f"{label} 천간이 올바르지 않습니다: {pillar!r}")
    if pillar[1] not in VALID_BRANCHES:
        raise ValueError(f"{label} 지지가 올바르지 않습니다: {pillar!r}")


def build_chart_from_pillars(
    year_pillar: str,
    month_pillar: str,
    day_pillar: str,
    hour_pillar: str,
) -> Chart:
    values = (
        (year_pillar, "연주"),
        (month_pillar, "월주"),
        (day_pillar, "일주"),
        (hour_pillar, "시주"),
    )
    for pillar, label in values:
        _validate_pillar(pillar, label)

    pillars = [pillar for pillar, _ in values]
    stems = [pillar[0] for pillar in pillars]
    branches = [pillar[1] for pillar in pillars]
    counts, percentages = _elements(stems, branches)

    return Chart(
        year_pillar=year_pillar,
        month_pillar=month_pillar,
        day_pillar=day_pillar,
        hour_pillar=hour_pillar,
        day_master=day_pillar[0],
        spouse_palace=day_pillar[1],
        stems=stems,
        branches=branches,
        element_counts=counts,
        element_percent=percentages,
    )


def chart_pillars(chart: Chart) -> dict[str, str]:
    return {
        "year": chart.year_pillar,
        "month": chart.month_pillar,
        "day": chart.day_pillar,
        "hour": chart.hour_pillar,
    }


def chart_differences(left: Chart, right: Chart) -> list[str]:
    labels = (
        ("연주", left.year_pillar, right.year_pillar),
        ("월주", left.month_pillar, right.month_pillar),
        ("일주", left.day_pillar, right.day_pillar),
        ("시주", left.hour_pillar, right.hour_pillar),
    )
    return [
        f"{label}: 로컬 {local_value} / 포스텔러 {source_value}"
        for label, local_value, source_value in labels
        if local_value != source_value
    ]


def calculate_chart_with_audit(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> tuple[Chart, dict[str, Any]]:
    """
    생년월일시와 위치 보정값으로 연·월·일·시주를 모두 계산한다.

    lunar_python의 exact 연주·월주를 사용하므로 입춘과 월 절입 시각을
    반영한다. 일주는 율리우스일 기반, 시주는 보정된 현지 시각과
    일간으로 계산한다. EightChar sect=2를 명시해 자시 경계 규칙도
    실행 환경에 따라 바뀌지 않게 고정한다.
    """
    input_datetime = datetime(year, month, day, hour, minute)
    adjusted = adjusted_candidate_datetime(
        year,
        month,
        day,
        hour,
        minute,
    )

    solar = Solar.fromYmdHms(
        adjusted.year,
        adjusted.month,
        adjusted.day,
        adjusted.hour,
        adjusted.minute,
        0,
    )
    eight_char = solar.getLunar().getEightChar()
    eight_char.setSect(DAY_BOUNDARY_SECT)

    chart = build_chart_from_pillars(
        eight_char.getYear(),
        eight_char.getMonth(),
        eight_char.getDay(),
        eight_char.getTime(),
    )

    audit: dict[str, Any] = {
        "engine_version": BAZI_ENGINE_VERSION,
        "library": "lunar_python",
        "library_version": _lunar_python_version(),
        "input_local_datetime": input_datetime.isoformat(timespec="minutes"),
        "location_text": SETTINGS.fixed_location_text,
        "location_id": SETTINGS.fixed_location_id,
        "longitude": SETTINGS.fixed_location_longitude,
        "standard_meridian_longitude": SETTINGS.standard_meridian_longitude,
        "longitude_correction_minutes": round(
            (
                SETTINGS.fixed_location_longitude
                - SETTINGS.standard_meridian_longitude
            )
            * 4
        ),
        "extra_correction_minutes": SETTINGS.solar_time_extra_minutes,
        "total_correction_minutes": candidate_location_correction_minutes(),
        "adjusted_datetime": adjusted.isoformat(timespec="minutes"),
        "year_month_rule": "exact_solar_terms",
        "day_rule": "julian_day",
        "day_boundary_sect": DAY_BOUNDARY_SECT,
        "pillars": chart_pillars(chart),
    }
    return chart, audit


def calculate_chart(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> Chart:
    chart, _ = calculate_chart_with_audit(
        year,
        month,
        day,
        hour,
        minute,
    )
    return chart


def calculate_profile_local_chart(
    profile: BirthProfile,
) -> tuple[Chart, dict[str, Any]]:
    solar = profile_to_solar(profile)
    return calculate_chart_with_audit(
        solar.getYear(),
        solar.getMonth(),
        solar.getDay(),
        solar.getHour(),
        solar.getMinute(),
    )


def validate_local_engine_against_forceteller(
    profile: BirthProfile,
    forceteller_chart: Chart,
) -> dict[str, Any]:
    local_chart, audit = calculate_profile_local_chart(profile)
    differences = chart_differences(local_chart, forceteller_chart)
    result = {
        "status": "matched" if not differences else "mismatch",
        "profile_name": profile.name,
        "local_chart": chart_pillars(local_chart),
        "forceteller_chart": chart_pillars(forceteller_chart),
        "differences": differences,
        "calculation_audit": audit,
    }
    if differences:
        raise RuntimeError(
            "로컬 사주 계산 규칙이 사용자 포스텔러 원국과 일치하지 "
            "않습니다. 후보 계산을 중단합니다: " + "; ".join(differences)
        )
    return result


def validate_double_hour_grid() -> dict[str, Any]:
    """12개 대표 시간이 실제로 12개 시지를 한 번씩 만드는지 검사한다."""
    # 절기와 날짜 경계에서 충분히 떨어진 기준일을 사용한다.
    rows: list[dict[str, Any]] = []
    branches: list[str] = []
    for label, hour, minute in DOUBLE_HOURS:
        chart, audit = calculate_chart_with_audit(
            2000,
            6,
            15,
            hour,
            minute,
        )
        branches.append(chart.hour_pillar[1])
        rows.append(
            {
                "label": label,
                "input_time": f"{hour:02d}:{minute:02d}",
                "adjusted_datetime": audit["adjusted_datetime"],
                "hour_pillar": chart.hour_pillar,
            }
        )

    expected = set(VALID_BRANCHES)
    actual = set(branches)
    if len(branches) != 12 or actual != expected:
        raise RuntimeError(
            "12시진 로컬 계산 격자가 올바르지 않습니다: "
            f"branches={branches}"
        )
    return {
        "status": "passed",
        "unique_hour_branches": branches,
        "rows": rows,
    }


def calculate_partial_chart(
    year: int,
    month: int,
    day: int,
) -> PartialChart:
    """날짜 참고점수용 3주. 최종 선발은 12시진의 완전한 4주로 한다."""
    chart = calculate_chart(year, month, day, 12, 0)
    stems = chart.stems[:3]
    branches = chart.branches[:3]
    counts, percentages = _elements(stems, branches)
    return PartialChart(
        year_pillar=chart.year_pillar,
        month_pillar=chart.month_pillar,
        day_pillar=chart.day_pillar,
        day_master=chart.day_master,
        spouse_palace=chart.spouse_palace,
        stems=stems,
        branches=branches,
        element_counts=counts,
        element_percent=percentages,
    )


def automatic_age_range(
    birth_year: int,
    max_older_years: int | None = None,
    max_younger_years: int | None = None,
) -> tuple[int, int, int, int]:
    current_age = datetime.now().year - birth_year
    if current_age < 19:
        raise ValueError("미성년자는 상대 후보 검색을 실행할 수 없습니다.")

    older = (
        SETTINGS.max_older_years
        if max_older_years is None
        else max_older_years
    )
    younger = (
        SETTINGS.max_younger_years
        if max_younger_years is None
        else max_younger_years
    )
    if older < 0 or younger < 0:
        raise ValueError("연상·연하 탐색 범위는 0 이상이어야 합니다.")

    return (
        birth_year - older,
        birth_year + younger,
        older,
        younger,
    )
