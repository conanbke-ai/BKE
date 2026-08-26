from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from bazi_engine import period_pillars, ten_god
from constants import CONTROLS, GENERATES, STEM_ELEMENT
from explain import branch_text, ten_god_text
from models import ForcetellerFacts
from scoring import branch_relations, clamp


PERIOD_ROLE = {
    '비견': {
        'career': '내가 직접 기준을 잡고 움직이는 일이 늘기 쉬운 흐름입니다. 동료와 역할이 겹치면 경쟁으로 느껴질 수 있어 담당 범위를 분명히 하는 편이 좋습니다.',
        'wealth': '공동비용·사람과 얽힌 지출처럼 “나 혼자 결정하지 않는 돈”을 관리하는 것이 중요합니다.',
        'relationships': '또래·동료와의 교류가 늘 수 있지만 비슷한 사람끼리 주도권이 겹치지 않게 조율하는 것이 핵심입니다.',
        'romance': '내 페이스를 지키려는 힘이 커질 수 있어 친밀감과 개인시간의 균형을 맞추는 것이 중요합니다.',
        'study': '남의 방식보다 스스로 계획을 세워 밀어붙이는 공부가 효율적입니다.',
        'caution': '고집·경쟁·비교가 과해지지 않도록 역할과 우선순위를 먼저 정하세요.',
    },
    '겁재': {
        'career': '협업과 경쟁이 동시에 커질 수 있는 흐름입니다. 사람을 통해 기회가 생기기도 하지만 권한과 성과 배분을 명확히 해야 피로가 줄어듭니다.',
        'wealth': '충동적 공동지출, 부탁을 거절하지 못해 나가는 돈, 경쟁적 소비를 특히 주의하는 편이 좋습니다.',
        'relationships': '사람이 많이 얽히는 만큼 친밀감과 피로가 같이 커질 수 있습니다.',
        'romance': '관계에서 속도와 주도권이 빨라질 수 있어 상대의 속도를 확인하는 것이 중요합니다.',
        'study': '혼자 하기보다 스터디나 경쟁 구조가 동력이 될 수 있으나 비교 자체가 목적이 되지 않게 해야 합니다.',
        'caution': '사람·돈·주도권이 동시에 얽히는 상황에서 한 번 더 확인하세요.',
    },
    '식신': {
        'career': '배운 것을 결과물로 만들고, 반복 가능한 실무 능력을 보여주기 좋은 흐름입니다. 문서·기획·코드·제작처럼 손에 잡히는 산출물이 중요합니다.',
        'wealth': '기술이나 생산성이 현실적인 수입으로 이어지는 구조를 만들기 좋습니다. 다만 편안함을 위한 소비가 늘지 않는지 살펴보세요.',
        'relationships': '말과 행동이 부드러워지고 함께 먹고 놀고 경험하는 관계에서 친밀감이 생기기 쉽습니다.',
        'romance': '호감을 행동으로 표현하거나 함께 시간을 보내며 관계를 키우는 방식이 자연스러울 수 있습니다.',
        'study': '암기보다 직접 풀고 만들어 보는 학습이 잘 맞습니다.',
        'caution': '편안함에 머물러 미뤄지는 일이 생기지 않도록 마감 기준을 두세요.',
    },
    '상관': {
        'career': '문제점을 발견하고 개선안을 내는 힘이 커질 수 있습니다. 기존 방식의 비효율을 잘 보지만 표현이 날카로워지면 조직과 마찰이 생길 수 있습니다.',
        'wealth': '아이디어·성과를 수익으로 연결할 여지가 있지만 즉흥적인 선택은 따로 검증해야 합니다.',
        'relationships': '솔직한 말이 장점이 되지만 상대가 공격으로 받아들이지 않도록 전달 순서를 조절하는 것이 중요합니다.',
        'romance': '답답한 관계 규칙을 바로 말하고 싶어질 수 있어 감정이 올라온 상태에서 결론을 내리지 않는 편이 좋습니다.',
        'study': '문제를 비판적으로 분석하고 틀린 이유를 파고드는 공부에 강점이 생길 수 있습니다.',
        'caution': '맞는 말을 하는 것과 관계를 살리는 방식은 다를 수 있습니다. 표현 강도를 조절하세요.',
    },
    '정재': {
        'career': '성과를 안정적으로 관리하고 일정·자원·마감을 지키는 일이 중요해지는 흐름입니다.',
        'wealth': '수입·지출·저축을 구조화하기 좋습니다. 큰 한방보다 반복 가능한 관리에 유리합니다.',
        'relationships': '약속과 신뢰를 행동으로 보여주는 관계가 중요해집니다.',
        'romance': '관계의 안정성, 일정한 연락, 현실적인 계획을 더 중요하게 볼 수 있습니다.',
        'study': '계획표와 진도 관리가 효과적인 시기입니다.',
        'caution': '안정에 집착해 변화 기회를 지나치게 피하지 않도록 균형을 봅니다.',
    },
    '편재': {
        'career': '외부 기회·사람·프로젝트를 넓게 보는 힘이 커질 수 있습니다. 여러 기회를 동시에 잡기보다 우선순위가 중요합니다.',
        'wealth': '돈의 흐름이 넓어질 수 있지만 수입과 지출 모두 변동성이 커지지 않게 관리해야 합니다.',
        'relationships': '대외 활동과 새로운 인맥이 늘기 쉬운 흐름입니다.',
        'romance': '새로운 만남이나 활동적인 데이트가 눈에 들어올 수 있지만 친밀감의 깊이는 별도로 확인해야 합니다.',
        'study': '현장에서 바로 쓰는 실무형 학습과 네트워킹이 도움이 됩니다.',
        'caution': '가능성이 많아 보일수록 시간과 돈의 상한선을 먼저 정하세요.',
    },
    '정관': {
        'career': '책임·평가·규칙·직책이 중요해지는 흐름입니다. 해야 할 일을 정확히 처리하면 신뢰를 쌓기 좋습니다.',
        'wealth': '무리한 확장보다 안정적인 수입과 의무지출 관리가 중요합니다.',
        'relationships': '예의와 경계, 약속의 명확성이 관계 만족도에 크게 작용합니다.',
        'romance': '관계의 정의와 책임, 앞으로의 계획을 더 진지하게 보게 될 수 있습니다.',
        'study': '시험·자격·평가처럼 기준이 분명한 공부에 집중하기 좋습니다.',
        'caution': '책임감이 압박감으로 변하지 않도록 “내가 꼭 다 해야 한다”는 생각을 조절하세요.',
    },
    '편관': {
        'career': '속도·압박·경쟁이 커질 수 있는 흐름입니다. 위기 대응과 실행력은 좋아질 수 있지만 무리한 일정은 피해야 합니다.',
        'wealth': '돈 자체보다 업무 압박이나 책임 때문에 지출이 늘지 않는지 살펴볼 필요가 있습니다.',
        'relationships': '강한 사람이나 강한 상황과 마주칠 수 있어 경계를 분명히 하는 것이 중요합니다.',
        'romance': '끌림이 강하거나 관계 진행이 빨라질 수 있지만 압박이나 통제와 호감을 혼동하지 않는 것이 중요합니다.',
        'study': '짧은 기간에 몰입해 성과를 내는 공부에는 도움이 될 수 있습니다.',
        'caution': '과로·과속·강한 압박을 정상으로 받아들이지 말고 휴식과 안전 기준을 지키세요.',
    },
    '정인': {
        'career': '배우고 정리하고 문서화하며 전문성을 쌓는 일이 중요해지는 흐름입니다. 상사·선배의 지원을 활용하기 좋습니다.',
        'wealth': '수익을 공격적으로 늘리기보다 정보와 기반을 쌓는 쪽에 무게가 갈 수 있습니다.',
        'relationships': '보호받고 이해받는 관계가 중요해집니다. 조언을 받되 의존이 과해지지 않게 균형을 봅니다.',
        'romance': '감정적 안정과 배려를 더 중요하게 볼 수 있습니다.',
        'study': '자격증·이론·기초 체계화에 유리한 흐름입니다.',
        'caution': '생각과 준비만 길어져 실행이 늦어지지 않게 작은 결과물을 정해 두세요.',
    },
    '편인': {
        'career': '남들이 지나치는 정보를 파고들고 전문적인 문제를 깊게 보는 힘이 커질 수 있습니다.',
        'wealth': '새로운 아이디어보다 실제 수익화 가능성을 별도로 검증하는 것이 중요합니다.',
        'relationships': '혼자 생각을 정리할 시간이 필요해질 수 있어 갑작스러운 거리두기로 보이지 않게 설명하는 편이 좋습니다.',
        'romance': '상대를 오래 관찰하거나 머릿속에서 여러 가능성을 검토할 수 있습니다.',
        'study': '전문 분야, 비정형 자료, 깊이 있는 분석 학습에 강점이 생길 수 있습니다.',
        'caution': '생각이 많아져 현실 행동이 늦어지거나 의심이 과해지지 않게 사실 확인을 우선하세요.',
    },
}


PERIOD_FOCUS = {
    '비견': '내 기준을 세우고 내 몫을 분명히 하는 것',
    '겁재': '사람과 역할·성과를 나누는 방식',
    '식신': '배운 것을 실제 결과물로 만드는 것',
    '상관': '문제를 발견하고 더 나은 방식으로 고치는 것',
    '정재': '일정·돈·성과를 안정적으로 관리하는 것',
    '편재': '외부 기회와 사람을 넓게 연결하는 것',
    '정관': '책임·평가·규칙을 내 편으로 만드는 것',
    '편관': '압박이 있는 일을 우선순위로 정리해 돌파하는 것',
    '정인': '배우고 정리한 것을 안정적인 기반으로 만드는 것',
    '편인': '전문 분야를 깊게 파고 새로운 관점을 찾는 것',
}

PERIOD_SCOPE = {
    'year': {
        'name':'올해',
        'horizon':'몇 달에 걸쳐 반복되는 큰 방향과 선택',
        'career':'직무 방향·평가·이직·장기 프로젝트처럼 한 달로 끝나지 않는 변화',
        'wealth':'연간 수입 구조·큰 지출·저축 계획처럼 누적되는 돈의 흐름',
        'relationships':'사람 관계의 판이 바뀌거나 오래 이어질 인연과 거리 조정',
        'romance':'관계의 시작·정리·정의처럼 몇 달에 걸쳐 방향이 잡히는 문제',
        'study':'자격증·장기 학습·전문성처럼 꾸준히 쌓아야 결과가 나는 일',
    },
    'month': {
        'name':'이번 달',
        'horizon':'이번 달의 일정·업무량·사람과의 접점처럼 당장 체감되는 흐름',
        'career':'이번 달 마감·업무 배분·회의·상사와의 조율처럼 가까운 실무',
        'wealth':'이번 달 소비·예산·정산처럼 바로 조정할 수 있는 돈의 움직임',
        'relationships':'연락·약속·모임·동료와의 대화처럼 자주 마주치는 관계',
        'romance':'연락 빈도·약속·데이트 일정처럼 관계에서 바로 체감되는 부분',
        'study':'이번 달 진도·시험 준비·복습 루틴처럼 실행 계획이 필요한 일',
    },
    'day': {
        'name':'오늘',
        'horizon':'오늘의 대화·집중력·일 처리 순서처럼 짧게 지나가는 반응',
        'career':'오늘 처리해야 할 우선순위·보고·협업 대화',
        'wealth':'오늘의 즉흥 지출이나 작은 금전 결정',
        'relationships':'오늘 오가는 말과 반응 속도, 약속 조정',
        'romance':'오늘 연락이나 대화에서 상대의 반응을 해석하는 방식',
        'study':'오늘 집중할 한두 가지 과제와 복습',
    },
}


def _relation_notes(facts: ForcetellerFacts, period_branch: str) -> tuple[float, list[dict[str, str]]]:
    score_effect = 0.0
    rows: list[dict[str, str]] = []
    pos_labels = ('연지', '월지', '일지', '시지')
    for pos, branch in zip(pos_labels, facts.chart.branches):
        rels = branch_relations(branch, period_branch)
        if not rels:
            continue
        for r in rels:
            if r in {'육합', '삼합계열', '삼회계열'}:
                score_effect += 3.5
            elif r == '충':
                score_effect -= 5.0
            elif r == '형':
                score_effect -= 3.0
            elif r == '해':
                score_effect -= 2.0
            elif r == '파':
                score_effect -= 1.5
        plain = {
            '육합': '연결점과 협력 가능성을 보는 관계', '삼합계열': '같은 흐름으로 묶일 수 있는 관계', '삼회계열': '같은 계절 방향이 모이는 관계',
            '충': '변화와 긴장을 크게 만드는 관계', '형': '반복 마찰이나 압박을 보는 관계', '해': '오해·서운함 같은 간접 불편을 보는 관계', '파': '작은 어긋남이 반복될 수 있는 관계',
        }
        rows.append({
            'position': pos,
            'relation': ', '.join(rels),
            'detail': f'기간 지지 {branch_text(period_branch)}가 원국 {pos} {branch_text(branch)}와 ' + ', '.join(f'{r}({plain.get(r,"지지 관계")})' for r in rels) + '를 이룹니다.',
        })
    return max(-17, min(17, score_effect)), rows


def _period_analysis(facts: ForcetellerFacts, pillar: str, label: str, period_type: str) -> dict[str, Any]:
    p_stem, p_branch = pillar[0], pillar[1]
    p_element = STEM_ELEMENT[p_stem]
    tg = ten_god(facts.chart.day_master, p_stem)
    score = 55.0
    useful_note = ''
    useful_direction = 'neutral'

    if facts.useful_elements:
        if p_element in facts.useful_elements:
            score += 17
            useful_direction = 'positive'
            useful_note = '원국의 균형을 돕는 방향과 이번 기간의 기운이 직접 맞물립니다.'
        else:
            notes = []
            for useful in facts.useful_elements:
                if GENERATES[p_element] == useful:
                    score += 5
                    notes.append('균형에 필요한 방향을 간접적으로 도와주는 연결이 있습니다.')
                if CONTROLS[p_element] == useful:
                    score -= 6
                    notes.append('균형에 필요한 방향과 힘이 부딪히는 부분이 있어 속도 조절이 필요합니다.')
            useful_note = ' '.join(notes) or '균형을 직접 돕거나 막는 신호는 강하지 않아 실제 상황과 함께 보는 편이 좋습니다.'
    else:
        useful_note = '균형 방향 자료가 충분하지 않아 기간의 역할과 원국 관계를 중심으로 봅니다.'

    rel_effect, relation_rows = _relation_notes(facts, p_branch)
    score += rel_effect
    score = round(clamp(score), 1)
    if score >= 75:
        tone = '기회를 잡아 움직이기 좋은 편'
    elif score >= 60:
        tone = '무난하게 활용할 여지가 있는 편'
    elif score >= 45:
        tone = '장점과 조율 포인트가 함께 있는 편'
    else:
        tone = '서두르기보다 확인과 조율이 중요한 편'

    role = PERIOD_ROLE.get(tg, {})
    scope = PERIOD_SCOPE[period_type]
    base_focus = PERIOD_FOCUS.get(tg, '우선순위를 다시 정리하는 것')
    if period_type == 'year':
        focus = f'{base_focus}을 장기 방향과 선택으로 연결하는 것'
    elif period_type == 'month':
        focus = f'{base_focus}을 이번 달 일정·약속·마감에 배치하는 것'
    else:
        focus = f'{base_focus}을 오늘 할 한두 가지 행동으로 옮기는 것'
    relation_hint = ''
    if relation_rows:
        positions = '·'.join(dict.fromkeys(r['position'] for r in relation_rows[:3]))
        relation_hint = f' 특히 원국의 {positions} 쪽과 연결이 생겨 이 영역은 평소보다 체감이 커질 수 있습니다.'
    else:
        relation_hint = ' 원국과 강하게 부딪히는 관계가 많지는 않아, 사건보다 내가 어떻게 선택하느냐에 따라 체감 차이가 커질 수 있습니다.'

    if period_type == 'year':
        summary = (
            f'올해는 **{focus}**이 몇 달에 걸쳐 반복되는 큰 주제입니다. '
            f'{role.get("career", "장기적으로 맡을 역할과 방향을 정리하는 흐름입니다.")} '
            '이직·평가·장기 프로젝트처럼 한 달 안에 끝나지 않는 선택을 기준으로 읽는 편이 좋습니다.'
        )
        keywords = [focus, '큰 방향', '장기 선택']
    elif period_type == 'month':
        summary = (
            f'이번 달에는 **{focus}**을 실제 일정에 어떻게 배치할지가 중요합니다. '
            f'{role.get("career", "당장 맡은 일의 순서와 조율이 중요합니다.")} '
            '회의·마감·지출·약속처럼 이번 달 안에 바로 조정할 수 있는 일부터 정리해 보세요.'
        )
        keywords = [focus, '이번 달 일정', '가까운 조율']
    else:
        summary = (
            f'오늘은 **{focus}**을 크게 벌이기보다 한두 가지 행동으로 옮기는 데 초점을 맞춰 보세요. '
            f'{role.get("career", "당장 처리할 일의 우선순위를 분명히 하는 편이 좋습니다.")} '
            '대화와 결정은 오늘 필요한 만큼만 하고, 큰 결론은 전체 흐름과 함께 보는 편이 좋습니다.'
        )
        keywords = [focus, '오늘의 행동', '대화·우선순위']
    if relation_hint:
        summary += relation_hint

    domains = {}
    domain_openers = {
        'year': {'career':'장기 커리어', 'wealth':'연간 돈의 흐름', 'relationships':'관계의 큰 변화', 'romance':'관계의 방향', 'study':'장기 학습'},
        'month': {'career':'이번 달 업무', 'wealth':'이번 달 예산', 'relationships':'이번 달 연락·약속', 'romance':'이번 달 관계 리듬', 'study':'이번 달 진도'},
        'day': {'career':'오늘 업무', 'wealth':'오늘 지출', 'relationships':'오늘 대화', 'romance':'오늘 연락', 'study':'오늘 집중'},
    }[period_type]
    for key in ('career','wealth','relationships','romance','study'):
        base = role.get(key, '')
        domains[key] = f'**{domain_openers[key]}** · {scope[key]}. {base}'

    evidence = [
        f'기간 간지는 {pillar}이고, 본인 기준으로 {ten_god_text(tg)} 역할이 들어옵니다.',
        useful_note,
    ] + [x['detail'] for x in relation_rows]
    if not relation_rows:
        evidence.append('기간 지지와 원국 사이의 뚜렷한 합·충·형·파·해가 많이 겹치지 않습니다.')

    return {
        'pillar': pillar,
        'score': score,
        'tone': tone,
        'ten_god': tg,
        'ten_god_label': ten_god_text(tg),
        'focus': focus,
        'keywords': keywords,
        'summary': summary,
        'why': f'{scope["name"]}에는 {focus}이 중심 주제로 들어오고, 원국과의 뚜렷한 관계는 {len(relation_rows)}개 확인됩니다. {useful_note}',
        'domains': domains,
        'cautions': [role.get('caution', '무리한 결론보다 실제 상황을 확인하세요.')],
        'opportunities': _opportunities(tg, useful_direction),
        'relations': relation_rows,
        'evidence': evidence,
        'period_scope': scope['horizon'],
    }


def _opportunities(tg: str, useful_direction: str) -> list[str]:
    base = {
        '비견':['내가 직접 주도해야 하는 일 정리','동료와 역할 재설계'],
        '겁재':['협업 구조 재정비','새로운 사람과 함께하는 프로젝트'],
        '식신':['결과물 완성','실무 기술·콘텐츠를 밖으로 보여주기'],
        '상관':['문제 개선안 제시','낡은 방식 수정'],
        '정재':['예산·저축·일정 관리','안정적인 성과 쌓기'],
        '편재':['외부 기회 탐색','네트워킹·대외 활동'],
        '정관':['평가·자격·책임 있는 역할','규칙과 기준을 정비하기'],
        '편관':['집중력이 필요한 과제 돌파','위기 대응·속도감 있는 실행'],
        '정인':['학습·자격·문서 정리','멘토·지원 자원 활용'],
        '편인':['전문 분야 깊이 파기','새로운 관점으로 분석하기'],
    }.get(tg, ['현재 우선순위를 정리하기'])
    if useful_direction == 'positive':
        return base + ['이번 흐름이 원국의 균형을 돕는 쪽이라 새 일을 무리하게 벌이기보다 이미 잘되는 영역을 한 단계 더 활용하기']
    return base


def build_period(facts: ForcetellerFacts, moment: datetime, period_type: str) -> dict[str, Any]:
    pillars = period_pillars(moment)
    pillar = pillars[period_type]
    labels = {
        'year': f'{moment.year}년',
        'month': f'{moment.year}년 {moment.month}월',
        'day': f'{moment.year}년 {moment.month}월 {moment.day}일',
    }
    result = _period_analysis(facts, pillar, labels[period_type], period_type)
    result['period_type'] = period_type
    result['label'] = labels[period_type]
    return result

def _daewoon_period_row(
    facts: ForcetellerFacts,
    ordered: list[dict[str, Any]],
    index: int,
    chart_age: int,
) -> dict[str, Any]:
    row = dict(ordered[index])
    start_age = int(row.get('age', 0))
    end_age = int(ordered[index + 1].get('age', start_age + 10)) - 1 if index + 1 < len(ordered) else start_age + 9
    pillar = str(row.get('pillar') or (str(row.get('stem','')) + str(row.get('branch',''))))
    stem = pillar[0] if len(pillar) >= 1 else str(row.get('stem',''))
    branch = pillar[1] if len(pillar) >= 2 else str(row.get('branch',''))
    tg = str(row.get('ten_god') or (ten_god(facts.chart.day_master, stem) if stem else ''))
    focus = PERIOD_FOCUS.get(tg, '삶의 큰 우선순위를 다시 정리하는 것')
    role = PERIOD_ROLE.get(tg, {})
    element = STEM_ELEMENT.get(stem, '')

    balance_label = '균형과 직접 맞물리는 신호는 강하지 않음'
    balance_tone = 'neutral'
    if facts.useful_elements and element:
        if element in facts.useful_elements:
            balance_label = '원국의 균형을 돕는 기운과 직접 맞물림'
            balance_tone = 'support'
        elif any(GENERATES.get(element) == useful for useful in facts.useful_elements):
            balance_label = '원국의 균형 방향을 간접적으로 도와주는 편'
            balance_tone = 'support'
        elif any(CONTROLS.get(element) == useful for useful in facts.useful_elements):
            balance_label = '원국의 균형 방향과 힘이 부딪힐 수 있어 조율이 필요'
            balance_tone = 'adjust'

    relation_rows: list[dict[str, str]] = []
    if branch:
        _, relation_rows = _relation_notes(facts, branch)
    relation_names = list(dict.fromkeys(r['relation'] for r in relation_rows if r.get('relation')))
    relation_label = '원국 지지와 강한 합·충 관계는 많지 않음' if not relation_names else ' · '.join(relation_names[:4])

    summary = (
        f'{start_age}~{end_age}세 대운은 {pillar or "간지 미확인"} 흐름으로, 「{focus}」이 약 10년 동안 반복해서 중요해지기 쉬운 배경입니다. '
        f'{balance_label}. {relation_label}. '
        '대운은 사건을 단정하는 예측이 아니라, 이 시기에 어떤 역할·선택 방식이 반복되기 쉬운지를 보는 큰 배경으로 활용합니다.'
    )
    domains = {
        'career': role.get('career', '직장에서는 맡는 역할과 책임의 방향을 함께 봅니다.'),
        'wealth': role.get('wealth', '돈은 실제 수입·지출 구조와 함께 봅니다.'),
        'relationships': role.get('relationships', '관계에서는 반복되는 대화와 경계 방식을 함께 봅니다.'),
        'study': role.get('study', '학습은 실제 목표와 반복 루틴을 함께 봅니다.'),
    }
    return {
        **row,
        'index': index,
        'start_age': start_age,
        'end_age': end_age,
        'pillar': pillar,
        'stem': stem,
        'branch': branch,
        'ten_god': tg,
        'focus': focus,
        'element': element,
        'balance_label': balance_label,
        'balance_tone': balance_tone,
        'relation_label': relation_label,
        'relations': relation_rows,
        'summary': summary,
        'domains': domains,
        'caution': role.get('caution', '무리한 결론보다 실제 상황을 확인하면서 조율하세요.'),
        'is_current': start_age <= chart_age <= end_age,
    }

def current_daewoon(facts: ForcetellerFacts, today: datetime | None = None) -> dict[str, Any]:
    today = today or datetime.now()
    birth_year = facts.profile.year
    actual_age = today.year - birth_year - ((today.month, today.day) < (facts.profile.month, facts.profile.day))
    # 포스텔러 대운표의 시작 나이는 전통 명리에서 쓰는 세수 표기와 맞춰 읽는다.
    # 만 나이로 구간을 고르면 생일 전후에 대운이 한 칸 어긋날 수 있다.
    chart_age = today.year - birth_year + 1
    if not facts.daewoon:
        return {
            'available': False,
            'age': actual_age,
            'chart_age': chart_age,
            'summary': '현재 대운 자료를 확인하지 못했어요. 확인되지 않은 값은 임의로 만들어 표시하지 않습니다.',
            'detail': '대운은 약 10년 동안 이어지는 큰 배경 흐름을 보는 항목입니다. 자료가 확인되면 올해·이번 달의 흐름과 겹쳐서 보여줍니다.',
            'raw': [],
        }
    ordered = sorted(facts.daewoon, key=lambda x: int(x.get('age', 999)))
    periods = [_daewoon_period_row(facts, ordered, i, chart_age) for i in range(len(ordered))]
    chosen_index = 0
    for i, item in enumerate(periods):
        if item.get('is_current'):
            chosen_index = i
            break
        if int(item.get('start_age', 0)) <= chart_age:
            chosen_index = i
    chosen = periods[chosen_index]
    start_age = int(chosen.get('start_age', 0))
    end_age = int(chosen.get('end_age', start_age + 9))
    pillar = chosen.get('pillar','')
    tg = str(chosen.get('ten_god',''))
    focus = chosen.get('focus') or PERIOD_FOCUS.get(tg, '삶의 큰 우선순위를 재정리하는 것')
    summary = (
        f'현재는 대운표 기준 {start_age}~{end_age}세 구간으로, 약 10년 동안 「{focus}」이 반복해서 중요한 주제가 되기 쉬운 시기입니다. '
        '대운은 당장 무슨 일이 생긴다는 예측이 아니라, 여러 해에 걸쳐 어떤 방식의 선택과 역할이 반복되는지를 보는 큰 배경입니다.'
    )
    keywords = [focus, f'{start_age}~{end_age}세 배경', '10년 흐름']
    return {
        'available': True,
        'age': actual_age,
        'chart_age': chart_age,
        'age_basis': '포스텔러 대운표의 세수 기준',
        'current': chosen,
        'start_age': start_age,
        'end_age': end_age,
        'pillar': pillar,
        'focus': focus,
        'keywords': keywords,
        'summary': summary,
        'detail': '현재 해와 달의 흐름이 이 10년 배경과 같은 방향이면 체감이 커지고, 반대 방향이면 일시적인 변동으로 느껴질 수 있습니다. 그래서 대운은 연운·월운보다 먼저 큰 배경으로 보고 세부 시기를 겹쳐 읽습니다.',
        'periods': periods,
        'raw': ordered,
    }

def build_fortunes(facts: ForcetellerFacts, moment: datetime | None = None) -> dict[str, Any]:
    moment = moment or datetime.now()
    yearly = build_period(facts, moment, 'year')
    monthly = build_period(facts, moment, 'month')
    daily = build_period(facts, moment, 'day')
    # 기간별 본문이 우연히 비슷해져도 그대로 노출하지 않는다.
    def _sim(a: str, b: str) -> float:
        clean = lambda x: ' '.join(str(x or '').replace('**','').split())
        return SequenceMatcher(None, clean(a), clean(b)).ratio()
    if _sim(yearly.get('summary',''), monthly.get('summary','')) >= 0.58:
        monthly['summary'] = (
            f'이번 달의 초점은 **{monthly.get("focus", "가까운 일정을 정리하는 것")}**입니다. '
            '올해의 큰 방향을 다시 설명하기보다, 이번 달 안에 끝낼 업무·약속·예산·대화 순서를 구체적으로 조정하는 데 활용하세요.'
        )
    if _sim(monthly.get('summary',''), daily.get('summary','')) >= 0.58:
        daily['summary'] = (
            f'오늘은 **{daily.get("focus", "한 가지 우선순위를 정하는 것")}**을 행동 한두 가지로 옮기는 날로 읽습니다. '
            '이번 달 전체 계획보다 오늘 처리할 일, 오늘 할 말, 오늘 미룰 일을 분리하는 데 초점을 맞춰 보세요.'
        )
    return {
        'daewoon': current_daewoon(facts, moment),
        'yearly': yearly,
        'monthly': monthly,
        'daily': daily,
        'generated_at': moment.isoformat(timespec='seconds'),
        'guide': '올해는 몇 달에 걸친 큰 방향, 이번 달은 가까운 일정과 관계, 오늘은 짧은 행동과 대화처럼 서로 다른 시간 범위를 봅니다. 같은 십성이 들어와도 해석 내용이 같아서는 안 됩니다.',
    }

