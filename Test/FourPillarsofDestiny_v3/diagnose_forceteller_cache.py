"""Developer-only offline diagnostic for saved Forceteller source caches.

No browser or network access is used. It reports whether each saved source actually
contains the core result cards and what the current parser extracts from them.
"""
from __future__ import annotations

from config import SETTINGS
from forceteller import _historical_data_roots, _legacy_profile_mapping, _reparse_cached_source
from models import BirthProfile
from storage import read_json


def _profile(folder):
    for filename in ('metadata.json', 'forceteller_facts.json', 'forceteller_profile.json'):
        raw = read_json(folder / filename, {}) or {}
        normalized = _legacy_profile_mapping(raw)
        if normalized:
            try:
                return BirthProfile(**normalized)
            except Exception:
                continue
    return None


def main() -> int:
    found = 0
    folders = set()
    for root in _historical_data_roots():
        for facts_path in root.rglob('forceteller_facts.json'):
            folders.add(facts_path.parent)
        for manifest in root.rglob('forceteller_profile.json'):
            folders.add(manifest.parent)
    for folder in sorted(folders):
        if not folder.is_dir():
            continue
        profile = _profile(folder)
        if profile is None:
            continue
        html_path = folder / 'result.html'
        raw = html_path.read_text(encoding='utf-8', errors='ignore') if html_path.exists() else ''
        markers = {
            '원국': '신살과 길성' in raw,
            '신강신약': 'data-test-id="singang"' in raw or "data-test-id='singang'" in raw,
            '용신': 'data-test-id="guardian"' in raw or "data-test-id='guardian'" in raw,
            '신살길성': '신살과 길성' in raw,
            '대운': 'data-test-id="daeun0top"' in raw or "data-test-id='daeun0top'" in raw,
        }
        result = _reparse_cached_source(profile, folder)
        if result is None:
            print(f'[FAIL] {profile.name}: 저장 원문 재파싱 실패 · markers={markers}')
            continue
        found += 1
        print(
            f'[OK] {profile.name}: {result.chart.hour_pillar or "--"}/'
            f'{result.chart.day_pillar}/{result.chart.month_pillar}/{result.chart.year_pillar} · '
            f'strength={result.strength_label or "--"} · '
            f'yongsin={"/".join(result.useful_elements) or "--"} · '
            f'stars={len(result.special_stars)} · daewoon={len(result.daewoon)} · raw={markers}'
        )
    print(f'\n진단 완료: {found}개 캐시를 현재 파서로 확인했습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
