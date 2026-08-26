from __future__ import annotations

from statistics import mean
from typing import Iterable

from bazi_engine import ten_god
from constants import (
    BRANCH_ELEMENT,
    CHONG,
    CONTROLS,
    GENERATES,
    HAI,
    LIUHE,
    PO,
    SANHE,
    SANHUI,
    SELF_XING,
    STEM_COMBINE,
    STEM_ELEMENT,
    XING_PAIRS,
)
from models import AxisScore, CompatibilityResult, Evidence, ForcetellerFacts, Mode


LOVE_WEIGHTS = {
    'element_need': 0.24,
    'spouse_palace': 0.20,
    'spouse_star': 0.16,
    'stem_daymaster': 0.14,
    'branch_network': 0.14,
    'month_life': 0.07,
    'conflict_buffer': 0.05,
}
FRIEND_WEIGHTS = {
    'element_need': 0.25,
    'stem_communication': 0.20,
    'branch_network': 0.20,
    'friend_ten_gods': 0.20,
    'month_social': 0.10,
    'conflict_buffer': 0.05,
}

RELATION_SEVERITY = {
    '육합': 14.0,
    '삼합계열': 9.0,
    '삼회계열': 7.0,
    '충': -16.0,
    '형': -11.0,
    '해': -8.0,
    '파': -5.0,
}


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def score_label(score: float, mode: Mode) -> str:
    if score >= 90:
        return '매우 뛰어난 연인 궁합' if mode == 'love' else '매우 뛰어난 우정 궁합'
    if score >= 80:
        return '매우 잘 맞는 편' if mode == 'love' else '아주 잘 맞는 친구'
    if score >= 70:
        return '잘 맞는 편' if mode == 'love' else '잘 맞고 오래가기 좋은 편'
    if score >= 60:
        return '대체로 맞는 편' if mode == 'love' else '대체로 편한 친구'
    if score >= 50:
        return '장단점이 비슷한 관계' if mode == 'love' else '무난하지만 차이가 있는 친구'
    if score >= 40:
        return '조율이 꽤 필요한 관계' if mode == 'love' else '맞추는 노력이 필요한 친구'
    if score >= 30:
        return '구조적 마찰이 큰 편' if mode == 'love' else '피로와 충돌이 잦을 수 있는 편'
    return '구조적으로 매우 어려운 편' if mode == 'love' else '구조적 마찰이 매우 큰 편'


def branch_relations(a: str, b: str) -> list[str]:
    """하나의 관계만 고르지 않고 동시에 성립하는 관계를 모두 보존한다."""
    pair = frozenset((a, b))
    result: list[str] = []
    if pair in LIUHE:
        result.append('육합')
    if any(a in g and b in g for g in SANHE):
        result.append('삼합계열')
    if any(a in g and b in g for g in SANHUI):
        result.append('삼회계열')
    if pair in CHONG:
        result.append('충')
    if pair in XING_PAIRS or (a == b and a in SELF_XING):
        result.append('형')
    if pair in HAI:
        result.append('해')
    if pair in PO:
        result.append('파')
    return result


def _relation_effect(relations: Iterable[str], primary_scale: float = 1.0) -> float:
    """
    여러 관계가 동시에 성립할 때 첫 관계만 취하지 않는다.
    가장 강한 긍정/부정 효과를 100% 반영하고 나머지는 35% 반영한다.
    """
    values = [RELATION_SEVERITY[r] * primary_scale for r in relations if r in RELATION_SEVERITY]
    if not values:
        return 0.0
    primary_index = max(range(len(values)), key=lambda i: abs(values[i]))
    primary = values[primary_index]
    rest = values[:primary_index] + values[primary_index + 1:]
    return primary + sum(rest) * 0.35


def _stem_relation(a: str, b: str) -> tuple[float, list[str]]:
    score = 58.0
    notes: list[str] = []
    pair = frozenset((a, b))
    if pair in STEM_COMBINE:
        name, result_element = STEM_COMBINE[pair]
        score += 24
        notes.append(f'{name} 성립 가능성: 두 천간이 결합하는 전통 관계이며 합화 결과 오행은 {result_element}로 봅니다.')
    ea, eb = STEM_ELEMENT[a], STEM_ELEMENT[b]
    if ea == eb:
        score += 8
        notes.append('두 일간의 오행이 같아 기본 반응의 온도와 속도에 공통점이 생길 수 있습니다.')
    elif GENERATES[ea] == eb:
        score += 12
        notes.append('A의 일간 오행이 B의 일간 오행을 생하는 상생 관계입니다.')
    elif GENERATES[eb] == ea:
        score += 14
        notes.append('B의 일간 오행이 A의 일간 오행을 생하는 상생 관계입니다.')
    elif CONTROLS[ea] == eb:
        score -= 8
        notes.append('A의 일간 오행이 B의 일간 오행을 극하는 관계라 주도권이나 속도 차이를 살펴봅니다.')
    elif CONTROLS[eb] == ea:
        score -= 10
        notes.append('B의 일간 오행이 A의 일간 오행을 극하는 관계라 압박감의 방향을 함께 살펴봅니다.')
    return clamp(score), notes


def _support_direction(receiver: ForcetellerFacts, giver: ForcetellerFacts) -> tuple[float, list[str]]:
    """receiver에게 giver가 얼마나 보완적인지 계산한다. 용신은 포스텔러 표시값을 최우선한다."""
    score = 55.0
    notes: list[str] = []
    useful = list(dict.fromkeys(receiver.useful_elements))
    if useful:
        supplied = sum(giver.element_percent.get(e, 0.0) for e in useful)
        # 용신 기운이 20~45% 정도면 강한 보완, 지나치게 70% 이상은 과잉으로 소폭 감점.
        if supplied <= 5:
            score -= 16
        elif supplied < 15:
            score -= 5
        elif supplied < 25:
            score += 11
        elif supplied <= 50:
            score += 22
        elif supplied <= 70:
            score += 15
        else:
            score += 5
        names = ', '.join(useful)
        notes.append(f'받는 사람의 용신({names})을 상대 원국이 합계 {supplied:.1f}% 보유합니다.')
    else:
        notes.append('포스텔러 용신 자료가 없어 이 축은 중립에 가깝게 보수적으로 계산했습니다.')

    # 가장 강한 오행을 상대가 과도하게 더 밀어주는 경우만 작은 감점.
    if receiver.element_percent:
        dominant = max(receiver.element_percent, key=receiver.element_percent.get)
        rec_dom = receiver.element_percent.get(dominant, 0.0)
        giv_dom = giver.element_percent.get(dominant, 0.0)
        if rec_dom >= 40 and giv_dom >= 40 and dominant not in useful:
            score -= 8
            notes.append(f'이미 강한 {dominant} 기운을 상대도 크게 보유해 한쪽 치우침이 강화될 여지가 있습니다.')

    # 강약은 세부 보정. 성격의 강약으로 해석하지 않는다.
    label = receiver.strength_label
    if label:
        if '신강' in label and any(giver.element_percent.get(e, 0) >= 20 for e in useful):
            score += 2
        elif '신약' in label and useful and sum(giver.element_percent.get(e, 0) for e in useful) >= 20:
            score += 4
        notes.append(f'받는 사람의 신강·신약 판정은 {label}이며, 이는 성격 평가가 아니라 일간의 세력 판단입니다.')
    return clamp(score), notes


def _element_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float) -> AxisScore:
    a_from_b, n1 = _support_direction(a, b)
    b_from_a, n2 = _support_direction(b, a)
    avg = (a_from_b + b_from_a) / 2
    asymmetry = abs(a_from_b - b_from_a)
    score = clamp(avg - asymmetry * 0.10)
    evidence = [
        Evidence('오행·용신', 'B → A 보완', '; '.join(n1), 'positive' if a_from_b >= 65 else 'neutral'),
        Evidence('오행·용신', 'A → B 보완', '; '.join(n2), 'positive' if b_from_a >= 65 else 'neutral'),
    ]
    return AxisScore(
        'element_need', '용신·오행·강약 상호보완', round(score, 1), weight,
        f'양방향 보완도는 A가 B에게 받는 방향 {a_from_b:.1f}, B가 A에게 받는 방향 {b_from_a:.1f}이며 한쪽에만 유리한 경우를 소폭 보정했습니다.',
        evidence,
    )


def _spouse_palace_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float) -> AxisScore:
    ar, br = a.chart.spouse_palace, b.chart.spouse_palace
    rels = branch_relations(ar, br)
    score = 58.0 + _relation_effect(rels, 1.35)
    # 지지 오행의 상생/상극은 합충형파해가 없을 때만 작은 보조값.
    ea, eb = BRANCH_ELEMENT[ar], BRANCH_ELEMENT[br]
    if not rels:
        if GENERATES[ea] == eb or GENERATES[eb] == ea:
            score += 8
        elif CONTROLS[ea] == eb or CONTROLS[eb] == ea:
            score -= 6
    details = ', '.join(rels) if rels else '특별한 합·충·형·파·해 없음'
    direction = 'positive' if score >= 65 else ('negative' if score < 50 else 'neutral')
    return AxisScore(
        'spouse_palace', '배우자궁·일지 친밀축', round(clamp(score), 1), weight,
        f'A의 일지 {ar}와 B의 일지 {br} 사이에서 {details}을/를 확인했습니다. 일지 관계 하나만으로 관계의 성패를 단정하지 않습니다.',
        [Evidence('배우자궁', f'{ar}-{br}', details, direction)],
    )


def _spouse_star_for(owner: ForcetellerFacts, partner: ForcetellerFacts) -> tuple[float, list[str]]:
    """전통적 배우자성 정편 구분을 쓰되, 상대에게 그 오행이 있다는 사실을 '배우자 확정'으로 보지 않는다."""
    gender = owner.profile.gender
    preferred = {'정관', '편관'} if gender == 'F' else {'정재', '편재'}
    partner_relation = ten_god(owner.chart.day_master, partner.chart.day_master)
    score = 52.0
    notes = [f'상대 일간을 기준으로 보이는 십성 관계는 {partner_relation or "중립"}입니다.']
    if partner_relation in preferred:
        score += 24 if partner_relation in {'정관', '정재'} else 18
        notes.append('상대 일간이 전통적으로 배우자성으로 보는 십성 축에 직접 들어옵니다.')

    # 상대 천간/지장간에 배우자성 역할을 하는 글자가 존재하는지 낮은 가중치로 참고.
    visible_hits = 0
    hidden_hits = 0
    for s in partner.chart.stems:
        if ten_god(owner.chart.day_master, s) in preferred:
            visible_hits += 1
    for hs in partner.hidden_stems.values():
        for s in hs:
            if ten_god(owner.chart.day_master, s) in preferred:
                hidden_hits += 1
    score += min(visible_hits * 5, 12)
    score += min(hidden_hits * 1.5, 6)
    if visible_hits or hidden_hits:
        notes.append(f'상대 원국에서 배우자성 계열은 천간 {visible_hits}회, 지장간 보조 {hidden_hits}회 확인됩니다.')
    if visible_hits >= 4:
        score -= 5
        notes.append('배우자성 계열이 지나치게 반복되는 경우는 단순 가점으로 보지 않고 과잉을 소폭 보정했습니다.')
    return clamp(score), notes


def _spouse_star_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float) -> AxisScore:
    a_score, na = _spouse_star_for(a, b)
    b_score, nb = _spouse_star_for(b, a)
    score = clamp((a_score + b_score) / 2 - abs(a_score - b_score) * 0.08)
    return AxisScore(
        'spouse_star', '배우자성·십성 상호성', round(score, 1), weight,
        f'배우자성은 여성의 관성, 남성의 재성을 전통적 참고축으로 보되 정편과 위치를 구분했습니다. 양방향은 {a_score:.1f}/{b_score:.1f}입니다.',
        [Evidence('배우자성', 'A 관점', '; '.join(na)), Evidence('배우자성', 'B 관점', '; '.join(nb))],
    )


def _stem_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float, key: str, label: str) -> AxisScore:
    score, notes = _stem_relation(a.chart.day_master, b.chart.day_master)
    # 다른 천간의 교차 합은 반복 개수에 따라 소폭 가점, 극 관계는 작은 감점.
    cross_combine = 0
    cross_control = 0
    for sa in a.chart.stems:
        for sb in b.chart.stems:
            if frozenset((sa, sb)) in STEM_COMBINE:
                cross_combine += 1
            ea, eb = STEM_ELEMENT[sa], STEM_ELEMENT[sb]
            if CONTROLS[ea] == eb or CONTROLS[eb] == ea:
                cross_control += 1
    score += min(cross_combine * 2.0, 8.0)
    score -= min(cross_control * 0.7, 5.0)
    notes.append(f'전체 천간 교차에서는 천간합 {cross_combine}건, 상극 계열 {cross_control}건을 보조적으로 확인했습니다.')
    return AxisScore(key, label, round(clamp(score), 1), weight, ' '.join(notes), [Evidence('천간', '일간 및 교차 천간', '; '.join(notes))])


def _branch_network_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float, include_day_day: bool = False) -> AxisScore:
    score = 58.0
    evidence: list[Evidence] = []
    positive = negative = 0
    position_weight = [0.65, 0.95, 1.15, 0.75]  # 년·월·일·시
    for i, ba in enumerate(a.chart.branches):
        for j, bb in enumerate(b.chart.branches):
            if not include_day_day and i == 2 and j == 2:
                continue
            rels = branch_relations(ba, bb)
            if not rels:
                continue
            scale = (position_weight[i] + position_weight[j]) / 2 * 0.34
            effect = _relation_effect(rels, scale)
            score += effect
            if effect > 0:
                positive += 1
            elif effect < 0:
                negative += 1
            evidence.append(Evidence(
                '지지 관계망', f'{i}:{ba} ↔ {j}:{bb}', ', '.join(rels),
                'positive' if effect > 0 else 'negative', abs(effect),
            ))
    # 두 원국의 합집합에서 완전한 삼합/삼회가 만들어지는지 보조적으로 봄.
    combined = set(a.chart.branches + b.chart.branches)
    for group in SANHE:
        if group.issubset(combined):
            score += 5
            evidence.append(Evidence('지지 관계망', '두 원국 결합 삼합', ''.join(sorted(group)), 'positive', 5))
    for group in SANHUI:
        if group.issubset(combined):
            score += 3
            evidence.append(Evidence('지지 관계망', '두 원국 결합 삼회', ''.join(sorted(group)), 'positive', 3))
    explanation = f'일지-일지 중복 계산은 {"포함" if include_day_day else "제외"}했습니다. 긍정 관계 {positive}건, 주의 관계 {negative}건을 위치별 가중치로 합산했습니다.'
    return AxisScore('branch_network', '전체 지지 관계망', round(clamp(score), 1), weight, explanation, evidence)


def _month_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float, key: str, label: str) -> AxisScore:
    am, bm = a.chart.month_pillar[1], b.chart.month_pillar[1]
    rels = branch_relations(am, bm)
    score = 58 + _relation_effect(rels, 0.8)
    ea, eb = BRANCH_ELEMENT[am], BRANCH_ELEMENT[bm]
    if GENERATES[ea] == eb or GENERATES[eb] == ea:
        score += 6
    elif CONTROLS[ea] == eb or CONTROLS[eb] == ea:
        score -= 5
    return AxisScore(
        key, label, round(clamp(score), 1), weight,
        f'두 사람의 월지 {am}-{bm}를 사회생활·생활 리듬의 보조축으로 봅니다. 관계: {", ".join(rels) if rels else "특별한 합충형파해 없음"}.',
        [Evidence('월지', f'{am}-{bm}', ', '.join(rels) if rels else '중립', 'neutral')],
    )


def _conflict_buffer_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float) -> AxisScore:
    negative = positive = 0.0
    for i, ba in enumerate(a.chart.branches):
        for j, bb in enumerate(b.chart.branches):
            rels = branch_relations(ba, bb)
            for r in rels:
                val = RELATION_SEVERITY.get(r, 0)
                if val > 0:
                    positive += val
                elif val < 0:
                    negative += -val
    stem_score, _ = _stem_relation(a.chart.day_master, b.chart.day_master)
    buffer = positive + max(0, stem_score - 58) * 1.2
    pressure = negative
    score = 58 + min(buffer * 0.7, 28) - min(pressure * 0.6, 32)
    if pressure > 0 and buffer > 0:
        score += 5  # 갈등 요인이 있어도 완충 연결이 있으면 회복 여지
    return AxisScore(
        'conflict_buffer', '충돌 증폭·완충 구조', round(clamp(score), 1), weight,
        f'관계망의 긴장량과 합·상생 등 완충량을 함께 봤습니다. 완충 신호 {buffer:.1f}, 긴장 신호 {pressure:.1f}.',
        [Evidence('갈등 완충', '완충/긴장', f'{buffer:.1f}/{pressure:.1f}', 'neutral')],
    )


def _friend_ten_gods_axis(a: ForcetellerFacts, b: ForcetellerFacts, weight: float) -> AxisScore:
    friendly = {'비견': 8, '식신': 11, '정인': 10, '편인': 7, '상관': 5, '정재': 5, '편재': 4, '정관': 4, '편관': 0, '겁재': -2}
    scores: list[float] = []
    notes: list[str] = []
    for owner, partner, tag in ((a, b, 'A→B'), (b, a, 'B→A')):
        vals = []
        for s in partner.chart.stems:
            tg = ten_god(owner.chart.day_master, s)
            vals.append(friendly.get(tg, 0))
        base = 55 + (mean(vals) if vals else 0) * 2.2
        # 과도한 겁재/편관 반복은 경쟁·압박 축으로 보조 감점.
        harsh = sum(1 for s in partner.chart.stems if ten_god(owner.chart.day_master, s) in {'겁재', '편관'})
        base -= max(0, harsh - 1) * 3
        scores.append(clamp(base))
        notes.append(f'{tag} 십성 관계 평균을 동료성·표현·지원·경쟁 관점으로 계산했습니다.')
    score = (scores[0] + scores[1]) / 2 - abs(scores[0] - scores[1]) * 0.08
    return AxisScore(
        'friend_ten_gods', '십성 기반 우정·협력/경쟁', round(clamp(score), 1), weight,
        ' '.join(notes), [Evidence('십성', '친구 관계 역할', '비견·식상·인성의 협력성과 겁재·편관의 경쟁성을 구분해 평가했습니다.')],
    )


def _directional_total(receiver: ForcetellerFacts, giver: ForcetellerFacts, mode: Mode) -> float:
    support, _ = _support_direction(receiver, giver)
    stem, _ = _stem_relation(receiver.chart.day_master, giver.chart.day_master)
    branch = _branch_network_axis(receiver, giver, 1.0, include_day_day=(mode == 'friend')).score
    if mode == 'love':
        spouse, _ = _spouse_star_for(receiver, giver)
        palace = _spouse_palace_axis(receiver, giver, 1.0).score
        return round(clamp(support * .34 + stem * .17 + branch * .18 + spouse * .18 + palace * .13), 1)
    friend = _friend_ten_gods_axis(receiver, giver, 1.0).score
    return round(clamp(support * .34 + stem * .22 + branch * .22 + friend * .22), 1)


def _summaries(axes: list[AxisScore]) -> tuple[list[str], list[str]]:
    strengths = [f'{a.label}: {a.score:.1f}점' for a in sorted(axes, key=lambda x: x.score, reverse=True)[:3]]
    risks = [f'{a.label}: {a.score:.1f}점' for a in sorted(axes, key=lambda x: x.score)[:3] if a.score < 60]
    if not risks:
        risks = ['뚜렷한 저점 축은 없지만 실제 관계에서는 생활 습관과 가치관을 별도로 확인해야 합니다.']
    return strengths, risks


def score_love(a: ForcetellerFacts, b: ForcetellerFacts) -> CompatibilityResult:
    w = LOVE_WEIGHTS
    axes = [
        _element_axis(a, b, w['element_need']),
        _spouse_palace_axis(a, b, w['spouse_palace']),
        _spouse_star_axis(a, b, w['spouse_star']),
        _stem_axis(a, b, w['stem_daymaster'], 'stem_daymaster', '일간·천간 관계'),
        _branch_network_axis(a, b, w['branch_network'], include_day_day=False),
        _month_axis(a, b, w['month_life'], 'month_life', '월지·생활/사회축'),
        _conflict_buffer_axis(a, b, w['conflict_buffer']),
    ]
    total = round(sum(axis.contribution for axis in axes), 1)
    strengths, risks = _summaries(axes)
    return CompatibilityResult(
        mode='love', total=total, label=score_label(total, 'love'), axes=axes,
        direction_a_to_b=_directional_total(a, b, 'love'),
        direction_b_to_a=_directional_total(b, a, 'love'),
        strengths=strengths, risks=risks,
        technical_notes=[
            '50점을 명리 구조상 중립에 가깝게 설계한 절대 적합도이며 성공 확률이 아닙니다.',
            '일지-일지 관계는 배우자궁 축에서만 주평가하고 전체 지지 관계망에서는 중복 제거했습니다.',
            '신살·띠·서양 별자리는 총점에 포함하지 않습니다.',
        ],
    )


def score_friend(a: ForcetellerFacts, b: ForcetellerFacts) -> CompatibilityResult:
    w = FRIEND_WEIGHTS
    axes = [
        _element_axis(a, b, w['element_need']),
        _stem_axis(a, b, w['stem_communication'], 'stem_communication', '일간·천간 소통'),
        _branch_network_axis(a, b, w['branch_network'], include_day_day=True),
        _friend_ten_gods_axis(a, b, w['friend_ten_gods']),
        _month_axis(a, b, w['month_social'], 'month_social', '월지·사회생활 리듬'),
        _conflict_buffer_axis(a, b, w['conflict_buffer']),
    ]
    total = round(sum(axis.contribution for axis in axes), 1)
    strengths, risks = _summaries(axes)
    return CompatibilityResult(
        mode='friend', total=total, label=score_label(total, 'friend'), axes=axes,
        direction_a_to_b=_directional_total(a, b, 'friend'),
        direction_b_to_a=_directional_total(b, a, 'friend'),
        strengths=strengths, risks=risks,
        technical_notes=[
            '친구 모드는 배우자궁·배우자성 점수를 사용하지 않고 동료성·소통·상호지원 중심으로 계산합니다.',
            '50점을 중립에 가깝게 두는 절대 적합도이며 실제 우정의 지속 확률을 뜻하지 않습니다.',
            '신살·띠·서양 별자리는 총점에 포함하지 않습니다.',
        ],
    )


def score_pair(a: ForcetellerFacts, b: ForcetellerFacts, mode: Mode) -> CompatibilityResult:
    result = score_love(a, b) if mode == 'love' else score_friend(a, b)
    unknown = [x.profile.name for x in (a, b) if not x.profile.time_known]
    if unknown:
        result.technical_notes.append(
            f'출생시간 미상: {", ".join(unknown)}. 시주를 임의로 대입하지 않고 연주·월주·일주만으로 계산했으므로 시간에 따라 달라질 수 있는 세부 관계는 미확정입니다.'
        )
    return result
