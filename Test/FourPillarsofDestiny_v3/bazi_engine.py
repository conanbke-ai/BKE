from __future__ import annotations

from datetime import datetime

from constants import (
    BRANCH_ELEMENT,
    ELEMENTS,
    HIDDEN_STEMS,
    STEM_ELEMENT,
    STEM_YANG,
    GENERATES,
    CONTROLS,
)
from models import BirthProfile, Chart
from solar_time import calculate_time_correction

try:
    from lunar_python import Lunar, Solar
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        'lunar_python이 필요합니다. `pip install lunar_python` 후 다시 실행하세요.'
    ) from exc


def _profile_to_civil_solar(profile: BirthProfile) -> Solar:
    """사용자가 기록한 출생시각 그대로 양력 시각을 만든다.

    음력 입력도 먼저 실제 양력 날짜로 바꾼 뒤 태양시 보정을 적용해야 균시차와
    역사적 시간대가 올바른 달력 날짜를 기준으로 계산된다.
    """
    # 시간 미상인 경우 정오를 날짜 변환용 안전 기준으로만 사용한다.
    hour = profile.hour if profile.time_known else 12
    minute = profile.minute if profile.time_known else 0
    if profile.calendar_type == 'solar':
        return Solar.fromYmdHms(
            profile.year, profile.month, profile.day, hour, minute, 0,
        )
    lunar_month = -profile.month if profile.is_leap_month else profile.month
    lunar = Lunar.fromYmdHms(
        profile.year, lunar_month, profile.day, hour, minute, 0,
    )
    return lunar.getSolar()


def _solar_datetime(solar: Solar) -> datetime:
    return datetime(
        solar.getYear(), solar.getMonth(), solar.getDay(),
        solar.getHour(), solar.getMinute(), solar.getSecond(),
    )


def profile_to_solar_with_correction(profile: BirthProfile) -> tuple[Solar, dict]:
    civil_solar = _profile_to_civil_solar(profile)
    civil_datetime = _solar_datetime(civil_solar)
    corrected, metadata = calculate_time_correction(
        country_code=profile.country_code,
        city=profile.city,
        civil_datetime=civil_datetime,
        time_known=profile.time_known,
        mode=profile.solar_time_mode,
    )
    if not metadata.get('applied'):
        return civil_solar, metadata
    return Solar.fromYmdHms(
        corrected.year, corrected.month, corrected.day,
        corrected.hour, corrected.minute, corrected.second,
    ), metadata


def profile_to_solar(profile: BirthProfile) -> Solar:
    solar, _ = profile_to_solar_with_correction(profile)
    return solar


def calculate_chart(profile: BirthProfile) -> Chart:
    solar, time_correction = profile_to_solar_with_correction(profile)
    eight = solar.getLunar().getEightChar()
    core_pillars = [eight.getYear(), eight.getMonth(), eight.getDay()]
    hour_pillar = eight.getTime() if profile.time_known else ''
    pillars = core_pillars + ([hour_pillar] if hour_pillar else [])
    stems = [p[0] for p in pillars]
    branches = [p[1] for p in pillars]
    counts = {e: 0 for e in ELEMENTS}
    for stem in stems:
        counts[STEM_ELEMENT[stem]] += 1
    for branch in branches:
        counts[BRANCH_ELEMENT[branch]] += 1
    total = sum(counts.values()) or 1
    percent = {e: round(counts[e] / total * 100, 1) for e in ELEMENTS}
    return Chart(
        year_pillar=core_pillars[0],
        month_pillar=core_pillars[1],
        day_pillar=core_pillars[2],
        hour_pillar=hour_pillar,
        day_master=core_pillars[2][0],
        spouse_palace=core_pillars[2][1],
        stems=stems,
        branches=branches,
        element_percent_local=percent,
        time_correction=time_correction,
    )


def ten_god(day_master: str, target_stem: str) -> str:
    dm_e = STEM_ELEMENT[day_master]
    target_e = STEM_ELEMENT[target_stem]
    same_polarity = (day_master in STEM_YANG) == (target_stem in STEM_YANG)

    if dm_e == target_e:
        return '비견' if same_polarity else '겁재'
    if GENERATES[dm_e] == target_e:
        return '식신' if same_polarity else '상관'
    if CONTROLS[dm_e] == target_e:
        return '편재' if same_polarity else '정재'
    if CONTROLS[target_e] == dm_e:
        return '편관' if same_polarity else '정관'
    if GENERATES[target_e] == dm_e:
        return '편인' if same_polarity else '정인'
    return ''


def derive_ten_gods(chart: Chart) -> dict[str, float]:
    """
    포스텔러에서 십성 비율을 얻지 못했을 때만 쓰는 보조 계산.
    천간은 1.0, 지장간은 0.35의 참고 가중치로 계산한다.
    포스텔러 표시값이 있으면 그 값이 항상 우선한다.
    """
    raw: dict[str, float] = {}
    for stem in chart.stems:
        tg = ten_god(chart.day_master, stem)
        raw[tg] = raw.get(tg, 0.0) + 1.0
    for branch in chart.branches:
        for hidden in HIDDEN_STEMS[branch]:
            tg = ten_god(chart.day_master, hidden)
            raw[tg] = raw.get(tg, 0.0) + 0.35
    total = sum(raw.values()) or 1.0
    return {k: round(v / total * 100, 1) for k, v in raw.items()}


def period_pillars(moment: datetime) -> dict[str, str]:
    eight = Solar.fromYmdHms(
        moment.year, moment.month, moment.day,
        moment.hour, moment.minute, moment.second,
    ).getLunar().getEightChar()
    return {
        'year': eight.getYear(),
        'month': eight.getMonth(),
        'day': eight.getDay(),
        'hour': eight.getTime(),
    }
