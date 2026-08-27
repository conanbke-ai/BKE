from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from models import BirthProfile, Chart, ForcetellerFacts, MatchCandidate

# These cache/mapping tests do not need astronomical conversion. Keep them runnable in the
# lightweight audit environment where lunar_python is intentionally absent.
if importlib.util.find_spec('lunar_python') is None:
    stub = types.ModuleType('bazi_engine')
    stub.calculate_chart = lambda profile: None
    stub.derive_ten_gods = lambda chart: {}
    stub.ten_god = lambda day_master, stem: '비견'
    stub.period_pillars = lambda moment: {'year':'甲子','month':'甲子','day':'甲子','hour':'甲子'}
    stub.profile_to_solar = lambda profile: profile
    sys.modules.setdefault('bazi_engine', stub)

from search_engine import (
    _best_exact_per_year,
    _candidate_key,
    _facts_complete,
    _facts_ranking_reproducible,
    _facts_recommendation_usable,
    _auto_cache_usable,
    _ranked_sources_reusable,
    ideal_from_auto,
)
from scoring import score_love, score_friend
from services import _build_candidate_payloads, _result_cache_usable
from forceteller import _historical_data_roots, _legacy_profile_mapping
from config import SETTINGS


def person(name: str, year: int, month: int, day: int, gender: str, hour: int, minute: int) -> BirthProfile:
    return BirthProfile(
        name=name,
        gender=gender,
        calendar_type='solar',
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        time_known=True,
        country_code='KR',
        country='대한민국',
        city='',
        partner_gender='M' if gender == 'F' else 'F',
    )


def cached_source_facts(profile: BirthProfile, day_pillar: str) -> ForcetellerFacts:
    stem, branch = day_pillar[0], day_pillar[1]
    chart = Chart(
        year_pillar='甲戌', month_pillar='丙子', day_pillar=day_pillar, hour_pillar='丁卯',
        day_master=stem, spouse_palace=branch,
        stems=['甲', '丙', stem, '丁'], branches=['戌', '子', branch, '卯'],
        element_percent_local={'木':25.0,'火':25.0,'土':25.0,'金':0.0,'水':25.0},
    )
    return ForcetellerFacts(
        profile=profile,
        chart=chart,
        element_percent={'木':25.0,'火':25.0,'土':25.0,'金':0.0,'水':25.0},
        ten_gods={'비견':20.0,'식신':20.0,'정재':20.0,'정관':20.0,'정인':20.0},
        strength_label='',
        useful_elements=[],
        source_quality=45,
        source='forceteller_cache',
    )


def export_candidate(user_facts, target_facts, mode: str):
    result = score_love(user_facts, target_facts) if mode == 'love' else score_friend(user_facts, target_facts)
    item = MatchCandidate(target_facts.profile, target_facts, result)
    payload = item.as_dict()
    payload['candidate_key'] = _candidate_key(target_facts.profile)
    payload['source_status'] = {'verified': False, 'label': '저장된 원국 자료', 'quality': target_facts.source_quality}
    payload['age_meta'] = {'age': 30}
    return payload


def test_partial_external_cache_is_still_recommendation_usable():
    facts = cached_source_facts(person('후보', 1995, 4, 19, 'M', 15, 0), '丁亥')
    assert _facts_recommendation_usable(facts) is True
    assert _facts_complete(facts) is False


def test_auto_cache_reuses_source_backed_rows_even_if_optional_fields_missing():
    user = cached_source_facts(person('나', 1994, 12, 7, 'F', 5, 30), '丁亥')
    target = cached_source_facts(person('후보', 1995, 4, 19, 'M', 15, 0), '壬子')
    love = export_candidate(user, target, 'love')
    friend = export_candidate(user, target, 'friend')
    from config import SETTINGS
    payload = {
        'love': [love], 'friend': [friend],
        'cache_meta': {'scoring_version': SETTINGS.scoring_version},
    }
    assert _auto_cache_usable(payload) is True


def test_requested_top_ten_cache_is_not_reused_when_rows_are_truncated():
    user = cached_source_facts(person('나', 1994, 12, 7, 'F', 5, 30), '丁亥')
    target = cached_source_facts(person('후보', 1995, 4, 19, 'M', 15, 0), '壬子')
    payload = {
        'love': [export_candidate(user, target, 'love')],
        'friend': [export_candidate(user, target, 'friend')],
        'cache_meta': {
            'scoring_version': SETTINGS.scoring_version,
            'cache_identity': {'top_n': 10},
        },
    }
    assert _auto_cache_usable(payload) is False

    initial_payload = {
        'auto_matches': payload,
        'request_options': {'build_matches': True},
        'cache_meta': {
            'parser_version': SETTINGS.parser_version,
            'scoring_version': SETTINGS.scoring_version,
            'report_revision': SETTINGS.report_revision,
            'reusable_sources': True,
        },
    }
    assert _result_cache_usable(initial_payload) is False


def test_local_facts_fill_missing_years_as_reproducible_provisional_candidates():
    from dataclasses import replace

    user = cached_source_facts(person('나', 1994, 12, 7, 'F', 5, 30), '丁亥')
    local = replace(
        cached_source_facts(person('예비후보', 1996, 8, 8, 'M', 13, 0), '甲子'),
        source='local',
        source_quality=0,
    )
    assert _facts_ranking_reproducible(local) is True
    assert _facts_recommendation_usable(local) is False
    winners = _best_exact_per_year(user, [local], 'love')
    assert len(winners) == 1
    assert winners[0].profile.name == '예비후보'


def test_candidate_key_is_carried_through_ideal_and_pair_report_mapping():
    user = cached_source_facts(person('나', 1994, 12, 7, 'F', 5, 30), '丁亥')
    target = cached_source_facts(person('추천 후보', 1995, 4, 19, 'M', 15, 0), '壬子')
    love = export_candidate(user, target, 'love')
    friend = export_candidate(user, target, 'friend')
    auto = {'love': [love], 'friend': [friend]}

    candidates, reports = _build_candidate_payloads(user, auto)
    key = love['candidate_key']
    assert candidates[0]['candidate_key'] == key
    assert f'love:{key}' in reports
    assert f'friend:{key}' in reports
    assert reports[f'love:{key}']['score'] == love['result']['total']
    assert ideal_from_auto([love], top_n=1)[0]['candidate_key'] == key


def test_legacy_v2_condition_metadata_maps_to_modern_birth_identity():
    metadata = {
        'completed': True,
        'condition': {
            'birth_date': '1995-04-19',
            'birth_time': '15:00',
            'gender': 'M',
            'calendar': 'solar',
            'location_text': '서울특별시, 대한민국',
            'location_id': '1835848',
        },
    }
    mapped = _legacy_profile_mapping(metadata)
    assert mapped is not None
    assert (mapped['year'], mapped['month'], mapped['day']) == (1995, 4, 19)
    assert (mapped['hour'], mapped['minute']) == (15, 0)
    assert mapped['gender'] == 'M'
    assert mapped['calendar_type'] == 'solar'


def test_historical_cache_search_includes_legacy_output_tree():
    roots = _historical_data_roots()
    assert SETTINGS.root / 'output' in roots or not (SETTINGS.root / 'output').exists()


def test_ranked_result_cache_does_not_depend_on_failed_shortlist_losers():
    user = cached_source_facts(person('나', 1994, 12, 7, 'F', 5, 30), '丁亥')
    target = cached_source_facts(person('후보', 1995, 4, 19, 'M', 15, 0), '壬子')
    payload = {
        'love': [export_candidate(user, target, 'love')],
        'friend': [export_candidate(user, target, 'friend')],
        # This diagnostic represents a non-winning shortlist row that failed collection.
        'cache_meta': {'unusable_shortlist_profiles': 1},
    }
    assert _ranked_sources_reusable(payload) is True


def test_collect_many_deduplicates_same_birth_identity_and_preserves_names(monkeypatch):
    import forceteller as ft

    first = person('첫사람', 1995, 4, 19, 'M', 15, 0)
    second = person('둘째사람', 1995, 4, 19, 'M', 15, 0)
    base = cached_source_facts(first, '壬子')
    calls = {'count': 0}

    def fake_resolve(profile, *, force=False, require_fortune=False):
        calls['count'] += 1
        return base, Path('.')

    monkeypatch.setattr(ft, '_resolve_best_cached_facts', fake_resolve)
    rows = ft.collect_many_facts([first, second])

    assert calls['count'] == 1
    assert [row.profile.name for row in rows] == ['첫사람', '둘째사람']
    assert rows[0] is not rows[1]


def test_direct_canonical_cache_short_circuits_legacy_scan(tmp_path, monkeypatch):
    import json
    from dataclasses import replace
    import forceteller as ft
    from storage import profile_key

    profile = person('캐시사용자', 1995, 4, 19, 'M', 15, 0)
    facts = cached_source_facts(profile, '壬子')
    fake_settings = replace(
        ft.SETTINGS,
        root=tmp_path,
        data_dir=tmp_path / 'data',
        cache_dir=tmp_path / 'data' / 'cache',
        report_dir=tmp_path / 'data' / 'reports',
        forceteller_dir=tmp_path / 'data' / 'forceteller',
        browser_profile_dir=tmp_path / '.browser-profile',
    )
    monkeypatch.setattr(ft, 'SETTINGS', fake_settings)

    folder = fake_settings.forceteller_dir / profile_key(profile.as_dict())
    folder.mkdir(parents=True)
    (folder / 'forceteller_facts.json').write_text(
        json.dumps(facts.as_dict(), ensure_ascii=False), encoding='utf-8'
    )
    (folder / 'metadata.json').write_text(
        json.dumps({'profile': profile.as_dict(), 'parser_version': fake_settings.parser_version}, ensure_ascii=False),
        encoding='utf-8',
    )

    def should_not_scan(_profile):
        raise AssertionError('legacy scan should not run on a canonical cache hit')

    monkeypatch.setattr(ft, '_matching_profile_cache_folders', should_not_scan)
    resolved, resolved_folder = ft._resolve_best_cached_facts(profile)

    assert resolved is not None
    assert resolved.chart.day_pillar == '壬子'
    assert resolved_folder == folder


def test_partial_retry_flag_never_forces_external_refresh(monkeypatch):
    from dataclasses import replace
    import forceteller as ft

    profile = person('기존캐시', 1995, 4, 19, 'M', 15, 0)
    facts = cached_source_facts(profile, '壬子')
    monkeypatch.setattr(ft, 'SETTINGS', replace(ft.SETTINGS, retry_partial_facts=True))

    # Optional detail gaps may trigger a local raw reparse, but the saved external source itself
    # remains authoritative enough to prevent an automatic browser revisit.
    assert ft._cached_facts_usable(facts.as_dict(), False) is True
    assert ft._cached_facts_usable(facts.as_dict(), True) is False


def test_collect_many_full_cache_hit_never_starts_playwright(monkeypatch):
    import forceteller as ft

    profile = person('캐시전용', 1995, 4, 19, 'M', 15, 0)
    cached = cached_source_facts(profile, '壬子')

    monkeypatch.setattr(
        ft,
        '_resolve_best_cached_facts',
        lambda profile, *, force=False, require_fortune=False: (cached, Path('.')),
    )

    def forbidden_playwright():
        raise AssertionError('Playwright must not start when the source cache already exists')

    monkeypatch.setattr(ft, 'sync_playwright', forbidden_playwright)
    rows = ft.collect_many_facts([profile])

    assert len(rows) == 1
    assert rows[0].chart.day_pillar == '壬子'
    assert rows[0].profile.name == '캐시전용'
