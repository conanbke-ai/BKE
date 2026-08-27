from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Iterable

from config import SETTINGS
from constants import DOUBLE_HOURS
from forceteller import _facts_from_dict as forceteller_facts_from_dict, collect_many_facts, local_facts
from models import BirthProfile, ForcetellerFacts, MatchCandidate, Mode
from scoring import score_friend, score_love, score_pair
from storage import cache_path, canonical_profile_identity, read_json, stable_hash, write_json


def _iter_dates(start_year: int, end_year: int) -> Iterable[date]:
    current = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    while current <= end:
        yield current
        current += timedelta(days=1)


def _candidate_profile(user: BirthProfile, d: date, hour: int, minute: int, name: str = '추천 후보') -> BirthProfile:
    return BirthProfile(
        name=name,
        gender=user.partner_gender,
        calendar_type='solar',
        year=d.year,
        month=d.month,
        day=d.day,
        hour=hour,
        minute=minute,
        country_code=user.country_code,
        country=user.country,
        city=user.city,
        location=user.location,
        location_id=user.location_id,
        partner_gender=user.gender,
    )


def automatic_age_range(user_year: int) -> tuple[int, int, int, int]:
    """예전 프로그램에서 사용하던 현실 연령 범위를 그대로 복원한다.

    연령은 기존 로직과 동일하게 현재연도-출생연도로 구간을 나눈다.
    """
    age = date.today().year - user_year
    if age < 19:
        raise ValueError('미성년자는 상대 후보 검색 대상이 아닙니다.')
    if age <= 24:
        older, younger = 5, 3
    elif age <= 39:
        older, younger = 8, 5
    elif age <= 49:
        older, younger = 10, 8
    else:
        older, younger = 12, 10
    return user_year - older, user_year + younger, older, younger


def _realistic_year_range(user: BirthProfile) -> tuple[int, int, int, int]:
    start_year, end_year, older, younger = automatic_age_range(user.year)
    start_year = max(1900, start_year)
    adult_latest_year = date.today().year - SETTINGS.min_partner_age
    end_year = min(end_year, adult_latest_year)
    if start_year > end_year:
        start_year = max(1900, end_year - older - younger)
    return start_year, end_year, older, younger


def _best_local_each_year_both_modes(
    user_facts: ForcetellerFacts,
    start_year: int,
    end_year: int,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[list[tuple[float, BirthProfile]], list[tuple[float, BirthProfile]], int]:
    """
    범위 안의 모든 날짜 × 12시진을 로컬 구조로 1차 비교한다.

    포스텔러에서만 확정되는 용신·신강신약이 최종 점수에 영향을 주므로, 연도별 로컬 상위
    후보를 몇 명 남겨 세부 원국으로 재확인한 뒤 그중 최종 1명만 순위에 포함한다.
    LOVE/FRIEND는 같은 후보 facts를 재사용하되 최종 점수는 각각 독립 계산한다.
    """
    # 로컬 계산만으로는 포스텔러의 용신·신강신약을 완전히 반영할 수 없으므로
    # 연도별 1명만 바로 확정하지 않고 상위 몇 명을 세부 원국으로 다시 확인한다.
    # 최종 순위에는 여전히 출생연도별 1명만 들어간다.
    shortlist_n = max(1, SETTINGS.auto_shortlist_per_year)
    love_best: dict[int, list[tuple[float, BirthProfile]]] = {}
    friend_best: dict[int, list[tuple[float, BirthProfile]]] = {}
    evaluated = 0
    user = user_facts.profile
    total_days = max(1, (date(end_year, 12, 31) - date(start_year, 1, 1)).days + 1)
    processed_days = 0
    last_emit_bucket = -1

    for d in _iter_dates(start_year, end_year):
        for _, hour, minute in DOUBLE_HOURS:
            p = _candidate_profile(user, d, hour, minute)
            f = local_facts(p)
            evaluated += 1

            love_score = score_pair(user_facts, f, 'love').total
            love_rows = love_best.setdefault(d.year, [])
            love_rows.append((love_score, p))
            love_rows.sort(key=lambda x: x[0], reverse=True)
            del love_rows[shortlist_n:]

            friend_score = score_pair(user_facts, f, 'friend').total
            friend_rows = friend_best.setdefault(d.year, [])
            friend_rows.append((friend_score, p))
            friend_rows.sort(key=lambda x: x[0], reverse=True)
            del friend_rows[shortlist_n:]

        processed_days += 1
        bucket = int(processed_days / total_days * 100)
        if progress_callback and (bucket >= last_emit_bucket + 2 or processed_days == total_days):
            last_emit_bucket = bucket
            progress_callback(processed_days / total_days, f'{d.year}년 후보를 비교하고 있어요.')

    love_rows = sorted((row for rows in love_best.values() for row in rows), key=lambda x: x[0], reverse=True)
    friend_rows = sorted((row for rows in friend_best.values() for row in rows), key=lambda x: x[0], reverse=True)
    return love_rows, friend_rows, evaluated


def _profile_identity(profile: BirthProfile) -> tuple:
    return (
        profile.gender,
        profile.calendar_type,
        profile.year,
        profile.month,
        profile.day,
        profile.hour,
        profile.minute,
        profile.country_code, profile.country, profile.city,
        profile.location_id or profile.location,
    )


def _collect_union(
    love_rows: list[tuple[float, BirthProfile]],
    friend_rows: list[tuple[float, BirthProfile]],
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[tuple, ForcetellerFacts]:
    """연인/친구 연도별 로컬 shortlist의 합집합만 세부 원국 자료로 정밀 확인한다."""
    profiles: dict[tuple, BirthProfile] = {}
    for _, profile in love_rows + friend_rows:
        profiles[_profile_identity(profile)] = profile
    ordered = list(profiles.items())
    collected = collect_many_facts(
        [profile for _, profile in ordered],
        progress_callback=progress_callback,
    )
    return {key: fact for (key, _), fact in zip(ordered, collected)}




def _candidate_key(profile: BirthProfile | dict) -> str:
    if isinstance(profile, dict):
        get = profile.get
        known = bool(get('time_known', True))
        year, month, day = int(get('year', 0)), int(get('month', 0)), int(get('day', 0))
        hour, minute = int(get('hour', 0) or 0), int(get('minute', 0) or 0)
        gender = str(get('gender', ''))
    else:
        known = bool(profile.time_known)
        year, month, day = int(profile.year), int(profile.month), int(profile.day)
        hour, minute = int(profile.hour), int(profile.minute)
        gender = str(profile.gender)
    time_key = f'{hour:02d}{minute:02d}' if known else 'UNKNOWN'
    return f'{year:04d}-{month:02d}-{day:02d}_{time_key}_{gender}'


def _facts_recommendation_usable(facts: ForcetellerFacts) -> bool:
    """Minimum source contract needed to rank a saved recommendation candidate.

    용신/신강신약이 비어 있어도 scoring.py가 해당 축을 중립으로 보수 계산할 수 있다.
    따라서 이미 확인한 외부 원국을 매번 다시 조회하지 않고, 실제 일주와 오행 자료가
    있는 캐시를 재사용한다.
    """
    return (
        str(facts.source).startswith('forceteller')
        and bool(str(facts.chart.day_pillar or '').strip())
        and bool(facts.element_percent)
    )


def _facts_ranking_reproducible(facts: ForcetellerFacts) -> bool:
    """Whether the deterministic local scoring inputs can be reproduced.

    Source-backed facts remain preferred, but a failed external detail lookup must not leave a
    TOP 10 screen with only one or two cards.  Local calendar facts are clearly marked as
    provisional and are safe to cache because the same birth input reproduces the same result.
    """
    return bool(str(facts.chart.day_pillar or '').strip()) and bool(facts.element_percent)

def _best_exact_per_year(
    user_facts: ForcetellerFacts,
    facts_rows: Iterable[ForcetellerFacts],
    mode: Mode,
) -> list[MatchCandidate]:
    """
    정밀 facts로 재채점한 뒤에도 연도별 1개 규칙을 다시 강제한다.
    연도별 shortlist 안의 후보를 세부 원국으로 다시 채점하고 최종 1명만 남긴다.
    """
    verified_winners: dict[int, MatchCandidate] = {}
    provisional_winners: dict[int, MatchCandidate] = {}
    for facts in facts_rows:
        if not _facts_ranking_reproducible(facts):
            continue
        result = score_love(user_facts, facts) if mode == 'love' else score_friend(user_facts, facts)
        item = MatchCandidate(facts.profile, facts, result)
        target = verified_winners if _facts_recommendation_usable(facts) else provisional_winners
        current = target.get(facts.profile.year)
        if current is None or item.result.total > current.result.total:
            target[facts.profile.year] = item
    # A source-backed row always wins its birth-year slot.  Other years remain visible as
    # provisional local candidates instead of disappearing from the requested TOP 10.
    winners = {**provisional_winners, **verified_winners}
    return sorted(winners.values(), key=lambda c: c.result.total, reverse=True)


def _source_status(facts: ForcetellerFacts) -> dict:
    source_backed = str(facts.source).startswith('forceteller')
    verified = facts.source_quality >= SETTINGS.min_verified_source_quality and source_backed
    label = (
        '세부 원국 자료 확인 완료'
        if verified else
        ('저장된 원국 자료 사용 · 일부 세부 항목은 보수 계산' if source_backed else '기본 원국 계산 기준 · 세부 원국 확인 전 예비 후보')
    )
    return {'verified': verified, 'source_backed': source_backed, 'label': label, 'quality': facts.source_quality}


def _age_meta(profile: BirthProfile) -> dict:
    today = date.today()
    age = today.year - profile.year - ((today.month, today.day) < (profile.month, profile.day))
    return {'age': age}



def _facts_complete(facts: ForcetellerFacts) -> bool:
    return (
        facts.source_quality >= SETTINGS.min_verified_source_quality
        and str(facts.source).startswith('forceteller')
        and bool(facts.chart.day_pillar)
        and bool(str(facts.strength_label or '').strip())
        and bool(facts.useful_elements)
    )


def _ranked_sources_reusable(payload: object) -> bool:
    """Whether the displayed LOVE/FRIEND ranking can be reproduced from saved facts.

    Temporary shortlist losers are intentionally ignored here.  They are not rendered and a
    failed loser must never force the whole candidate pool to be collected again.
    """
    if not isinstance(payload, dict):
        return False
    love_rows = list(payload.get('love') or [])
    friend_rows = list(payload.get('friend') or [])
    if not love_rows or not friend_rows:
        return False
    try:
        return all(
            _facts_recommendation_usable(forceteller_facts_from_dict(row.get('facts') or {}))
            for row in [*love_rows, *friend_rows]
        )
    except Exception:
        return False


def _ranked_rows_reproducible(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    rows = [*(payload.get('love') or []), *(payload.get('friend') or [])]
    if not rows:
        return False
    try:
        return all(
            _facts_ranking_reproducible(forceteller_facts_from_dict(row.get('facts') or {}))
            for row in rows
        )
    except Exception:
        return False


def _auto_cache_usable(payload: object) -> bool:
    """Recommendation cache validity is based on scoring inputs, not UI/parser revision.

    A parser release should not force another exhaustive date scan when the cached candidate
    facts already contain the fields used by the scoring engine.
    """
    if not isinstance(payload, dict):
        return False
    meta = payload.get('cache_meta') or {}
    if meta.get('scoring_version') != SETTINGS.scoring_version:
        return False
    requested = int((meta.get('cache_identity') or {}).get('top_n') or 0)
    if requested:
        if len(payload.get('love') or []) < requested or len(payload.get('friend') or []) < requested:
            return False
    return _ranked_rows_reproducible(payload)

def search_auto_matches(
    user_facts: ForcetellerFacts,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    연인/친구를 독립 계산한다.

    - 현실 연령 범위만 탐색한다.
    - 범위 안의 모든 날짜와 12시진을 로컬 구조로 1차 계산한다.
    - 연도별 상위 shortlist만 세부 원국으로 다시 확인한다.
    - 같은 출생연도에서는 최종적으로 생년월일시 1개만 순위에 포함한다.
    """
    start_year, end_year, older, younger = _realistic_year_range(user_facts.profile)
    cache_identity = {
        'user': canonical_profile_identity(user_facts.profile.as_dict()),
        'range': [start_year, end_year],
        'top_n': SETTINGS.top_n,
        'shortlist_per_year': SETTINGS.auto_shortlist_per_year,
        'scoring': SETTINGS.scoring_version,
        'age_policy': 'dynamic-v1',
    }
    cache_key = stable_hash(cache_identity)[:32]
    result_cache = cache_path('auto_matches', cache_key)
    cached = read_json(result_cache)
    if _auto_cache_usable(cached):
        if progress_callback:
            progress_callback(1.0, '저장된 추천 결과를 바로 불러왔어요.')
        return cached
    def local_progress(frac: float, message: str) -> None:
        if progress_callback:
            progress_callback(frac * 0.72, message)

    love_shortlist, friend_shortlist, evaluated = _best_local_each_year_both_modes(
        user_facts, start_year, end_year, progress_callback=local_progress
    )

    def collect_progress(frac: float, message: str) -> None:
        if progress_callback:
            progress_callback(0.72 + frac * 0.24, message)

    # Older caches may contain only the few candidates whose remote detail pages happened to
    # succeed.  Keep those verified facts, but do not repeat the entire remote collection just
    # to fill the visible TOP 10.  The newly scanned shortlist can be scored deterministically
    # with local facts and is marked provisional in the UI.
    if _ranked_sources_reusable(cached):
        collected: dict[tuple, ForcetellerFacts] = {}
        for _, profile in love_shortlist + friend_shortlist:
            collected[_profile_identity(profile)] = local_facts(profile)
        for row in [*(cached.get('love') or []), *(cached.get('friend') or [])]:
            facts = forceteller_facts_from_dict(row.get('facts') or {})
            collected[_profile_identity(facts.profile)] = facts
        if progress_callback:
            progress_callback(0.96, '확인된 후보는 유지하고 TOP 10의 빈자리를 정리하고 있어요.')
    else:
        collected = _collect_union(love_shortlist, friend_shortlist, progress_callback=collect_progress)
    love_candidates = _best_exact_per_year(user_facts, collected.values(), 'love')[:SETTINGS.top_n]
    friend_candidates = _best_exact_per_year(user_facts, collected.values(), 'friend')[:SETTINGS.top_n]

    for i, item in enumerate(love_candidates, 1):
        item.rank = i
    for i, item in enumerate(friend_candidates, 1):
        item.rank = i

    if progress_callback:
        progress_callback(1.0, '연인·친구 추천 순위를 정리했어요.')

    def export(c: MatchCandidate) -> dict:
        payload = c.as_dict()
        payload['candidate_key'] = _candidate_key(c.profile)
        payload['source_status'] = _source_status(c.facts)
        payload['ranking_tier'] = 'verified' if _facts_recommendation_usable(c.facts) else 'provisional'
        payload['age_meta'] = _age_meta(c.profile)
        return payload

    payload = {
        'love': [export(c) for c in love_candidates],
        'friend': [export(c) for c in friend_candidates],
        'search_range': {
            'start_year': start_year,
            'end_year': end_year,
            'older_years': older,
            'younger_years': younger,
            'shortlist_per_year': SETTINGS.auto_shortlist_per_year,
            'rule': '모든 날짜·12시진을 로컬 구조로 비교하고 출생연도별 1명만 남깁니다. 세부 원국 확인 후보를 우선하며, 확인 실패로 순위가 부족하면 로컬 원국 기반 예비 후보로 TOP 10을 채웁니다.',
        },
        'evaluated_local_birth_datetimes': evaluated,
        'collected_unique_profiles': len(collected),
        'verified_unique_profiles': sum(1 for f in collected.values() if _facts_complete(f)),
        'unverified_unique_profiles': sum(1 for f in collected.values() if not _facts_complete(f)),
    }
    complete_sources = all(_facts_complete(f) for f in collected.values())
    all_shortlist_reusable = all(_facts_recommendation_usable(f) for f in collected.values())
    usable_count = sum(1 for f in collected.values() if _facts_recommendation_usable(f))
    ranked_sources_reusable = _ranked_sources_reusable(payload)
    ranked_rows_reproducible = _ranked_rows_reproducible(payload)
    display_complete = len(payload['love']) >= SETTINGS.top_n and len(payload['friend']) >= SETTINGS.top_n
    payload['usable_unique_profiles'] = usable_count
    payload['cache_meta'] = {
        'parser_version': SETTINGS.parser_version,
        'scoring_version': SETTINGS.scoring_version,
        'complete_sources': complete_sources,
        # A failed non-winning shortlist row must not invalidate an already reproducible TOP list.
        'reusable_sources': ranked_sources_reusable,
        'reproducible_rows': ranked_rows_reproducible,
        'display_complete': display_complete,
        'all_shortlist_reusable': all_shortlist_reusable,
        'unusable_shortlist_profiles': max(0, len(collected) - usable_count),
        'cache_policy': 'cache_first_manual_refresh',
        'cache_identity': cache_identity,
    }
    # Cache the displayed recommendation set as soon as every displayed row has reproducible
    # source-backed facts.  Older behavior required every temporary shortlist row to succeed;
    # one failed loser therefore caused the entire 49-profile source pass to repeat next run.
    if ranked_rows_reproducible and payload['love'] and payload['friend']:
        write_json(result_cache, payload)
    return payload


def ideal_from_auto(auto_rows: list[dict], top_n: int | None = None) -> list[dict]:
    """현실 연령 범위와 연도별 1개 규칙을 통과한 정밀 후보 중 상위 결과를 보여준다."""
    top_n = top_n or SETTINGS.ideal_top_n
    result: list[dict] = []
    seen_years: set[int] = set()
    for row in auto_rows:
        p = row['profile']
        if p['year'] in seen_years:
            continue
        seen_years.add(p['year'])
        result.append({
            'candidate_key': row.get('candidate_key') or _candidate_key(p),
            'birth': p,
            'chart': row['facts']['chart'],
            'score': row['result']['total'],
            'label': row['result']['label'],
            'axes': row['result']['axes'],
            'source_quality': row['facts'].get('source_quality', 0),
            'source_status': row.get('source_status', {}),
            'age_meta': row.get('age_meta', {}),
            'note': '설정한 현실 연령 범위의 실제 달력상 날짜·12시진을 로컬 구조로 먼저 비교하고, 연도별 상위 후보를 세부 원국으로 재확인한 뒤 출생연도마다 최종 1개만 남긴 결과입니다. 특정 실존 인물을 검색한 결과는 아닙니다.',
        })
        if len(result) >= top_n:
            break
    return result
