from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from config import SETTINGS
from solar_time import CALCULATION_VERSION


def _default(value: Any):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, data: Any) -> Path:
    if not SETTINGS.persist_user_data:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_default), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def stable_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=_default).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()



def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'y', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'n', 'off', ''}:
        return False
    return default


def canonical_profile_identity(profile_dict: dict[str, Any]) -> dict[str, Any]:
    """표시 이름과 입력 포맷 차이를 제거한 사람 단위 캐시 키.

    같은 생년월일시/성별/달력/출생지/시간보정 방식이면 이름을 다르게 적어도 같은
    원국 자료를 재사용한다. 경도 기반 보정을 적용하므로 대한민국도 도시가 캐시 키에
    포함된다. 계산식이 바뀌었을 때 과거 결과를 잘못 재사용하지 않도록 버전도 보존한다.
    """
    code = str(profile_dict.get('country_code') or 'KR').upper().strip()
    time_known = _bool_value(profile_dict.get('time_known'), True)
    identity = {
        'gender': 'F' if str(profile_dict.get('gender', 'F')).upper() == 'F' else 'M',
        'calendar_type': 'lunar' if str(profile_dict.get('calendar_type', 'solar')).lower() == 'lunar' else 'solar',
        'year': int(profile_dict.get('year') or 0),
        'month': int(profile_dict.get('month') or 0),
        'day': int(profile_dict.get('day') or 0),
        'time_known': time_known,
        'hour': int(profile_dict.get('hour') or 0) if time_known else None,
        'minute': int(profile_dict.get('minute') or 0) if time_known else None,
        # 윤달 여부는 음력에서만 의미가 있다. 양력 입력의 숨은/과거 UI 값 때문에
        # 동일 인물이 다른 캐시 키로 갈라지지 않게 정규화한다.
        'is_leap_month': (
            _bool_value(profile_dict.get('is_leap_month'), False)
            if str(profile_dict.get('calendar_type', 'solar')).lower() == 'lunar'
            else False
        ),
        'country_code': code,
        'country': str(profile_dict.get('country') or '').strip().casefold(),
        'city': str(profile_dict.get('city') or '').strip().casefold(),
        'location_id': str(profile_dict.get('location_id') or '').strip(),
        'solar_time_mode': str(profile_dict.get('solar_time_mode') or 'true_solar').strip().lower(),
        'solar_time_version': CALCULATION_VERSION,
    }
    return identity


def profile_key(profile_dict: dict[str, Any]) -> str:
    return stable_hash(canonical_profile_identity(profile_dict))[:20]


def legacy_profile_key(profile_dict: dict[str, Any]) -> str:
    """2026-08-17 이전 폴더를 찾기 위한 과거 키 형식."""
    important = {
        k: profile_dict.get(k) for k in (
            'name', 'gender', 'calendar_type', 'year', 'month', 'day',
            'hour', 'minute', 'time_known', 'is_leap_month',
            'country_code', 'country', 'city', 'location', 'location_id',
        )
    }
    return stable_hash(important)[:20]


def cache_path(namespace: str, key: str) -> Path:
    return SETTINGS.cache_dir / namespace / f'{key}.json'
