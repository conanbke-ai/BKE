from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import geonamescache
except ImportError:  # pragma: no cover - requirements installs it in normal runtime
    geonamescache = None

CALCULATION_VERSION = 'true-solar-v1-20260905'

BRANCHES = ('子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥')
BRANCH_READING = {
    '子': '자', '丑': '축', '寅': '인', '卯': '묘', '辰': '진', '巳': '사',
    '午': '오', '未': '미', '申': '신', '酉': '유', '戌': '술', '亥': '해',
}


@dataclass(frozen=True)
class ResolvedLocation:
    name: str
    country_code: str
    latitude: float
    longitude: float
    timezone_id: str
    source: str


# 한국어 도시명은 GeoNames의 alternate names 유무와 무관하게 안정적으로 찾도록
# 주요 도시를 먼저 둡니다. 목록에 없는 도시는 geonamescache로 이어서 찾습니다.
_KR_LOCATIONS: dict[str, tuple[str, float, float]] = {
    '서울': ('서울특별시', 37.5665, 126.9780),
    '부산': ('부산광역시', 35.1796, 129.0756),
    '인천': ('인천광역시', 37.4563, 126.7052),
    '대구': ('대구광역시', 35.8714, 128.6014),
    '대전': ('대전광역시', 36.3504, 127.3845),
    '광주': ('광주광역시', 35.1595, 126.8526),
    '울산': ('울산광역시', 35.5384, 129.3114),
    '세종': ('세종특별자치시', 36.4800, 127.2890),
    '수원': ('수원시', 37.2636, 127.0286),
    '성남': ('성남시', 37.4200, 127.1265),
    '고양': ('고양시', 37.6584, 126.8320),
    '용인': ('용인시', 37.2411, 127.1776),
    '부천': ('부천시', 37.5034, 126.7660),
    '안산': ('안산시', 37.3219, 126.8309),
    '안양': ('안양시', 37.3943, 126.9568),
    '남양주': ('남양주시', 37.6360, 127.2165),
    '화성': ('화성시', 37.1995, 126.8312),
    '평택': ('평택시', 36.9921, 127.1129),
    '의정부': ('의정부시', 37.7381, 127.0337),
    '시흥': ('시흥시', 37.3800, 126.8029),
    '파주': ('파주시', 37.7599, 126.7800),
    '김포': ('김포시', 37.6153, 126.7156),
    '광명': ('광명시', 37.4786, 126.8644),
    '군포': ('군포시', 37.3617, 126.9352),
    '하남': ('하남시', 37.5393, 127.2148),
    '오산': ('오산시', 37.1498, 127.0772),
    '이천': ('이천시', 37.2720, 127.4350),
    '안성': ('안성시', 37.0079, 127.2797),
    '구리': ('구리시', 37.5943, 127.1296),
    '양주': ('양주시', 37.7853, 127.0458),
    '포천': ('포천시', 37.8949, 127.2002),
    '여주': ('여주시', 37.2982, 127.6372),
    '과천': ('과천시', 37.4292, 126.9876),
    '춘천': ('춘천시', 37.8813, 127.7298),
    '원주': ('원주시', 37.3422, 127.9202),
    '강릉': ('강릉시', 37.7519, 128.8761),
    '청주': ('청주시', 36.6424, 127.4890),
    '충주': ('충주시', 36.9910, 127.9259),
    '천안': ('천안시', 36.8151, 127.1139),
    '아산': ('아산시', 36.7898, 127.0018),
    '공주': ('공주시', 36.4465, 127.1190),
    '전주': ('전주시', 35.8242, 127.1480),
    '익산': ('익산시', 35.9483, 126.9576),
    '군산': ('군산시', 35.9677, 126.7366),
    '목포': ('목포시', 34.8118, 126.3922),
    '여수': ('여수시', 34.7604, 127.6622),
    '순천': ('순천시', 34.9506, 127.4872),
    '포항': ('포항시', 36.0190, 129.3435),
    '경주': ('경주시', 35.8562, 129.2247),
    '구미': ('구미시', 36.1195, 128.3446),
    '창원': ('창원시', 35.2279, 128.6811),
    '김해': ('김해시', 35.2285, 128.8894),
    '진주': ('진주시', 35.1800, 128.1076),
    '제주': ('제주시', 33.4996, 126.5312),
    '서귀포': ('서귀포시', 33.2541, 126.5601),
}


def _normalize_place(value: str) -> str:
    text = re.sub(r'\s+', '', str(value or '').strip().casefold())
    text = text.replace('대한민국', '').replace('southkorea', '').replace('republicofkorea', '')
    for suffix in ('특별자치시', '특별시', '광역시', '자치시'):
        text = text.replace(suffix, '')
    text = re.sub(r'(시|군|구)$', '', text)
    return text


def _kr_location(city: str) -> ResolvedLocation | None:
    raw = str(city or '').strip()
    if not raw:
        return None
    candidates = [raw]
    candidates.extend(re.split(r'[ ,/]+', raw))
    for candidate in reversed(candidates):
        key = _normalize_place(candidate)
        if key in _KR_LOCATIONS:
            name, lat, lon = _KR_LOCATIONS[key]
            return ResolvedLocation(name, 'KR', lat, lon, 'Asia/Seoul', 'builtin_kr')
    return None


@lru_cache(maxsize=1)
def _city_rows() -> tuple[dict[str, Any], ...]:
    if geonamescache is None:
        return ()
    cache = geonamescache.GeonamesCache()
    return tuple(cache.get_cities().values())


@lru_cache(maxsize=512)
def _geonames_location(country_code: str, city: str) -> ResolvedLocation | None:
    wanted = _normalize_place(city)
    if not wanted:
        return None
    rows: list[dict[str, Any]] = []
    for row in _city_rows():
        if str(row.get('countrycode') or '').upper() != country_code:
            continue
        names = [str(row.get('name') or '')]
        names.extend(str(x) for x in (row.get('alternatenames') or []))
        if any(_normalize_place(name) == wanted for name in names if name):
            rows.append(row)
    if not rows:
        return None
    row = max(rows, key=lambda item: int(item.get('population') or 0))
    timezone_id = str(row.get('timezone') or '').strip()
    if not timezone_id:
        return None
    return ResolvedLocation(
        str(row.get('name') or city),
        country_code,
        float(row['latitude']),
        float(row['longitude']),
        timezone_id,
        'geonamescache',
    )


def resolve_birth_location(country_code: str, city: str) -> ResolvedLocation | None:
    code = str(country_code or 'KR').upper().strip()
    city = str(city or '').strip()
    if not city:
        return None
    if code == 'KR':
        resolved = _kr_location(city)
        if resolved:
            return resolved
    return _geonames_location(code, city)


def equation_of_time_minutes(moment: datetime) -> float:
    """NOAA의 fractional-year 근사식으로 균시차를 분 단위로 계산합니다."""
    days = 366 if _is_leap_year(moment.year) else 365
    day_of_year = moment.timetuple().tm_yday
    hour = moment.hour + moment.minute / 60 + moment.second / 3600
    gamma = 2 * math.pi / days * (day_of_year - 1 + (hour - 12) / 24)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def hour_branch(moment: datetime) -> str:
    return BRANCHES[((moment.hour + 1) // 2) % 12]


def _branch_label(branch: str) -> str:
    return f'{BRANCH_READING.get(branch, branch)}시'


def _format_local(moment: datetime) -> str:
    return moment.strftime('%Y-%m-%d %H:%M')


def _timezone_offsets(moment: datetime, timezone_id: str) -> tuple[float, float]:
    zone = ZoneInfo(timezone_id)
    aware = moment.replace(tzinfo=zone)
    utc_offset = (aware.utcoffset() or timedelta()).total_seconds() / 3600
    dst_offset = (aware.dst() or timedelta()).total_seconds() / 3600
    return utc_offset, dst_offset


def calculate_time_correction(
    *,
    country_code: str,
    city: str,
    civil_datetime: datetime,
    time_known: bool,
    mode: str = 'true_solar',
) -> tuple[datetime, dict[str, Any]]:
    """기록된 출생시각을 보존하면서 선택 계산법의 보정시각과 경계 메타데이터를 반환합니다.

    두 개의 명식을 만들지 않습니다. 기본값은 진태양시이고, 표준시/경도 보정/진태양시
    중 시주가 갈릴 때만 사용자 화면에 한 줄 경고를 보여줄 수 있도록 정보를 남깁니다.
    """
    base: dict[str, Any] = {
        'calculation_version': CALCULATION_VERSION,
        'mode': mode,
        'time_known': bool(time_known),
        'civil_datetime': _format_local(civil_datetime),
        'applied': False,
        'location_resolved': False,
        'boundary_warning': False,
        'warning': '',
    }
    if not time_known:
        return civil_datetime, base

    location = resolve_birth_location(country_code, city)
    if location is None:
        base['location_warning'] = '출생지가 확인되지 않아 기록된 출생시간을 그대로 사용했습니다.'
        base['selected_datetime'] = _format_local(civil_datetime)
        base['civil_branch'] = hour_branch(civil_datetime)
        base['selected_branch'] = base['civil_branch']
        return civil_datetime, base

    try:
        utc_offset_hours, dst_offset_hours = _timezone_offsets(civil_datetime, location.timezone_id)
    except ZoneInfoNotFoundError:
        base['location_warning'] = '출생지 시간대 자료를 확인하지 못해 기록된 출생시간을 그대로 사용했습니다.'
        base['selected_datetime'] = _format_local(civil_datetime)
        base['civil_branch'] = hour_branch(civil_datetime)
        base['selected_branch'] = base['civil_branch']
        return civil_datetime, base

    longitude_minutes = 4 * location.longitude - 60 * utc_offset_hours
    eot_minutes = equation_of_time_minutes(civil_datetime)
    mean_solar = civil_datetime + timedelta(minutes=longitude_minutes)
    true_solar = civil_datetime + timedelta(minutes=longitude_minutes + eot_minutes)

    requested_mode = str(mode or 'true_solar').strip().lower()
    if requested_mode == 'civil':
        selected = civil_datetime
        selected_mode = 'civil'
    elif requested_mode in {'local_mean', 'mean_solar', 'longitude'}:
        selected = mean_solar
        selected_mode = 'local_mean'
    else:
        selected = true_solar
        selected_mode = 'true_solar'

    branch_by_method = {
        'civil': hour_branch(civil_datetime),
        'local_mean': hour_branch(mean_solar),
        'true_solar': hour_branch(true_solar),
    }
    unique_branches = sorted(set(branch_by_method.values()), key=BRANCHES.index)
    boundary_warning = len(unique_branches) > 1
    warning = ''
    if boundary_warning:
        labels = '/'.join(_branch_label(branch) for branch in unique_branches)
        warning = (
            '시주 경계에 가까운 출생시간입니다. '
            f'적용하는 만세력 계산법에 따라 {labels}가 달라질 수 있습니다.'
        )

    base.update({
        'applied': selected_mode != 'civil',
        'location_resolved': True,
        'location': asdict(location),
        'timezone_id': location.timezone_id,
        'utc_offset_hours': round(utc_offset_hours, 3),
        'dst_offset_hours': round(dst_offset_hours, 3),
        'longitude_correction_minutes': round(longitude_minutes, 3),
        'equation_of_time_minutes': round(eot_minutes, 3),
        'true_solar_correction_minutes': round(longitude_minutes + eot_minutes, 3),
        'civil_datetime': _format_local(civil_datetime),
        'local_mean_datetime': _format_local(mean_solar),
        'true_solar_datetime': _format_local(true_solar),
        'selected_datetime': _format_local(selected),
        'mode': selected_mode,
        'branch_by_method': branch_by_method,
        'civil_branch': branch_by_method['civil'],
        'selected_branch': hour_branch(selected),
        'boundary_warning': boundary_warning,
        'warning': warning,
    })
    return selected, base
