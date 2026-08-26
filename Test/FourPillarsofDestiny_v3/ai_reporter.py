from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from config import SETTINGS
from quality import lint_object, replace_bad_text
from storage import read_json, write_json

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


CANDIDATE_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': [
        'candidate_key', 'common_analysis', 'love_analysis', 'friend_analysis',
        'communication', 'daily_life', 'long_term', 'strengths', 'cautions',
    ],
    'properties': {
        'candidate_key': {'type': 'string'},
        'common_analysis': {'type': 'string'},
        'love_analysis': {'type': 'string'},
        'friend_analysis': {'type': 'string'},
        'communication': {'type': 'string'},
        'daily_life': {'type': 'string'},
        'long_term': {'type': 'string'},
        'strengths': {'type': 'array', 'items': {'type': 'string'}},
        'cautions': {'type': 'array', 'items': {'type': 'string'}},
    },
}

SYNTHESIS_SCHEMA = {
    'type':'object','additionalProperties':False,
    'required':['request_id','summary','interaction','communication','conflict','daily_life','long_term','practical_advice'],
    'properties':{
        'request_id':{'type':'string'},
        'summary':{'type':'string'},
        'interaction':{'type':'string'},
        'communication':{'type':'string'},
        'conflict':{'type':'string'},
        'daily_life':{'type':'string'},
        'long_term':{'type':'string'},
        'practical_advice':{'type':'array','items':{'type':'string'}},
    },
}

REPORT_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['profile', 'fortune', 'ideal_love', 'ideal_friend', 'candidates', 'pair_extras', 'group_extras', 'methodology_note'],
    'properties': {
        'profile': {
            'type': 'object', 'additionalProperties': False,
            'required': ['overview', 'personality', 'career', 'wealth', 'relationships', 'romance', 'growth'],
            'properties': {k: {'type': 'string'} for k in ['overview', 'personality', 'career', 'wealth', 'relationships', 'romance', 'growth']},
        },
        'fortune': {
            'type': 'object', 'additionalProperties': False,
            'required': ['daewoon', 'yearly', 'monthly', 'daily'],
            'properties': {k: {'type': 'string'} for k in ['daewoon', 'yearly', 'monthly', 'daily']},
        },
        'ideal_love': {'type': 'string'},
        'ideal_friend': {'type': 'string'},
        'candidates': {'type': 'array', 'items': CANDIDATE_SCHEMA},
        'pair_extras': {'type':'array','items':SYNTHESIS_SCHEMA},
        'group_extras': {'type':'array','items':SYNTHESIS_SCHEMA},
        'methodology_note': {'type': 'string'},
    },
}

INSTRUCTIONS = r'''
당신은 전통 사주명리학의 구조를 일반인이 실제 생활에 적용할 수 있도록 설명하는 전문 해설자다.
입력의 원국·오행·십성·신강신약·용신·기간 간지·합충형파해·점수·순위는 계산 엔진이 확정한 사실이다. 절대로 수정하거나 새로 계산하지 않는다.

가장 중요한 작성 원칙:
- 입력에 이미 있는 기본 해설을 다시 바꾸어 말하지 않는다. 기본 해설의 '다음 단계'를 써야 한다.
- 반드시 `구체적 근거 → 두 요소가 함께 작동하는 방식 → 실제 생활에서 나타날 수 있는 형태 → 주의할 오해` 순서로 설명한다.
- 사용자에게 보여주는 본문은 숫자·비율·용신·십성 이름으로 시작하지 않는다. 먼저 "이 사람은 무엇을 원하고, 어떤 상황에서 편하며, 어디서 부딪히는가"를 생활 언어로 결론낸다. 수치와 전문용어는 그 뒤의 근거로만 사용한다.
- 1:1 관계에서는 반드시 A와 B를 비교해 쓴다: `A가 원하는 것 / B가 원하는 것 / 잘 맞는 이유 / 실제 갈등 장면 / A에게 효과적인 말하기 / B에게 효과적인 말하기 / 역할 또는 생활 분담`을 구체적으로 설명한다.
- work 그룹과 그 안의 pair에는 호감·애정표현·배우자·데이트·연애 같은 표현을 절대 사용하지 않는다. 대신 업무 방식·역할 분담·의사결정·피드백·마감·정보 공유·갈등 조율로 쓴다.
- friends 그룹은 애정/배우자 관점이 아니라 친구로서의 편안함·거리·대화·활동 방식으로 쓴다.
- 연애 궁합에서는 서로 원하는 애정 방식, 연락·개인시간·약속·돈·생활·갈등 회복 방식을 실제 장면처럼 비교한다.
- 올해·이번 달·오늘의 해설은 서로 복사하거나 같은 문장을 쓰지 않는다. 올해는 몇 달 단위의 큰 방향, 이번 달은 일정·업무량·관계 접점, 오늘은 당일 행동·대화로 시간 범위를 명확히 구분한다.
- 한 섹션 안에서 최소 3개의 서로 다른 구조 근거를 연결하되, 본문에는 내부 축 이름(resource/peer/output/wealth/officer)이나 원시 키를 절대 노출하지 않는다.
- 전문용어는 `漢字(독음·쉬운 뜻)` 또는 `용어(독음·쉬운 뜻)` 형태로 풀어 쓴다.
- 용신은 부족 오행과 동일시하지 않는다. 신강신약은 사람의 성격이 강하거나 약하다는 뜻이 아니다.
- 합·충·형·파·해를 이별·사고·성공 같은 사건으로 단정하지 않는다.
- 입력에 없는 직업, 재산, 외모, 건강, 정치성향, 실제 행동을 사실처럼 만들지 않는다.
- profile.time_known=false인 사람은 출생시간 미상이다. 시주를 추정하거나 임의의 시각(예: 12:00)을 실제 생시처럼 해석하지 않는다. 연주·월주·일주처럼 확정된 구조만 근거로 쓰고, 시주에 따라 달라질 부분은 미확정이라고 명시한다.
- 점수는 성공확률이 아니다. 방향성 점수는 누가 더 사랑하는지 뜻하지 않는다.
- pair_extra와 group_extra가 입력되면 같은 한 번의 응답 안에서 함께 종합한다. 별도 분석처럼 반복하지 말고 각 관계의 강한 근거와 약한 근거를 동시에 연결한다.
- pair_extra/group_extra가 없으면 각각 빈 배열을 반환한다.
- 편집자 메모, 자기검토, 프롬프트/지침/더미/placeholder/API/모델 자기언급을 출력하지 않는다.
'''


def _cache_key(payload: dict[str, Any], cache_identity: dict[str, Any] | None = None) -> str:
    """Stable paid-AI cache identity.

    UI/report/parser revisions must not trigger another paid call for the same people and
    same analysis selection.  The local deterministic report can be regenerated freely
    while this narrative cache is reused.
    """
    base = {
        'identity': cache_identity or payload.get('cache_identity') or {},
        'model_family': SETTINGS.openai_model,
        'schema_family': 'user-first-bundle-v1',
    }
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def _fortune_fallback_block(row: dict[str, Any]) -> str:
    if not row:
        return ''
    domains = row.get('domains', {})
    return ' '.join(filter(None, [
        row.get('why', ''),
        f"직장에서는 {domains.get('career','')}" if domains.get('career') else '',
        f"금전에서는 {domains.get('wealth','')}" if domains.get('wealth') else '',
        f"관계에서는 {domains.get('relationships','')}" if domains.get('relationships') else '',
        f"연애에서는 {domains.get('romance','')}" if domains.get('romance') else '',
        f"학습에서는 {domains.get('study','')}" if domains.get('study') else '',
    ]))



def _ideal_fallback_text(rows: list[dict[str, Any]], mode_label: str) -> str:
    if not rows:
        return f'{mode_label} 최적 출생일시를 아직 계산하지 않았습니다.'
    top = rows[0]
    birth = top.get('birth', {})
    date_text = f"{birth.get('year','')}.{int(birth.get('month',0)):02d}.{int(birth.get('day',0)):02d} {int(birth.get('hour',0)):02d}:{int(birth.get('minute',0)):02d}"
    return (
        f'현실 연령 범위에서 모든 날짜와 12시진을 1차 비교하고 연도별 상위 후보를 세부 원국으로 재확인했을 때 '
        f'{mode_label} 1위 출생일시는 {date_text}, 명리 구조 적합도는 {float(top.get("score",0)):.1f}/100입니다. '
        '이 순위는 한 가지 오행이나 일주만으로 정한 것이 아니라 여러 관계 요소를 함께 비교한 결과입니다. '
        '후보를 선택하면 상대가 어떤 편인지, 나와 어디가 편하고 어디서 부딪힐 수 있는지, 실제로 어떻게 맞춰 가면 좋은지를 먼저 확인할 수 있습니다.'
    )

def _fallback(payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload.get('profile_local', {})
    deep = profile.get('deep_synthesis', {})
    fortunes = payload.get('fortunes', {})
    candidates = []
    for row in payload.get('candidate_payloads', []):
        report = row.get('report', {})
        analysis = report.get('analysis', {})
        candidates.append({
            'candidate_key': row['candidate_key'],
            'common_analysis': analysis.get('one_line') or row.get('common_summary', ''),
            'love_analysis': analysis.get('why_attracted') if row.get('love_summary') != '해당 모드 TOP10 대상이 아님' else '해당 모드 TOP10 대상이 아님',
            'friend_analysis': analysis.get('communication') if row.get('friend_summary') != '해당 모드 TOP10 대상이 아님' else '해당 모드 TOP10 대상이 아님',
            'communication': analysis.get('communication', ''),
            'daily_life': analysis.get('daily_life', ''),
            'long_term': analysis.get('long_term', ''),
            'strengths': report.get('strengths', row.get('strengths', [])),
            'cautions': report.get('risks', row.get('risks', [])),
        })
    key_points = profile.get('key_points', [])
    overview_deep = ' '.join(f"{x.get('title')}: {x.get('meaning')}" for x in key_points[:4])
    return {
        'profile': {
            'overview': overview_deep or profile.get('overview', ''),
            'personality': deep.get('personality', profile.get('personality', '')),
            'career': deep.get('career', profile.get('career', '')),
            'wealth': deep.get('wealth', profile.get('wealth', '')),
            'relationships': deep.get('relationships', profile.get('relationships', '')),
            'romance': deep.get('romance', profile.get('romance', '')),
            'growth': '강한 축을 더 많이 쓰는 것보다, 강한 축이 과해질 때 생기는 피로를 관리하고 약한 축은 습관·도구·환경으로 보완하는 방식이 실제 활용에 더 적합합니다.',
        },
        'fortune': {
            'daewoon': fortunes.get('daewoon', {}).get('detail', fortunes.get('daewoon', {}).get('summary', '')),
            'yearly': _fortune_fallback_block(fortunes.get('yearly', {})),
            'monthly': _fortune_fallback_block(fortunes.get('monthly', {})),
            'daily': _fortune_fallback_block(fortunes.get('daily', {})),
        },
        'ideal_love': _ideal_fallback_text(payload.get('ideal_love', []), '연인'),
        'ideal_friend': _ideal_fallback_text(payload.get('ideal_friend', []), '친구'),
        'candidates': candidates,
        'pair_extras': [dict({'request_id': row.get('request_id','initial-pair')}, **{k:v for k,v in _optional_fallback(row, 'pair-'+str(row.get('mode','love'))).items() if k != 'methodology_note'}) for row in payload.get('pair_extras', [])],
        'group_extras': [dict({'request_id': row.get('request_id','initial-group')}, **{k:v for k,v in _optional_fallback(row.get('compact', row), 'group-'+str(row.get('mode','friend'))).items() if k != 'methodology_note'}) for row in payload.get('group_extras', [])],
        'methodology_note': '여러 명리 근거를 연결해 실제 생활에서의 의미를 보완합니다.',
    }


def _sanitize(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        return replace_bad_text(value, fallback if isinstance(fallback, str) else '현재 확인된 정보만으로는 이 항목을 단정하기 어렵습니다. 실제 행동과 대화 패턴을 함께 확인해 주세요.')
    if isinstance(value, list):
        return [_sanitize(item, fallback[i] if isinstance(fallback, list) and i < len(fallback) else '') for i, item in enumerate(value)]
    if isinstance(value, dict):
        return {k: _sanitize(v, fallback.get(k, '') if isinstance(fallback, dict) else '') for k, v in value.items()}
    return value


def _too_similar(text: str, base: str) -> bool:
    a=' '.join(str(text or '').split())
    b=' '.join(str(base or '').split())
    if not a or not b:
        return False
    # Very short copy is not automatically bad.  Compare it normally instead of
    # replacing every concise user-facing sentence with a fallback.
    threshold = 0.88 if min(len(a), len(b)) < 120 else 0.60
    return SequenceMatcher(None, a[:2500], b[:2500]).ratio() >= threshold


def _remove_redundant_ai(parsed: dict[str, Any], payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    profile_local = payload.get('profile_local', {})
    profile_out = parsed.get('profile')
    if isinstance(profile_out, dict) and isinstance(profile_local, dict):
        mapping = {'overview':'overview','personality':'personality','career':'career','wealth':'wealth','relationships':'relationships','romance':'romance'}
        for out_key, local_key in mapping.items():
            if _too_similar(profile_out.get(out_key, ''), profile_local.get(local_key, '')):
                profile_out[out_key] = (fallback.get('profile') or {}).get(out_key, profile_out.get(out_key, ''))
    fortunes=payload.get('fortunes',{})
    fortune_out = parsed.get('fortune')
    if isinstance(fortune_out, dict):
        for out_key, local_key in [('yearly','yearly'),('monthly','monthly'),('daily','daily')]:
            if _too_similar(fortune_out.get(out_key,''), fortunes.get(local_key,{}).get('summary','')):
                fortune_out[out_key]=(fallback.get('fortune') or {}).get(out_key, fortune_out.get(out_key,''))
    else:
        fortune_out = {}

    # 올해/이번 달/오늘은 시간 범위가 다르므로 AI가 같은 문장을 재사용하면
    # 추가 호출 없이 각각의 로컬 기간 해설로 교체한다.
    period_pairs = [('yearly', 'monthly'), ('yearly', 'daily'), ('monthly', 'daily')]
    for left, right in period_pairs:
        a = ' '.join(str(fortune_out.get(left, '') or '').split())
        b = ' '.join(str(fortune_out.get(right, '') or '').split())
        if not a or not b:
            continue
        ratio = SequenceMatcher(None, a[:3000], b[:3000]).ratio()
        if a == b or ratio >= 0.48:
            fortune_out[left] = fallback['fortune'][left]
            fortune_out[right] = fallback['fortune'][right]
    return parsed


def generate_initial_ai(
    payload: dict[str, Any],
    cache_dir: Path,
    force: bool = False,
    *,
    cache_identity: dict[str, Any] | None = None,
    reuse_ai: dict[str, Any] | None = None,
    cache_only: bool = False,
) -> dict[str, Any]:
    """Return a narrative without accidentally paying twice for the same request.

    Priority: stable cache -> salvaged previous report AI -> local fallback when cache-only
    -> one paid call for a genuinely new request.  Report/parser/UI revisions are purposely
    excluded from the paid-AI key.
    """
    fallback = _fallback(payload)
    key = _cache_key(payload, cache_identity)
    cache_file = cache_dir / 'ai_stable' / f'initial_{key}.json'
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    allow_force = bool(force and SETTINGS.allow_force_ai_regeneration)
    if cache_file.exists() and not allow_force:
        cached = read_json(cache_file)
        if isinstance(cached, dict):
            cleaned = _remove_redundant_ai(_sanitize(cached, fallback), payload, fallback)
            if cleaned != cached:
                write_json(cache_file, cleaned)
            return cleaned

    if isinstance(reuse_ai, dict) and reuse_ai and not allow_force:
        cleaned = _remove_redundant_ai(_sanitize(reuse_ai, fallback), payload, fallback)
        write_json(cache_file, cleaned)
        return cleaned

    if cache_only or not SETTINGS.ai_enabled or not SETTINGS.openai_api_key or OpenAI is None:
        return fallback

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    try:
        response = client.responses.create(
            model=SETTINGS.openai_model,
            reasoning={'effort': 'low'},
            instructions=INSTRUCTIONS,
            input=[{'role':'user','content':[{'type':'input_text','text':'<source_data>\n'+json.dumps(payload,ensure_ascii=False,default=str)+'\n</source_data>'}]}],
            text={'format': {'type':'json_schema','name':'saju_initial_report','strict':True,'schema':REPORT_SCHEMA}},
            max_output_tokens=SETTINGS.ai_max_output_tokens,
            store=False,
        )
        if getattr(response,'status','')=='incomplete':
            return fallback
        parsed=json.loads(response.output_text)
        parsed=_sanitize(parsed,fallback)
        parsed=_remove_redundant_ai(parsed,payload,fallback)
        if lint_object(parsed):
            parsed=fallback
        write_json(cache_file,parsed)
        return parsed
    except Exception:
        return fallback


OPTIONAL_SCHEMA = {
    'type':'object','additionalProperties':False,
    'required':['summary','interaction','communication','conflict','daily_life','long_term','practical_advice','methodology_note'],
    'properties':{
        'summary':{'type':'string'},
        'interaction':{'type':'string'},
        'communication':{'type':'string'},
        'conflict':{'type':'string'},
        'daily_life':{'type':'string'},
        'long_term':{'type':'string'},
        'practical_advice':{'type':'array','items':{'type':'string'}},
        'methodology_note':{'type':'string'},
    },
}


def _optional_fallback(payload: dict[str, Any], purpose: str) -> dict[str, Any]:
    """AI를 쓰지 못해도 빈 문구나 개발 상태 문구 대신 실제 계산 결과로 심층 해설을 만든다."""
    if purpose.startswith('pair-'):
        report = payload.get('report', {})
        analysis = report.get('analysis', {})
        axes = sorted(report.get('axes', []), key=lambda x: float(x.get('score', 0)), reverse=True)
        strong = axes[0] if axes else {}
        weak = axes[-1] if axes else {}
        interaction = ' '.join(filter(None, [
            analysis.get('element_useful', ''),
            analysis.get('day_stem', ''),
            analysis.get('intimacy', ''),
            analysis.get('ten_gods', ''),
        ]))
        return {
            'summary': analysis.get('one_line') or report.get('overview', ''),
            'interaction': interaction,
            'communication': analysis.get('communication', ''),
            'conflict': analysis.get('conflict', ''),
            'daily_life': analysis.get('daily_life', ''),
            'long_term': analysis.get('long_term', ''),
            'practical_advice': list(report.get('reality_checks', []))[:6] or list(report.get('risks', []))[:6],
            'methodology_note': (
                f"강점 축 {strong.get('label','')} {float(strong.get('score',0)):.1f}점과 "
                f"조율 축 {weak.get('label','')} {float(weak.get('score',0)):.1f}점을 동시에 놓고 "
                '오행·용신, 일간, 일지, 십성, 전체 지지 관계를 교차해서 읽었습니다.'
            ),
        }

    if purpose.startswith('group-'):
        names = payload.get('names', [])
        anchor = payload.get('anchor', {}) or {}
        bridge = payload.get('bridge', {}) or {}
        roles = payload.get('roles', []) or []
        context = payload.get('context', 'friends')
        strongest_pair = payload.get('strongest_pair', {}) or {}
        weakest_pair = payload.get('weakest_pair', {}) or {}
        role_text = '; '.join(
            f"{r.get('name','')}님은 {r.get('role_guide') or r.get('role_reason','')}" for r in roles[:8]
        )
        if context == 'work':
            summary = (
                f"이 팀에서는 {strongest_pair.get('a','')}–{strongest_pair.get('b','')} 조합이 자연스럽게 협업하기 쉽고, "
                f"{weakest_pair.get('a','')}–{weakest_pair.get('b','')} 조합은 요청 방식과 결정권을 더 분명히 하는 편이 좋습니다."
            )
            communication = '업무 요청은 목적·마감·완료 기준을 함께 말하고, 의견이 다를 때는 사람의 태도보다 쟁점과 근거를 분리해 확인하는 방식이 좋습니다.'
            conflict = '갈등이 생기면 누가 예민한지를 판단하기보다 역할 중복, 정보 부족, 결정 속도, 피드백 방식 중 무엇이 반복되는지 먼저 찾는 편이 좋습니다.'
            daily = '제안자·검토자·최종 결정자를 구분하고, 결정 뒤에는 담당자와 마감 시점을 남기는 식의 운영 규칙이 효과적입니다.'
        else:
            summary = f"{strongest_pair.get('a','')}–{strongest_pair.get('b','')} 연결은 비교적 편하고, {weakest_pair.get('a','')}–{weakest_pair.get('b','')}는 거리·대화 속도·약속 방식을 더 맞출 필요가 있습니다."
            communication = '모든 사람이 같은 연락·대화 방식을 좋아한다고 가정하지 말고, 빠른 피드백을 원하는 사람과 생각할 시간이 필요한 사람의 차이를 존중하는 편이 좋습니다.'
            conflict = '갈등은 한 사람의 성격 문제로 몰기보다 반복되는 조합과 상황을 따로 보는 편이 좋습니다.'
            daily = '모임에서는 일정, 비용, 참여 방식, 결정 방법을 미리 정하면 작은 어긋남이 누적되는 것을 줄일 수 있습니다.'
        return {
            'summary': summary,
            'interaction': f"여러 사람을 이어 주는 위치에는 {bridge.get('name') or anchor.get('name','')}님이 가깝습니다. 구성원별 추천 역할은 {role_text}",
            'communication': communication,
            'conflict': conflict,
            'daily_life': daily,
            'long_term': '강한 두세 사람에게 정보와 결정이 몰리지 않도록 공유 규칙을 두고, 조율이 필요한 조합에는 중재자보다 명확한 업무·관계 규칙을 먼저 제공하는 편이 좋습니다.',
            'practical_advice': list(payload.get('team_actions', []))[:6] or [
                '요청 목적·마감·완료 기준을 한 번에 전달합니다.',
                '제안자와 최종 결정자를 구분합니다.',
                '갈등이 생기면 반복되는 상황을 먼저 특정합니다.',
            ],
            'methodology_note': '전체 관계 행렬과 구성원별 역할, 강한 연결과 조율이 필요한 연결을 함께 참고했습니다.',
        }

    return {
        'summary':'계산된 구조를 바탕으로 강점과 조율 지점을 함께 읽습니다.',
        'interaction':'단일 오행이나 십성 하나가 아니라 여러 관계축이 동시에 작동하는 방식을 기준으로 봅니다.',
        'communication':'표현 속도와 근거를 맞추는 방식이 실제 관계에서 중요합니다.',
        'conflict':'점수가 낮은 축은 운명적 갈등이 아니라 미리 합의해야 할 생활 규칙을 찾는 단서로 봅니다.',
        'daily_life':'시간·돈·약속·개인 공간처럼 반복되는 생활 규칙을 실제로 맞출 수 있는지가 중요합니다.',
        'long_term':'장기 관계는 존중·안전·책임·갈등 복구 능력을 명리 구조와 별도로 확인해야 합니다.',
        'practical_advice':['강한 축과 약한 축을 실제 행동에서 각각 확인하세요.'],
        'methodology_note':'여러 명리 요소를 교차해 해석했습니다.',
    }


def generate_optional_deep_ai(
    payload: dict[str, Any],
    cache_dir: Path,
    purpose: str,
    *,
    cache_identity: dict[str, Any] | None = None,
    cache_only: bool = False,
) -> dict[str, Any]:
    """Optional deep narrative. Identical relation identity is never billed twice."""
    fallback=_optional_fallback(payload,purpose)
    identity = cache_identity or {'purpose': purpose, 'payload': payload}
    raw=json.dumps({'purpose':purpose,'identity':identity,'schema_family':'optional-v1'},ensure_ascii=False,sort_keys=True,default=str).encode()
    key=hashlib.sha256(raw).hexdigest()
    cache_file=cache_dir/'ai_stable'/f'optional_{key}.json'
    cache_file.parent.mkdir(parents=True,exist_ok=True)
    cached=read_json(cache_file)
    if isinstance(cached,dict):
        cleaned = _remove_redundant_ai(_sanitize(cached, fallback), payload, fallback)
        if cleaned != cached:
            write_json(cache_file, cleaned)
        return cleaned
    if cache_only or not SETTINGS.ai_enabled or not SETTINGS.openai_api_key or OpenAI is None:
        return fallback
    client=OpenAI(api_key=SETTINGS.openai_api_key)
    try:
        response=client.responses.create(
            model=SETTINGS.openai_model,
            reasoning={'effort':'low'},
            instructions=INSTRUCTIONS+'\n이 추가 해설은 기본 해설을 반복하면 안 된다. 가장 강한 근거와 가장 약한 근거가 동시에 있을 때 실제 관계에서 어떻게 나타날 수 있는지 통합해서 설명하라.',
            input=json.dumps(payload,ensure_ascii=False,default=str),
            text={'format':{'type':'json_schema','name':'saju_optional_deep','strict':True,'schema':OPTIONAL_SCHEMA}},
            max_output_tokens=min(SETTINGS.ai_max_output_tokens,12000),
            store=False,
        )
        result=_sanitize(json.loads(response.output_text),fallback)
        if lint_object(result):
            return fallback
        write_json(cache_file,result)
        return result
    except Exception:
        return fallback

