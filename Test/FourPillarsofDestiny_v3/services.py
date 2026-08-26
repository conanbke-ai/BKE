from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from ai_reporter import generate_initial_ai, generate_optional_deep_ai
from bazi_engine import profile_to_solar
from config import SETTINGS
from constants import TERM_DICTIONARY
from explain import build_pair_report, build_profile_report
from forceteller import _facts_from_dict as forceteller_facts_from_dict, collect_facts, collect_many_facts
from fortune import build_fortunes
from group import analyze_group
from locations import country_name, location_fields
from models import BirthProfile, Chart, ForcetellerFacts
from quality import (
    ensure_no_contract_issues,
    validate_fortunes,
    validate_group_analysis,
    validate_pair_report,
    validate_profile_report,
)
from scoring import score_pair
from search_engine import ideal_from_auto, search_auto_matches
from storage import cache_path, canonical_profile_identity, read_json, stable_hash, write_json

ProgressCallback = Callable[[str, float, str], None]


def _emit(progress_callback: ProgressCallback | None, stage: str, fraction: float, message: str) -> None:
    if progress_callback:
        progress_callback(stage, max(0.0, min(1.0, float(fraction))), message)



def _as_bool(value: Any, default: bool = False) -> bool:
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


def _required_int(data: dict[str, Any], key: str, label: str) -> int:
    value = data.get(key)
    if value in (None, ''):
        raise ValueError(f'{label}을 입력해 주세요.')
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}을 숫자로 입력해 주세요.') from exc


def _validate_birth_values(*, calendar_type: str, year: int, month: int, day: int, hour: int, minute: int, time_known: bool) -> None:
    if not 1900 <= year <= 2100:
        raise ValueError('출생연도는 1900~2100년 사이로 입력해 주세요.')
    if not 1 <= month <= 12:
        raise ValueError('출생월은 1~12월 사이로 입력해 주세요.')
    if not 1 <= day <= 31:
        raise ValueError('출생일을 확인해 주세요.')
    if calendar_type == 'solar':
        try:
            date(year, month, day)
        except ValueError as exc:
            raise ValueError('존재하지 않는 양력 생년월일입니다.') from exc
    else:
        # 음력은 월 길이와 윤달 여부를 lunar_python에서 최종 검증한다.
        if day > 30:
            raise ValueError('음력 날짜는 1~30일 사이로 입력해 주세요.')
    if time_known and not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError('출생시간은 00:00~23:59 사이로 입력해 주세요.')


def birth_profile_from_dict(data: dict[str, Any], *, default_name: str = '분석대상') -> BirthProfile:
    code = str(data.get('country_code') or 'KR').upper().strip()
    country = str(data.get('country') or country_name(code)).strip()
    city = str(data.get('city') or '').strip()
    location, default_location_id = location_fields(code, country, city)
    location_id = str(data.get('location_id') or default_location_id or '')
    if code == 'KR' and not location_id:
        location_id = SETTINGS.default_location_id

    calendar_type = 'lunar' if str(data.get('calendar_type', 'solar')).lower() == 'lunar' else 'solar'
    year = _required_int(data, 'year', '출생연도')
    month = _required_int(data, 'month', '출생월')
    day = _required_int(data, 'day', '출생일')
    time_known = _as_bool(data.get('time_known'), True)
    if time_known:
        hour = _required_int(data, 'hour', '출생 시')
        minute_value = data.get('minute', 0)
        if minute_value in (None, ''):
            minute = 0
        else:
            try:
                minute = int(minute_value)
            except (TypeError, ValueError) as exc:
                raise ValueError('출생 분을 숫자로 입력해 주세요.') from exc
    else:
        hour, minute = 12, 0
    is_leap_month = _as_bool(data.get('is_leap_month'), False) if calendar_type == 'lunar' else False
    _validate_birth_values(
        calendar_type=calendar_type, year=year, month=month, day=day,
        hour=hour, minute=minute, time_known=time_known,
    )

    gender_raw = str(data.get('gender', 'F')).upper().strip()
    partner_raw = str(data.get('partner_gender', 'M')).upper().strip()
    profile = BirthProfile(
        name=str(data.get('name') or default_name).strip() or default_name,
        gender='M' if gender_raw == 'M' else 'F',
        calendar_type=calendar_type,
        year=year, month=month, day=day,
        # 출생시간 미상은 날짜 변환용 내부 기준값만 보관하며 시주에는 사용하지 않는다.
        hour=hour if time_known else 12,
        minute=minute if time_known else 0,
        time_known=time_known,
        is_leap_month=is_leap_month,
        country_code=code,
        country=country,
        city=city,
        location=location,
        location_id=location_id,
        partner_gender='F' if partner_raw == 'F' else 'M',
    )
    if calendar_type == 'lunar':
        try:
            profile_to_solar(profile)
        except Exception as exc:
            raise ValueError('존재하지 않는 음력 날짜이거나 해당 연도의 윤달이 아닙니다.') from exc
    return profile


def facts_from_dict(data: dict[str, Any]) -> ForcetellerFacts:
    # 포스텔러 캐시 스키마의 구버전/신버전 호환 처리는 한 곳에서만 수행한다.
    return forceteller_facts_from_dict(data)



def _facts_verified(facts: ForcetellerFacts, *, require_fortune: bool = False) -> bool:
    core = (
        facts.source_quality >= SETTINGS.min_verified_source_quality
        and str(facts.source).startswith('forceteller')
        and bool(facts.chart.day_pillar)
        and bool(str(facts.strength_label or '').strip())
        and bool(facts.useful_elements)
    )
    if require_fortune:
        return core and bool(facts.daewoon)
    return core



def _facts_recommendation_usable(facts: ForcetellerFacts) -> bool:
    return (
        str(facts.source).startswith('forceteller')
        and bool(str(facts.chart.day_pillar or '').strip())
        and bool(facts.element_percent)
    )


def _cache_meta(*, complete_sources: bool, reusable_sources: bool | None = None) -> dict[str, Any]:
    # 'complete' means every optional enrichment field is present.  'reusable' means the
    # saved source is sufficient to reproduce the current report without another browser hit.
    # They are deliberately separate so missing 용신/신강/대운 does not trigger re-collection.
    reusable = bool(complete_sources if reusable_sources is None else reusable_sources)
    return {
        'parser_version': SETTINGS.parser_version,
        'scoring_version': SETTINGS.scoring_version,
        'report_revision': SETTINGS.report_revision,
        'ai_prompt_version': SETTINGS.ai_prompt_version,
        'complete_sources': bool(complete_sources),
        'reusable_sources': reusable,
        'cache_policy': 'source-cache-first-no-network-refresh',
    }


def _result_cache_usable(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    meta = payload.get('cache_meta') or {}
    reusable = meta.get('reusable_sources')
    if reusable is None:
        # Backward compatibility: old result caches only had complete_sources.
        reusable = meta.get('complete_sources')
    return (
        meta.get('parser_version') == SETTINGS.parser_version
        and meta.get('scoring_version') == SETTINGS.scoring_version
        and meta.get('report_revision') == SETTINGS.report_revision
        and bool(reusable)
    )

def _candidate_key(profile_dict: dict[str, Any]) -> str:
    return (f"{profile_dict['year']:04d}-{profile_dict['month']:02d}-{profile_dict['day']:02d}_" + (f"{profile_dict['hour']:02d}{profile_dict['minute']:02d}" if profile_dict.get('time_known', True) else 'UNKNOWN') + f"_{profile_dict.get('gender','')}")


def _build_candidate_payloads(user_facts: ForcetellerFacts, auto: dict[str, Any]) -> tuple[list[dict], dict[str, dict]]:
    unique: dict[str, dict[str, Any]] = {}
    deterministic_reports: dict[str, dict] = {}
    for mode in ('love', 'friend'):
        for row in auto.get(mode, []):
            p = row['profile']
            key = str(row.get('candidate_key') or _candidate_key(p))
            facts = facts_from_dict(row['facts'])
            result = score_pair(user_facts, facts, mode)  # 정밀 facts 기준 재확인
            report = build_pair_report(user_facts, facts, result)
            deterministic_reports[f'{mode}:{key}'] = report
            entry = unique.setdefault(key, {
                'candidate_key': key,
                'birth': p,
                'chart': row['facts']['chart'],
                'source_quality': row['facts'].get('source_quality', 0),
                'common_summary': report['person_b']['overview'],
                'love_summary': '해당 모드 TOP10 대상이 아님',
                'friend_summary': '해당 모드 TOP10 대상이 아님',
                'strengths': [],
                'risks': [],
                'report': report,
            })
            entry[f'{mode}_summary'] = report['overview']
            entry['report'] = report
            entry['strengths'] = list(dict.fromkeys(entry['strengths'] + result.strengths))
            entry['risks'] = list(dict.fromkeys(entry['risks'] + result.risks))
    return list(unique.values()), deterministic_reports


def _compact_group_for_synthesis(local: dict[str, Any]) -> dict[str, Any]:
    """AI 종합 서술에는 필요한 구조만 보낸다.

    그룹 인원이 커질 때 NxN 행렬 전체를 그대로 보내면 입력 토큰이 급격히
    증가한다. 점수/순위/모든 1:1 상세는 Python 결과에 그대로 보존하고,
    종합 서술에는 대표 연결과 역할을 압축해서 전달한다.
    """
    pairs = sorted(
        (
            {
                'a': row.get('a'),
                'b': row.get('b'),
                'score': row.get('score'),
                'label': row.get('label'),
            }
            for row in local.get('pairwise', [])
        ),
        key=lambda row: float(row.get('score') or 0),
        reverse=True,
    )
    names = list(local.get('names', []))
    return {
        'mode': local['mode'],
        'context': local.get('context', 'friends'),
        'context_label': local.get('context_label', ''),
        'team_actions': list(local.get('team_actions', [])),
        'group_score': local['group_score'],
        'group_label': local['group_label'],
        'member_count': len(names),
        'names': names,
        'matrix': local['matrix'] if len(names) <= 15 else None,
        'strongest_pair': {
            'a': local['strongest_pair'].get('a'),
            'b': local['strongest_pair'].get('b'),
            'score': local['strongest_pair'].get('score'),
        },
        'weakest_pair': {
            'a': local['weakest_pair'].get('a'),
            'b': local['weakest_pair'].get('b'),
            'score': local['weakest_pair'].get('score'),
        },
        'top_connections': pairs[:8],
        'needs_coordination': list(reversed(pairs[-8:])),
        'anchor': local['anchor'],
        'bridge': local['bridge'],
        'roles': local['roles'],
        'clusters': local['clusters'],
    }



def _sorted_member_identity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [canonical_profile_identity(row) for row in rows if isinstance(row, dict)]
    return sorted(normalized, key=lambda row: stable_hash(row))


def _initial_ai_identity(
    profile: BirthProfile,
    *,
    build_matches: bool,
    pair_request: dict[str, Any] | None,
    group_request: dict[str, Any] | None,
    moment: datetime,
) -> dict[str, Any]:
    pair_identity = None
    if pair_request and isinstance(pair_request.get('target'), dict):
        pair_identity = {
            'mode': 'friend' if pair_request.get('mode') == 'friend' else 'love',
            'target': canonical_profile_identity(pair_request['target']),
        }
    group_identity = None
    if group_request and isinstance(group_request.get('members'), list):
        group_identity = {
            'context': str(group_request.get('context') or 'friends'),
            'members': _sorted_member_identity(group_request.get('members') or []),
        }
    return {
        'profile': canonical_profile_identity(profile.as_dict()),
        'build_matches': bool(build_matches),
        'pair': pair_identity,
        'group': group_identity,
        # Fortune narrative changes with the calendar period, but UI/parser/report revisions do not.
        'period': {'year': moment.year, 'month': moment.month, 'day': moment.day},
    }


def _old_initial_identity(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        profile = payload.get('profile') or {}
        if not isinstance(profile, dict):
            return None
        generated = str(payload.get('generated_at') or '')[:10]
        period = None
        if generated:
            dt = datetime.fromisoformat(generated)
            period = {'year': dt.year, 'month': dt.month, 'day': dt.day}
        else:
            return None
        auto = payload.get('auto_matches') or {}
        build_matches = bool((auto.get('love') or []) or (auto.get('friend') or []))
        pair_identity = None
        pair = payload.get('initial_pair') or {}
        target_profile = ((pair.get('target_facts') or {}).get('profile') if isinstance(pair, dict) else None)
        if isinstance(target_profile, dict):
            pair_identity = {
                'mode': str((pair.get('result') or {}).get('mode') or 'love'),
                'target': canonical_profile_identity(target_profile),
            }
        group_identity = None
        group = payload.get('initial_group') or {}
        members = group.get('members') if isinstance(group, dict) else None
        if isinstance(members, list) and members:
            member_profiles = [row.get('profile') for row in members if isinstance(row, dict) and isinstance(row.get('profile'), dict)]
            # initial_group includes the user as the first member; request identity stores only extras.
            extras = [row for row in member_profiles if canonical_profile_identity(row) != canonical_profile_identity(profile)]
            group_identity = {
                'context': str((group.get('analysis') or {}).get('context') or 'friends'),
                'members': _sorted_member_identity(extras),
            }
        return {
            'profile': canonical_profile_identity(profile),
            'build_matches': build_matches,
            'pair': pair_identity,
            'group': group_identity,
            'period': period,
        }
    except Exception:
        return None


def _find_reusable_initial_ai(cache_identity: dict[str, Any]) -> dict[str, Any] | None:
    """Salvage AI already paid for from older final-report caches.

    This lets a new parser/UI/report revision rebuild deterministic content without another API
    charge.  Only an exact same people/selection/day identity is accepted.
    """
    root = SETTINGS.cache_dir / 'initial'
    if not root.exists():
        return None
    try:
        files = sorted(root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:250]
    except Exception:
        files = list(root.glob('*.json'))[:250]
    for path in files:
        old = read_json(path)
        if not isinstance(old, dict) or not isinstance(old.get('ai'), dict):
            continue
        if _old_initial_identity(old) == cache_identity:
            return old['ai']
    return None


def _auto_payload_complete(auto: object) -> bool:
    if not isinstance(auto, dict):
        return False
    love_rows = list(auto.get('love') or [])
    friend_rows = list(auto.get('friend') or [])
    # The first-run recommendation feature builds both tabs. A past run where only one tab
    # survived collection must not become the reusable canonical result.
    if not love_rows or not friend_rows:
        return False
    rows = [*love_rows, *friend_rows]
    try:
        return all(_facts_recommendation_usable(facts_from_dict(row.get('facts') or {})) for row in rows)
    except Exception:
        return False


def _find_reusable_auto_matches(profile: BirthProfile) -> dict[str, Any] | None:
    """Reuse an already-computed recommendation set from an older report revision.

    This is intentionally independent of report/UI/parser revision. The expensive exhaustive
    date search only needs to repeat when the scoring contract or actual candidate source facts
    are incomplete.
    """
    root = SETTINGS.cache_dir / 'initial'
    if not root.exists():
        return None
    wanted = canonical_profile_identity(profile.as_dict())
    try:
        paths = sorted(root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:300]
    except Exception:
        paths = list(root.glob('*.json'))[:300]
    for path in paths:
        row = read_json(path)
        if not isinstance(row, dict):
            continue
        old_profile = row.get('profile') or {}
        if not isinstance(old_profile, dict) or canonical_profile_identity(old_profile) != wanted:
            continue
        meta = row.get('cache_meta') or {}
        if meta.get('scoring_version') not in (None, '', SETTINGS.scoring_version):
            continue
        auto = row.get('auto_matches')
        if _auto_payload_complete(auto):
            return auto
    return None


def _pair_ai_identity(user: BirthProfile, target: BirthProfile, mode: str) -> dict[str, Any]:
    return {
        'mode': 'friend' if mode == 'friend' else 'love',
        'a': canonical_profile_identity(user.as_dict()),
        'b': canonical_profile_identity(target.as_dict()),
    }


def _group_ai_identity(profiles: list[BirthProfile], context: str) -> dict[str, Any]:
    return {
        'context': context,
        'members': sorted(
            [
                {'identity': canonical_profile_identity(p.as_dict()), 'name': p.name}
                for p in profiles
            ],
            key=lambda row: stable_hash(row),
        ),
    }

def initial_analysis(
    profile: BirthProfile,
    *,
    force_ai: bool = False,
    ai_cache_only: bool = False,
    build_matches: bool | None = None,
    pair_request: dict[str, Any] | None = None,
    group_request: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """첫 제출에서 선택된 분석을 한 번에 구성한다.

    화면에서 1:1/그룹을 미리 선택했다면 로컬 계산을 먼저 끝낸 뒤 초기 종합
    해설 요청 payload에 함께 넣는다. 따라서 이 초기 리포트 생성 단계의 자연어
    종합 호출은 최대 한 번이다.
    """
    build_matches = SETTINGS.build_auto_matches_on_first_run if build_matches is None else _as_bool(build_matches, SETTINGS.build_auto_matches_on_first_run)
    # A UI/test request cannot accidentally force a paid regeneration unless the operator has
    # explicitly enabled it in .env.
    force_ai = bool(force_ai and SETTINGS.allow_force_ai_regeneration)
    moment = datetime.now()
    ai_cache_identity = _initial_ai_identity(
        profile, build_matches=build_matches, pair_request=pair_request, group_request=group_request, moment=moment
    )
    request_signature = {
        'profile': profile.as_dict(),
        'build_matches': build_matches,
        'pair_request': pair_request or {},
        'group_request': group_request or {},
        'revision': SETTINGS.report_revision,
        'parser': SETTINGS.parser_version,
        'prompt': SETTINGS.ai_prompt_version,
    }
    key = stable_hash(request_signature)[:28]
    final_cache = cache_path('initial', f'{key}_{SETTINGS.scoring_version}_{SETTINGS.parser_version}_{SETTINGS.report_revision}')
    if final_cache.exists() and not force_ai:
        cached = read_json(final_cache)
        if _result_cache_usable(cached):
            _emit(progress_callback, 'finalize', 1.0, '저장된 리포트를 바로 불러왔어요.')
            return cached

    _emit(progress_callback, 'natal', 0.0, '출생정보와 원국 자료를 확인하고 있어요.')
    user_facts = collect_facts(
        profile,
        require_fortune=True,
        progress_callback=lambda frac, msg: _emit(progress_callback, 'natal', frac, msg),
    )
    _emit(progress_callback, 'natal', 1.0, '원국 자료 확인이 끝났어요.')

    _emit(progress_callback, 'local', 0.0, '내 사주와 운세 구조를 정리하고 있어요.')
    profile_local = build_profile_report(user_facts)
    ensure_no_contract_issues(
        validate_profile_report(profile_local, path='initial.profile_local'),
        label='내 사주 해설',
    )
    _emit(progress_callback, 'local', 0.55, '성격·직장·재물·관계 구조를 정리했어요.')
    fortunes = build_fortunes(user_facts, moment)
    ensure_no_contract_issues(
        validate_fortunes(fortunes, path='initial.fortunes'),
        label='기간별 운세',
    )
    _emit(progress_callback, 'local', 1.0, '현재 운의 흐름까지 정리했어요.')

    auto = {'love': [], 'friend': [], 'search_range': {}, 'collected_unique_profiles': 0}
    ideal_love: list[dict] = []
    ideal_friend: list[dict] = []
    deterministic_reports: dict[str, dict] = {}
    candidate_payloads: list[dict] = []

    if build_matches:
        _emit(progress_callback, 'auto_scan', 0.0, '현실적인 연령 범위에서 후보를 비교하기 시작했어요.')

        def auto_progress(frac: float, msg: str) -> None:
            frac = max(0.0, min(1.0, float(frac)))
            # search_auto_matches uses 0~0.72 for the exhaustive local scan and
            # 0.72~0.96 for Forceteller verification. Split those phases so a slow
            # external request cannot distort or freeze the whole recommendation ETA.
            if frac <= 0.72:
                _emit(progress_callback, 'auto_scan', frac / 0.72 if 0.72 else 1.0, msg)
            else:
                _emit(progress_callback, 'auto_scan', 1.0, '추천 후보 탐색을 마쳤어요.')
            if frac >= 0.72:
                collect_frac = max(0.0, min(1.0, (frac - 0.72) / 0.24))
                _emit(progress_callback, 'auto_collect', collect_frac, msg)

        reusable_auto = _find_reusable_auto_matches(profile)
        if reusable_auto is not None:
            auto = reusable_auto
            _emit(progress_callback, 'auto_scan', 1.0, '저장된 추천 후보 계산을 바로 사용했어요.')
            _emit(progress_callback, 'auto_collect', 1.0, '저장된 추천 후보 원국 자료를 바로 사용했어요.')
        else:
            auto = search_auto_matches(
                user_facts,
                progress_callback=auto_progress,
            )
        _emit(progress_callback, 'auto_scan', 1.0, '추천 후보 탐색을 마쳤어요.')
        _emit(progress_callback, 'auto_collect', 1.0, '추천 후보 원국 자료 확인이 끝났어요.')
        ideal_love = ideal_from_auto(auto.get('love', []))
        ideal_friend = ideal_from_auto(auto.get('friend', []))
        candidate_payloads, deterministic_reports = _build_candidate_payloads(user_facts, auto)

    prebuilt_pair: dict[str, Any] | None = None
    pair_extra_payloads: list[dict[str, Any]] = []
    if pair_request and pair_request.get('target'):
        target = birth_profile_from_dict(pair_request['target'], default_name='상대')
        mode = 'friend' if pair_request.get('mode') == 'friend' else 'love'
        _emit(progress_callback, 'pair_collect', 0.0, '선택한 상대의 원국 자료를 확인하고 있어요.')

        def initial_pair_progress(stage: str, frac: float, msg: str) -> None:
            mapped = 'pair_collect' if stage == 'collect' else 'pair_score'
            _emit(progress_callback, mapped, frac, msg)

        prebuilt_pair = pair_analysis(
            profile, target, mode, use_ai=False, progress_callback=initial_pair_progress
        )
        _emit(progress_callback, 'pair_collect', 1.0, '1:1 상대 원국 확인이 끝났어요.')
        _emit(progress_callback, 'pair_score', 1.0, '1:1 궁합 계산이 끝났어요.')
        pair_extra_payloads.append({
            'request_id': 'initial-pair',
            'mode': mode,
            'report': prebuilt_pair['report'],
        })

    prebuilt_group: dict[str, Any] | None = None
    group_extra_payloads: list[dict[str, Any]] = []
    if group_request and group_request.get('members'):
        extra_members = [birth_profile_from_dict(row, default_name=f'멤버 {i+2}') for i, row in enumerate(group_request.get('members') or [])]
        if extra_members:
            context = str(group_request.get('context') or 'friends')
            _emit(progress_callback, 'group_collect', 0.0, '그룹 구성원의 원국 자료를 확인하고 있어요.')

            def initial_group_progress(stage: str, frac: float, msg: str) -> None:
                mapped = 'group_collect' if stage == 'collect' else 'group_pairwise'
                _emit(progress_callback, mapped, frac, msg)

            prebuilt_group = group_analysis(
                [profile, *extra_members],
                context=context,
                use_ai=False,
                progress_callback=initial_group_progress,
            )
            _emit(progress_callback, 'group_collect', 1.0, '그룹 구성원 원국 확인이 끝났어요.')
            _emit(progress_callback, 'group_pairwise', 1.0, '그룹 관계 구조 계산이 끝났어요.')
            analyzed_context = str(prebuilt_group.get('analysis', {}).get('context') or 'friends')
            group_extra_payloads.append({
                'request_id': 'initial-group',
                'mode': 'friend',
                'context': analyzed_context,
                'compact': _compact_group_for_synthesis(prebuilt_group['analysis']),
            })

    ai_payload = {
        'user_facts': user_facts.as_dict(),
        'profile_local': profile_local,
        'fortunes': fortunes,
        'auto_match_summary': {
            'love': [{'rank': x['rank'], 'birth': x['profile'], 'score': x['result']['total'], 'label': x['result']['label'], 'axes': x['result']['axes']} for x in auto.get('love', [])],
            'friend': [{'rank': x['rank'], 'birth': x['profile'], 'score': x['result']['total'], 'label': x['result']['label'], 'axes': x['result']['axes']} for x in auto.get('friend', [])],
        },
        'ideal_love': ideal_love,
        'ideal_friend': ideal_friend,
        'candidate_payloads': candidate_payloads,
        'pair_extras': pair_extra_payloads,
        'group_extras': group_extra_payloads,
    }
    _emit(progress_callback, 'narrative', 0.0, '계산 결과를 읽기 쉬운 해설로 정리하고 있어요.')
    reusable_ai = None if force_ai else _find_reusable_initial_ai(ai_cache_identity)
    ai = generate_initial_ai(
        ai_payload,
        SETTINGS.cache_dir,
        force=force_ai,
        cache_identity=ai_cache_identity,
        reuse_ai=reusable_ai,
        cache_only=bool(ai_cache_only),
    )
    _emit(progress_callback, 'narrative', 1.0, '상세 해설을 정리했어요.')

    if prebuilt_pair:
        synthesis = next((x for x in ai.get('pair_extras', []) if x.get('request_id') == 'initial-pair'), None)
        prebuilt_pair['synthesis'] = synthesis
    if prebuilt_group:
        synthesis = next((x for x in ai.get('group_extras', []) if x.get('request_id') == 'initial-group'), None)
        prebuilt_group['synthesis'] = synthesis

    result = {
        'profile': profile.as_dict(),
        'facts': user_facts.as_dict(),
        'profile_local': profile_local,
        'fortunes': fortunes,
        'auto_matches': auto,
        'request_options': {
            'build_matches': bool(build_matches),
            'pair_requested': bool(pair_request and pair_request.get('target')),
            'group_requested': bool(group_request and group_request.get('members')),
            'ai_cache_only': bool(ai_cache_only),
        },
        'ideal_love': ideal_love,
        'ideal_friend': ideal_friend,
        'pair_reports': deterministic_reports,
        'ai': ai,
        'initial_pair': prebuilt_pair,
        'initial_group': prebuilt_group,
        'generated_at': moment.isoformat(timespec='seconds'),
        'ai_cache_identity': ai_cache_identity,
        'glossary': {k: {'reading': v[0], 'plain': v[1], 'detail': v[2]} for k, v in TERM_DICTIONARY.items()},
        'notice': '사주명리는 전통 해석 체계이며 과학적으로 검증된 사건 예측이나 관계 성공확률이 아닙니다.',
    }
    source_complete = _facts_verified(user_facts, require_fortune=True)
    source_reusable = _facts_recommendation_usable(user_facts)
    if build_matches:
        source_complete = source_complete and _auto_payload_complete(auto)
        source_reusable = source_reusable and _auto_payload_complete(auto)
    elif auto.get('love') or auto.get('friend'):
        rows = [*auto.get('love', []), *auto.get('friend', [])]
        source_complete = source_complete and all(_facts_verified(facts_from_dict(row['facts'])) for row in rows)
        source_reusable = source_reusable and all(_facts_recommendation_usable(facts_from_dict(row['facts'])) for row in rows)
    if prebuilt_pair:
        pair_reusable = _result_cache_usable(prebuilt_pair)
        source_complete = source_complete and bool((prebuilt_pair.get('cache_meta') or {}).get('complete_sources'))
        source_reusable = source_reusable and pair_reusable
    if prebuilt_group:
        group_reusable = _result_cache_usable(prebuilt_group)
        source_complete = source_complete and bool((prebuilt_group.get('cache_meta') or {}).get('complete_sources'))
        source_reusable = source_reusable and group_reusable
    result['cache_meta'] = _cache_meta(complete_sources=source_complete, reusable_sources=source_reusable)
    _emit(progress_callback, 'finalize', 0.35, '리포트 화면에 필요한 데이터를 묶고 있어요.')
    # Reproducible source-backed data is cached even if optional enrichment is absent.
    # RETRY_PARTIAL_FACTS remains the explicit opt-in path for an operator who wants a refresh.
    if source_reusable:
        write_json(final_cache, result)
    _emit(progress_callback, 'finalize', 1.0, '리포트 준비가 끝났어요.')
    return result


def pair_analysis(
    user: BirthProfile,
    target: BirthProfile,
    mode: str = 'love',
    use_ai: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    cache_key = stable_hash({
        'a': canonical_profile_identity(user.as_dict()), 'a_name': user.name,
        'b': canonical_profile_identity(target.as_dict()), 'b_name': target.name,
        'mode': 'friend' if mode == 'friend' else 'love',
        'scoring': SETTINGS.scoring_version, 'parser': SETTINGS.parser_version,
        'report': SETTINGS.report_revision, 'with_ai': bool(use_ai),
        'prompt': SETTINGS.ai_prompt_version if use_ai else '',
    })[:36]
    result_cache = cache_path('pair_results', cache_key)
    cached = read_json(result_cache)
    if _result_cache_usable(cached) and cached.get('report') and cached.get('result'):
        _emit(progress_callback, 'collect', 1.0, '저장된 두 사람의 분석 자료를 바로 불러왔어요.')
        _emit(progress_callback, 'pairwise', 1.0, '저장된 궁합 결과를 바로 불러왔어요.')
        return cached
    _emit(progress_callback, 'collect', 0.0, '두 사람의 원국 자료를 확인하고 있어요.')
    user_facts, target_facts = collect_many_facts(
        [user, target],
        progress_callback=lambda frac, msg: _emit(progress_callback, 'collect', frac, msg),
    )
    _emit(progress_callback, 'collect', 1.0, '두 사람의 원국 자료를 확인했어요.')
    _emit(progress_callback, 'pairwise', 0.0, '궁합 축별 점수를 계산하고 있어요.')
    result = score_pair(user_facts, target_facts, 'friend' if mode == 'friend' else 'love')
    report = build_pair_report(user_facts, target_facts, result)
    ensure_no_contract_issues(
        validate_pair_report(
            report, expected_a=user.name, expected_b=target.name, path='pair.report'
        ),
        label='1:1 궁합',
    )
    _emit(progress_callback, 'pairwise', 1.0, '궁합 축별 계산을 마쳤어요.')
    response = {
        'user_facts': user_facts.as_dict(),
        'target_facts': target_facts.as_dict(),
        'result': result.as_dict(),
        'report': report,
        'synthesis': None,
        'cache_meta': _cache_meta(
            complete_sources=_facts_verified(user_facts) and _facts_verified(target_facts),
            reusable_sources=_facts_recommendation_usable(user_facts) and _facts_recommendation_usable(target_facts),
        ),
    }
    if use_ai:
        response['synthesis'] = generate_optional_deep_ai(
            response, SETTINGS.cache_dir, f'pair-{mode}', cache_identity=_pair_ai_identity(user, target, mode)
        )
    if response['cache_meta']['reusable_sources']:
        write_json(result_cache, response)
    return response


def group_analysis(
    profiles: list[BirthProfile],
    context: str = 'friends',
    use_ai: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    # UI 밖에서 잘못된 문자열이 들어와도 그룹을 연애 모드처럼 해석하지 않는다.
    context = context if context in {'friends', 'work', 'family', 'hobby', 'mixed'} else 'friends'
    cache_key = stable_hash({
        'members': [
            {'identity': canonical_profile_identity(p.as_dict()), 'name': p.name}
            for p in profiles
        ],
        'context': context, 'scoring': SETTINGS.scoring_version,
        'parser': SETTINGS.parser_version, 'report': SETTINGS.report_revision,
        'with_ai': bool(use_ai),
        'prompt': SETTINGS.ai_prompt_version if use_ai else '',
    })[:36]
    result_cache = cache_path('group_results', cache_key)
    cached = read_json(result_cache)
    if _result_cache_usable(cached) and cached.get('analysis') and cached.get('members'):
        _emit(progress_callback, 'collect', 1.0, '저장된 구성원 원국 자료를 바로 불러왔어요.')
        _emit(progress_callback, 'pairwise', 1.0, '저장된 그룹 관계 결과를 바로 불러왔어요.')
        return cached
    _emit(progress_callback, 'collect', 0.0, '구성원의 원국 자료를 확인하고 있어요.')
    facts = collect_many_facts(
        profiles,
        progress_callback=lambda frac, msg: _emit(progress_callback, 'collect', frac, msg),
    )
    _emit(progress_callback, 'collect', 1.0, '구성원의 원국 자료를 모두 확인했어요.')
    _emit(progress_callback, 'pairwise', 0.0, '모든 1:1 연결을 계산하고 있어요.')
    local = analyze_group(
        facts,
        'friend',
        context=context,
        progress_callback=lambda frac, msg: _emit(progress_callback, 'pairwise', frac, msg),
    )
    ensure_no_contract_issues(
        validate_group_analysis(
            local, member_names=[f.profile.name for f in facts], path='group.analysis'
        ),
        label='그룹 궁합',
    )
    _emit(progress_callback, 'pairwise', 1.0, '모든 1:1 연결 계산이 끝났어요.')
    response = {
        'members': [f.as_dict() for f in facts],
        'analysis': local,
        'synthesis': None,
        'cache_meta': _cache_meta(
            complete_sources=all(_facts_verified(f) for f in facts),
            reusable_sources=all(_facts_recommendation_usable(f) for f in facts),
        ),
    }
    if use_ai:
        # 원문 HTML을 보내지 않고 Python 구조화 결과만 전달한다.
        compact = _compact_group_for_synthesis(local)
        compact['context'] = local.get('context')
        compact['context_label'] = local.get('context_label')
        response['synthesis'] = generate_optional_deep_ai(
            compact, SETTINGS.cache_dir, f'group-{context}', cache_identity=_group_ai_identity(profiles, context)
        )
    if response['cache_meta']['reusable_sources']:
        write_json(result_cache, response)
    return response
