from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from ai_reporter import (
    AIQuotaError,
    AIReportFormatError,
    REPORT_JSON_SCHEMA,
)
from config import SETTINGS
from forceteller_parser import (
    compact_facts_for_ai,
    ensure_forceteller_facts,
)
from group_mode import group_path
from logging_utils import LOGGER
from models import (
    AICandidateReport,
    AITop10Report,
)
from pair_reporting import (
    build_pair_candidate,
    pair_context,
)
from storage import read_json, write_json
from calendar_labels import (
    western_zodiac_basis,
    western_zodiac_from_date,
    zodiac_basis,
    zodiac_from_year_pillar,
)


PAIR_PROMPT_VERSION = "pair-personal-detail-v3-unknown-time"
PAIR_SCHEMA_VERSION = "pair-personal-detail-v3-unknown-time"


def _single_schema() -> dict[str, Any]:
    schema = copy.deepcopy(REPORT_JSON_SCHEMA)
    candidates = schema["properties"]["candidates"]
    candidates["minItems"] = 1
    candidates["maxItems"] = 1

    item_properties = candidates["items"]["properties"]
    detailed_fields = (
        "summary",
        "candidate_personality",
        "emotional_and_affection_style",
        "communication_style",
        "relationship_fit",
        "conflict_pattern",
        "daily_life_compatibility",
        "long_term_outlook",
        "comparison_reason",
    )
    for field_name in detailed_fields:
        item_properties[field_name]["minLength"] = 120

    item_properties["zodiac_and_sign_reading"]["minLength"] = 60

    for field_name in (
        "strengths",
        "risks",
        "evidence",
        "reality_checks",
        "term_explanations",
    ):
        item_properties[field_name]["minItems"] = 2

    return schema


def _facts_from_member(member: dict[str, Any]) -> dict[str, Any]:
    data_dir = Path(
        str(member.get("forceteller_data_dir", "")).strip()
    )
    if not data_dir.exists():
        raise RuntimeError(
            f"{member.get('name', '구성원')}의 대표 포스텔러 원본 폴더가 없습니다."
        )
    return compact_facts_for_ai(
        ensure_forceteller_facts(data_dir)
    )


def _candidate_payload(
    candidate: Any,
    target_name: str,
) -> dict[str, Any]:
    if candidate.forceteller_chart is None:
        raise RuntimeError(
            "지정 상대방의 포스텔러 원국이 없습니다."
        )

    facts = {}
    if candidate.data_dir and Path(candidate.data_dir).exists():
        facts = compact_facts_for_ai(
            ensure_forceteller_facts(
                Path(candidate.data_dir)
            )
        )

    birth_date = datetime.strptime(
        candidate.birth_date,
        "%Y-%m-%d",
    ).date()

    return {
        "candidate_id": candidate.candidate_id,
        "candidate_display_name": target_name,
        "birth_datetime": (
            f"{candidate.birth_date} "
            f"{candidate.birth_time}"
        ),
        "birth_time_known": bool(
            candidate.local_calculation_audit.get(
                "birth_time_known", True
            )
        ),
        "representative_time": {
            "label": candidate.local_calculation_audit.get(
                "representative_time_label", ""
            ),
            "time": candidate.local_calculation_audit.get(
                "representative_birth_time", ""
            ),
        },
        "zodiac": zodiac_from_year_pillar(
            candidate.forceteller_chart.year_pillar
        ),
        "zodiac_basis": zodiac_basis(
            candidate.forceteller_chart.year_pillar
        ),
        "western_zodiac": western_zodiac_from_date(
            birth_date
        ),
        "western_zodiac_basis": western_zodiac_basis(
            birth_date
        ),
        "forceteller_chart": asdict(
            candidate.forceteller_chart
        ),
        "forceteller_facts": facts,
        "selection_scores": {
            "score_type": (
                "weighted_quality_internal_comparison"
            ),
            "score_1000": candidate.local_score,
            "quality_scores_100": (
                candidate.score.quality_scores
            ),
            "component_weights_1000": (
                candidate.score.component_weights
            ),
            "positive_evidence": [
                asdict(item)
                for item in candidate.evidence
                if item.score > 0
            ][:4],
            "risk_evidence": [
                asdict(item)
                for item in candidate.evidence
                if item.score < 0
            ][:4],
        },
    }


def _compact_unknown_time_analysis(
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not value:
        return None
    allowed = (
        "version",
        "user_birth_time_known",
        "target_birth_time_known",
        "user_scenario_count",
        "target_scenario_count",
        "combination_count",
        "forceteller_lookup_maximum",
        "openai_call_count_planned",
        "representative_selection",
        "representative",
        "user_to_target",
        "target_to_user",
        "mutual",
        "stability",
        "user_evidence",
        "target_evidence",
    )
    return {
        key: value[key]
        for key in allowed
        if key in value
    }


def _payload(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    context = pair_context(definition, rankings)
    user_profile = context["user_profile"]
    target_profile = context["target_profile"]
    candidate = build_pair_candidate(
        target_profile,
        context["target_member"],
        context["user_to_target"],
    )

    target_name = (
        target_profile.name
        if target_profile.name.endswith("님")
        else f"{target_profile.name}님"
    )
    user_name = (
        user_profile.name
        if user_profile.name.endswith("님")
        else f"{user_profile.name}님"
    )

    return {
        "method": {
            "execution_type": "specified_single_person",
            "relationship_mode": (
                user_profile.relationship_mode
            ),
            "ranking_used": False,
            "top10_table_used": False,
            "user_chart_source": "forceteller",
            "target_chart_source": "forceteller",
            "api_call_count_planned": 1,
            "unknown_time_scenarios_used": bool(
                context.get("unknown_time_analysis")
            ),
        },
        "user": {
            "display_name": user_name,
            "gender": user_profile.gender,
            "forceteller_chart": (
                context["user_member"]["chart"]
            ),
            "birth_time_known": user_profile.birth_time_known,
            "forceteller_facts": _facts_from_member(
                context["user_member"]
            ),
        },
        "candidates": [
            _candidate_payload(
                candidate,
                target_name,
            )
        ],
        "mutual_scores": {
            "user_to_target": (
                context["user_to_target"]["score"]["total"]
            ),
            "target_to_user": (
                context["target_to_user"]["score"]["total"]
            ),
            "average": context["mutual"]["average_score"],
        },
        "unknown_time_analysis": _compact_unknown_time_analysis(
            context.get("unknown_time_analysis")
        ),
    }, candidate


def _instructions(mode: str) -> str:
    common = """
포스텔러에서 확인한 기준 사용자와 지정 상대방 한 명의 원국·오행·
신살·길성, 그리고 Python이 계산한 방향성 궁합 근거를 바탕으로
개인 모드와 동일한 수준의 상세 한국어 궁합 보고서를 작성한다.

- candidates 배열에는 지정 상대방 정확히 한 명만 작성한다.
- candidate_id를 한 글자도 바꾸지 않는다.
- 순위 경쟁이 아니므로 comparison_reason에는 왜 1위인지가 아니라
  이 궁합 평가와 점수가 나온 이유를 설명한다.
- candidate_display_name을 상대방 호칭으로 사용한다.
- 사주·신살·길성을 새로 계산하거나 추측하지 않는다.
- 포스텔러에서 실제 확인된 정보만 근거로 사용한다.
- 전문용어를 쓰면 바로 쉬운 뜻과 실제 관계 장면을 설명한다.
- 한자를 쓰면 丁(정화), 卯(묘목), 丁卯(정화·묘목)처럼 뜻음을 붙인다.
- summary, candidate_personality, zodiac_and_sign_reading,
  emotional_and_affection_style, communication_style,
  relationship_fit, conflict_pattern, daily_life_compatibility,
  long_term_outlook를 모두 충분히 구분해서 작성한다.
- strengths, risks, evidence, reality_checks, term_explanations도
  서로 중복되지 않게 작성한다.
- AI가 점수를 새로 만들지 않는다.
- selection_scores와 evidence에 있는 내부 계산 문구를 그대로 복사하지 않는다.
  특히 '목표분포', '품질 82.0/100', '환산 2.00개', '중복 제거',
  원소별 백분율 나열 같은 진단 문자열을 본문에 붙여 넣지 않는다.
- 내부 계산 근거는 일반인이 이해할 수 있는 실제 관계 의미로 번역한다.
  예: '표현 속도가 비슷해 대화가 빠르게 이어질 수 있다',
  '서운함을 처리하는 속도가 달라 한쪽이 압박을 느낄 수 있다'처럼 쓴다.
- 점수·백분율·계산식은 항목별 점수표와 evidence 영역에만 맡기고,
  성격·감정·대화·일상·장기 전망 본문은 자연스러운 서술문으로 작성한다.
- 각 상세 본문은 최소 3문장으로 쓰며, 첫 문장은 해석,
  두 번째 문장은 실제 관계 장면, 세 번째 문장은 조율 방법을 포함한다.
- unknown_time_analysis가 있으면 단일 대표 시주를 실제 출생시간처럼 단정하지 않는다.
- 출생시간 미상 결과는 중앙값, 전체 범위, 중앙 80% 범위,
  반복되는 안정 근거, 시주에 따라 달라지는 요소를 구분해 설명한다.
- 대표 시나리오는 화면 표시용이며 실제 시주 확정값이 아니라는 점을
  summary와 certainty_reason에 명확히 포함한다.
- 144개 시나리오를 각각 나열하지 말고 Python이 집계한 통계만 해설한다.
"""
    if mode == "friend":
        return common + """
[친구 모드]
- 연애 감정, 배우자, 결혼 가능성을 언급하지 않는다.
- 정서적 친밀감, 대화, 활동 리듬, 신뢰, 갈등 회복,
  장기 우정을 중심으로 설명한다.
"""
    return common + """
[연인 모드]
- 감정 표현, 애정 방식, 대화, 갈등, 생활 리듬,
  장기 연애와 결혼 관점을 현실적으로 설명한다.
"""


def _cache_key(
    definition: dict[str, Any],
    rankings: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    raw = json.dumps(
        {
            "pair_id": definition["group_id"],
            "relationship_mode": (
                rankings["relationship_mode"]
            ),
            "scoring_version": rankings["scoring_version"],
            "prompt_version": PAIR_PROMPT_VERSION,
            "schema_version": PAIR_SCHEMA_VERSION,
            "payload": payload,
            "model": SETTINGS.openai_model,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse(data: dict[str, Any]) -> AITop10Report:
    item = dict(data["candidates"][0])
    item["rank"] = 1
    return AITop10Report(
        title=str(data["title"]),
        methodology_note=str(data["methodology_note"]),
        overall_cautions=[
            str(value)
            for value in data["overall_cautions"]
        ],
        candidates=[
            AICandidateReport(**item)
        ],
    )


def load_cached_pair_ai_report(
    definition: dict[str, Any],
    rankings: dict[str, Any],
) -> AITop10Report:
    root = group_path(definition["group_id"])
    cached = read_json(root / "pair_ai_report.json")
    if not isinstance(cached, dict):
        raise RuntimeError(
            "저장된 pair_ai_report.json이 없습니다. "
            "먼저 pair-report를 실행하세요."
        )

    payload, _ = _payload(definition, rankings)
    expected = _cache_key(
        definition,
        rankings,
        payload,
    )
    if cached.get("cache_key") != expected:
        raise RuntimeError(
            "현재 원국·점수와 저장된 1:1 AI 보고서가 다릅니다. "
            "pair-report를 다시 실행하세요."
        )
    return _parse(cached["report"])


def generate_pair_ai_report(
    definition: dict[str, Any],
    rankings: dict[str, Any],
    force: bool = False,
) -> AITop10Report:
    if not SETTINGS.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."
        )

    context = pair_context(definition, rankings)
    # API 객체 생성 전에 대표 포스텔러 원본이 모두 존재하는지 확인한다.
    _facts_from_member(context["user_member"])
    _facts_from_member(context["target_member"])

    payload, candidate = _payload(
        definition,
        rankings,
    )
    root = group_path(definition["group_id"])
    cache_path = root / "pair_ai_report.json"
    cache_key = _cache_key(
        definition,
        rankings,
        payload,
    )

    if not force:
        cached = read_json(cache_path)
        if (
            isinstance(cached, dict)
            and cached.get("cache_key") == cache_key
        ):
            LOGGER.info(
                "지정 1인 상세 AI 캐시 재사용"
            )
            return _parse(cached["report"])

    write_json(
        root / "pair_ai_request_manifest.json",
        {
            "created_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "pair_id": definition["group_id"],
            "relationship_mode": (
                rankings["relationship_mode"]
            ),
            "api_call_count_planned": 1,
            "model": SETTINGS.openai_model,
            "prompt_version": PAIR_PROMPT_VERSION,
            "schema_version": PAIR_SCHEMA_VERSION,
        },
    )

    client = OpenAI(
        api_key=SETTINGS.openai_api_key
    )
    raw_text = ""

    try:
        response = client.responses.create(
            model=SETTINGS.openai_model,
            instructions=_instructions(
                rankings["relationship_mode"]
            ),
            input=[{
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": (
                        "<source_data>\n"
                        + json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n</source_data>"
                    ),
                }],
            }],
            text={
                "format": {
                    "type": "json_schema",
                    "name": (
                        "specified_single_person_compatibility"
                    ),
                    "strict": True,
                    "schema": _single_schema(),
                }
            },
            max_output_tokens=(
                SETTINGS.ai_max_output_tokens
            ),
            prompt_cache_key=(
                f"four-pillars-{PAIR_PROMPT_VERSION}"
            ),
            safety_identifier=hashlib.sha256(
                definition["group_id"].encode("utf-8")
            ).hexdigest()[:32],
            store=False,
        )
        raw_text = response.output_text or ""

        status = str(
            getattr(response, "status", "") or ""
        )
        incomplete = getattr(
            response,
            "incomplete_details",
            None,
        )
        if status == "incomplete" or incomplete:
            raise AIReportFormatError(
                "지정 1인 AI 응답이 출력 한도 전에 완성되지 않았습니다."
            )

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AIReportFormatError(
                "지정 1인 AI 응답 JSON이 완성되지 않았습니다: "
                f"{exc}"
            ) from exc

        returned = data.get("candidates")
        if (
            not isinstance(returned, list)
            or len(returned) != 1
            or returned[0].get("candidate_id")
            != candidate.candidate_id
        ):
            raise AIReportFormatError(
                "지정 상대방 ID가 AI 요청과 다릅니다."
            )

        returned[0]["rank"] = 1
        returned[0]["ai_score"] = round(
            candidate.local_score / 10.0,
            1,
        )
        if rankings.get("unknown_time_analysis"):
            returned[0]["interpretation_certainty"] = "limited"
            returned[0]["certainty_reason"] = (
                "출생시간 미상 가능성을 12개 또는 144개 시나리오로 "
                "계산한 결과이며, 표시 원국은 중앙값에 가장 가까운 "
                "대표 시나리오이지 실제 시주 확정값이 아닙니다."
            )
        report = _parse(data)

        write_json(
            cache_path,
            {
                "cache_key": cache_key,
                "created_at": datetime.now().isoformat(
                    timespec="seconds"
                ),
                "prompt_version": PAIR_PROMPT_VERSION,
                "schema_version": PAIR_SCHEMA_VERSION,
                "report": {
                    "title": report.title,
                    "methodology_note": (
                        report.methodology_note
                    ),
                    "overall_cautions": (
                        report.overall_cautions
                    ),
                    "candidates": [
                        asdict(item)
                        for item in report.candidates
                    ],
                },
            },
        )
        return report

    except (
        AIReportFormatError,
        RuntimeError,
    ):
        (root / "pair_ai_raw_response.txt").write_text(
            raw_text,
            encoding="utf-8",
        )
        raise
    except Exception as exc:
        (root / "pair_ai_raw_response.txt").write_text(
            raw_text,
            encoding="utf-8",
        )
        message = str(exc)
        if any(
            key in message.lower()
            for key in (
                "quota",
                "insufficient_quota",
                "billing",
            )
        ):
            raise AIQuotaError(message) from exc
        raise
