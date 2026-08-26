from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, fields, replace
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from bazi_engine import DOUBLE_HOURS, profile_to_solar
from collector import ensure_profiles_forceteller_charts
from group_mode import (
    _GROUP_MODE_NAMES,
    _brief_compatibility_explanation,
    _facts_and_data_dir,
    group_path,
    profiles_from_definition,
)
from models import BirthProfile, Chart, RelationEvidence, ScoreBreakdown
from scoring import score_compatibility
from storage import profile_id, write_json


UNKNOWN_TIME_ANALYSIS_VERSION = "unknown-time-12x12-v1"


def has_unknown_birth_time(profile: BirthProfile) -> bool:
    return not bool(getattr(profile, "birth_time_known", True))


def pair_has_unknown_time(definition: dict[str, Any]) -> bool:
    return any(
        has_unknown_birth_time(profile)
        for _, profile in profiles_from_definition(definition)
    )


def _scenario_profiles(
    profile: BirthProfile,
) -> list[dict[str, Any]]:
    if not has_unknown_birth_time(profile):
        return [{
            "label": "확정 시각",
            "time": f"{profile.hour:02d}:{profile.minute:02d}",
            "profile": profile,
        }]

    scenarios: list[dict[str, Any]] = []
    for label, hour, minute in DOUBLE_HOURS:
        scenario = replace(
            profile,
            hour=hour,
            minute=minute,
            birth_time_known=True,
        )
        scenarios.append({
            "label": label,
            "time": f"{hour:02d}:{minute:02d}",
            "profile": scenario,
        })
    return scenarios


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(
        ordered[lower]
        + (ordered[upper] - ordered[lower]) * fraction
    )


def _score_statistics(values: Iterable[float]) -> dict[str, float]:
    scores = [float(value) for value in values]
    if not scores:
        return {
            "median": 0.0,
            "mean": 0.0,
            "minimum": 0.0,
            "maximum": 0.0,
            "p10": 0.0,
            "p90": 0.0,
            "central_80_width": 0.0,
        }
    p10 = _percentile(scores, 0.10)
    p90 = _percentile(scores, 0.90)
    return {
        "median": round(float(median(scores)), 1),
        "mean": round(float(mean(scores)), 1),
        "minimum": round(min(scores), 1),
        "maximum": round(max(scores), 1),
        "p10": round(p10, 1),
        "p90": round(p90, 1),
        "central_80_width": round(p90 - p10, 1),
    }


def _median_dict(values: list[dict[str, float]]) -> dict[str, float]:
    keys: set[str] = set()
    for value in values:
        keys.update(value)
    return {
        key: round(
            float(median([
                float(value.get(key, 0.0))
                for value in values
            ])),
            2,
        )
        for key in sorted(keys)
    }


def _aggregate_score(
    scores: list[ScoreBreakdown],
) -> dict[str, Any]:
    if not scores:
        raise RuntimeError("집계할 궁합 점수가 없습니다.")

    numeric_fields = (
        "spouse_palace",
        "day_master",
        "branch_relations",
        "element_balance",
        "spouse_star",
        "zodiac",
        "month_support",
        "internal_stability",
        "base_score",
        "raw_total",
        "total",
    )
    payload: dict[str, Any] = {
        field_name: round(
            float(median([
                float(getattr(score, field_name))
                for score in scores
            ])),
            2,
        )
        for field_name in numeric_fields
    }
    payload["quality_scores"] = _median_dict([
        score.quality_scores
        for score in scores
    ])
    payload["component_weights"] = dict(
        scores[0].component_weights
    )
    payload["scoring_mode"] = scores[0].scoring_mode
    payload["formula_version"] = scores[0].formula_version
    return payload


def _evidence_key(value: RelationEvidence) -> tuple[str, str]:
    return (
        str(value.category).strip(),
        str(value.relation).strip(),
    )


def _aggregate_evidence(
    evidence_sets: list[list[RelationEvidence]],
) -> dict[str, list[dict[str, Any]]]:
    total = len(evidence_sets)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    examples: dict[tuple[str, str], str] = {}

    for evidence in evidence_sets:
        strongest_in_scenario: dict[
            tuple[str, str], RelationEvidence
        ] = {}
        for item in evidence:
            key = _evidence_key(item)
            previous = strongest_in_scenario.get(key)
            if (
                previous is None
                or abs(item.score) > abs(previous.score)
            ):
                strongest_in_scenario[key] = item
        for key, item in strongest_in_scenario.items():
            counts[key] += 1
            scores[key].append(float(item.score))
            examples.setdefault(key, str(item.evidence).strip())

    result = {
        "stable_positive": [],
        "stable_risk": [],
        "time_sensitive_positive": [],
        "time_sensitive_risk": [],
    }
    for key, count in counts.items():
        frequency = count / total if total else 0.0
        median_score = float(median(scores[key]))
        category, relation = key
        record = {
            "category": category,
            "relation": relation,
            "score": round(median_score, 2),
            "frequency": round(frequency, 4),
            "occurrences": count,
            "scenario_count": total,
            "evidence": (
                f"{count}/{total}개 시나리오({frequency * 100:.0f}%)에서 반복"
                + (
                    f"; 대표 설명: {examples[key]}"
                    if examples[key]
                    else ""
                )
            ),
        }
        if frequency >= 0.80:
            bucket = (
                "stable_positive"
                if median_score > 0
                else "stable_risk"
            )
        elif frequency >= 0.30:
            bucket = (
                "time_sensitive_positive"
                if median_score > 0
                else "time_sensitive_risk"
            )
        else:
            continue
        result[bucket].append(record)

    for values in result.values():
        values.sort(
            key=lambda item: (
                item["frequency"],
                abs(item["score"]),
            ),
            reverse=True,
        )
    return result


def _combined_evidence(
    aggregated: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    values = (
        aggregated["stable_positive"][:4]
        + aggregated["stable_risk"][:4]
        + aggregated["time_sensitive_positive"][:3]
        + aggregated["time_sensitive_risk"][:3]
    )
    values.sort(
        key=lambda item: (
            item["frequency"],
            abs(item["score"]),
        ),
        reverse=True,
    )
    return values


def _stability_label(
    mutual_stats: dict[str, float],
    stable_count: int,
) -> str:
    width = mutual_stats["central_80_width"]
    if width <= 40 and stable_count >= 3:
        return "높음"
    if width <= 80 and stable_count >= 1:
        return "보통"
    return "낮음"


def _brief(
    stats: dict[str, float],
    evidence: dict[str, list[dict[str, Any]]],
    scenario_count: int,
) -> str:
    positives = evidence["stable_positive"][:2]
    risks = evidence["stable_risk"][:2]
    parts = [
        f"출생시간 미상 가능성을 포함한 {scenario_count}개 시나리오의 "
        f"대표점수는 {stats['median']:.1f}점이며, 중앙 80% 범위는 "
        f"{stats['p10']:.1f}~{stats['p90']:.1f}점입니다."
    ]
    if positives:
        parts.append(
            "시간이 달라도 반복된 장점은 "
            + ", ".join(
                item["relation"] or item["category"]
                for item in positives
            )
            + "입니다."
        )
    if risks:
        parts.append(
            "시간과 무관하게 주의할 요소는 "
            + ", ".join(
                item["relation"] or item["category"]
                for item in risks
            )
            + "입니다."
        )
    if not risks:
        parts.append(
            "반복적으로 나타나는 큰 위험 요소는 적지만 실제 소통과 생활 습관은 별도로 확인해야 합니다."
        )
    return " ".join(parts)


def _solar_date(profile: BirthProfile) -> date:
    solar = profile_to_solar(profile)
    return date(
        solar.getYear(),
        solar.getMonth(),
        solar.getDay(),
    )


def build_unknown_time_pair_rankings(
    definition: dict[str, Any],
) -> dict[str, Any]:
    members = profiles_from_definition(definition)
    if len(members) != 2:
        raise RuntimeError(
            "출생시간 미상 분석은 지정 1인 궁합 두 명만 지원합니다."
        )

    (user_id, user_profile), (
        target_id,
        target_profile,
    ) = members
    mode = str(definition["relationship_mode"])

    user_scenarios = _scenario_profiles(user_profile)
    target_scenarios = _scenario_profiles(target_profile)

    all_profiles = [
        item["profile"]
        for item in user_scenarios + target_scenarios
    ]
    charts = ensure_profiles_forceteller_charts(all_profiles)

    for scenario in user_scenarios + target_scenarios:
        scenario_profile = scenario["profile"]
        chart = charts.get(profile_id(scenario_profile))
        if chart is None:
            raise RuntimeError(
                f"{scenario_profile.name} {scenario['label']}의 포스텔러 원국이 없습니다."
            )
        facts, data_dir = _facts_and_data_dir(scenario_profile)
        scenario["chart"] = chart
        scenario["facts"] = facts
        scenario["data_dir"] = data_dir

    combinations: list[dict[str, Any]] = []
    for user_scenario in user_scenarios:
        user_chart: Chart = user_scenario["chart"]
        for target_scenario in target_scenarios:
            target_chart: Chart = target_scenario["chart"]

            user_score, user_evidence = score_compatibility(
                user_chart,
                target_chart.year_pillar,
                target_chart.month_pillar,
                target_chart.day_pillar,
                target_chart.hour_pillar,
                user_profile.gender,
                mode,
                candidate_chart=target_chart,
            )
            target_score, target_evidence = score_compatibility(
                target_chart,
                user_chart.year_pillar,
                user_chart.month_pillar,
                user_chart.day_pillar,
                user_chart.hour_pillar,
                target_profile.gender,
                mode,
                candidate_chart=user_chart,
            )
            mutual_score = round(
                (user_score.total + target_score.total) / 2.0,
                2,
            )
            combinations.append({
                "user_scenario": user_scenario,
                "target_scenario": target_scenario,
                "user_score": user_score,
                "target_score": target_score,
                "user_evidence": user_evidence,
                "target_evidence": target_evidence,
                "mutual_score": mutual_score,
            })

    mutual_stats = _score_statistics(
        item["mutual_score"]
        for item in combinations
    )
    user_stats = _score_statistics(
        item["user_score"].total
        for item in combinations
    )
    target_stats = _score_statistics(
        item["target_score"].total
        for item in combinations
    )

    representative = min(
        combinations,
        key=lambda item: (
            abs(
                item["mutual_score"]
                - mutual_stats["median"]
            ),
            abs(
                item["user_score"].total
                - user_stats["median"]
            ),
        ),
    )

    user_evidence_aggregate = _aggregate_evidence([
        item["user_evidence"]
        for item in combinations
    ])
    target_evidence_aggregate = _aggregate_evidence([
        item["target_evidence"]
        for item in combinations
    ])

    stable_count = (
        len(user_evidence_aggregate["stable_positive"])
        + len(user_evidence_aggregate["stable_risk"])
        + len(target_evidence_aggregate["stable_positive"])
        + len(target_evidence_aggregate["stable_risk"])
    )
    stability = _stability_label(
        mutual_stats,
        stable_count,
    )

    user_score_payload = _aggregate_score([
        item["user_score"]
        for item in combinations
    ])
    target_score_payload = _aggregate_score([
        item["target_score"]
        for item in combinations
    ])

    user_direction = {
        "target_id": target_id,
        "target_name": target_profile.name,
        "rank": 1,
        "score": user_score_payload,
        "evidence": _combined_evidence(
            user_evidence_aggregate
        ),
        "brief_explanation": _brief(
            user_stats,
            user_evidence_aggregate,
            len(combinations),
        ),
        "score_statistics": user_stats,
        "evidence_stability": user_evidence_aggregate,
    }
    target_direction = {
        "target_id": user_id,
        "target_name": user_profile.name,
        "rank": 1,
        "score": target_score_payload,
        "evidence": _combined_evidence(
            target_evidence_aggregate
        ),
        "brief_explanation": _brief(
            target_stats,
            target_evidence_aggregate,
            len(combinations),
        ),
        "score_statistics": target_stats,
        "evidence_stability": target_evidence_aggregate,
    }

    representative_user = representative["user_scenario"]
    representative_target = representative["target_scenario"]

    def member_record(
        member_id: str,
        base_profile: BirthProfile,
        representative_scenario: dict[str, Any],
        scenarios: list[dict[str, Any]],
    ) -> dict[str, Any]:
        chart: Chart = representative_scenario["chart"]
        born = _solar_date(base_profile)
        return {
            "member_id": member_id,
            "profile_id": profile_id(base_profile),
            "name": base_profile.name,
            "gender": base_profile.gender,
            "calendar_type": base_profile.calendar_type,
            "birth_datetime": (
                f"{base_profile.year:04d}-{base_profile.month:02d}-{base_profile.day:02d} "
                + (
                    f"{base_profile.hour:02d}:{base_profile.minute:02d}"
                    if base_profile.birth_time_known
                    else "UNKNOWN"
                )
            ),
            "birth_time_known": base_profile.birth_time_known,
            "solar_birth_date": born.isoformat(),
            "chart": asdict(chart),
            "representative_time_label": representative_scenario["label"],
            "representative_birth_time": representative_scenario["time"],
            "representative_profile": asdict(
                representative_scenario["profile"]
            ),
            "scenario_count": len(scenarios),
            "scenario_charts": [
                {
                    "label": item["label"],
                    "time": item["time"],
                    "chart": asdict(item["chart"]),
                    "forceteller_data_dir": str(item["data_dir"]),
                }
                for item in scenarios
            ],
            "zodiac": chart.year_pillar[1],
            "forceteller_data_dir": str(
                representative_scenario["data_dir"]
            ),
            "facts_summary": representative_scenario[
                "facts"
            ].get("summary", {}),
        }

    member_records = [
        member_record(
            user_id,
            user_profile,
            representative_user,
            user_scenarios,
        ),
        member_record(
            target_id,
            target_profile,
            representative_target,
            target_scenarios,
        ),
    ]

    scenario_matrix = [
        {
            "user_label": item["user_scenario"]["label"],
            "user_time": item["user_scenario"]["time"],
            "target_label": item["target_scenario"]["label"],
            "target_time": item["target_scenario"]["time"],
            "user_to_target": round(
                item["user_score"].total,
                1,
            ),
            "target_to_user": round(
                item["target_score"].total,
                1,
            ),
            "mutual": round(item["mutual_score"], 1),
        }
        for item in combinations
    ]

    unknown_time_analysis = {
        "version": UNKNOWN_TIME_ANALYSIS_VERSION,
        "user_birth_time_known": user_profile.birth_time_known,
        "target_birth_time_known": target_profile.birth_time_known,
        "user_scenario_count": len(user_scenarios),
        "target_scenario_count": len(target_scenarios),
        "combination_count": len(combinations),
        "forceteller_lookup_maximum": (
            len(user_scenarios) + len(target_scenarios)
        ),
        "openai_call_count_planned": 1,
        "representative_selection": (
            "상호 평균점수 중앙값에 가장 가까운 시나리오"
        ),
        "representative": {
            "user_label": representative_user["label"],
            "user_time": representative_user["time"],
            "target_label": representative_target["label"],
            "target_time": representative_target["time"],
            "mutual_score": round(
                representative["mutual_score"],
                1,
            ),
        },
        "user_to_target": user_stats,
        "target_to_user": target_stats,
        "mutual": mutual_stats,
        "stability": stability,
        "user_evidence": user_evidence_aggregate,
        "target_evidence": target_evidence_aggregate,
        "scenario_matrix": scenario_matrix,
    }

    mutual_pair = {
        "rank": 1,
        "left_id": user_id,
        "left_name": user_profile.name,
        "right_id": target_id,
        "right_name": target_profile.name,
        "left_to_right": user_stats["median"],
        "right_to_left": target_stats["median"],
        "average_score": mutual_stats["median"],
        "lower_score": round(
            min(
                user_stats["median"],
                target_stats["median"],
            ),
            1,
        ),
        "direction_gap": round(
            abs(
                user_stats["median"]
                - target_stats["median"]
            ),
            1,
        ),
        "minimum_score": mutual_stats["minimum"],
        "maximum_score": mutual_stats["maximum"],
        "p10": mutual_stats["p10"],
        "p90": mutual_stats["p90"],
        "stability": stability,
    }

    result = {
        "group_id": definition["group_id"],
        "group_name": definition["group_name"],
        "execution_type": "pair",
        "analysis_type": "unknown_time_scenarios",
        "relationship_mode": mode,
        "mode_name": _GROUP_MODE_NAMES[mode],
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "scoring_version": user_score_payload[
            "formula_version"
        ],
        "score_direction": (
            "출생시간 미상 시나리오 전체의 방향성 점수를 중앙값으로 집계"
        ),
        "member_count": 2,
        "members": member_records,
        "rankings_by_user": [
            {
                "user_id": user_id,
                "user_name": user_profile.name,
                "rankings": [user_direction],
            },
            {
                "user_id": target_id,
                "user_name": target_profile.name,
                "rankings": [target_direction],
            },
        ],
        "mutual_pairs": [mutual_pair],
        "unknown_time_analysis": unknown_time_analysis,
    }

    root = group_path(definition["group_id"])
    write_json(root / "group_rankings.json", result)
    write_json(
        root / "unknown_time_analysis.json",
        unknown_time_analysis,
    )
    return result
