from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from config import SETTINGS
from storage import read_json, write_json


class _VisibleTextParser(HTMLParser):
    """HTML에서 script/style을 제외한 텍스트만 추출한다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        elif tag.lower() in {"br", "p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag.lower() in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


SECTION_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "five_elements_ten_gods": (
        "오행과 십성 분석",
        "오행과 십성",
        "오행 분석",
        "십성 분석",
    ),
    "strength": (
        "신강/신약지수",
        "신강/신약 지수",
        "신강 신약 지수",
        "신강·신약",
        "신강 신약",
    ),
    "special_stars": (
        "신살과 길성",
        "신살·길성",
        "신살 길성",
    ),
    "useful_god": (
        "용신",
        "희신",
        "기신",
    ),
    "hidden_stems": (
        "지장간",
    ),
    "twelve_stages": (
        "십이운성",
        "12운성",
    ),
}

OTHER_STOP_HEADINGS = (
    "사주 풀이 자세히 보기",
    "대운",
    "세운",
    "연운",
    "월운",
    "오늘의 운세",
    "평생운",
    "재물운",
    "직업운",
    "연애운",
    "결혼운",
    "건강운",
    "가족운",
)

# 포스텔러 화면에 등장할 가능성이 높은 신살·길성 명칭.
# 실제 화면에 존재하는 명칭만 추출하며, 없는 항목을 계산하거나 만들어내지 않는다.
STAR_ALIASES: dict[str, tuple[str, ...]] = {
    "도화살": ("도화살", "도화"),
    "홍염살": ("홍염살", "홍염"),
    "역마살": ("역마살", "역마"),
    "화개살": ("화개살", "화개"),
    "백호살": ("백호대살", "백호살"),
    "괴강살": ("괴강살", "괴강"),
    "양인살": ("양인살", "양인"),
    "현침살": ("현침살", "현침"),
    "귀문관살": ("귀문관살", "귀문"),
    "원진살": ("원진살", "원진"),
    "고신살": ("고신살", "고신"),
    "과숙살": ("과숙살", "과숙"),
    "탕화살": ("탕화살", "탕화"),
    "급각살": ("급각살", "급각"),
    "상문살": ("상문살", "상문"),
    "조객살": ("조객살", "조객"),
    "장성살": ("장성살", "장성"),
    "반안살": ("반안살", "반안"),
    "망신살": ("망신살", "망신"),
    "육해살": ("육해살", "육해"),
    "겁살": ("겁살",),
    "재살": ("재살",),
    "천살": ("천살",),
    "지살": ("지살",),
    "년살": ("년살", "연살"),
    "월살": ("월살",),
    "천라지망": ("천라지망",),
    "공망": ("공망",),
    "천을귀인": ("천을귀인",),
    "천덕귀인": ("천덕귀인",),
    "월덕귀인": ("월덕귀인",),
    "문창귀인": ("문창귀인",),
    "문곡귀인": ("문곡귀인",),
    "학당귀인": ("학당귀인",),
    "태극귀인": ("태극귀인",),
    "복성귀인": ("복성귀인",),
    "천관귀인": ("천관귀인",),
    "천복귀인": ("천복귀인",),
    "국인귀인": ("국인귀인",),
    "천주귀인": ("천주귀인",),
    "관귀학관": ("관귀학관",),
    "금여성": ("금여성", "금여"),
    "천의성": ("천의성", "천의"),
    "암록": ("암록",),
    "건록": ("건록",),
    "협록": ("협록",),
}

STAR_INFO: dict[str, dict[str, str]] = {
    "도화살": {
        "group": "매력·관계",
        "tone": "accent",
        "meaning": "사람의 시선을 끄는 매력, 친화력, 감각적인 표현과 관련해 보는 보조 신살입니다. 불륜이나 바람기를 뜻한다고 단정하지 않습니다.",
    },
    "홍염살": {
        "group": "매력·관계",
        "tone": "accent",
        "meaning": "호감과 감정 표현, 개성 있는 매력 발산과 관련해 해석하는 보조 신살입니다.",
    },
    "역마살": {
        "group": "이동·변화",
        "tone": "neutral",
        "meaning": "이동, 변화, 새로운 환경에 대한 활동성과 관련해 보는 보조 신살입니다.",
    },
    "화개살": {
        "group": "내면·예술",
        "tone": "neutral",
        "meaning": "내면 탐구, 예술적 감수성, 혼자 생각을 정리하는 성향과 관련해 보는 보조 신살입니다.",
    },
    "천을귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "곤란할 때 도움을 받거나 좋은 인연과 연결될 가능성을 상징하는 길성으로 봅니다.",
    },
    "천덕귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "관계에서 완충과 배려, 어려움을 부드럽게 넘기는 힘을 상징하는 길성으로 봅니다.",
    },
    "월덕귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "주변의 호의와 관계 회복력, 사람을 통해 도움을 얻는 흐름을 상징하는 길성으로 봅니다.",
    },
    "문창귀인": {
        "group": "학습·표현",
        "tone": "positive",
        "meaning": "말과 글, 학습, 정리력과 관련해 보는 길성입니다.",
    },
    "학당귀인": {
        "group": "학습·표현",
        "tone": "positive",
        "meaning": "배움, 이해력, 전문성을 쌓는 성향과 관련해 보는 길성입니다.",
    },
    "태극귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "사고의 깊이와 보호받는 흐름을 상징하는 길성으로 봅니다.",
    },
    "복성귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "생활 속 복과 도움, 무난하게 풀리는 흐름을 상징하는 길성으로 봅니다.",
    },
    "괴강살": {
        "group": "강한 기질",
        "tone": "caution",
        "meaning": "주관과 결단력이 강하게 나타날 수 있다고 보는 신살입니다. 강점이지만 관계에서는 완고함으로 보일 수 있습니다.",
    },
    "양인살": {
        "group": "강한 기질",
        "tone": "caution",
        "meaning": "추진력과 자기 방어가 강해질 수 있다고 보는 신살입니다. 성급함이나 강한 반응으로 단정하지 않고 원국 전체와 함께 봅니다.",
    },
    "현침살": {
        "group": "표현·민감성",
        "tone": "caution",
        "meaning": "섬세하고 날카로운 감각이나 표현과 관련해 보는 신살입니다. 말이 예리하게 전달될 가능성을 함께 살핍니다.",
    },
    "귀문관살": {
        "group": "내면·민감성",
        "tone": "caution",
        "meaning": "감수성과 생각의 복잡성, 특정 문제에 깊이 몰입하는 경향과 관련해 보는 보조 신살입니다.",
    },
    "원진살": {
        "group": "관계 주의",
        "tone": "caution",
        "meaning": "가까운 관계에서 이유를 명확히 설명하기 어려운 서운함이나 엇갈림이 생길 수 있다고 보는 신살입니다.",
    },
    "고신살": {
        "group": "독립·고독",
        "tone": "neutral",
        "meaning": "혼자 결정하거나 개인 시간을 중시하는 경향과 관련해 보는 보조 신살입니다.",
    },
    "과숙살": {
        "group": "독립·고독",
        "tone": "neutral",
        "meaning": "감정을 혼자 정리하거나 관계 안에서도 독립성을 유지하려는 성향과 관련해 보는 보조 신살입니다.",
    },
    "백호살": {
        "group": "강한 기질",
        "tone": "caution",
        "meaning": "강한 에너지와 극단적인 집중력이 나타날 수 있다고 보는 신살입니다. 사고나 불행을 단정하는 항목이 아닙니다.",
    },
    "장성살": {
        "group": "리더십",
        "tone": "positive",
        "meaning": "주도성, 책임감, 앞에 나서려는 기질과 관련해 보는 보조 신살입니다.",
    },
    "반안살": {
        "group": "안정·성취",
        "tone": "positive",
        "meaning": "자리 잡음과 안정, 성취 흐름과 관련해 보는 보조 신살입니다.",
    },
    "망신살": {
        "group": "표현·노출",
        "tone": "caution",
        "meaning": "자신을 드러내는 상황과 평판 변화에 민감할 수 있다고 보는 보조 신살입니다. 실제 망신을 예고하는 뜻으로 단정하지 않습니다.",
    },
}


SUPPLEMENTAL_STAR_INFO: dict[str, dict[str, str]] = {
    "탕화살": {
        "group": "감정·반응",
        "tone": "caution",
        "meaning": "감정과 반응의 온도가 빠르게 높아질 수 있다고 보는 보조 신살입니다.",
    },
    "급각살": {
        "group": "속도·변화",
        "tone": "caution",
        "meaning": "일을 급히 결정하거나 상황 전환이 빠를 수 있다고 보는 보조 신살입니다.",
    },
    "상문살": {
        "group": "정서·관계",
        "tone": "neutral",
        "meaning": "주변의 무거운 분위기나 타인의 감정에 영향을 받기 쉬운 흐름을 참고하는 신살입니다.",
    },
    "조객살": {
        "group": "정서·관계",
        "tone": "neutral",
        "meaning": "주변 사람의 일이나 관계 변화에 신경을 많이 쓰는 흐름을 참고하는 신살입니다.",
    },
    "육해살": {
        "group": "관계 주의",
        "tone": "caution",
        "meaning": "가까운 관계에서 오해나 미묘한 불편이 생기기 쉬운지를 참고하는 신살입니다.",
    },
    "겁살": {
        "group": "경쟁·변화",
        "tone": "caution",
        "meaning": "경쟁심과 돌발적인 변화에 대한 반응이 강해질 수 있다고 보는 보조 신살입니다.",
    },
    "재살": {
        "group": "긴장·대응",
        "tone": "caution",
        "meaning": "압박이 생겼을 때 방어적이거나 예민하게 대응할 가능성을 참고하는 신살입니다.",
    },
    "천살": {
        "group": "환경·변화",
        "tone": "neutral",
        "meaning": "개인 의지만으로 통제하기 어려운 환경 변화에 민감할 수 있다고 보는 신살입니다.",
    },
    "지살": {
        "group": "이동·활동",
        "tone": "neutral",
        "meaning": "생활 반경이 넓고 움직임이 잦을 수 있는 흐름을 참고하는 신살입니다.",
    },
    "년살": {
        "group": "매력·표현",
        "tone": "accent",
        "meaning": "대인관계에서 시선을 끌거나 감각적으로 자신을 표현하는 면을 참고하는 신살입니다.",
    },
    "월살": {
        "group": "정서·정체",
        "tone": "neutral",
        "meaning": "일이 잠시 정체될 때 생각이 많아지거나 감정을 안으로 정리하는 흐름을 참고합니다.",
    },
    "천라지망": {
        "group": "압박·몰입",
        "tone": "caution",
        "meaning": "책임이나 생각에 스스로 얽매여 답답함을 느끼기 쉬운지를 참고하는 신살입니다.",
    },
    "공망": {
        "group": "비움·변동",
        "tone": "neutral",
        "meaning": "특정 영역에서 기대와 실제 체감 사이에 공백이 생기기 쉬운지를 참고합니다.",
    },
    "문곡귀인": {
        "group": "학습·표현",
        "tone": "positive",
        "meaning": "말과 글, 예술적 표현과 섬세한 이해력을 상징하는 길성으로 봅니다.",
    },
    "금여성": {
        "group": "생활·관계",
        "tone": "positive",
        "meaning": "생활의 안정감과 관계에서 배려받는 흐름을 상징하는 길성으로 봅니다.",
    },
    "천의성": {
        "group": "회복·돌봄",
        "tone": "positive",
        "meaning": "돌봄, 회복, 건강 문제에 관심을 기울이는 성향과 연결해 보는 길성입니다.",
    },
    "암록": {
        "group": "생활·도움",
        "tone": "positive",
        "meaning": "겉으로 크게 드러나지 않아도 생활 속 도움과 자원이 이어지는 흐름을 뜻합니다.",
    },
    "건록": {
        "group": "자립·생활력",
        "tone": "positive",
        "meaning": "자립심과 생활 기반을 스스로 다지는 힘을 상징하는 길성으로 봅니다.",
    },
    "협록": {
        "group": "협력·도움",
        "tone": "positive",
        "meaning": "주변과 협력하며 현실적인 도움을 주고받는 흐름을 상징합니다.",
    },
    "천관귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "사회적 관계나 책임 영역에서 도움을 받을 수 있는 흐름을 상징합니다.",
    },
    "천복귀인": {
        "group": "귀인·도움",
        "tone": "positive",
        "meaning": "생활 속 복과 주변의 호의를 얻는 흐름을 상징하는 길성입니다.",
    },
    "국인귀인": {
        "group": "책임·신뢰",
        "tone": "positive",
        "meaning": "책임감과 신뢰, 조직 안에서 역할을 맡는 힘을 상징하는 길성입니다.",
    },
    "천주귀인": {
        "group": "생활·먹거리",
        "tone": "positive",
        "meaning": "생활의 풍요와 먹거리, 돌봄의 복을 상징하는 길성으로 봅니다.",
    },
    "관귀학관": {
        "group": "학습·직업",
        "tone": "positive",
        "meaning": "학습 능력과 전문성, 직업적 책임을 키우는 흐름과 연결해 보는 길성입니다.",
    },
}

DEFAULT_STAR_INFO = {
    "group": "기타 신살·길성",
    "tone": "neutral",
    "meaning": "포스텔러의 신살·길성 항목에 표시된 전통 명리 보조 정보입니다. 단독으로 성격이나 궁합을 결정하지 않습니다.",
}


def _html_to_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return "".join(parser.parts)


def _clean_lines(text: str) -> list[str]:
    result: list[str] = []
    previous = ""
    for raw_line in text.replace("\r", "\n").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line == previous:
            continue
        result.append(line)
        previous = line
    return result


def _is_heading(
    line: str,
    ignore_aliases: tuple[str, ...] = (),
) -> bool:
    compact = re.sub(r"\s+", "", line)
    ignored = {re.sub(r"\s+", "", alias) for alias in ignore_aliases}

    for aliases in SECTION_DEFINITIONS.values():
        for alias in aliases:
            normalized = re.sub(r"\s+", "", alias)
            if normalized in ignored:
                continue
            if compact == normalized:
                return True

    return any(
        compact == re.sub(r"\s+", "", heading)
        for heading in OTHER_STOP_HEADINGS
    )


def _extract_section(lines: list[str], aliases: tuple[str, ...]) -> dict[str, Any]:
    start_index: int | None = None
    found_title = ""

    for index, line in enumerate(lines):
        if any(alias in line for alias in aliases):
            start_index = index
            found_title = next(alias for alias in aliases if alias in line)
            break

    if start_index is None:
        return {"found": False, "title": aliases[0], "text": ""}

    collected: list[str] = []
    heading_line = lines[start_index]
    suffix = heading_line
    for alias in aliases:
        suffix = suffix.replace(alias, "")
    suffix = suffix.strip(" :-·|")
    if suffix:
        collected.append(suffix)

    for line in lines[start_index + 1 :]:
        if collected and _is_heading(line, ignore_aliases=aliases):
            break
        if len(collected) >= SETTINGS.forceteller_section_max_lines:
            break
        collected.append(line)

    text = "\n".join(collected).strip()
    return {
        "found": bool(text),
        "title": found_title or aliases[0],
        "text": text[: SETTINGS.forceteller_section_max_chars],
    }


def _flatten_relevant_network_strings(node: Any, output: list[str]) -> None:
    if len(output) >= 500:
        return

    if isinstance(node, str):
        value = re.sub(r"\s+", " ", node).strip()
        if value and any(
            keyword in value
            for keyword in (
                "신살", "길성", "도화", "홍염", "역마", "화개",
                "귀인", "용신", "희신", "기신", "신강", "신약",
                "지장간", "운성",
            )
        ):
            output.append(value)
        return

    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            if any(
                keyword in key_text.lower()
                for keyword in (
                    "sinsal", "special", "star", "yongsin", "useful",
                    "strength", "sibsin", "hidden", "unseong",
                )
            ):
                output.append(key_text)
            _flatten_relevant_network_strings(value, output)
        return

    if isinstance(node, list):
        for value in node:
            _flatten_relevant_network_strings(value, output)


def _normalize_label(value: str) -> str:
    return re.sub(
        r"[\s·ㆍ:：|/()\[\]{}<>《》「」『』-]+",
        "",
        value,
    )


def _star_info(canonical_name: str) -> dict[str, str]:
    if canonical_name in STAR_INFO:
        return STAR_INFO[canonical_name]
    if canonical_name in SUPPLEMENTAL_STAR_INFO:
        return SUPPLEMENTAL_STAR_INFO[canonical_name]

    if canonical_name.endswith("귀인"):
        return {
            "group": "귀인·도움",
            "tone": "positive",
            "meaning": (
                f"{canonical_name}은 전통 명리에서 주변의 도움과 보호를 "
                "상징적으로 참고하는 길성입니다."
            ),
        }
    if canonical_name.endswith("살"):
        return {
            "group": "기타 신살",
            "tone": "neutral",
            "meaning": (
                f"{canonical_name}은 전통 명리에서 성향과 관계 흐름을 "
                "보조적으로 살피는 신살입니다."
            ),
        }
    return DEFAULT_STAR_INFO


def _visible_special_star_section(
    visible_lines: list[str],
) -> tuple[list[str], str]:
    normalized_headings = {
        _normalize_label(alias)
        for alias in SECTION_DEFINITIONS["special_stars"]
    }

    start_index: int | None = None
    heading = ""

    for index, line in enumerate(visible_lines):
        if _normalize_label(line) in normalized_headings:
            start_index = index
            heading = line
            break

    if start_index is None:
        return [], ""

    result: list[str] = []
    for line in visible_lines[start_index + 1:]:
        if _is_heading(
            line,
            ignore_aliases=SECTION_DEFINITIONS["special_stars"],
        ):
            break
        if len(result) >= SETTINGS.forceteller_section_max_lines:
            break
        result.append(line)

    return result, heading


def _star_names_in_line(line: str) -> list[str]:
    found: list[str] = []
    normalized_line = _normalize_label(line)

    for canonical_name, aliases in STAR_ALIASES.items():
        if any(
            _normalize_label(alias) in normalized_line
            for alias in aliases
        ):
            found.append(canonical_name)

    return list(dict.fromkeys(found))


def _verified_star_title(line: str) -> str | None:
    """
    한 줄에 신살명이 정확히 하나만 나타나는 짧은 항목 줄만 인정한다.

    여러 신살명이 한꺼번에 나오는 도움말·전체 목록 문장은 제외한다.
    """
    compact = " ".join(line.split()).strip()
    if not compact or len(compact) > 80:
        return None

    names = _star_names_in_line(compact)
    if len(names) != 1:
        return None

    # 전체 종류를 설명하는 문장은 항목으로 보지 않는다.
    if any(
        token in compact
        for token in (
            "등의 신살",
            "다양한 신살",
            "신살의 종류",
            "대표적인 신살",
            "신살이 있습니다",
            "길성이 있습니다",
        )
    ):
        return None

    return names[0]


def _strict_star_excerpt(
    section_lines: list[str],
    index: int,
) -> str:
    context = [section_lines[index]]

    for line in section_lines[index + 1:index + 3]:
        if _verified_star_title(line):
            break
        if _is_heading(line):
            break
        context.append(line)

    return " ".join(context)[
        : SETTINGS.forceteller_star_excerpt_chars
    ]


def _extract_special_stars_strict(
    visible_lines: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    section_lines, heading = _visible_special_star_section(
        visible_lines
    )

    if not section_lines:
        return [], {
            "verified_section_found": False,
            "section_heading": heading,
            "rejected_possible_mentions": 0,
        }

    stars: list[dict[str, Any]] = []
    seen: set[str] = set()
    rejected = 0

    for index, line in enumerate(section_lines):
        name = _verified_star_title(line)
        if name is None:
            if _star_names_in_line(line):
                rejected += 1
            continue
        if name in seen:
            continue

        seen.add(name)
        info = _star_info(name)
        stars.append(
            {
                "name": name,
                "group": info["group"],
                "tone": info["tone"],
                "plain_meaning": info["meaning"],
                "source_excerpt": _strict_star_excerpt(
                    section_lines,
                    index,
                ),
                "verified": True,
                "source_scope": "visible_special_stars_section",
            }
        )

    return stars[: SETTINGS.forceteller_max_special_stars], {
        "verified_section_found": True,
        "section_heading": heading,
        "rejected_possible_mentions": rejected,
    }



STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
GANJI_RE = re.compile(rf"([{STEMS}][{BRANCHES}])")

KOREAN_STEMS = {
    "갑": "甲", "을": "乙", "병": "丙", "정": "丁", "무": "戊",
    "기": "己", "경": "庚", "신": "辛", "임": "壬", "계": "癸",
}
KOREAN_BRANCHES = {
    "자": "子", "축": "丑", "인": "寅", "묘": "卯", "진": "辰",
    "사": "巳", "오": "午", "미": "未", "신": "申", "유": "酉",
    "술": "戌", "해": "亥",
}
PILLAR_LABELS = {
    "year": ("연주", "년주", "생년"),
    "month": ("월주", "생월"),
    "day": ("일주", "생일"),
    "hour": ("시주", "생시"),
}
PILLAR_KEYS = ("year", "month", "day", "hour")



NETWORK_PILLAR_KEY_ALIASES = {
    "year": {
        "yearpillar", "year_pillar", "yearganji", "year_ganji",
        "yearcolumn", "year_column", "생년", "년주", "연주",
    },
    "month": {
        "monthpillar", "month_pillar", "monthganji", "month_ganji",
        "monthcolumn", "month_column", "생월", "월주",
    },
    "day": {
        "daypillar", "day_pillar", "dayganji", "day_ganji",
        "daycolumn", "day_column", "생일", "일주",
    },
    "hour": {
        "hourpillar", "hour_pillar", "hourganji", "hour_ganji",
        "timepillar", "time_pillar", "생시", "시주",
    },
}


def _normalize_network_key(value: object) -> str:
    return re.sub(
        r"[^0-9a-zA-Z가-힣_]",
        "",
        str(value),
    ).lower()


def _parse_network_ganji(
    value: object,
) -> str | None:
    """
    Network JSON의 다음 형태를 모두 간지 한 쌍으로 변환한다.

    - "甲戌"
    - "갑술"
    - {"stem": "甲", "branch": "戌"}
    - {"천간": "甲", "지지": "戌"}
    """
    if isinstance(value, str):
        compact = re.sub(r"\s+", "", value)

        match = GANJI_RE.search(compact)
        if match:
            return match.group(1)

        korean_match = re.search(
            r"(갑|을|병|정|무|기|경|신|임|계)"
            r"(자|축|인|묘|진|사|오|미|신|유|술|해)",
            compact,
        )
        if korean_match:
            return (
                KOREAN_STEMS[korean_match.group(1)]
                + KOREAN_BRANCHES[korean_match.group(2)]
            )

    if isinstance(value, dict):
        normalized = {
            _normalize_network_key(key): item
            for key, item in value.items()
        }

        stem_aliases = {
            "stem",
            "heavenlystem",
            "heavenly_stem",
            "gan",
            "cheongan",
            "천간",
        }
        branch_aliases = {
            "branch",
            "earthlybranch",
            "earthly_branch",
            "ji",
            "jiji",
            "지지",
        }

        stem_value = next(
            (
                normalized[key]
                for key in stem_aliases
                if key in normalized
            ),
            None,
        )
        branch_value = next(
            (
                normalized[key]
                for key in branch_aliases
                if key in normalized
            ),
            None,
        )

        if isinstance(stem_value, str) and isinstance(
            branch_value,
            str,
        ):
            stem = stem_value.strip()
            branch = branch_value.strip()

            if stem in STEMS and branch in BRANCHES:
                return stem + branch

            if (
                stem in KOREAN_STEMS
                and branch in KOREAN_BRANCHES
            ):
                return (
                    KOREAN_STEMS[stem]
                    + KOREAN_BRANCHES[branch]
                )

    return None


def _find_pillars_in_network_object(
    node: object,
) -> dict[str, str] | None:
    """
    네트워크 JSON을 재귀 순회하되, 연·월·일·시 역할이 명시된
    객체만 원국으로 인정한다. 단순 간지 배열은 오탐 위험 때문에
    사용하지 않는다.
    """
    if isinstance(node, dict):
        normalized_items = [
            (_normalize_network_key(key), value)
            for key, value in node.items()
        ]

        found: dict[str, str] = {}
        for pillar_name, aliases in (
            NETWORK_PILLAR_KEY_ALIASES.items()
        ):
            for normalized_key, value in normalized_items:
                if normalized_key not in aliases:
                    continue
                parsed = _parse_network_ganji(value)
                if parsed:
                    found[pillar_name] = parsed
                    break

        if (
            set(found) == set(PILLAR_KEYS)
            and all(_valid_pillar(found[key]) for key in PILLAR_KEYS)
        ):
            return found

        container_aliases = {
            "year": {"year", "생년", "년", "연"},
            "month": {"month", "생월", "월"},
            "day": {"day", "생일", "일"},
            "hour": {"hour", "time", "생시", "시"},
        }
        nested: dict[str, str] = {}

        for pillar_name, aliases in container_aliases.items():
            for normalized_key, value in normalized_items:
                if normalized_key not in aliases:
                    continue
                parsed = _parse_network_ganji(value)
                if parsed:
                    nested[pillar_name] = parsed
                    break

        if (
            set(nested) == set(PILLAR_KEYS)
            and all(_valid_pillar(nested[key]) for key in PILLAR_KEYS)
        ):
            return nested

        for value in node.values():
            result = _find_pillars_in_network_object(value)
            if result is not None:
                return result

    elif isinstance(node, list):
        # 뒤쪽 응답·객체가 실제 계산 결과일 가능성이 높아 역순 검사
        for value in reversed(node):
            result = _find_pillars_in_network_object(value)
            if result is not None:
                return result

    return None


def _extract_network_chart(
    network_data: Any,
) -> dict[str, Any] | None:
    if network_data is None:
        return None

    responses = (
        network_data
        if isinstance(network_data, list)
        else [network_data]
    )

    for response in reversed(responses):
        payload = (
            response.get("payload")
            if isinstance(response, dict)
            and "payload" in response
            else response
        )
        pillars = _find_pillars_in_network_object(payload)
        if pillars is None:
            continue

        return {
            "pillars": pillars,
            "source": "network_json_fallback_pillars",
            "confidence": "medium",
            "evidence": {
                "response_url": (
                    response.get("url", "")
                    if isinstance(response, dict)
                    else ""
                ),
            },
        }

    return None


def _extract_live_chart(
    live_chart_data: Any,
) -> dict[str, Any] | None:
    """
    수집 시 실제 브라우저 DOM의 생시·생일·생월·생년 열에서
    직접 읽어 저장한 live_chart.json을 검증한다.
    """
    if not isinstance(live_chart_data, dict):
        return None
    if not live_chart_data.get("found"):
        return None

    pillar_fields = {
        "year": "year_pillar",
        "month": "month_pillar",
        "day": "day_pillar",
        "hour": "hour_pillar",
    }
    pillars = {
        key: str(live_chart_data.get(field, "")).strip()
        for key, field in pillar_fields.items()
    }

    if not all(
        _valid_pillar(pillars[key])
        for key in PILLAR_KEYS
    ):
        return None

    return {
        "pillars": pillars,
        "source": str(
            live_chart_data.get(
                "source",
                "live_result_table_dom",
            )
        ),
        "confidence": "high",
        "evidence": live_chart_data.get("evidence", {}),
    }


def _valid_pillar(value: str) -> bool:
    return (
        len(value) == 2
        and value[0] in STEMS
        and value[1] in BRANCHES
    )


def _korean_ganji_to_hanja(value: str) -> str | None:
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 2:
        return None
    stem = KOREAN_STEMS.get(compact[0])
    branch = KOREAN_BRANCHES.get(compact[1])
    if not stem or not branch:
        return None
    return stem + branch


def _normalize_pillar_label(value: str) -> str:
    return re.sub(r"[\s:：·ㆍ|/()\[\]{}<>_-]+", "", value)


def _pillar_label_key(value: str) -> str | None:
    compact = _normalize_pillar_label(value)
    for key, aliases in PILLAR_LABELS.items():
        if compact in aliases:
            return key
    return None


def _label_order_in_text(value: str) -> list[str]:
    compact = _normalize_pillar_label(value)
    hits: list[tuple[int, str]] = []
    for key, aliases in PILLAR_LABELS.items():
        positions = [compact.find(alias) for alias in aliases if alias in compact]
        if positions:
            hits.append((min(positions), key))
    hits.sort()
    result: list[str] = []
    for _, key in hits:
        if key not in result:
            result.append(key)
    return result


def _single_ganji(value: str) -> str | None:
    found = list(dict.fromkeys(GANJI_RE.findall(value)))
    if len(found) == 1:
        return found[0]
    if found:
        return None

    # HTML 셀 안에서 천간과 지지가 줄바꿈·공백으로 분리된 경우도
    # 같은 열의 한 기둥으로 안전하게 결합한다.
    stems = list(dict.fromkeys(char for char in value if char in STEMS))
    branches = list(dict.fromkeys(char for char in value if char in BRANCHES))
    if len(stems) == 1 and len(branches) == 1:
        return stems[0] + branches[0]
    return None


def _single_stem(value: str) -> str | None:
    if GANJI_RE.search(value):
        return None
    found = list(dict.fromkeys(char for char in value if char in STEMS))
    return found[0] if len(found) == 1 else None


def _single_branch(value: str) -> str | None:
    if GANJI_RE.search(value):
        return None
    found = list(dict.fromkeys(char for char in value if char in BRANCHES))
    return found[0] if len(found) == 1 else None


class _ChartTableParser(HTMLParser):
    """포스텔러 결과 HTML의 표 셀 순서를 보존한다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "tr":
            self._row = []
        elif lowered in {"th", "td"} and self._row is not None:
            self._cell = []
        elif lowered == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if lowered in {"th", "td"} and self._cell is not None:
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif lowered == "tr" and self._row is not None:
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._cell is not None:
            self._cell.append(data)


def _header_map(row: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, cell in enumerate(row):
        key = _pillar_label_key(cell)
        if key is not None and key not in result:
            result[key] = index
    return result


def _extract_from_table_rows(
    rows: list[list[str]],
    source: str,
) -> dict[str, Any] | None:
    for header_index, header_row in enumerate(rows):
        header = _header_map(header_row)
        if set(header) != set(PILLAR_KEYS):
            continue

        direct: dict[str, str] | None = None
        stem_values: dict[str, str] | None = None
        branch_values: dict[str, str] | None = None

        for row in rows[header_index + 1:header_index + 14]:
            if max(header.values()) >= len(row):
                continue

            combined = {
                key: _single_ganji(row[column])
                for key, column in header.items()
            }
            if all(combined.values()):
                direct = {key: str(value) for key, value in combined.items()}
                break

            stems = {
                key: _single_stem(row[column])
                for key, column in header.items()
            }
            if stem_values is None and all(stems.values()):
                stem_values = {key: str(value) for key, value in stems.items()}
                continue

            branches = {
                key: _single_branch(row[column])
                for key, column in header.items()
            }
            if branch_values is None and all(branches.values()):
                branch_values = {key: str(value) for key, value in branches.items()}

        pillars = direct
        if pillars is None and stem_values and branch_values:
            pillars = {
                key: stem_values[key] + branch_values[key]
                for key in PILLAR_KEYS
            }

        if pillars and all(_valid_pillar(pillars[key]) for key in PILLAR_KEYS):
            return {
                "pillars": pillars,
                "source": source,
                "confidence": "high",
                "evidence": {
                    "header_order": [
                        key
                        for key, _ in sorted(header.items(), key=lambda item: item[1])
                    ],
                    "header_cells": header_row,
                },
            }
    return None


def _extract_html_table(html_text: str) -> dict[str, Any] | None:
    if not html_text.strip():
        return None
    parser = _ChartTableParser()
    try:
        parser.feed(html_text)
    except Exception:
        return None
    return _extract_from_table_rows(parser.rows, "structured_html_table")



KOREAN_STEM_WORD_RE = re.compile(
    r"(갑목|을목|병화|정화|무토|기토|경금|신금|임수|계수)"
)
KOREAN_BRANCH_WORD_RE = re.compile(
    r"(자수|축토|인목|묘목|진토|사화|오화|미토|신금|유금|술토|해수)"
)
KOREAN_STEM_WORDS = {
    "갑목": "甲",
    "을목": "乙",
    "병화": "丙",
    "정화": "丁",
    "무토": "戊",
    "기토": "己",
    "경금": "庚",
    "신금": "辛",
    "임수": "壬",
    "계수": "癸",
}
KOREAN_BRANCH_WORDS = {
    "자수": "子",
    "축토": "丑",
    "인목": "寅",
    "묘목": "卯",
    "진토": "辰",
    "사화": "巳",
    "오화": "午",
    "미토": "未",
    "신금": "申",
    "유금": "酉",
    "술토": "戌",
    "해수": "亥",
}
CHART_SECTION_STOP_WORDS = (
    "사주 풀이 자세히 보기",
    "대운",
    "세운",
    "신살과 길성",
    "오행과 십성",
    "신강/신약",
    "용신",
)


def _ordered_hanja_chars(
    value: str,
    allowed: str,
) -> list[str]:
    return [
        character
        for character in value
        if character in allowed
    ]


def _ordered_stems_from_line(value: str) -> list[str]:
    """
    포스텔러 result.txt의 두 가지 행 표현을 모두 지원한다.

    - 壬 丁 乙 甲
    - 임수 정화 을목 갑목
    """
    hanja = _ordered_hanja_chars(value, STEMS)
    if len(hanja) >= 4:
        return hanja

    return [
        KOREAN_STEM_WORDS[token]
        for token in KOREAN_STEM_WORD_RE.findall(value)
    ]


def _ordered_branches_from_line(value: str) -> list[str]:
    """
    포스텔러 result.txt의 두 가지 행 표현을 모두 지원한다.

    - 寅 卯 亥 戌
    - 인목 묘목 해수 술토
    """
    hanja = _ordered_hanja_chars(value, BRANCHES)
    if len(hanja) >= 4:
        return hanja

    return [
        KOREAN_BRANCH_WORDS[token]
        for token in KOREAN_BRANCH_WORD_RE.findall(value)
    ]


def _ordered_ganji_from_line(value: str) -> list[str]:
    direct = GANJI_RE.findall(value)
    if len(direct) >= 4:
        return direct

    korean = re.findall(
        r"(갑|을|병|정|무|기|경|신|임|계)"
        r"(자|축|인|묘|진|사|오|미|신|유|술|해)",
        value,
    )
    return [
        KOREAN_STEMS[stem] + KOREAN_BRANCHES[branch]
        for stem, branch in korean
    ]


def _chart_window(
    visible_lines: list[str],
    start: int,
    limit: int = 32,
) -> list[str]:
    result: list[str] = []

    for line in visible_lines[start:start + limit]:
        if result and any(
            stop_word in line
            for stop_word in CHART_SECTION_STOP_WORDS
        ):
            break
        result.append(line)

    return result


def _matrix_pillars(
    header_order: list[str],
    data_lines: list[str],
) -> dict[str, str] | None:
    """
    헤더 순서를 보존한 채 4열 행을 읽는다.

    포스텔러의 body.inner_text()는 각 셀을 한 줄씩 내보내기도 하고,
    한 행 전체를 한 줄로 내보내기도 한다. 기존 코드는 전자만 처리해
    후자에서는 원국을 찾지 못했다.
    """
    if len(header_order) != 4:
        return None

    # 1. 네 간지가 한 줄에 직접 있는 형태
    for line in data_lines:
        ganji = _ordered_ganji_from_line(line)
        if len(ganji) == 4:
            pillars = {
                key: ganji[index]
                for index, key in enumerate(header_order)
            }
            if all(
                _valid_pillar(pillars[key])
                for key in PILLAR_KEYS
            ):
                return pillars

    # 2. 천간 4개 행 + 지지 4개 행
    stem_row: list[str] | None = None
    branch_row: list[str] | None = None

    for line in data_lines:
        stems = _ordered_stems_from_line(line)
        if stem_row is None and len(stems) == 4:
            stem_row = stems

        branches = _ordered_branches_from_line(line)
        if branch_row is None and len(branches) == 4:
            branch_row = branches

        if stem_row is not None and branch_row is not None:
            break

    if stem_row is not None and branch_row is not None:
        pillars = {
            key: stem_row[index] + branch_row[index]
            for index, key in enumerate(header_order)
        }
        if all(
            _valid_pillar(pillars[key])
            for key in PILLAR_KEYS
        ):
            return pillars

    # 3. 셀 하나가 한 줄인 형태
    single_ganji = [
        value
        for line in data_lines
        if (value := _single_ganji(line)) is not None
    ]
    if len(single_ganji) >= 4:
        pillars = {
            key: single_ganji[index]
            for index, key in enumerate(header_order)
        }
        if all(
            _valid_pillar(pillars[key])
            for key in PILLAR_KEYS
        ):
            return pillars

    single_stems = [
        value
        for line in data_lines
        if (value := _single_stem(line)) is not None
    ]
    single_branches = [
        value
        for line in data_lines
        if (value := _single_branch(line)) is not None
    ]
    if len(single_stems) >= 4 and len(single_branches) >= 4:
        pillars = {
            key: (
                single_stems[index]
                + single_branches[index]
            )
            for index, key in enumerate(header_order)
        }
        if all(
            _valid_pillar(pillars[key])
            for key in PILLAR_KEYS
        ):
            return pillars

    return None



ROLE_BLOCK_ORDER = ("hour", "day", "month", "year")


def _first_hanja_character(
    lines: list[str],
    allowed: str,
) -> str | None:
    for line in lines:
        for character in line:
            if character in allowed:
                return character
    return None


def _extract_visible_role_blocks(
    visible_lines: list[str],
) -> dict[str, Any] | None:
    """
    실제 포스텔러 result.txt의 기본 원국 배치를 읽는다.

    포스텔러 본문은 다음과 같이 '행렬'이 아니라 역할별 세로 블록으로
    저장될 수 있다.

        생시
        임壬
        +수
        정관
        인寅
        +목
        ...
        생일
        정丁
        ...
        묘卯
        ...
        생월
        을乙
        ...
        해亥
        ...
        생년
        갑甲
        ...
        술戌

    첫 번째 '사주 풀이 자세히 보기' 이전의 원국 영역만 사용하므로
    뒤쪽 궁성·대운·연운·월운의 반복 생시/생일 표를 원국으로 오인하지
    않는다.
    """
    stop_index = len(visible_lines)
    for index, line in enumerate(visible_lines):
        if "사주 풀이 자세히 보기" in line:
            stop_index = index
            break

    chart_lines = visible_lines[:stop_index]
    role_positions: list[tuple[int, str]] = []

    for index, line in enumerate(chart_lines):
        key = _pillar_label_key(line)
        if key is None:
            continue
        if key not in ROLE_BLOCK_ORDER:
            continue
        role_positions.append((index, key))

    # 동일 역할이 여러 번 있더라도 첫 원국 구간에서
    # hour -> day -> month -> year 순서가 연속으로 나타나는 묶음만 채택한다.
    for start in range(len(role_positions)):
        sequence = role_positions[start:start + 4]
        if len(sequence) < 4:
            break
        keys = tuple(key for _, key in sequence)
        if keys != ROLE_BLOCK_ORDER:
            continue

        pillars: dict[str, str] = {}
        evidence_blocks: dict[str, Any] = {}

        for position_index, (line_index, key) in enumerate(sequence):
            next_index = (
                sequence[position_index + 1][0]
                if position_index + 1 < len(sequence)
                else stop_index
            )
            block = chart_lines[line_index + 1:next_index]

            stem = _first_hanja_character(block, STEMS)
            branch = _first_hanja_character(block, BRANCHES)
            if stem is None or branch is None:
                break

            pillar = stem + branch
            if not _valid_pillar(pillar):
                break

            pillars[key] = pillar
            evidence_blocks[key] = {
                "label_line": line_index,
                "block_preview": block[:12],
                "stem": stem,
                "branch": branch,
                "pillar": pillar,
            }

        if set(pillars) != set(PILLAR_KEYS):
            continue

        return {
            "pillars": pillars,
            "source": "visible_text_role_blocks",
            "confidence": "high",
            "evidence": {
                "role_order": list(ROLE_BLOCK_ORDER),
                "blocks": evidence_blocks,
                "stop_heading": "사주 풀이 자세히 보기",
            },
        }

    return None


def _extract_visible_row_table(
    visible_lines: list[str],
    *,
    source: str = "visible_text_matrix",
) -> dict[str, Any] | None:
    for start in range(len(visible_lines)):
        header_order = _label_order_in_text(
            visible_lines[start]
        )
        data_start = start + 1

        if len(header_order) != 4:
            header_order = []
            header_positions: list[int] = []

            for index in range(
                start,
                min(start + 12, len(visible_lines)),
            ):
                key = _pillar_label_key(
                    visible_lines[index]
                )
                if key is None or key in header_order:
                    continue

                header_order.append(key)
                header_positions.append(index)

                if len(header_order) == 4:
                    data_start = max(header_positions) + 1
                    break

        if set(header_order) != set(PILLAR_KEYS):
            continue

        data_lines = _chart_window(
            visible_lines,
            data_start,
        )
        pillars = _matrix_pillars(
            header_order,
            data_lines,
        )
        if pillars is None:
            continue

        return {
            "pillars": pillars,
            "source": source,
            "confidence": "high",
            "evidence": {
                "header_order": header_order,
                "header_start_line": start,
                "data_preview": data_lines[:12],
            },
        }

    return None


def _extract_explicit_pillars_strict(
    visible_text: str,
    visible_lines: list[str],
) -> dict[str, Any] | None:
    found: dict[str, str] = {}

    # 갑술년·을해월·정묘일·임인시처럼 기둥 역할이 직접 붙은 문장만 우선 인정한다.
    suffix_map = {"년": "year", "월": "month", "일": "day", "시": "hour"}
    for match in re.finditer(
        r"([갑을병정무기경신임계][자축인묘진사오미신유술해])\s*([년월일시])",
        visible_text,
    ):
        converted = _korean_ganji_to_hanja(match.group(1))
        if converted:
            found[suffix_map[match.group(2)]] = converted

    if all(key in found for key in PILLAR_KEYS):
        return {
            "pillars": found,
            "source": "explicit_role_suffix",
            "confidence": "high",
            "evidence": {},
        }

    found = {}
    for line in visible_lines:
        label_keys = _label_order_in_text(line)
        ganji = list(dict.fromkeys(GANJI_RE.findall(line)))

        # 여러 열의 헤더와 여러 간지가 한 줄에 함께 있는 경우 첫 간지를 모든 기둥에
        # 복사하는 기존 오탐을 방지한다.
        if len(label_keys) != 1 or len(ganji) != 1:
            continue
        found[label_keys[0]] = ganji[0]

    if all(key in found for key in PILLAR_KEYS):
        return {
            "pillars": found,
            "source": "strict_explicit_labels",
            "confidence": "medium",
            "evidence": {},
        }
    return None


def _chart_result(result: dict[str, Any]) -> dict[str, Any]:
    pillars = result["pillars"]
    return {
        "found": True,
        "source": result["source"],
        "confidence": result["confidence"],
        "evidence": result.get("evidence", {}),
        "year_pillar": pillars["year"],
        "month_pillar": pillars["month"],
        "day_pillar": pillars["day"],
        "hour_pillar": pillars["hour"],
    }


def _pillar_signature(result: dict[str, Any]) -> tuple[str, str, str, str]:
    pillars = result["pillars"]
    return tuple(str(pillars[key]) for key in PILLAR_KEYS)


def _chart_source_record(result: dict[str, Any]) -> dict[str, Any]:
    pillars = result["pillars"]
    return {
        "source": result.get("source", ""),
        "confidence": result.get("confidence", ""),
        "year_pillar": pillars["year"],
        "month_pillar": pillars["month"],
        "day_pillar": pillars["day"],
        "hour_pillar": pillars["hour"],
    }


def _extract_forceteller_chart(
    visible_text: str,
    visible_lines: list[str],
    html_text: str,
    network_data: Any = None,
    live_chart_data: Any = None,
) -> dict[str, Any]:
    """
    원국은 현재 대운·연운·월운이 아니라 출생 사주 네 기둥이어야 한다.

    가장 신뢰할 수 있는 원본은 result.txt의 첫 번째
    '사주 풀이 자세히 보기' 이전 생시·생일·생월·생년 세로 블록이다.
    network.json에는 현재 연운/월운 또는 달력 데이터도 함께 들어올 수
    있으므로 화면 원국을 덮어쓰는 최종 원본으로 사용하지 않는다.
    """
    source_specs = (
        (
            "visible_text_role_blocks",
            lambda: _extract_visible_role_blocks(visible_lines),
        ),
        (
            "visible_text_matrix",
            lambda: _extract_visible_row_table(
                visible_lines,
                source="visible_text_matrix",
            ),
        ),
        (
            "html_plain_text_matrix",
            lambda: _extract_visible_row_table(
                _clean_lines(_html_to_text(html_text)),
                source="html_plain_text_matrix",
            ),
        ),
        (
            "structured_html_table",
            lambda: _extract_html_table(html_text),
        ),
        (
            "live_result_table_dom",
            lambda: _extract_live_chart(live_chart_data),
        ),
        (
            "explicit_role_labels",
            lambda: _extract_explicit_pillars_strict(
                visible_text,
                visible_lines,
            ),
        ),
        (
            "network_json_fallback_pillars",
            lambda: _extract_network_chart(network_data),
        ),
    )

    attempts: list[str] = []
    candidates: list[dict[str, Any]] = []

    for name, extractor in source_specs:
        try:
            result = extractor()
        except Exception:
            result = None
        if result is None:
            attempts.append(name)
            continue
        if not all(
            _valid_pillar(str(result["pillars"].get(key, "")))
            for key in PILLAR_KEYS
        ):
            attempts.append(name)
            continue
        candidates.append(result)

    if not candidates:
        return {
            "found": False,
            "source": "",
            "confidence": "none",
            "attempts": attempts,
            "warning": (
                "포스텔러 결과 화면은 열렸지만 출생 원국 네 기둥을 "
                "확정하지 못했습니다."
            ),
        }

    role_block = next(
        (
            item
            for item in candidates
            if item.get("source") == "visible_text_role_blocks"
        ),
        None,
    )

    if role_block is not None:
        selected = role_block
    else:
        grouped: dict[
            tuple[str, str, str, str],
            list[dict[str, Any]],
        ] = {}
        for item in candidates:
            grouped.setdefault(
                _pillar_signature(item),
                [],
            ).append(item)

        priority = {
            name: index
            for index, (name, _) in enumerate(source_specs)
        }
        selected_group = max(
            grouped.values(),
            key=lambda group: (
                len(group),
                -min(
                    priority.get(
                        str(item.get("source", "")),
                        999,
                    )
                    for item in group
                ),
            ),
        )
        selected = min(
            selected_group,
            key=lambda item: priority.get(
                str(item.get("source", "")),
                999,
            ),
        )

    selected_signature = _pillar_signature(selected)
    conflicts = [
        _chart_source_record(item)
        for item in candidates
        if _pillar_signature(item) != selected_signature
    ]

    result = _chart_result(selected)
    evidence = dict(result.get("evidence", {}))
    evidence["source_candidates"] = [
        _chart_source_record(item)
        for item in candidates
    ]
    evidence["conflicts"] = conflicts
    evidence["selection_policy"] = (
        "출생 원국 세로 블록 우선; 없으면 소스 합의; "
        "network.json은 최후 fallback"
    )
    result["evidence"] = evidence

    if conflicts:
        result["warning"] = (
            "일부 보조 소스가 출생 원국과 달랐으나 "
            f"{result['source']} 값을 최종 원국으로 채택했습니다."
        )

    return result


SCORING_ELEMENT_MAP = {
    "목": "木",
    "화": "火",
    "토": "土",
    "금": "金",
    "수": "水",
    "木": "木",
    "火": "火",
    "土": "土",
    "金": "金",
    "水": "水",
}


def _extract_forceteller_scoring_context(
    visible_text: str,
    sections: dict[str, Any],
) -> dict[str, Any]:
    """포스텔러가 화면에 표시한 오행 비율·강약·용신을 구조화한다."""
    element_percent: dict[str, float] = {}
    element_pattern = re.compile(
        r"([목화토금수])\s*\(\s*([木火土金水])\s*\)\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*%"
    )
    for korean, hanja, raw_value in element_pattern.findall(visible_text):
        element = SCORING_ELEMENT_MAP.get(hanja) or SCORING_ELEMENT_MAP[korean]
        element_percent[element] = float(raw_value)

    if len(element_percent) != 5:
        element_percent = {}
    elif not 98.0 <= sum(element_percent.values()) <= 102.0:
        element_percent = {}

    strength_text = str(
        (sections.get("strength") or {}).get("text", "")
    )
    strength_label = ""
    for label in (
        "극신강", "중화신강", "중화신약", "극신약", "신강", "신약", "중화",
    ):
        if label in strength_text:
            strength_label = label
            break

    useful_text = str(
        (sections.get("useful_god") or {}).get("text", "")
    )
    useful_elements: list[str] = []
    for token in re.findall(
        r"([목화토금수木火土金水])\s*\([^)]*용신[^)]*\)",
        useful_text,
    ):
        element = SCORING_ELEMENT_MAP[token]
        if element not in useful_elements:
            useful_elements.append(element)

    return {
        "element_percent": element_percent,
        "element_source": (
            "forceteller_display_percent"
            if element_percent
            else "pillar_simple"
        ),
        "strength_label": strength_label,
        "useful_elements": useful_elements,
    }

def chart_from_facts(facts: dict[str, Any]):
    chart_data = facts.get("chart") if isinstance(facts, dict) else None
    if not isinstance(chart_data, dict) or not chart_data.get("found"):
        return None
    if chart_data.get("confidence") not in {"high", "medium"}:
        return None

    required = (
        "year_pillar",
        "month_pillar",
        "day_pillar",
        "hour_pillar",
    )
    if not all(
        _valid_pillar(str(chart_data.get(key, "")))
        for key in required
    ):
        return None

    try:
        from bazi_engine import build_chart_from_pillars

        chart = build_chart_from_pillars(
            str(chart_data["year_pillar"]),
            str(chart_data["month_pillar"]),
            str(chart_data["day_pillar"]),
            str(chart_data["hour_pillar"]),
        )
        context = facts.get("scoring_context") or {}
        percentages = context.get("element_percent") or {}
        if isinstance(percentages, dict) and len(percentages) == 5:
            chart.element_percent = {
                element: float(percentages.get(element, 0.0))
                for element in ("木", "火", "土", "金", "水")
            }
            chart.element_source = str(
                context.get(
                    "element_source",
                    "forceteller_display_percent",
                )
            )
        chart.useful_elements = list(
            context.get("useful_elements", [])
        )
        chart.strength_label = str(
            context.get("strength_label", "")
        )
        return chart
    except (KeyError, TypeError, ValueError):
        return None


def parse_forceteller_sources(
    visible_text: str,
    html_text: str = "",
    network_data: Any = None,
    live_chart_data: Any = None,
) -> dict[str, Any]:
    """
    일반 섹션은 수집 원본을 함께 참고하되, 신살·길성은 오탐 방지를 위해
    result.txt의 실제 보이는 '신살과 길성' 섹션만 사용한다.
    """
    visible_lines = _clean_lines(visible_text)

    html_plain = _html_to_text(html_text) if html_text else ""
    network_strings: list[str] = []
    if network_data is not None:
        _flatten_relevant_network_strings(
            network_data,
            network_strings,
        )

    combined_lines = _clean_lines(
        "\n".join(
            part
            for part in (
                visible_text,
                html_plain,
                "\n".join(network_strings),
            )
            if part
        )
    )

    sections = {
        key: _extract_section(combined_lines, aliases)
        for key, aliases in SECTION_DEFINITIONS.items()
        if key != "special_stars"
    }

    special_section_lines, special_heading = (
        _visible_special_star_section(visible_lines)
    )
    sections["special_stars"] = {
        "found": bool(special_section_lines),
        "title": (
            special_heading
            or SECTION_DEFINITIONS["special_stars"][0]
        ),
        "text": "\n".join(special_section_lines)[
            : SETTINGS.forceteller_section_max_chars
        ],
    }

    special_stars, verification = (
        _extract_special_stars_strict(visible_lines)
    )
    scoring_context = _extract_forceteller_scoring_context(
        visible_text,
        sections,
    )
    chart = _extract_forceteller_chart(
        visible_text,
        visible_lines,
        html_text,
        network_data=network_data,
        live_chart_data=live_chart_data,
    )

    return {
        "parser_version": SETTINGS.parser_version,
        "parsed_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "source_policy": (
            "신살·길성은 result.txt에서 실제로 보이는 신살과 길성 "
            "섹션의 개별 항목만 추출함. HTML 숨김 텍스트와 "
            "network.json의 전체 명칭 목록은 신살 판정에 사용하지 않음."
        ),
        "sections": sections,
        "chart": chart,
        "scoring_context": scoring_context,
        "special_stars": special_stars,
        "special_star_verification": verification,
        "summary": {
            "chart_found": bool(chart.get("found")),
            "special_star_count": len(special_stars),
            "verified_special_star_count": sum(
                1
                for item in special_stars
                if item.get("verified") is True
            ),
            "section_count": sum(
                1
                for section in sections.values()
                if section["found"]
            ),
        },
    }


def ensure_forceteller_facts(
    candidate_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    기존 수집 파일만으로 forceteller_facts.json을 생성한다.
    브라우저 재수집이나 OpenAI 호출은 발생하지 않는다.
    """
    facts_path = candidate_path / "forceteller_facts.json"
    existing = read_json(facts_path)

    def existing_chart_is_usable(
        value: object,
    ) -> bool:
        if not isinstance(value, dict):
            return False

        chart = value.get("chart")
        if not isinstance(chart, dict):
            return False
        if not chart.get("found"):
            return False
        if chart.get("confidence") not in {"high", "medium"}:
            return False

        return all(
            _valid_pillar(
                str(chart.get(field, ""))
            )
            for field in (
                "year_pillar",
                "month_pillar",
                "day_pillar",
                "hour_pillar",
            )
        )

    if (
        not force
        and isinstance(existing, dict)
        and existing.get("parser_version")
        == SETTINGS.parser_version
        and existing_chart_is_usable(existing)
    ):
        return existing

    text_path = candidate_path / "result.txt"
    html_path = candidate_path / "result.html"
    network_path = candidate_path / "network.json"
    live_chart_path = candidate_path / "live_chart.json"

    visible_text = (
        text_path.read_text(encoding="utf-8", errors="ignore")
        if text_path.exists()
        else ""
    )
    html_text = (
        html_path.read_text(encoding="utf-8", errors="ignore")
        if html_path.exists()
        else ""
    )
    network_data = (
        read_json(network_path)
        if network_path.exists()
        else None
    )
    live_chart_data = (
        read_json(live_chart_path)
        if live_chart_path.exists()
        else None
    )

    facts = parse_forceteller_sources(
        visible_text=visible_text,
        html_text=html_text,
        network_data=network_data,
        live_chart_data=live_chart_data,
    )
    write_json(facts_path, facts)
    return facts


def compact_facts_for_ai(
    facts: dict[str, Any],
) -> dict[str, Any]:
    """
    API 비용을 줄이기 위해 HTML 표시용 전체 facts 중 핵심만 압축한다.
    """
    sections = facts.get("sections", {}) if isinstance(facts, dict) else {}
    compact_sections: dict[str, str] = {}

    for key in (
        "strength",
        "useful_god",
        "special_stars",
        "five_elements_ten_gods",
    ):
        section = sections.get(key) or {}
        text = str(section.get("text", "")).strip()
        if text:
            compact_sections[key] = text[: SETTINGS.forceteller_ai_section_chars]

    compact_stars = []
    for item in facts.get("special_stars", [])[: SETTINGS.forceteller_ai_max_special_stars]:
        compact_stars.append(
            {
                "name": item.get("name", ""),
                "group": item.get("group", ""),
                "plain_meaning": str(item.get("plain_meaning", ""))[
                    : SETTINGS.forceteller_ai_star_meaning_chars
                ],
                "source_excerpt": str(item.get("source_excerpt", ""))[
                    : SETTINGS.forceteller_ai_star_excerpt_chars
                ],
            }
        )

    chart = facts.get("chart", {}) if isinstance(facts, dict) else {}
    compact_chart = {
        key: chart.get(key, "")
        for key in (
            "year_pillar",
            "month_pillar",
            "day_pillar",
            "hour_pillar",
        )
        if chart.get(key)
    }

    return {
        "chart": compact_chart,
        "scoring_context": facts.get("scoring_context", {}),
        "sections": compact_sections,
        "special_stars": compact_stars,
    }
