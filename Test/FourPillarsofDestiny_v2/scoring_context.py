from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from forceteller_parser import ensure_forceteller_facts
from models import BirthProfile, Chart
from storage import profile_dir, read_json


ELEMENT_ORDER = ("木", "火", "土", "金", "水")
ELEMENT_ALIASES = {
    "木": ("木", "목"),
    "火": ("火", "화"),
    "土": ("土", "토"),
    "金": ("金", "금"),
    "水": ("水", "수"),
}


@dataclass(frozen=True)
class UserScoringContext:
    primary_preferred_element: str
    preferred_elements: tuple[str, ...]
    unfavorable_elements: tuple[str, ...]
    least_elements: tuple[str, ...]
    dominant_elements: tuple[str, ...]
    source: str
    source_note: str


def _elements_in_text(text: str) -> list[str]:
    source = str(text or "")
    result: list[str] = []
    for element, aliases in ELEMENT_ALIASES.items():
        hanja, korean = aliases
        korean_pattern = rf"(?<![가-힣]){re.escape(korean)}(?![가-힣])"
        if hanja in source or re.search(korean_pattern, source):
            result.append(element)
    return result


def _elements_near_label(text: str, labels: tuple[str, ...]) -> list[str]:
    normalized = " ".join(str(text or "").split())
    found: list[str] = []
    for label in labels:
        for match in re.finditer(re.escape(label), normalized):
            start = match.end()
            snippet = normalized[start:start + 90]
            found.extend(_elements_in_text(snippet))
    return list(dict.fromkeys(found))


def _fallback_elements(user_chart: Chart) -> tuple[tuple[str, ...], tuple[str, ...]]:
    minimum = min(user_chart.element_counts.values())
    maximum = max(user_chart.element_counts.values())
    least = tuple(
        element
        for element in ELEMENT_ORDER
        if user_chart.element_counts.get(element, 0) == minimum
    )
    dominant = tuple(
        element
        for element in ELEMENT_ORDER
        if user_chart.element_counts.get(element, 0) == maximum
    )
    return least, dominant


def load_user_scoring_context(
    profile: BirthProfile,
    user_chart: Chart,
) -> UserScoringContext:
    """
    사용자 쪽 용신·희신·기신은 포스텔러 자료를 우선한다.

    전체 후보를 포스텔러에서 조회하지 않는 예선 구조이므로, 후보 쪽은
    위치 보정 로컬 원국을 사용하고 사용자 보완 기준만 포스텔러에서 가져온다.
    포스텔러 본문에서 명시적 오행을 읽지 못하면 사용자 원국의 최소/최다
    오행으로 안전하게 대체하고 그 사실을 진단 정보에 남긴다.
    """
    least, dominant = _fallback_elements(user_chart)

    manifest = read_json(profile_dir(profile) / "forceteller_profile.json")
    data_dir = ""
    if isinstance(manifest, dict):
        data_dir = str(manifest.get("data_dir", "")).strip()

    useful_text = ""
    if data_dir and Path(data_dir).exists():
        facts = ensure_forceteller_facts(Path(data_dir))
        sections = facts.get("sections", {}) if isinstance(facts, dict) else {}
        useful = sections.get("useful_god", {}) if isinstance(sections, dict) else {}
        useful_text = str(useful.get("text", "")).strip()

    preferred = _elements_near_label(
        useful_text,
        ("용신", "희신", "도움이 되는 오행", "필요한 오행"),
    )
    unfavorable = _elements_near_label(
        useful_text,
        ("기신", "구신", "주의 오행", "불리한 오행"),
    )

    if preferred:
        source = "forceteller_useful_god"
        source_note = (
            "포스텔러 용신·희신 문구에서 사용자 보완 오행을 추출했습니다."
        )
    else:
        preferred = list(least[:1])
        source = "chart_minimum_fallback"
        source_note = (
            "포스텔러에서 용신 오행을 구조적으로 읽지 못해 사용자 원국의 "
            "최소 오행을 예선 보완 기준으로 사용했습니다."
        )

    if not unfavorable:
        unfavorable = list(dominant[:1])

    primary = preferred[0] if preferred else least[0]
    return UserScoringContext(
        primary_preferred_element=primary,
        preferred_elements=tuple(dict.fromkeys(preferred)),
        unfavorable_elements=tuple(dict.fromkeys(unfavorable)),
        least_elements=least,
        dominant_elements=dominant,
        source=source,
        source_note=source_note,
    )
