from __future__ import annotations

from itertools import combinations
from math import sqrt
from typing import Any

from bazi_engine import BRANCH_ELEMENT, ELEMENTS, STEM_ELEMENT
from models import Chart, PartialChart, RelationEvidence, ScoreBreakdown

GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

LIUHE = {
    frozenset(pair)
    for pair in [
        ("子", "丑"), ("寅", "亥"), ("卯", "戌"),
        ("辰", "酉"), ("巳", "申"), ("午", "未"),
    ]
}
CHONG = {
    frozenset(pair)
    for pair in [
        ("子", "午"), ("丑", "未"), ("寅", "申"),
        ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
    ]
}
HAI = {
    frozenset(pair)
    for pair in [
        ("子", "未"), ("丑", "午"), ("寅", "巳"),
        ("卯", "辰"), ("申", "亥"), ("酉", "戌"),
    ]
}
PO = {
    frozenset(pair)
    for pair in [
        ("子", "酉"), ("丑", "辰"), ("寅", "亥"),
        ("卯", "午"), ("巳", "申"), ("未", "戌"),
    ]
}
XING = {
    frozenset(pair)
    for pair in [
        ("子", "卯"), ("寅", "巳"), ("巳", "申"),
        ("寅", "申"), ("丑", "戌"), ("戌", "未"),
        ("丑", "未"),
    ]
}
SANHE = [
    {"申", "子", "辰"},
    {"亥", "卯", "未"},
    {"寅", "午", "戌"},
    {"巳", "酉", "丑"},
]
STEM_COMBINATIONS = {
    frozenset(("甲", "己")): "갑기합",
    frozenset(("乙", "庚")): "을경합",
    frozenset(("丙", "辛")): "병신합",
    frozenset(("丁", "壬")): "정임합",
    frozenset(("戊", "癸")): "무계합",
}
STEM_POLARITY = {
    "甲": "+", "乙": "-", "丙": "+", "丁": "-", "戊": "+",
    "己": "-", "庚": "+", "辛": "-", "壬": "+", "癸": "-",
}

LOCAL_SCORE_MIN = 0.0
LOCAL_SCORE_MAX = 1000.0
SCORING_FORMULA_VERSION = "weighted-quality-v2"

# 각 항목은 먼저 0~100 품질점수로 평가한 뒤 아래 가중치만큼 환산한다.
# 따라서 특정 항목 하나가 전체 결과를 독식하거나 1000점 상한에 몰리는 것을 막는다.
MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "lover": {
        "spouse_palace": 230.0,
        "day_master": 140.0,
        "branch_relations": 160.0,
        "element_balance": 160.0,
        "spouse_star": 90.0,
        "zodiac": 40.0,
        "month_support": 90.0,
        "internal_stability": 90.0,
    },
    "friend": {
        "spouse_palace": 150.0,
        "day_master": 140.0,
        "branch_relations": 220.0,
        "element_balance": 200.0,
        "spouse_star": 0.0,
        "zodiac": 50.0,
        "month_support": 130.0,
        "internal_stability": 110.0,
    },
}

MODE_LABELS = {
    "lover": {
        "core": "배우자궁",
        "month": "생활·사회 리듬",
    },
    "friend": {
        "core": "친구관계 핵심 일지",
        "month": "활동·사회 리듬",
    },
}

POSITION_NAMES = ("연지", "월지", "일지", "시지")
POSITION_IMPORTANCE = (0.45, 0.80, 1.00, 0.65)
NEUTRAL_QUALITY = 55.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _relationship_mode(value: str) -> str:
    normalized = str(value or "lover").strip().lower()
    aliases = {
        "lover": "lover", "love": "lover", "l": "lover",
        "연인": "lover", "연애": "lover",
        "friend": "friend", "friendship": "friend", "f": "friend",
        "친구": "friend", "우정": "friend",
    }
    mode = aliases.get(normalized)
    if mode is None:
        raise ValueError(f"지원하지 않는 관계 모드입니다: {value!r}")
    return mode


def spouse_star_elements(day_master: str, gender: str) -> set[str]:
    day_element = STEM_ELEMENT[day_master]
    if gender == "F":
        return {
            element
            for element, target in CONTROLS.items()
            if target == day_element
        }
    return {CONTROLS[day_element]}


def _same_sanhe_group(left: str, right: str) -> bool:
    return any(left in group and right in group for group in SANHE)


def _branch_relation(left: str, right: str) -> str:
    if left == right:
        return "동일 지지"

    pair = frozenset((left, right))
    if pair in CHONG:
        return "충"
    if pair in XING:
        return "형"
    if pair in HAI:
        return "해"
    if pair in LIUHE and pair in PO:
        return "육합·파 중첩"
    if pair in LIUHE:
        return "육합"
    if _same_sanhe_group(left, right):
        return "삼합 계열"
    if pair in PO:
        return "파"
    return "중립"


def _branch_quality(
    relation: str,
    mode: str,
    context: str,
) -> float:
    tables: dict[str, dict[str, dict[str, float]]] = {
        "core": {
            "lover": {
                "육합": 84.0,
                "육합·파 중첩": 70.0,
                "삼합 계열": 74.0,
                "동일 지지": 60.0,
                "중립": 55.0,
                "파": 44.0,
                "해": 34.0,
                "형": 28.0,
                "충": 18.0,
            },
            "friend": {
                "육합": 80.0,
                "육합·파 중첩": 68.0,
                "삼합 계열": 78.0,
                "동일 지지": 70.0,
                "중립": 58.0,
                "파": 48.0,
                "해": 42.0,
                "형": 38.0,
                "충": 30.0,
            },
        },
        "cross": {
            "lover": {
                "육합": 76.0,
                "육합·파 중첩": 65.0,
                "삼합 계열": 68.0,
                "동일 지지": 60.0,
                "중립": 55.0,
                "파": 45.0,
                "해": 38.0,
                "형": 32.0,
                "충": 24.0,
            },
            "friend": {
                "육합": 74.0,
                "육합·파 중첩": 64.0,
                "삼합 계열": 72.0,
                "동일 지지": 66.0,
                "중립": 57.0,
                "파": 48.0,
                "해": 42.0,
                "형": 36.0,
                "충": 29.0,
            },
        },
        "month": {
            "lover": {
                "육합": 74.0,
                "육합·파 중첩": 64.0,
                "삼합 계열": 68.0,
                "동일 지지": 63.0,
                "중립": 55.0,
                "파": 45.0,
                "해": 40.0,
                "형": 36.0,
                "충": 28.0,
            },
            "friend": {
                "육합": 72.0,
                "육합·파 중첩": 64.0,
                "삼합 계열": 72.0,
                "동일 지지": 68.0,
                "중립": 58.0,
                "파": 49.0,
                "해": 44.0,
                "형": 40.0,
                "충": 34.0,
            },
        },
        "zodiac": {
            "lover": {
                "육합": 70.0,
                "육합·파 중첩": 60.0,
                "삼합 계열": 66.0,
                "동일 지지": 58.0,
                "중립": 52.0,
                "파": 47.0,
                "해": 44.0,
                "형": 40.0,
                "충": 35.0,
            },
            "friend": {
                "육합": 69.0,
                "육합·파 중첩": 60.0,
                "삼합 계열": 68.0,
                "동일 지지": 64.0,
                "중립": 54.0,
                "파": 48.0,
                "해": 45.0,
                "형": 42.0,
                "충": 38.0,
            },
        },
        "internal": {
            "lover": {
                "육합": 75.0,
                "육합·파 중첩": 61.0,
                "삼합 계열": 68.0,
                "동일 지지": 55.0,
                "중립": 60.0,
                "파": 45.0,
                "해": 38.0,
                "형": 32.0,
                "충": 25.0,
            },
            "friend": {
                "육합": 74.0,
                "육합·파 중첩": 61.0,
                "삼합 계열": 69.0,
                "동일 지지": 57.0,
                "중립": 60.0,
                "파": 47.0,
                "해": 40.0,
                "형": 35.0,
                "충": 29.0,
            },
        },
    }
    return tables[context][mode][relation]


def _day_master_quality(
    user_stem: str,
    candidate_stem: str,
    mode: str,
) -> tuple[float, str]:
    pair = frozenset((user_stem, candidate_stem))
    if pair in STEM_COMBINATIONS:
        return (
            (78.0 if mode == "lover" else 72.0),
            STEM_COMBINATIONS[pair],
        )

    user_element = STEM_ELEMENT[user_stem]
    candidate_element = STEM_ELEMENT[candidate_stem]

    if GENERATES[candidate_element] == user_element:
        return (
            (72.0 if mode == "lover" else 68.0),
            "상대 일간이 사용자 일간을 생함",
        )
    if GENERATES[user_element] == candidate_element:
        return (
            (63.0 if mode == "lover" else 65.0),
            "사용자 일간이 상대 일간을 생함",
        )
    if CONTROLS[candidate_element] == user_element:
        return (
            (38.0 if mode == "lover" else 44.0),
            "상대 일간이 사용자 일간을 극함",
        )
    if CONTROLS[user_element] == candidate_element:
        return (
            (44.0 if mode == "lover" else 48.0),
            "사용자 일간이 상대 일간을 극함",
        )
    if user_element == candidate_element:
        opposite = STEM_POLARITY[user_stem] != STEM_POLARITY[candidate_stem]
        if mode == "lover":
            return (63.0 if opposite else 57.0), "일간 오행 동일"
        return (68.0 if opposite else 64.0), "일간 오행 동일"
    return (55.0 if mode == "lover" else 58.0), "중립"


def _candidate_element_counts(pillars: list[str]) -> dict[str, float]:
    values: list[str] = []
    for pillar in pillars:
        values.append(STEM_ELEMENT[pillar[0]])
        values.append(BRANCH_ELEMENT[pillar[1]])
    return {
        element: float(values.count(element))
        for element in ELEMENTS
    }


def _normalize_distribution(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(values.get(element, 0.0))) for element in ELEMENTS)
    if total <= 0:
        return {element: 0.2 for element in ELEMENTS}
    return {
        element: max(0.0, float(values.get(element, 0.0))) / total
        for element in ELEMENTS
    }


def _chart_distribution(
    chart: Chart | PartialChart | None,
    fallback_counts: dict[str, float],
) -> dict[str, float]:
    if chart is not None:
        percentages = getattr(chart, "element_percent", None)
        if isinstance(percentages, dict):
            clean = {
                element: float(percentages.get(element, 0.0))
                for element in ELEMENTS
            }
            total = sum(clean.values())
            if 95.0 <= total <= 105.0:
                return _normalize_distribution(clean)

    return _normalize_distribution(fallback_counts)


def _component(
    field_name: str,
    quality: float,
    mode: str,
    breakdown: ScoreBreakdown,
) -> float:
    quality = round(_clamp(quality, 0.0, 100.0), 2)
    weight = MODE_WEIGHTS[mode][field_name]
    contribution = round(weight * quality / 100.0, 2)
    setattr(breakdown, field_name, contribution)
    breakdown.quality_scores[field_name] = quality
    breakdown.component_weights[field_name] = weight
    return contribution


def _evidence_delta(
    quality: float,
    weight: float,
    neutral_quality: float = NEUTRAL_QUALITY,
) -> float:
    return round(weight * (quality - neutral_quality) / 100.0, 2)


def _score_core_relation(
    user_branch: str,
    candidate_branch: str,
    mode: str,
) -> tuple[float, list[RelationEvidence]]:
    relation = _branch_relation(user_branch, candidate_branch)
    quality = _branch_quality(relation, mode, "core")
    weight = MODE_WEIGHTS[mode]["spouse_palace"]
    category = MODE_LABELS[mode]["core"]
    return quality, [
        RelationEvidence(
            category,
            relation,
            _evidence_delta(quality, weight),
            f"{user_branch}-{candidate_branch}; 품질 {quality:.1f}/100",
        )
    ]


def _score_cross_relations(
    user_branches: list[str],
    candidate_branches: list[str],
    mode: str,
) -> tuple[float, list[RelationEvidence]]:
    weighted_sum = 0.0
    weight_sum = 0.0
    evidence: list[RelationEvidence] = []
    repeats: dict[tuple[str, frozenset[str]], int] = {}

    for user_index, user_branch in enumerate(user_branches):
        for candidate_index, candidate_branch in enumerate(candidate_branches):
            # 핵심 일지, 띠, 월지 리듬 항목에서 별도로 평가해 중복 가산하지 않는다.
            if (user_index, candidate_index) in {(2, 2), (0, 0), (1, 1)}:
                continue

            pair_weight = sqrt(
                POSITION_IMPORTANCE[user_index]
                * POSITION_IMPORTANCE[candidate_index]
            )
            relation = _branch_relation(user_branch, candidate_branch)
            quality = _branch_quality(relation, mode, "cross")

            repeat_key = (
                relation,
                frozenset((user_branch, candidate_branch)),
            )
            repeat_index = repeats.get(repeat_key, 0)
            repeats[repeat_key] = repeat_index + 1
            damping = (1.0, 0.55, 0.30, 0.15)[min(repeat_index, 3)]
            effective_quality = (
                NEUTRAL_QUALITY
                + (quality - NEUTRAL_QUALITY) * damping
            )

            weighted_sum += effective_quality * pair_weight
            weight_sum += pair_weight

            if relation != "중립":
                detail_delta = round(
                    (effective_quality - NEUTRAL_QUALITY)
                    * pair_weight
                    / 10.0,
                    2,
                )
                evidence.append(
                    RelationEvidence(
                        "지지교차",
                        relation,
                        detail_delta,
                        (
                            f"사용자 {POSITION_NAMES[user_index]} {user_branch} - "
                            f"후보 {POSITION_NAMES[candidate_index]} {candidate_branch}; "
                            f"반복감쇠 {damping:.2f}"
                        ),
                    )
                )

    quality = weighted_sum / weight_sum if weight_sum else NEUTRAL_QUALITY

    combined = set(user_branches + candidate_branches)
    complete_groups = [group for group in SANHE if group.issubset(combined)]
    if complete_groups:
        bonus = min(8.0, len(complete_groups) * 4.0)
        quality += bonus
        evidence.append(
            RelationEvidence(
                "지지교차",
                "완전 삼합 보조",
                round(MODE_WEIGHTS[mode]["branch_relations"] * bonus / 100.0, 2),
                ", ".join("".join(sorted(group)) for group in complete_groups),
            )
        )

    quality = _clamp(quality, 15.0, 90.0)
    evidence.insert(
        0,
        RelationEvidence(
            "지지교차 종합",
            "중복 제거·위치 가중 평균",
            _evidence_delta(
                quality,
                MODE_WEIGHTS[mode]["branch_relations"],
            ),
            f"종합 품질 {quality:.1f}/100",
        ),
    )
    return quality, evidence


def _score_element_balance(
    user: Chart,
    candidate_chart: Chart | PartialChart | None,
    fallback_counts: dict[str, float],
    mode: str,
) -> tuple[float, list[RelationEvidence]]:
    user_distribution = _chart_distribution(
        user,
        {element: float(user.element_counts.get(element, 0)) for element in ELEMENTS},
    )
    candidate_distribution = _chart_distribution(
        candidate_chart,
        fallback_counts,
    )

    useful_elements = set(getattr(user, "useful_elements", []) or [])
    target_raw: dict[str, float] = {}
    for element in ELEMENTS:
        # 균형점 20%에서 사용자의 부족분은 보완하고 과다분은 덜 요구한다.
        value = 0.20 + 0.75 * (0.20 - user_distribution[element])
        if element in useful_elements:
            value += 0.055
        target_raw[element] = _clamp(value, 0.06, 0.38)
    target = _normalize_distribution(target_raw)

    distance = 0.5 * sum(
        abs(candidate_distribution[element] - target[element])
        for element in ELEMENTS
    )
    quality = 92.0 - 78.0 * distance

    max_element = max(candidate_distribution, key=candidate_distribution.get)
    max_share = candidate_distribution[max_element]
    if max_share > 0.50:
        quality -= (max_share - 0.50) * 65.0

    missing_count = sum(
        1
        for value in candidate_distribution.values()
        if value < 0.01
    )
    if missing_count >= 3:
        quality -= (missing_count - 2) * 4.0

    quality = _clamp(quality, 20.0, 95.0)
    weight = MODE_WEIGHTS[mode]["element_balance"]

    target_text = ", ".join(
        f"{element} {target[element] * 100:.1f}%"
        for element in ELEMENTS
    )
    candidate_text = ", ".join(
        f"{element} {candidate_distribution[element] * 100:.1f}%"
        for element in ELEMENTS
    )

    evidence = [
        RelationEvidence(
            "오행 보완",
            "과다·부족 동시 보정",
            _evidence_delta(quality, weight),
            (
                f"품질 {quality:.1f}/100; 목표 [{target_text}]; "
                f"후보 [{candidate_text}]"
            ),
        )
    ]
    if useful_elements:
        evidence.append(
            RelationEvidence(
                "오행 보완",
                "포스텔러 용신 요소 참고",
                0.0,
                ", ".join(sorted(useful_elements)),
            )
        )
    if max_share > 0.50:
        evidence.append(
            RelationEvidence(
                "오행 보완",
                "후보 오행 편중",
                -round((max_share - 0.50) * weight * 0.65, 2),
                f"{max_element} {max_share * 100:.1f}%",
            )
        )
    return quality, evidence


def _score_spouse_star(
    user: Chart,
    candidate_distribution: dict[str, float],
    candidate_day_stem: str,
    user_gender: str,
) -> tuple[float, list[RelationEvidence]]:
    elements = spouse_star_elements(user.day_master, user_gender)
    raw_units = sum(candidate_distribution[element] * 8.0 for element in elements)
    day_element = STEM_ELEMENT[candidate_day_stem]
    duplicate = 1.0 if day_element in elements else 0.0
    effective_units = max(0.0, raw_units - duplicate)

    if effective_units < 0.25:
        quality = 46.0
    elif effective_units <= 2.0:
        quality = 58.0 + effective_units * 12.0
    else:
        quality = 82.0 - (effective_units - 2.0) * 14.0
    quality = _clamp(quality, 35.0, 84.0)

    return quality, [
        RelationEvidence(
            "배우자성",
            "적정 범위 평가",
            _evidence_delta(
                quality,
                MODE_WEIGHTS["lover"]["spouse_star"],
            ),
            (
                f"{','.join(sorted(elements))}; 환산 {raw_units:.2f}개, "
                f"후보 일간 중복 {duplicate:.0f}개 제외, "
                f"유효 {effective_units:.2f}개; 품질 {quality:.1f}/100"
            ),
        )
    ]


def _score_simple_branch_component(
    category: str,
    user_branch: str,
    candidate_branch: str,
    mode: str,
    context: str,
    field_name: str,
) -> tuple[float, list[RelationEvidence]]:
    relation = _branch_relation(user_branch, candidate_branch)
    quality = _branch_quality(relation, mode, context)
    return quality, [
        RelationEvidence(
            category,
            relation,
            _evidence_delta(quality, MODE_WEIGHTS[mode][field_name]),
            f"{user_branch}-{candidate_branch}; 품질 {quality:.1f}/100",
        )
    ]


def _score_candidate_internal_stability(
    candidate_branches: list[str],
    candidate_chart: Chart | PartialChart | None,
    mode: str,
) -> tuple[float, list[RelationEvidence]]:
    qualities: list[float] = []
    evidence: list[RelationEvidence] = []

    for left, right in combinations(candidate_branches, 2):
        relation = _branch_relation(left, right)
        quality = _branch_quality(relation, mode, "internal")
        qualities.append(quality)
        if relation != "중립":
            evidence.append(
                RelationEvidence(
                    "후보안정성",
                    relation,
                    round((quality - 60.0) / 10.0, 2),
                    f"{left}-{right}",
                )
            )

    quality = sum(qualities) / len(qualities) if qualities else 60.0
    combined = set(candidate_branches)
    if any(group.issubset(combined) for group in SANHE):
        quality += 5.0

    strength = str(getattr(candidate_chart, "strength_label", "") or "")
    if strength:
        if "중화" in strength:
            quality += 4.0
        elif "극신강" in strength or "극신약" in strength:
            quality -= 8.0
        elif "신강" in strength or "신약" in strength:
            quality -= 3.0

    quality = _clamp(quality, 20.0, 88.0)
    evidence.insert(
        0,
        RelationEvidence(
            "후보안정성 종합",
            "내부 지지 평균",
            _evidence_delta(
                quality,
                MODE_WEIGHTS[mode]["internal_stability"],
                neutral_quality=60.0,
            ),
            (
                f"품질 {quality:.1f}/100"
                + (f"; 포스텔러 강약 {strength}" if strength else "")
            ),
        ),
    )
    return quality, evidence


def criterion_maximums(
    relationship_mode: str = "lover",
) -> dict[str, float]:
    mode = _relationship_mode(relationship_mode)
    return {
        "base_score": 0.0,
        **MODE_WEIGHTS[mode],
        "total": LOCAL_SCORE_MAX,
    }


def score_compatibility(
    user: Chart,
    candidate_year: str,
    candidate_month: str,
    candidate_day: str,
    candidate_hour: str | None,
    user_gender: str,
    relationship_mode: str = "lover",
    candidate_chart: Chart | PartialChart | None = None,
) -> tuple[ScoreBreakdown, list[RelationEvidence]]:
    """
    연인·친구 모드별 가중 품질점수 모델.

    각 기준을 0~100으로 먼저 평가하고 모드별 가중치로 환산한다.
    최종점수는 항목별 기여도의 합이므로 1000점 상한 절삭으로 인한
    동점군이 발생하지 않는다. 이 값은 포스텔러 공식 점수가 아니라
    후보 비교를 위한 내부 구조화 점수다.
    """
    mode = _relationship_mode(relationship_mode)
    breakdown = ScoreBreakdown(
        base_score=0.0,
        total=0.0,
        raw_total=0.0,
        scoring_mode=mode,
        formula_version=SCORING_FORMULA_VERSION,
        quality_scores={},
        component_weights=dict(MODE_WEIGHTS[mode]),
    )
    evidence: list[RelationEvidence] = []

    candidate_pillars = [candidate_year, candidate_month, candidate_day]
    if candidate_hour:
        candidate_pillars.append(candidate_hour)

    candidate_branches = [pillar[1] for pillar in candidate_pillars]
    fallback_counts = _candidate_element_counts(candidate_pillars)
    candidate_distribution = _chart_distribution(
        candidate_chart,
        fallback_counts,
    )

    quality, details = _score_core_relation(
        user.spouse_palace,
        candidate_day[1],
        mode,
    )
    _component("spouse_palace", quality, mode, breakdown)
    evidence.extend(details)

    quality, label = _day_master_quality(
        user.day_master,
        candidate_day[0],
        mode,
    )
    _component("day_master", quality, mode, breakdown)
    evidence.append(
        RelationEvidence(
            "일간",
            label,
            _evidence_delta(quality, MODE_WEIGHTS[mode]["day_master"]),
            (
                f"{user.day_master}-{candidate_day[0]}; "
                f"품질 {quality:.1f}/100"
            ),
        )
    )

    quality, details = _score_cross_relations(
        user.branches,
        candidate_branches,
        mode,
    )
    _component("branch_relations", quality, mode, breakdown)
    evidence.extend(details)

    quality, details = _score_element_balance(
        user,
        candidate_chart,
        fallback_counts,
        mode,
    )
    _component("element_balance", quality, mode, breakdown)
    evidence.extend(details)

    if mode == "lover":
        quality, details = _score_spouse_star(
            user,
            candidate_distribution,
            candidate_day[0],
            user_gender,
        )
        _component("spouse_star", quality, mode, breakdown)
        evidence.extend(details)
    else:
        _component("spouse_star", 0.0, mode, breakdown)
        evidence.append(
            RelationEvidence(
                "친구 모드",
                "배우자성 점수 미사용",
                0.0,
                "친구 순위에는 관성·재성 배우자성 가중치를 적용하지 않음",
            )
        )

    quality, details = _score_simple_branch_component(
        "띠 보조",
        user.year_pillar[1],
        candidate_year[1],
        mode,
        "zodiac",
        "zodiac",
    )
    _component("zodiac", quality, mode, breakdown)
    evidence.extend(details)

    quality, details = _score_simple_branch_component(
        MODE_LABELS[mode]["month"],
        user.month_pillar[1],
        candidate_month[1],
        mode,
        "month",
        "month_support",
    )
    _component("month_support", quality, mode, breakdown)
    evidence.extend(details)

    quality, details = _score_candidate_internal_stability(
        candidate_branches,
        candidate_chart,
        mode,
    )
    _component("internal_stability", quality, mode, breakdown)
    evidence.extend(details)

    contributions = (
        breakdown.spouse_palace,
        breakdown.day_master,
        breakdown.branch_relations,
        breakdown.element_balance,
        breakdown.spouse_star,
        breakdown.zodiac,
        breakdown.month_support,
        breakdown.internal_stability,
    )
    breakdown.raw_total = round(sum(contributions), 2)
    breakdown.total = round(
        _clamp(
            breakdown.raw_total,
            LOCAL_SCORE_MIN,
            LOCAL_SCORE_MAX,
        ),
        1,
    )
    return breakdown, evidence
