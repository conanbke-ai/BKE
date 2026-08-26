from __future__ import annotations

import html
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any

from bazi_engine import profile_to_solar
from forceteller_parser import ensure_forceteller_facts
from group_mode import (
    _brief_compatibility_explanation,
    group_path,
    profiles_from_definition,
)
from models import (
    AICandidateReport,
    AITop10Report,
    BirthProfile,
    Candidate,
    Chart,
    RelationEvidence,
    ScoreBreakdown,
)
from reporting import (
    _annotate_hanja_terms,
    _relationship_labels,
    _user_personality_points,
    write_ai_reports,
)
from storage import safe_filename_component
from calendar_labels import (
    western_zodiac_from_date,
    zodiac_from_year_pillar,
)


def _honorific(name: str) -> str:
    cleaned = str(name or "").strip() or "사용자"
    return cleaned if cleaned.endswith("님") else f"{cleaned}님"


def _profile_solar_date(profile: BirthProfile) -> date:
    solar = profile_to_solar(profile)
    return date(
        solar.getYear(),
        solar.getMonth(),
        solar.getDay(),
    )


def _chart_from_dict(value: dict[str, Any]) -> Chart:
    allowed = {item.name for item in fields(Chart)}
    return Chart(**{
        key: item
        for key, item in dict(value or {}).items()
        if key in allowed
    })


def _score_from_dict(value: dict[str, Any]) -> ScoreBreakdown:
    allowed = {item.name for item in fields(ScoreBreakdown)}
    return ScoreBreakdown(**{
        key: item
        for key, item in dict(value or {}).items()
        if key in allowed
    })


def _evidence_from_dicts(
    values: list[dict[str, Any]],
) -> list[RelationEvidence]:
    return [
        RelationEvidence(
            category=str(item.get("category", "")),
            relation=str(item.get("relation", "")),
            score=float(item.get("score", 0.0)),
            evidence=str(item.get("evidence", "")),
        )
        for item in values
    ]


def _direction_maps(
    rankings: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for user_result in rankings.get("rankings_by_user", []):
        user_id = str(user_result["user_id"])
        for item in user_result.get("rankings", []):
            result[(user_id, str(item["target_id"]))] = item
    return result


def _facts_from_member(member: dict[str, Any]) -> dict[str, Any]:
    data_dir = Path(
        str(member.get("forceteller_data_dir", "")).strip()
    )
    if not data_dir.exists():
        raise RuntimeError(
            f"{member.get('name', '구성원')}의 대표 포스텔러 원본 폴더가 없습니다."
        )
    return ensure_forceteller_facts(data_dir)


def build_pair_candidate(
    target_profile: BirthProfile,
    target_member: dict[str, Any],
    direction: dict[str, Any],
) -> Candidate:
    chart = _chart_from_dict(target_member["chart"])
    score = _score_from_dict(direction["score"])
    data_dir = Path(
        str(target_member.get("forceteller_data_dir", "")).strip()
    )
    birth_date = str(
        target_member.get(
            "solar_birth_date",
            target_member.get("birth_datetime", "").split()[0],
        )
    )
    time_known = bool(
        target_member.get(
            "birth_time_known",
            getattr(target_profile, "birth_time_known", True),
        )
    )
    if time_known:
        birth_time = str(
            target_member.get("birth_datetime", "").split()[-1]
        )
        time_label = "지정 출생시"
    else:
        birth_time = "미상"
        time_label = (
            "출생시간 미상 · 대표 시나리오 "
            f"{target_member.get('representative_time_label', '')} "
            f"{target_member.get('representative_birth_time', '')}"
        ).strip()

    candidate = Candidate(
        candidate_id=str(target_member["member_id"]),
        birth_date=birth_date,
        birth_time=birth_time,
        time_label=time_label,
        chart=chart,
        stage1_score=float(score.total),
        local_score=float(score.total),
        score=score,
        evidence=_evidence_from_dicts(
            direction.get("evidence", [])
        ),
        forceteller_chart=chart,
        chart_source="forceteller_rescored",
        final_score_source="forceteller_rescored",
        data_dir=str(data_dir),
        collection_status="cached",
        prefilter_rank=1,
        prefilter_score=float(score.total),
        selected_time_score=float(score.total),
    )
    candidate.local_calculation_audit = {
        "birth_time_known": time_known,
        "representative_time_label": target_member.get(
            "representative_time_label", ""
        ),
        "representative_birth_time": target_member.get(
            "representative_birth_time", ""
        ),
        "scenario_count": target_member.get(
            "scenario_count", 1
        ),
    }
    return candidate


def pair_context(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> dict[str, Any]:
    profiles = profiles_from_definition(definition)
    if len(profiles) != 2:
        raise RuntimeError(
            "지정 1인 궁합 구성원이 정확히 두 명이 아닙니다."
        )

    (user_id, user_profile), (
        target_id,
        target_profile,
    ) = profiles
    members = {
        str(item["member_id"]): item
        for item in rankings.get("members", [])
    }
    directions = _direction_maps(rankings)

    return {
        "user_id": user_id,
        "target_id": target_id,
        "user_profile": user_profile,
        "target_profile": target_profile,
        "user_member": members[user_id],
        "target_member": members[target_id],
        "user_to_target": directions[(user_id, target_id)],
        "target_to_user": directions[(target_id, user_id)],
        "mutual": rankings["mutual_pairs"][0],
        "unknown_time_analysis": rankings.get(
            "unknown_time_analysis"
        ),
        "rankings": rankings,
    }


def _evidence_text(item: dict[str, Any]) -> str:
    category = str(item.get("category", "관계 요소")).strip()
    relation = str(item.get("relation", "")).strip()
    detail = str(item.get("evidence", "")).strip()
    text = f"{category}의 {relation}" if relation else category
    if detail:
        text += f" — {detail}"
    return _annotate_hanja_terms(text)


def _top_evidence(
    direction: dict[str, Any],
    *,
    positive: bool,
    limit: int = 3,
) -> list[str]:
    values = [
        item
        for item in direction.get("evidence", [])
        if (
            float(item.get("score", 0.0)) > 0
            if positive
            else float(item.get("score", 0.0)) < 0
        )
    ]
    values.sort(
        key=lambda item: abs(float(item.get("score", 0.0))),
        reverse=True,
    )
    return [_evidence_text(item) for item in values[:limit]]


def _term_explanations(
    direction: dict[str, Any],
) -> list[str]:
    mapping = {
        "육합": "육합: 두 지지가 가까이 결합하는 관계로, 편안함과 협력 가능성을 보는 요소입니다.",
        "삼합": "삼합: 여러 지지가 한 방향의 기운을 만드는 관계로, 공통 목표와 흐름을 보는 요소입니다.",
        "충": "충: 서로 정면으로 부딪히는 관계로, 속도·표현·생활 방식 차이로 나타날 수 있습니다.",
        "형": "형: 반복되는 긴장이나 까다로운 반응 패턴을 살펴보는 관계입니다.",
        "파": "파: 관계 흐름이 끊기거나 약속이 어긋나는 양상을 보조적으로 살펴봅니다.",
        "해": "해: 직접 충돌보다 오해나 서운함이 누적되는 양상을 살펴봅니다.",
        "천간합": "천간합: 겉으로 드러나는 기운끼리 결합하는 관계로, 자연스러운 끌림을 볼 때 사용합니다.",
    }
    joined = " ".join(
        str(item.get("relation", ""))
        for item in direction.get("evidence", [])
    )
    result = [
        explanation
        for key, explanation in mapping.items()
        if key in joined
    ]
    return result[:4] or [
        "일간: 태어난 날의 천간으로, 기본적인 자아와 반응 방식을 보는 중심 기운입니다.",
        "일지: 태어난 날의 지지로, 가까운 관계에서 드러나는 생활·정서 반응을 참고합니다.",
    ]


def build_pair_fallback_report(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> tuple[AITop10Report, Candidate, Chart]:
    context = pair_context(definition, rankings)
    user_profile = context["user_profile"]
    target_profile = context["target_profile"]
    user_chart = _chart_from_dict(
        context["user_member"]["chart"]
    )
    target_chart = _chart_from_dict(
        context["target_member"]["chart"]
    )
    direction = context["user_to_target"]
    reverse = context["target_to_user"]
    mutual = context["mutual"]

    candidate = build_pair_candidate(
        target_profile,
        context["target_member"],
        direction,
    )

    positives = _top_evidence(direction, positive=True)
    risks = _top_evidence(direction, positive=False)
    target_born = _profile_solar_date(target_profile)
    mode = user_profile.relationship_mode
    labels = _relationship_labels(mode)
    brief = (
        direction.get("brief_explanation")
        or _brief_compatibility_explanation(
            direction.get("evidence", []),
            mode,
        )
    )
    personality = " ".join(
        _user_personality_points(
            target_profile,
            target_chart,
        )
    )
    zodiac_text = (
        f"{_honorific(target_profile.name)}은 "
        f"{zodiac_from_year_pillar(target_chart.year_pillar)}이며 "
        f"{western_zodiac_from_date(target_born)}입니다. "
        "띠와 별자리는 원국보다 낮은 비중의 보조 성향으로 참고합니다."
    )

    if mode == "friend":
        emotional = (
            "정서적 친밀감은 연락량 자체보다 약속을 지키는 방식과 "
            "서로의 개인 시간을 존중하는 태도에서 안정되기 쉽습니다."
        )
        long_term = (
            f"상호 평균은 {float(mutual['average_score']):.1f}/1000입니다. "
            "장기 우정에서는 연락 주기와 함께하는 활동의 강도를 맞추는 것이 중요합니다."
        )
        reality_checks = [
            "연락이 뜸해졌을 때 이를 거리감으로 받아들이는지 확인합니다.",
            "함께하는 활동과 개인 시간의 비율이 비슷한지 확인합니다.",
            "서운한 일이 생겼을 때 바로 말하는지 시간을 두는지 확인합니다.",
        ]
    else:
        emotional = (
            "애정 표현은 말과 행동의 속도를 맞추고, 상대가 편안하게 "
            "받아들이는 표현 방식을 확인할 때 안정되기 쉽습니다."
        )
        long_term = (
            f"상호 평균은 {float(mutual['average_score']):.1f}/1000입니다. "
            "장기 연애에서는 연락·약속·개인 시간·생활 리듬을 실제로 맞춰 보는 과정이 필요합니다."
        )
        reality_checks = [
            "연락 빈도와 답장 속도에 대한 기대가 비슷한지 확인합니다.",
            "갈등 시 바로 대화할지 시간을 둘지 합의합니다.",
            "개인 시간과 장기 계획의 우선순위가 맞는지 확인합니다.",
        ]

    positive_sentence = (
        " ".join(positives)
        if positives
        else "큰 단일 가점보다 원국 전체 균형이 중심이 된 관계입니다."
    )
    risk_sentence = (
        " ".join(risks)
        if risks
        else "구조 점수에서 두드러진 큰 충돌 근거는 적습니다."
    )

    item = AICandidateReport(
        rank=1,
        candidate_id=candidate.candidate_id,
        ai_score=round(candidate.local_score / 10.0, 1),
        interpretation_certainty=(
            "limited"
            if context.get("unknown_time_analysis")
            else "high"
        ),
        certainty_reason=(
            (
                "출생시간 미상 가능성을 12개 또는 144개 시나리오로 "
                "계산했으며, 표시 점수는 시나리오 중앙값입니다."
            )
            if context.get("unknown_time_analysis")
            else (
                "두 사람 모두 포스텔러에서 확인한 연·월·일·시주를 "
                "기준으로 평가했습니다."
            )
        ),
        candidate_type=f"{labels['mode_name']} 관계의 지정 상대방",
        summary=(
            f"{brief} "
            f"{_honorific(user_profile.name)}→{_honorific(target_profile.name)} "
            f"{float(direction['score']['total']):.1f}/1000, "
            f"반대 방향 {float(reverse['score']['total']):.1f}/1000, "
            f"상호 평균 {float(mutual['average_score']):.1f}/1000입니다."
        ),
        candidate_personality=personality,
        zodiac_and_sign_reading=zodiac_text,
        emotional_and_affection_style=emotional,
        communication_style=(
            "두 사람의 대화에서는 결론을 빨리 내리려는 순간과 감정을 "
            "충분히 설명해야 하는 순간을 구분하는 것이 중요합니다. "
            "한쪽이 해결책을 먼저 제시할 때 다른 쪽은 자신의 감정이 "
            "무시됐다고 느낄 수 있으므로, 먼저 들은 내용을 짧게 확인한 뒤 "
            "해결 방법을 논의하는 방식이 안정적입니다. "
            "갈등이 커졌을 때는 즉시 결론을 강요하기보다 다시 이야기할 "
            "시간을 구체적으로 정하는 편이 좋습니다."
        ),
        relationship_fit=(
            f"이 관계에서 긍정적으로 작용하는 중심은 {positive_sentence} "
            "입니다. 이러한 요소는 서로의 장점을 비교적 빠르게 알아보고, "
            "상대가 필요한 도움을 자연스럽게 제공하는 모습으로 나타날 수 "
            "있습니다. 다만 좋은 구조가 실제 만족으로 이어지려면 각자가 "
            "원하는 애정 표현이나 친밀감의 방식을 말로 확인해야 합니다."
        ),
        conflict_pattern=(
            f"조율이 필요한 중심은 {risk_sentence} "
            "입니다. 이 차이는 잘못의 문제가 아니라 반응 속도와 기대 방식의 "
            "차이로 나타날 가능성이 큽니다. 같은 문제가 반복될 때는 누가 "
            "옳은지를 따지기보다 어떤 상황에서 서운함이 시작됐는지와 다음에 "
            "어떻게 대응할지를 구체적으로 합의하는 편이 효과적입니다."
        ),
        daily_life_compatibility=(
            "실제 일상에서는 연락 주기, 약속 변경을 알리는 시점, 개인 시간, "
            "함께 보내는 시간의 밀도가 관계 만족도를 크게 좌우합니다. "
            "평소에는 서로의 리듬을 존중하되 중요한 일정과 감정 문제는 "
            "미루지 않는 기준을 정하는 것이 좋습니다. "
            "데이트나 공동 활동도 한쪽 취향에만 맞추기보다 익숙한 활동과 "
            "새로운 활동을 번갈아 선택하면 부담을 줄일 수 있습니다."
        ),
        long_term_outlook=long_term,
        strengths=positives or [
            "한 가지 관계 요소보다 전체 원국 균형을 통해 안정성을 확보하는 관계입니다."
        ],
        risks=risks or [
            "큰 구조적 충돌이 적더라도 실제 표현 방식과 생활 습관은 확인해야 합니다."
        ],
        evidence=[
            _evidence_text(value)
            for value in direction.get("evidence", [])[:4]
        ],
        reality_checks=reality_checks,
        comparison_reason=(
            "지정 상대방 한 명을 대상으로 하므로 순위가 아니라, "
            "포스텔러 원국을 현재 모드의 동일 공식에 적용해 관계 강점과 위험을 평가했습니다."
        ),
        term_explanations=_term_explanations(direction),
    )

    report = AITop10Report(
        title=(
            f"{_honorific(user_profile.name)}과 "
            f"{_honorific(target_profile.name)}의 "
            f"{labels['mode_name']} 궁합"
        ),
        methodology_note=(
            (
                "출생시간 미상인 사람은 가능한 12개 시진을 모두 포스텔러에서 "
                "확인하고, 두 사람 모두 미상이면 144개 궁합 조합을 로컬에서 "
                "계산했습니다. 대표점수는 최고점이 아니라 중앙값이며, "
                "대표 원국은 중앙값에 가장 가까운 시나리오입니다."
            )
            if context.get("unknown_time_analysis")
            else (
                "현재 문서는 AI 상세 해설을 실행하기 전에도 확인할 수 있는 "
                "로컬 간략본입니다. 포스텔러 원국과 구조화 점수는 확정값이며, "
                "성격·대화·장기 관계의 세부 서술은 AI 상세 보고서에서 "
                "개인 모드와 같은 분량으로 확장됩니다."
            )
        ),
        overall_cautions=[
            "사주 궁합은 관계를 단정하는 자료가 아니라 실제 소통을 점검하는 참고자료입니다.",
        ],
        candidates=[item],
    )
    return report, candidate, user_chart



def _unknown_time_intro(
    analysis: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    if not analysis:
        return "", []

    mutual = analysis["mutual"]
    representative = analysis["representative"]
    stability = str(analysis.get("stability", "보통"))
    count = int(analysis["combination_count"])
    lookups = int(analysis["forceteller_lookup_maximum"])

    markdown = [
        "## 출생시간 미상 분석",
        "",
        f"- 계산한 궁합 조합: {count}개",
        f"- 포스텔러 원국 조회 최대치: {lookups}개",
        "- OpenAI 상세 해설: 집계 결과 전체를 1회 호출",
        f"- 대표점수(중앙값): {mutual['median']:.1f}/1000",
        f"- 전체 범위: {mutual['minimum']:.1f}~{mutual['maximum']:.1f}",
        f"- 중앙 80% 범위: {mutual['p10']:.1f}~{mutual['p90']:.1f}",
        f"- 해석 안정도: {stability}",
        (
            "- 화면에 표시한 시주는 실제 출생시간을 확정한 값이 아니라 "
            f"중앙값에 가장 가까운 대표 시나리오입니다: "
            f"기준 사용자 {representative['user_label']} "
            f"{representative['user_time']}, 상대방 "
            f"{representative['target_label']} "
            f"{representative['target_time']}"
        ),
    ]

    html_text = f'''
<section class="summary-highlight uncertainty-panel">
  <span class="section-kicker">출생시간 미상 분석</span>
  <h2>한 시각을 임의로 확정하지 않고 {count}개 조합을 비교했습니다</h2>
  <p>
    표시 점수는 최고점이 아니라 <b>중앙값 {mutual['median']:.1f}/1000</b>이며,
    전체 범위는 {mutual['minimum']:.1f}~{mutual['maximum']:.1f},
    중앙 80% 범위는 {mutual['p10']:.1f}~{mutual['p90']:.1f}입니다.
    해석 안정도는 <b>{html.escape(stability)}</b>입니다.
  </p>
  <p>
    화면의 시주는 실제 출생시간 확정값이 아니라 중앙값에 가장 가까운
    대표 시나리오입니다. 기준 사용자:
    {html.escape(str(representative['user_label']))}
    {html.escape(str(representative['user_time']))}, 상대방:
    {html.escape(str(representative['target_label']))}
    {html.escape(str(representative['target_time']))}.
  </p>
  <p>
    포스텔러 원국은 최대 {lookups}개를 조회하고, 궁합 조합은 로컬에서
    계산한 뒤 OpenAI에는 압축된 집계 결과를 한 번만 전달합니다.
  </p>
</section>
'''
    return html_text, markdown


def pair_report_basename(
    definition: dict[str, Any],
) -> str:
    profiles = profiles_from_definition(definition)
    (_, user), (_, target) = profiles
    mode_name = _relationship_labels(
        user.relationship_mode
    )["mode_name"]
    return (
        f"{safe_filename_component(user.name, '사용자')}_"
        f"{safe_filename_component(target.name, '상대방')}_"
        f"{safe_filename_component(mode_name, '모드')}"
    )


def write_pair_reports(
    definition: dict[str, Any],
    rankings: dict[str, Any],
    ai_report: AITop10Report | None = None,
) -> tuple[Any, Any]:
    fallback_report, candidate, user_chart = (
        build_pair_fallback_report(
            definition,
            rankings,
        )
    )
    report = ai_report or fallback_report
    context = pair_context(definition, rankings)
    user_profile = context["user_profile"]
    target_profile = context["target_profile"]
    user_member = context["user_member"]
    target_member = context["target_member"]
    target_name = _honorific(target_profile.name)
    basename = pair_report_basename(definition)
    root = group_path(definition["group_id"])
    analysis = context.get("unknown_time_analysis")
    intro_html, intro_markdown = _unknown_time_intro(
        analysis
    )

    user_facts = _facts_from_member(user_member)
    user_chart_title = (
        f"{_honorific(user_profile.name)}의 대표 시나리오 원국"
        if analysis and not user_profile.birth_time_known
        else f"{_honorific(user_profile.name)}의 사주 원국"
    )
    candidate_chart_title = (
        f"{target_name}의 대표 시나리오 원국"
        if analysis and not target_profile.birth_time_known
        else f"{target_name}의 포스텔러 원국"
    )

    return write_ai_reports(
        user_profile,
        user_chart,
        report,
        [candidate],
        [candidate],
        include_comparison_table=False,
        candidate_display_names={
            candidate.candidate_id: target_name,
        },
        candidate_rank_labels={
            candidate.candidate_id: "지정 상대방",
        },
        output_root=root,
        html_filename=f"{basename}.html",
        md_filename=f"{basename}.md",
        include_age_policy=False,
        include_alternative_times=False,
        title_override=report.title,
        verify_user_chart=False,
        user_facts_override=user_facts,
        intro_html=intro_html,
        intro_markdown=intro_markdown,
        user_chart_title_override=user_chart_title,
        candidate_chart_title_overrides={
            candidate.candidate_id: candidate_chart_title,
        },
    )

