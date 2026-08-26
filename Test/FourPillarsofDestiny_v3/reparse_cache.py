"""저장된 포스텔러 자료를 현재 파서/스키마로 통합합니다.

- 브라우저나 OpenAI를 호출하지 않습니다.
- data/forceteller뿐 아니라 과거 data/candidates 및 manifest가 가리키는 저장 폴더도 찾습니다.
- 같은 생년월일시/성별/달력/지역은 이름이 달라도 동일 원국으로 묶습니다.
- 불완전 재파싱 결과는 기존 완전 캐시를 덮어쓰지 않습니다.
"""
from __future__ import annotations

from pathlib import Path

from config import SETTINGS
from forceteller import (
    _historical_cache_index,
    _legacy_profile_mapping,
    _reparse_cached_source,
    _resolve_best_cached_facts,
    refresh_historical_cache_index,
)
from models import BirthProfile
from storage import canonical_profile_identity, read_json, stable_hash


def _profile_from_folder(folder: Path) -> BirthProfile | None:
    for filename in ('metadata.json', 'forceteller_facts.json', 'forceteller_profile.json'):
        raw = read_json(folder / filename, {}) or {}
        normalized = _legacy_profile_mapping(raw)
        if not normalized:
            continue
        try:
            return BirthProfile(**normalized)
        except Exception:
            continue
    return None


def main() -> int:
    refresh_historical_cache_index()
    index = _historical_cache_index()
    folders = sorted({Path(path) for rows in index.values() for path in rows if Path(path).exists()})
    total = complete = partial = skipped = 0
    profiles_by_identity: dict[str, BirthProfile] = {}

    for folder in folders:
        total += 1
        profile = _profile_from_folder(folder)
        if profile is None:
            skipped += 1
            continue
        identity_key = stable_hash(canonical_profile_identity(profile.as_dict()))
        profiles_by_identity[identity_key] = profile
        result = _reparse_cached_source(profile, folder)
        if result is None:
            skipped += 1
            print(f'[SKIP] {folder}: 저장 원문 없음 또는 재파싱 실패')
            continue
        missing: list[str] = []
        if not result.chart.day_pillar:
            missing.append('일주')
        if not result.strength_label:
            missing.append('신강·신약')
        if not result.useful_elements:
            missing.append('용신')
        if not result.special_stars:
            missing.append('신살·길성')
        if not result.daewoon:
            missing.append('대운')
        if missing:
            partial += 1
            print(
                f'[PARTIAL] {profile.name}: 누락={", ".join(missing)} · '
                f'stars={len(result.special_stars)} · folder={folder}'
            )
        else:
            complete += 1
            print(
                f'[OK] {profile.name}: strength={result.strength_label}, '
                f'yongsin={"/".join(result.useful_elements)}, '
                f'stars={len(result.special_stars)}, daewoon={len(result.daewoon)}'
            )

    # 재파싱 후 인덱스를 갱신하고 동일인 여러 폴더의 가장 풍부한 값을 canonical folder에 병합한다.
    refresh_historical_cache_index()
    merged = 0
    for profile in profiles_by_identity.values():
        facts, _ = _resolve_best_cached_facts(profile, require_fortune=False)
        if facts is not None:
            merged += 1
    print(
        f'\n완료: 발견 폴더 {total} / 완전 {complete} / 부분 {partial} / '
        f'건너뜀 {skipped} / 동일인 canonical 통합 {merged}'
    )
    print('이 작업은 브라우저·OpenAI를 호출하지 않았습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
