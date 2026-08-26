from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from models import BirthProfile, Candidate, Chart
from scoring import criterion_maximums


def _name_with_honorific(name: str) -> str:
    cleaned = str(name or "").strip() or "사용자"
    return cleaned if cleaned.endswith("님") else f"{cleaned}님"


def _mode_labels(profile: BirthProfile) -> dict[str, str]:
    if profile.relationship_mode == "friend":
        return {
            "mode": "친구",
            "relation_palace": "관계 중심 일지",
            "relation_score": "친구관계 핵심 일지",
            "score_title": "친구 궁합 점수",
            "source_note": (
                "친구 모드에서는 배우자성 점수를 사용하지 않고 "
                "정서적 교류·대화·활동 리듬 중심으로 평가합니다."
            ),
        }
    return {
        "mode": "연인",
        "relation_palace": "배우자궁",
        "relation_score": "배우자궁",
        "score_title": "연인 궁합 점수",
        "source_note": (
            "연인 모드에서는 배우자궁과 배우자성을 포함한 "
            "연애 궁합 기준으로 평가합니다."
        ),
    }


def _criterion_lines(
    profile: BirthProfile,
    candidate: Candidate,
) -> list[str]:
    maximums = criterion_maximums(profile.relationship_mode)
    labels = _mode_labels(profile)
    score = candidate.score

    rows = [
        (
            "spouse_palace",
            labels["relation_score"],
            score.spouse_palace,
        ),
        ("day_master", "일간 관계", score.day_master),
        (
            "branch_relations",
            "중복 제거 지지 관계망",
            score.branch_relations,
        ),
        (
            "element_balance",
            "오행 보완 적합도",
            score.element_balance,
        ),
        (
            "spouse_star",
            "배우자성" if profile.relationship_mode == "lover"
            else "배우자성(미사용)",
            score.spouse_star,
        ),
        ("zodiac", "띠 보조", score.zodiac),
        (
            "month_support",
            "생활·사회 리듬" if profile.relationship_mode == "lover"
            else "활동·사회 리듬",
            score.month_support,
        ),
        (
            "internal_stability",
            "후보 원국 안정성",
            score.internal_stability,
        ),
    ]

    result: list[str] = []
    for field_name, label, contribution in rows:
        maximum = float(maximums[field_name])
        quality = float(
            score.quality_scores.get(
                field_name,
                (contribution / maximum * 100.0)
                if maximum > 0
                else 0.0,
            )
        )
        result.append(
            f"- {label}: 품질 {quality:.1f}/100 → "
            f"가중 기여 {contribution:.1f}/{maximum:.1f}"
        )
    return result


def write_candidate_summary(
    path: Path,
    profile: BirthProfile,
    user_chart: Chart,
    candidate: Candidate,
    quality_score: int,
    quality_warnings: list[str],
) -> Path:
    positive = [
        item for item in candidate.evidence
        if item.score > 0
    ]
    negative = [
        item for item in candidate.evidence
        if item.score < 0
    ]
    source_chart = (
        candidate.forceteller_chart
        or candidate.chart
    )
    user_name = _name_with_honorific(profile.name)
    labels = _mode_labels(profile)

    lines = [
        f"# 후보 {candidate.birth_date} {candidate.birth_time} "
        f"({candidate.time_label})",
        "",
        f"- 분석 모드: {labels['mode']}",
        f"- 기준 설명: {labels['source_note']}",
        (
            "- 점수 성격: 포스텔러 공식 궁합점수가 아니라, 각 기준을 "
            "0~100 품질로 평가한 뒤 모드별 가중치를 적용한 내부 비교점수"
        ),
        "",
        f"## {user_name}의 포스텔러 원국",
        (
            f"- {user_chart.year_pillar} · "
            f"{user_chart.month_pillar} · "
            f"{user_chart.day_pillar} · "
            f"{user_chart.hour_pillar}"
        ),
        f"- 일간: {user_chart.day_master}",
        (
            f"- {labels['relation_palace']}: "
            f"{user_chart.spouse_palace}"
        ),
        f"- 오행: {user_chart.element_percent}",
        "",
        "## 후보 포스텔러 원국",
        (
            f"- {source_chart.year_pillar} · "
            f"{source_chart.month_pillar} · "
            f"{source_chart.day_pillar} · "
            f"{source_chart.hour_pillar}"
        ),
        f"- 일간: {source_chart.day_master}",
        (
            f"- {labels['relation_palace']}: "
            f"{source_chart.spouse_palace}"
        ),
        f"- 오행: {source_chart.element_percent}",
        "",
        f"## {labels['score_title']} (0~1000)",
        (
            f"- 로컬 예선 순위: "
            f"{candidate.prefilter_rank or '-'}"
        ),
        (
            f"- 로컬 예선 강건 점수: "
            f"{candidate.prefilter_score:.1f} "
            "(최고 시주 65% + 상위 3개 평균 25% + 12시진 중앙값 10%)"
        ),
        (
            f"- 선택 시주 단일 점수: "
            f"{candidate.selected_time_score:.1f}"
        ),
        (
            f"- 포스텔러 원국 기반 최종 구조화 점수: "
            f"{candidate.local_score:.1f}"
        ),
        f"- 최종 점수 원본: {candidate.final_score_source}",
        f"- 세부 점수: {asdict(candidate.score)}",
        "",
        "### 항목별 품질과 가중 기여도",
    ]
    lines.extend(_criterion_lines(profile, candidate))

    lines.extend([
        "",
        "## 로컬 예선 원국",
        (
            "- 최종 순위 확정 전 위치 보정 로컬 계산에 "
            "사용한 원국입니다."
        ),
        (
            f"- {candidate.chart.year_pillar} · "
            f"{candidate.chart.month_pillar} · "
            f"{candidate.chart.day_pillar} · "
            f"{candidate.chart.hour_pillar}"
        ),
    ])

    if candidate.chart_difference:
        lines.extend([
            "",
            "## 로컬 계산과 포스텔러 원국 차이",
        ])
        lines.extend(
            f"- {value}"
            for value in candidate.chart_difference
        )

    lines.extend(["", "## 긍정 근거"])
    lines.extend(
        f"- {item.category} · {item.relation} "
        f"({item.score:+g}) — {item.evidence}"
        for item in positive
    )

    lines.extend(["", "## 위험 근거"])
    lines.extend(
        f"- {item.category} · {item.relation} "
        f"({item.score:+g}) — {item.evidence}"
        for item in negative
    )

    lines.extend([
        "",
        "## 수집 품질",
        f"- 품질 점수: {quality_score}",
    ])
    lines.extend(
        f"- 경고: {warning}"
        for warning in quality_warnings
    )

    lines.extend([
        "",
        "## 포스텔러 본문",
        (
            Path(candidate.text_path).read_text(
                encoding="utf-8",
                errors="ignore",
            )[:8000]
            if candidate.text_path
            and Path(candidate.text_path).exists()
            else "(본문 없음)"
        ),
    ])

    output = path / "candidate_summary.md"
    output.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return output
