from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from bazi_engine import profile_to_solar
from calendar_labels import (
    western_zodiac_basis,
    western_zodiac_from_date,
    zodiac_basis,
    zodiac_from_year_pillar,
)
from config import SETTINGS
from forceteller_parser import ensure_forceteller_facts
from models import AITop10Report, BirthProfile, Candidate, Chart
from storage import profile_dir, project_dir, read_json
from validation import validate_candidate_directory


STEM_READING = {
    "甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무",
    "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계",
}
BRANCH_READING = {
    "子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진",
    "巳": "사", "午": "오", "未": "미", "申": "신", "酉": "유",
    "戌": "술", "亥": "해",
}
ELEMENT_NAME = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}
STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}
ELEMENT_CLASS = {
    "木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water",
}
CERTAINTY_KO = {"high": "높음", "medium": "보통", "limited": "제한적"}


def _pillar_reading(pillar: str) -> str:
    if len(pillar) < 2:
        return pillar
    return (
        STEM_READING.get(pillar[0], pillar[0])
        + BRANCH_READING.get(pillar[1], pillar[1])
    )


def _full_age(born: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - born.year - (
        (today.month, today.day) < (born.month, born.day)
    )


def _age_gap(user_born: date, candidate_born: date) -> str:
    gap = user_born.year - candidate_born.year
    if gap > 0:
        return f"출생연도 기준 {gap}세 연상"
    if gap < 0:
        return f"출생연도 기준 {-gap}세 연하"
    return "출생연도 기준 동갑"


def _profile_solar_date(profile: BirthProfile) -> date:
    solar = profile_to_solar(profile)
    return date(solar.getYear(), solar.getMonth(), solar.getDay())



def _effective_candidate_chart(candidate: Candidate) -> Chart:
    return candidate.forceteller_chart or candidate.chart


def _chart_verification_html(candidate: Candidate) -> str:
    if candidate.forceteller_chart is None:
        return (
            '<p class="chart-verification warning">'
            '포스텔러 원국이 아직 확인되지 않았습니다.'
            '</p>'
        )
    if not candidate.chart_difference:
        audit = candidate.local_calculation_audit
        adjusted = html.escape(str(audit.get("adjusted_datetime", "")))
        correction = html.escape(
            str(audit.get("total_correction_minutes", ""))
        )
        audit_note = (
            f" · 보정 시각 {adjusted} · 위치 보정 {correction}분"
            if adjusted
            else ""
        )
        return (
            '<p class="chart-verification matched">'
            '로컬 계산 원국과 포스텔러 원국의 연·월·일·시주가 모두 '
            '일치했습니다.'
            + audit_note
            + '</p>'
        )
    items = "".join(
        f"<li>{html.escape(value)}</li>"
        for value in candidate.chart_difference
    )
    return (
        '<div class="chart-verification different">'
        '<strong>로컬 예선과 포스텔러 원국 차이</strong>'
        '<p>이 후보는 엄격 검증 모드에서 보고서 생성 대상이 될 수 없습니다.</p>'
        f'<ul>{items}</ul>'
        '</div>'
    )


def _chart_verification_markdown(candidate: Candidate) -> list[str]:
    if candidate.forceteller_chart is None:
        return ["- 원국 확인: 포스텔러 미확인"]
    if not candidate.chart_difference:
        return ["- 원국 확인: 로컬 예선 원국과 포스텔러 원국 일치"]
    return [
        "- 원국 확인: 로컬 예선과 포스텔러 원국에 차이가 있으며, "
        "최종 해설은 포스텔러 원국 기준",
        *[f"  - {value}" for value in candidate.chart_difference],
    ]


def _source_note(candidate: Candidate) -> tuple[str, str]:
    """
    기술적인 '수집되지 않음' 대신 사용자가 이해할 수 있는 분석 자료 설명을 반환한다.
    """
    if not candidate.data_dir or not Path(candidate.data_dir).exists():
        return (
            "포스텔러 미확인",
            "이 후보는 포스텔러 상세 자료가 아직 확인되지 않았습니다.",
        )

    quality = validate_candidate_directory(Path(candidate.data_dir))
    if quality.valid:
        return (
            "포스텔러 확인 완료",
            "포스텔러 원국과 본문을 확인해 상세 분석했습니다. 로컬 계산은 TOP 10 예선에만 사용했습니다.",
        )

    return (
        "포스텔러 일부 확인",
        "포스텔러 결과 일부가 불완전해 상세 해석 범위가 제한됩니다.",
    )


def _symbol(value: str, element_map: dict[str, str]) -> str:
    element = element_map.get(value, "")
    reading = STEM_READING.get(value, BRANCH_READING.get(value, value))
    css_class = ELEMENT_CLASS.get(element, "")
    return (
        f'<div class="symbol {css_class}">{html.escape(value)}</div>'
        f'<div class="reading">{html.escape(reading)} · '
        f'{html.escape(ELEMENT_NAME.get(element, element))}</div>'
    )


def _chart_html(title: str, chart: Chart) -> str:
    pillars = {
        "hour": chart.hour_pillar,
        "day": chart.day_pillar,
        "month": chart.month_pillar,
        "year": chart.year_pillar,
    }
    order = [
        ("hour", "시주"),
        ("day", "일주"),
        ("month", "월주"),
        ("year", "연주"),
    ]

    heads = "".join(f"<th>{label}</th>" for _, label in order)
    stems = "".join(
        f"<td>{_symbol(pillars[key][0], STEM_ELEMENT)}</td>"
        for key, _ in order
    )
    branches = "".join(
        f"<td>{_symbol(pillars[key][1], BRANCH_ELEMENT)}</td>"
        for key, _ in order
    )
    readings = "".join(
        f"<td>{_pillar_reading(pillars[key])}<br>"
        f'<span class="hanja">{pillars[key]}</span></td>'
        for key, _ in order
    )

    return f"""
<section class="chart-panel">
  <h2>{html.escape(title)}</h2>
  <table class="four-pillars">
    <thead><tr><th></th>{heads}</tr></thead>
    <tbody>
      <tr>
        <th>천간<br><small>겉으로 드러나는 기운</small></th>
        {stems}
      </tr>
      <tr>
        <th>지지<br><small>바탕과 생활 기운</small></th>
        {branches}
      </tr>
      <tr><th>기둥 읽기</th>{readings}</tr>
    </tbody>
  </table>
  <div class="chart-notes">
    <span><b>일간:</b> {STEM_READING.get(chart.day_master)}({chart.day_master})
    — 기본 기질의 중심 기운</span>
    <span><b>배우자궁:</b> {BRANCH_READING.get(chart.spouse_palace)}
    ({chart.spouse_palace}) — 연애·배우자 관계를 보는 일지</span>
  </div>
</section>
"""


def _person_info_html(
    born: date,
    year_pillar: str,
    user_born: date | None = None,
) -> str:
    zodiac = zodiac_from_year_pillar(year_pillar)
    sign = western_zodiac_from_date(born)
    values = [
        f"<span><b>만 나이:</b> {_full_age(born)}세</span>",
        f"<span><b>띠:</b> {html.escape(zodiac)} "
        f"<small>({html.escape(zodiac_basis(year_pillar))})</small></span>",
        f"<span><b>별자리:</b> {html.escape(sign)} "
        f"<small>({html.escape(western_zodiac_basis(born))})</small></span>",
    ]
    if user_born is not None:
        values.append(
            f"<span><b>나이 차이:</b> {_age_gap(user_born, born)}</span>"
        )
    return '<div class="person-info">' + "".join(values) + "</div>"


def _same_date_alternatives(
    selected: Candidate,
    limit: int = 3,
) -> list[dict[str, object]]:
    alternatives = list(selected.alternate_times or [])
    alternatives.sort(
        key=lambda item: float(item.get("local_score", 0.0)),
        reverse=True,
    )
    return alternatives[:limit]


def _alternatives_html(selected: Candidate) -> str:
    alternatives = _same_date_alternatives(selected)
    if not alternatives:
        return ""

    rows = []
    for item in alternatives:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('birth_time', '')))}</td>"
            f"<td>{html.escape(str(item.get('time_label', '')))}</td>"
            f"<td>{html.escape(str(item.get('hour_pillar', '')))}</td>"
            f"<td>{float(item.get('local_score', 0.0)):.1f}</td>"
            f"<td>{float(item.get('difference_from_best', 0.0)):+.1f}</td>"
            "</tr>"
        )

    return f"""
<section class="alternate-times">
  <h3>같은 생일의 다른 시주 참고</h3>
  <p>
    이 날짜는 12시진을 모두 계산한 뒤 가장 점수가 높은 시주 1개만
    공식 후보로 선정했습니다. 아래 시주들은 포스텔러 수집과 AI 순위에서는
    제외하고 로컬 점수 차이만 참고로 보여줍니다.
  </p>
  <div class="time-stability">
    <span><b>상위 3개 시주 평균:</b> {selected.time_top3_average:.1f}</span>
    <span><b>최고·최저 시주 차이:</b> {selected.time_score_range:.1f}</span>
  </div>
  <div class="table-scroll">
  <table>
    <thead>
      <tr>
        <th>출생시간</th><th>시진</th><th>시주</th>
        <th>로컬 점수</th><th>대표 후보 대비</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</section>
"""


def _markdown_alternatives(selected: Candidate) -> list[str]:
    alternatives = _same_date_alternatives(selected)
    if not alternatives:
        return []

    result = [
        "",
        "### 같은 생일의 다른 시주 참고",
        "",
        "> 12시진을 모두 계산한 뒤 최고점 시주 1개만 공식 후보로 선정했습니다.",
        "",
        f"- 상위 3개 시주 평균: {selected.time_top3_average:.1f}",
        f"- 최고·최저 시주 점수 차이: {selected.time_score_range:.1f}",
        "",
        "|출생시간|시진|시주|로컬 점수|대표 후보 대비|",
        "|---|---|---|---:|---:|",
    ]
    for item in alternatives:
        result.append(
            f"|{item.get('birth_time', '')}|{item.get('time_label', '')}|"
            f"{item.get('hour_pillar', '')}|"
            f"{float(item.get('local_score', 0.0)):.1f}|"
            f"{float(item.get('difference_from_best', 0.0)):+.1f}|"
        )
    return result


def _candidate_facts(candidate: Candidate) -> dict:
    if not candidate.data_dir:
        return {}
    path = Path(candidate.data_dir)
    if not path.exists():
        return {}
    return ensure_forceteller_facts(path)


def _user_facts(profile: BirthProfile) -> dict:
    manifest = read_json(
        profile_dir(profile) / "forceteller_profile.json"
    )
    if not isinstance(manifest, dict):
        return {}

    data_dir = str(manifest.get("data_dir", "")).strip()
    if not data_dir:
        return {}

    path = Path(data_dir)
    if not path.exists():
        return {}

    return ensure_forceteller_facts(path)


def _short_star_meaning(value: object, max_chars: int = 105) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return "전통 명리에서 참고하는 보조 기운입니다."

    # 장황한 일반 경고 문구는 카드마다 반복하지 않고 공통 안내로 이동한다.
    text = re.sub(
        r"\s*(불륜이나 바람기를 뜻한다고 단정하지 않습니다|"
        r"사고나 불행을 단정하는 항목이 아닙니다|"
        r"단독으로 성격이나 궁합을 결정하지 않습니다)\.?",
        "",
        text,
    ).strip()

    first_sentence = re.split(r"(?<=[.!?다요])\s+", text, maxsplit=1)[0]
    selected = first_sentence or text
    if len(selected) > max_chars:
        selected = selected[: max_chars - 1].rstrip() + "…"
    return selected



def _chart_source_audit_html(
    chart: Chart,
    facts: dict,
) -> str:
    chart_meta = facts.get("chart", {}) if isinstance(facts, dict) else {}
    source = str(chart_meta.get("source", "포스텔러 결과"))
    confidence = str(chart_meta.get("confidence", ""))
    pillars = (
        f"연주 {chart.year_pillar} · 월주 {chart.month_pillar} · "
        f"일주 {chart.day_pillar} · 시주 {chart.hour_pillar}"
    )
    return (
        '<p class="chart-source-audit">'
        '<b>원국 검증:</b> '
        + html.escape(pillars)
        + ' / 파싱 근거 '
        + html.escape(source)
        + (f' / 신뢰도 {html.escape(confidence)}' if confidence else '')
        + '</p>'
    )


def _special_stars_markdown(
    title: str,
    facts: dict,
    *,
    missing_message: str = "",
) -> list[str]:
    stars = list(facts.get("special_stars", [])) if facts else []
    if not stars:
        if not missing_message:
            return []
        return ["", f"### {title}", "", f"> {missing_message}"]

    result = ["", f"### {title}", ""]
    for star in stars:
        result.append(
            f"- **{star.get('name', '')}**: "
            f"{_short_star_meaning(star.get('plain_meaning', ''))}"
        )
    result.extend([
        "",
        "> 신살·길성은 실제로 확인된 항목만 표시하며, "
        "사주 전체를 보완해서 보는 참고 정보입니다.",
    ])
    return result


def _special_stars_html(
    title: str,
    facts: dict,
    *,
    owner: str,
    missing_message: str = "",
) -> str:
    stars = list(facts.get("special_stars", [])) if facts else []

    if not stars:
        if not missing_message:
            return ""
        return f"""
<section class="special-stars compact empty {html.escape(owner)}">
  <div class="section-title-row">
    <h3>{html.escape(title)}</h3>
  </div>
  <p class="empty-guide">{html.escape(missing_message)}</p>
</section>
"""

    items = []
    for star in stars:
        tone = html.escape(str(star.get("tone", "neutral")))
        items.append(
            f"""
<li class="star-item {tone}">
  <strong>{html.escape(str(star.get('name', '')))}</strong>
  <span>{html.escape(_short_star_meaning(star.get('plain_meaning', '')))}</span>
</li>
"""
        )

    return f"""
<section class="special-stars compact {html.escape(owner)}">
  <div class="section-title-row">
    <h3>{html.escape(title)}</h3>
    <span class="count-badge">{len(stars)}개</span>
  </div>
  <ul class="compact-star-list">{''.join(items)}</ul>
  <p class="micro-guide">
    실제 포스텔러 원문에서 확인된 항목만 표시했습니다.
    신살·길성 하나만으로 성격이나 관계를 단정하지 않습니다.
  </p>
</section>
"""



def _honorific_name(name: str) -> str:
    cleaned = str(name or "").strip() or "사용자"
    return cleaned if cleaned.endswith("님") else f"{cleaned}님"


def _candidate_label(rank: int) -> str:
    return f"{rank}순위 후보"


def _personalize_text(
    value: object,
    profile: BirthProfile,
    rank: int,
) -> str:
    """
    기존 AI 캐시에도 실제 이름과 순위 호칭을 적용한다.
    API를 다시 호출하지 않고 render만 실행해도 반영된다.
    """
    text = str(value or "")
    user_name = _honorific_name(profile.name)
    candidate_name = _candidate_label(rank)

    user_replacements = (
        ("사용자와", f"{user_name}과"),
        ("사용자가", f"{user_name}이"),
        ("사용자는", f"{user_name}은"),
        ("사용자의", f"{user_name}의"),
        ("사용자에게", f"{user_name}에게"),
        ("사용자를", f"{user_name}을"),
        ("사용자", user_name),
        ("나와", f"{user_name}과"),
        ("나에게", f"{user_name}에게"),
        ("나를", f"{user_name}을"),
        ("나의", f"{user_name}의"),
    )
    for old, new in user_replacements:
        text = text.replace(old, new)

    candidate_replacements = (
        ("이 후보와", f"{candidate_name}와"),
        ("이 후보가", f"{candidate_name}가"),
        ("이 후보는", f"{candidate_name}는"),
        ("이 후보의", f"{candidate_name}의"),
        ("이 후보", candidate_name),
        ("해당 후보와", f"{candidate_name}와"),
        ("해당 후보가", f"{candidate_name}가"),
        ("해당 후보는", f"{candidate_name}는"),
        ("해당 후보의", f"{candidate_name}의"),
        ("해당 후보", candidate_name),
        ("후보와", f"{candidate_name}와"),
        ("후보가", f"{candidate_name}가"),
        ("후보는", f"{candidate_name}는"),
        ("후보의", f"{candidate_name}의"),
        ("후보에게", f"{candidate_name}에게"),
        ("후보를", f"{candidate_name}를"),
    )
    for old, new in candidate_replacements:
        text = text.replace(old, new)

    return text


def _sentence_points(value: object) -> list[str]:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return []

    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]
    return parts or [text]


def _readable_prose_html(
    value: object,
    profile: BirthProfile,
    rank: int,
    *,
    max_items: int = 6,
) -> str:
    personalized = _personalize_text(
        value,
        profile,
        rank,
    )
    points = _sentence_points(personalized)

    if not points:
        return '<p class="empty-text">표시할 내용이 없습니다.</p>'

    if len(points) > max_items:
        points = points[: max_items - 1] + [
            " ".join(points[max_items - 1:])
        ]

    lead = html.escape(points[0])
    if len(points) == 1:
        return f'<p class="lead-prose">{lead}</p>'

    items = "".join(
        f"<li>{html.escape(point)}</li>"
        for point in points[1:]
    )
    return (
        f'<p class="lead-prose">{lead}</p>'
        f'<ul class="prose-points">{items}</ul>'
    )


def _quick_glance_html(
    item,
    profile: BirthProfile,
    rank: int,
    certainty: str,
) -> str:
    strengths = [
        _personalize_text(value, profile, rank)
        for value in item.strengths
    ]
    risks = [
        _personalize_text(value, profile, rank)
        for value in item.risks
    ]
    best = strengths[0] if strengths else "상세 분석에서 확인"
    caution = risks[0] if risks else "상세 분석에서 확인"

    return f"""
<section class="quick-glance">
  <article>
    <span>관계 유형</span>
    <strong>{html.escape(item.candidate_type)}</strong>
  </article>
  <article class="positive">
    <span>대표 장점</span>
    <strong>{html.escape(best)}</strong>
  </article>
  <article class="caution">
    <span>대표 주의점</span>
    <strong>{html.escape(caution)}</strong>
  </article>
  <article>
    <span>해석 확실성</span>
    <strong>{html.escape(certainty)}</strong>
  </article>
</section>
"""


def write_ai_reports(
    profile: BirthProfile,
    user_chart: Chart,
    report: AITop10Report,
    top10: list[Candidate],
    all_candidates: list[Candidate] | None = None,
) -> tuple[Path, Path]:
    root = project_dir(profile)
    md_path = root / "top10_ai_report.md"
    html_path = root / "top10_ai_report.html"

    candidate_map = {candidate.candidate_id: candidate for candidate in top10}
    user_born = _profile_solar_date(profile)

    md = [
        f"# {report.title}",
        "",
        f"## {_honorific_name(profile.name)}의 사주 원국",
        "",
        f"- 양력 생년월일: {user_born.isoformat()}",
        f"- 만 나이: {_full_age(user_born)}세",
        f"- 띠: {zodiac_from_year_pillar(user_chart.year_pillar)} "
        f"({zodiac_basis(user_chart.year_pillar)})",
        f"- 별자리: {western_zodiac_from_date(user_born)} "
        f"({western_zodiac_basis(user_born)})",
        f"- 연주: {_pillar_reading(user_chart.year_pillar)}"
        f"({user_chart.year_pillar})",
        f"- 월주: {_pillar_reading(user_chart.month_pillar)}"
        f"({user_chart.month_pillar})",
        f"- 일주: {_pillar_reading(user_chart.day_pillar)}"
        f"({user_chart.day_pillar})",
        f"- 시주: {_pillar_reading(user_chart.hour_pillar)}"
        f"({user_chart.hour_pillar})",
        *_special_stars_markdown(
            f"{_honorific_name(profile.name)}의 신살·길성",
            _user_facts(profile),
            missing_message=(
                f"{_honorific_name(profile.name)}의 포스텔러 신살·길성 "
        "자료가 아직 없습니다. "
                "`python app.py local` 실행 시 포스텔러에서 확인됩니다."
            ),
        ),
        "",
        "## TOP 10 비교표",
        "",
        "> 각 생년월일의 12시진을 모두 계산한 뒤 최고점 시주 1개만 공식 후보로 선정했습니다. "
        "나머지 시주는 각 후보 아래 참고표에서 확인할 수 있습니다.",
        "",
        "|순위|생년월일시|나이|띠|별자리|구조 점수|해석 확실성|유형|",
        "|---:|---|---:|---|---|---:|---|---|",
    ]

    rows: list[str] = []
    cards: list[str] = []
    nav_links: list[str] = []

    for item in report.candidates:
        candidate = candidate_map[item.candidate_id]
        born = date.fromisoformat(candidate.birth_date)
        certainty = CERTAINTY_KO.get(
            item.interpretation_certainty,
            item.interpretation_certainty,
        )
        source_label, source_note = _source_note(candidate)

        md.append(
            f"|{item.rank}|{candidate.birth_date} {candidate.birth_time}|"
            f"{_full_age(born)}세|"
            f"{zodiac_from_year_pillar(_effective_candidate_chart(candidate).year_pillar)}|"
            f"{western_zodiac_from_date(born)}|"
            f"{item.ai_score:.1f}|{certainty}|{item.candidate_type}|"
        )

        md.extend([
            "",
            f"## {_candidate_label(item.rank)} — {candidate.birth_date} "
            f"{candidate.birth_time} ({candidate.time_label})",
            "",
            f"- 만 나이: {_full_age(born)}세 ({_age_gap(user_born, born)})",
            f"- 띠: {zodiac_from_year_pillar(_effective_candidate_chart(candidate).year_pillar)} "
            f"({zodiac_basis(_effective_candidate_chart(candidate).year_pillar)})",
            f"- 별자리: {western_zodiac_from_date(born)} "
            f"({western_zodiac_basis(born)})",
            f"- 로컬 구조 점수: {candidate.local_score:.1f} / 1000",
            f"- 로컬 구조점수: {item.ai_score:.1f} / 100",
            f"- 분석 자료: {source_label} — {source_note}",
            f"- 해석 확실성: {certainty} — {item.certainty_reason}",
            f"- 유형: {item.candidate_type}",
        ])
        md.extend(_chart_verification_markdown(candidate))
        md.extend(
            _special_stars_markdown(
                f"{_candidate_label(item.rank)}의 신살·길성",
                _candidate_facts(candidate),
            )
        )
        md.extend([
            "",
            f"### 한눈에 보는 요약\n{_personalize_text(item.summary, profile, item.rank)}",
            "",
            f"### 상대의 기본 성향 — 사주·띠·별자리 종합\n"
            f"{_personalize_text(item.candidate_personality, profile, item.rank)}",
            "",
            f"### 띠와 별자리로 보는 보조 성향\n"
            f"{_personalize_text(item.zodiac_and_sign_reading, profile, item.rank)}",
            "",
            f"### 감정 표현과 애정 방식\n"
            f"{_personalize_text(item.emotional_and_affection_style, profile, item.rank)}",
            "",
            f"### 대화와 문제 해결 방식\n{_personalize_text(item.communication_style, profile, item.rank)}",
            "",
            f"### 나와 만났을 때 나타날 관계 모습 — 종합 궁합\n"
            f"{_personalize_text(item.relationship_fit, profile, item.rank)}",
            "",
            f"### 갈등이 생길 수 있는 지점\n{_personalize_text(item.conflict_pattern, profile, item.rank)}",
            "",
            f"### 일상생활에서의 궁합\n{_personalize_text(item.daily_life_compatibility, profile, item.rank)}",
            "",
            f"### 장기 연애·결혼 관점\n{_personalize_text(item.long_term_outlook, profile, item.rank)}",
            "",
            "### 이 관계의 장점",
        ])
        md.extend(
    f"- {_personalize_text(value, profile, item.rank)}"
    for value in item.strengths
)
        md.append("\n### 주의할 점")
        md.extend(
    f"- {_personalize_text(value, profile, item.rank)}"
    for value in item.risks
)
        md.append("\n### 해석의 핵심 근거")
        md.extend(f"- {value}" for value in item.evidence)
        md.append("\n### 실제 만남에서 확인할 부분")
        md.extend(f"- {value}" for value in item.reality_checks)
        md.append("\n### 용어 풀이")
        md.extend(f"- {value}" for value in item.term_explanations)
        md.extend([
            "",
            f"### 이 순위가 된 이유\n{_personalize_text(item.comparison_reason, profile, item.rank)}",
        ])
        md.extend(
            _markdown_alternatives(candidate)
        )

        rows.append(
            "<tr>"
            f"<td>{item.rank}</td>"
            f"<td>{candidate.birth_date} {candidate.birth_time}</td>"
            f"<td>{_full_age(born)}세</td>"
            f"<td>{zodiac_from_year_pillar(_effective_candidate_chart(candidate).year_pillar)}</td>"
            f"<td>{western_zodiac_from_date(born)}</td>"
            f"<td>{item.ai_score:.1f}</td>"
            f"<td>{certainty}</td>"
            f"<td>{html.escape(item.candidate_type)}</td>"
            "</tr>"
        )

        def list_html(values: list[str]) -> str:
            return "".join(
                f"<li>{html.escape(value)}</li>" for value in values
            )

        nav_links.append(
            f'<a href="#candidate-{item.rank}">'
            f'{_candidate_label(item.rank)} · {candidate.birth_date}</a>'
        )

        candidate_name = _candidate_label(item.rank)

        def personalized_list(values: list[str]) -> str:
            return "".join(
                "<li>"
                + html.escape(
                    _personalize_text(
                        value,
                        profile,
                        item.rank,
                    )
                )
                + "</li>"
                for value in values
            )

        cards.append(f"""
<section class="candidate-card" id="candidate-{item.rank}">
  <header class="candidate-heading">
    <div>
      <span class="rank-label">{candidate_name}</span>
      <h2>{candidate.birth_date} {candidate.birth_time}
        <small>({html.escape(candidate.time_label)})</small>
      </h2>
      <p class="candidate-subtitle">
        {_full_age(born)}세 ·
        {html.escape(_age_gap(user_born, born))} ·
        {zodiac_from_year_pillar(_effective_candidate_chart(candidate).year_pillar)} ·
        {western_zodiac_from_date(born)}
      </p>
    </div>
    <div class="score-bubble">
      <strong>{item.ai_score:.1f}</strong>
      <span>로컬 구조점수</span>
    </div>
  </header>

  {_quick_glance_html(
      item,
      profile,
      item.rank,
      certainty,
  )}

  <section class="summary-highlight">
    <span class="section-kicker">핵심 요약</span>
    <h3>{candidate_name}와의 관계를 먼저 보면</h3>
    {_readable_prose_html(
        item.summary,
        profile,
        item.rank,
        max_items=5,
    )}
  </section>

  <div class="section-divider">
    <span>01</span>
    <div>
      <h3>{candidate_name}의 성격과 기질</h3>
      <p>기본 성향, 감정 표현, 대화 방식을 나누어 봅니다.</p>
    </div>
  </div>

  <div class="insight-grid three">
    <article class="insight-card personality">
      <span class="section-kicker">성격·기질</span>
      <h3>기본 성향</h3>
      {_readable_prose_html(
          item.candidate_personality,
          profile,
          item.rank,
      )}
    </article>
    <article class="insight-card affection">
      <span class="section-kicker">감정·애정</span>
      <h3>애정 표현 방식</h3>
      {_readable_prose_html(
          item.emotional_and_affection_style,
          profile,
          item.rank,
      )}
    </article>
    <article class="insight-card communication">
      <span class="section-kicker">대화·소통</span>
      <h3>문제 해결 방식</h3>
      {_readable_prose_html(
          item.communication_style,
          profile,
          item.rank,
      )}
    </article>
  </div>

  <details class="secondary-details">
    <summary>띠와 별자리로 덧붙여 보는 보조 성향</summary>
    <div>
      {_readable_prose_html(
          item.zodiac_and_sign_reading,
          profile,
          item.rank,
          max_items=5,
      )}
    </div>
  </details>

  <div class="section-divider">
    <span>02</span>
    <div>
      <h3>{_honorific_name(profile.name)}과 {candidate_name}의 궁합</h3>
      <p>잘 맞는 부분과 갈등 가능성을 실제 관계 장면 중심으로 봅니다.</p>
    </div>
  </div>

  <div class="relationship-grid">
    <article class="relation-card fit">
      <span class="relation-icon">+</span>
      <div>
        <span class="section-kicker">잘 맞는 부분</span>
        <h3>함께 있을 때 편해질 수 있는 점</h3>
        {_readable_prose_html(
            item.relationship_fit,
            profile,
            item.rank,
        )}
      </div>
    </article>
    <article class="relation-card conflict">
      <span class="relation-icon">!</span>
      <div>
        <span class="section-kicker">주의할 부분</span>
        <h3>갈등이 생기기 쉬운 지점</h3>
        {_readable_prose_html(
            item.conflict_pattern,
            profile,
            item.rank,
        )}
      </div>
    </article>
  </div>

  <div class="pros-cons">
    <section class="list-card pros">
      <h3>이 관계의 장점</h3>
      <ul>{personalized_list(item.strengths)}</ul>
    </section>
    <section class="list-card cons">
      <h3>주의할 점</h3>
      <ul>{personalized_list(item.risks)}</ul>
    </section>
  </div>

  <div class="section-divider">
    <span>03</span>
    <div>
      <h3>실제로 연애할 때</h3>
      <p>연락·약속·생활 리듬과 장기 관계를 구분해 봅니다.</p>
    </div>
  </div>

  <div class="insight-grid two">
    <article class="insight-card daily">
      <span class="section-kicker">일상 궁합</span>
      <h3>연락·약속·생활 리듬</h3>
      {_readable_prose_html(
          item.daily_life_compatibility,
          profile,
          item.rank,
      )}
    </article>
    <article class="insight-card longterm">
      <span class="section-kicker">장기 궁합</span>
      <h3>장기 연애·결혼 관점</h3>
      {_readable_prose_html(
          item.long_term_outlook,
          profile,
          item.rank,
      )}
    </article>
  </div>

  <details class="profile-details">
    <summary>{candidate_name}의 포스텔러 원국·신살·길성 보기</summary>
    <div class="profile-details-body">
      <div class="profile-layout">
        {_chart_html(
            f"{candidate_name}의 포스텔러 원국",
            _effective_candidate_chart(candidate),
        )}
        {_special_stars_html(
            f"{candidate_name}의 신살·길성",
            _candidate_facts(candidate),
            owner="candidate",
        )}
      </div>
      {_chart_source_audit_html(
          _effective_candidate_chart(candidate),
          _candidate_facts(candidate),
      )}
      {_chart_verification_html(candidate)}

      <div class="meta-strip">
        <span><b>로컬 구조 점수</b>{candidate.local_score:.1f}/1000</span>
        <span><b>분석 자료</b>{html.escape(source_label)}</span>
        <span><b>해석 확실성</b>{html.escape(certainty)}</span>
        <span><b>관계 유형</b>{html.escape(item.candidate_type)}</span>
      </div>

      <div class="note-grid">
        <p><b>자료 기준</b>{html.escape(source_note)}</p>
        <p><b>확실성 기준</b>{html.escape(item.certainty_reason)}</p>
      </div>
    </div>
  </details>

  <details class="supporting-details">
    <summary>판단 근거·실제 확인 항목·명리 용어 풀이</summary>
    <div class="detail-columns">
      <section>
        <h3>해석의 핵심 근거</h3>
        <ul>{personalized_list(item.evidence)}</ul>
      </section>
      <section>
        <h3>실제 만남에서 확인할 부분</h3>
        <ul>{personalized_list(item.reality_checks)}</ul>
      </section>
      <section>
        <h3>용어 풀이</h3>
        <ul>{personalized_list(item.term_explanations)}</ul>
      </section>
    </div>
  </details>

  <section class="ranking-reason">
    <span class="section-kicker">순위 근거</span>
    <h3>{candidate_name}가 이 순위에 놓인 이유</h3>
    {_readable_prose_html(
        item.comparison_reason,
        profile,
        item.rank,
        max_items=5,
    )}
  </section>

  {_alternatives_html(candidate)}
</section>
""")

    md.extend(["", "## 전체 주의사항"])
    md.extend(f"- {value}" for value in report.overall_cautions)
    md_path.write_text("\n".join(md), encoding="utf-8")

    css = """
:root {
  --bg: #f3f1ed;
  --paper: #ffffff;
  --ink: #2b2927;
  --muted: #6f6861;
  --line: #e5dfd7;
  --soft: #f8f5f0;
  --accent: #8a6752;
  --accent-soft: #f2e8df;
  --good: #3f7f65;
  --good-soft: #edf7f1;
  --warn: #b06b36;
  --warn-soft: #fff4e8;
  --blue: #4f718c;
  --blue-soft: #edf4f8;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: "Pretendard", "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
  max-width: 1240px;
  margin: auto;
  padding: 34px;
  background:
    radial-gradient(circle at top left, #fff9f2 0, transparent 34%),
    var(--bg);
  color: var(--ink);
  font-size: 16.5px;
  line-height: 1.85;
  word-break: keep-all;
}
h1, h2, h3 { line-height: 1.35; letter-spacing: -0.025em; }
p { margin: 8px 0 0; color: #3d3935; }
a { color: inherit; }
.page-header,
.compare,
.candidate-card {
  background: var(--paper);
  border: 1px solid rgba(120, 100, 82, .12);
  border-radius: 22px;
  box-shadow: 0 10px 34px rgba(63, 48, 37, .07);
}
.page-header { padding: 30px; margin-bottom: 26px; }
.compare { padding: 26px; margin-bottom: 30px; }
.candidate-card {
  padding: 30px;
  margin-bottom: 34px;
  scroll-margin-top: 20px;
}
.candidate-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}
.candidate-heading h2 { margin: 6px 0 0; font-size: 28px; }
.candidate-heading h2 small {
  display: inline-block;
  color: var(--muted);
  font-size: 15px;
  font-weight: 500;
}
.rank-label,
.section-kicker {
  display: inline-block;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.score-bubble {
  flex: 0 0 102px;
  height: 102px;
  border-radius: 50%;
  background: linear-gradient(145deg, #9a7963, #765340);
  color: white;
  display: grid;
  place-content: center;
  text-align: center;
  box-shadow: 0 10px 22px rgba(117, 80, 58, .2);
}
.score-bubble strong { font-size: 27px; line-height: 1.1; }
.score-bubble span { font-size: 11px; opacity: .86; margin-top: 5px; }
.person-info,
.chart-notes,
.meta-strip {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
}
.person-info span,
.chart-notes span {
  background: var(--soft);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 8px 12px;
  color: #4f4943;
}
.meta-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 18px 0 0;
}
.meta-strip span {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  background: #f7f4ef;
  border-radius: 12px;
}
.meta-strip b { color: var(--muted); font-size: 12px; }
.profile-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(280px, .75fr);
  gap: 18px;
  align-items: start;
  margin-top: 20px;
}
.chart-panel {
  background: #fff;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 16px;
  margin: 0;
}
.chart-panel h2 { margin-top: 0; font-size: 20px; }
table { width: 100%; border-collapse: collapse; }
th, td {
  border: 1px solid var(--line);
  padding: 10px;
  text-align: center;
}
th { background: #f5f2ee; color: #4d4741; }
.table-scroll { overflow-x: auto; }
.symbol {
  font-size: 32px;
  font-weight: 800;
  display: inline-block;
  padding: 5px 13px;
  border-radius: 12px;
}
.reading { font-size: 13px; color: #5f5953; }
.hanja { color: #8a827a; }
.wood { color: #287a8c; background: #e5f4f6; }
.fire { color: #c95555; background: #fdeaea; }
.earth { color: #a97527; background: #fff1ce; }
.metal { color: #626a73; background: #eef0f2; }
.water { color: #4d4e60; background: #ececf2; }

.special-stars {
  background: #fffdf9;
  border: 1px solid #eadfd3;
  border-radius: 16px;
  padding: 18px;
}
.special-stars h3 { margin: 0; font-size: 19px; }
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.count-badge {
  min-width: 38px;
  text-align: center;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}
.compact-star-list {
  list-style: none;
  padding: 0;
  margin: 13px 0 0;
  display: grid;
  gap: 9px;
}
.star-item {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 10px;
  padding: 10px 11px;
  background: white;
  border: 1px solid var(--line);
  border-left-width: 4px;
  border-radius: 10px;
}
.star-item strong { font-size: 14px; }
.star-item span { color: #5b554f; font-size: 13.5px; line-height: 1.55; }
.star-item.positive { border-left-color: var(--good); }
.star-item.accent { border-left-color: #c66d8a; }
.star-item.caution { border-left-color: var(--warn); }
.star-item.neutral { border-left-color: #778490; }
.micro-guide,
.empty-guide {
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.55;
  margin-top: 11px;
}
.note-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.note-grid p {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  background: #fbf8f3;
  border-left: 4px solid #b49a84;
  border-radius: 10px;
  font-size: 14px;
}
.note-grid b { color: var(--accent); }

.summary-highlight,
.ranking-reason {
  margin-top: 22px;
  padding: 22px;
  border-radius: 16px;
}
.summary-highlight {
  background: linear-gradient(135deg, #f5ece4, #fbf7f3);
  border: 1px solid #eadbcf;
}
.summary-highlight h3,
.ranking-reason h3 { margin: 5px 0 6px; font-size: 22px; }

.insight-grid,
.relationship-grid,
.pros-cons,
.detail-columns {
  display: grid;
  gap: 15px;
  margin-top: 16px;
}
.insight-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.insight-grid.two,
.relationship-grid,
.pros-cons { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.insight-card,
.relation-card,
.list-card {
  padding: 19px;
  border: 1px solid var(--line);
  border-radius: 15px;
  background: white;
}
.insight-card h3,
.relation-card h3,
.list-card h3 {
  margin: 5px 0 8px;
  font-size: 19px;
}
.insight-card p,
.relation-card p {
  white-space: pre-line;
}
.insight-card.personality { background: #faf7f2; }
.insight-card.affection { background: #fdf4f6; }
.insight-card.communication { background: #f3f7fa; }
.insight-card.zodiac { margin-top: 15px; background: #f8f6fb; }
.relation-card.fit {
  background: var(--good-soft);
  border-color: #cfe6d9;
}
.relation-card.conflict {
  background: var(--warn-soft);
  border-color: #efd6bc;
}
.list-card ul,
.supporting-details ul { margin: 8px 0 0; padding-left: 21px; }
.list-card li,
.supporting-details li { margin: 7px 0; }
.list-card.pros { background: #f2f9f5; }
.list-card.cons { background: #fff7ef; }

.supporting-details {
  margin-top: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fafafa;
  overflow: hidden;
}
.supporting-details summary {
  cursor: pointer;
  padding: 15px 18px;
  font-weight: 750;
  color: #514a44;
}
.supporting-details[open] summary { border-bottom: 1px solid var(--line); }
.detail-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  padding: 16px;
  margin-top: 0;
}
.detail-columns section {
  padding: 12px;
  background: white;
  border-radius: 10px;
}
.detail-columns h3 { font-size: 16px; margin-top: 0; }
.ranking-reason {
  background: var(--blue-soft);
  border: 1px solid #d1e0e9;
}
.alternate-times {
  margin-top: 20px;
  padding: 18px;
  background: #f4f7fa;
  border-radius: 14px;
}
.time-stability {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.time-stability span {
  background: #e9f0f5;
  padding: 7px 10px;
  border-radius: 8px;
}
.candidate-nav {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 16px 0 20px;
}
.candidate-nav a {
  text-decoration: none;
  padding: 7px 10px;
  border-radius: 999px;
  background: #f3eee8;
  border: 1px solid #e2d8ce;
  font-size: 13px;
}
.candidate-nav a:hover { background: #eaded3; }


.chart-verification {
  margin-top: 13px;
  padding: 11px 13px;
  border-radius: 10px;
  font-size: 13.5px;
}
.chart-verification.matched {
  background: var(--good-soft);
  border-left: 4px solid var(--good);
}
.chart-verification.warning,
.chart-verification.different {
  background: var(--warn-soft);
  border-left: 4px solid var(--warn);
}
.chart-verification.different p { margin: 4px 0; }
.chart-verification.different ul { margin: 7px 0 0; }


.quick-glance {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 11px;
  margin-top: 18px;
}
.quick-glance article {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--soft);
}
.quick-glance article.positive {
  background: var(--good-soft);
  border-color: #cfe6d9;
}
.quick-glance article.caution {
  background: var(--warn-soft);
  border-color: #efd6bc;
}
.quick-glance span {
  display: block;
  margin-bottom: 7px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 750;
}
.quick-glance strong {
  display: block;
  font-size: 14px;
  line-height: 1.55;
}
.candidate-subtitle {
  margin: 7px 0 0;
  color: var(--muted);
  font-size: 14px;
}
.section-divider {
  display: flex;
  align-items: center;
  gap: 13px;
  margin: 28px 0 14px;
  padding-bottom: 11px;
  border-bottom: 2px solid #eee6df;
}
.section-divider > span {
  flex: 0 0 40px;
  height: 40px;
  display: grid;
  place-content: center;
  border-radius: 11px;
  background: var(--accent);
  color: white;
  font-size: 13px;
  font-weight: 800;
}
.section-divider h3 {
  margin: 0;
  font-size: 21px;
}
.section-divider p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.lead-prose {
  margin: 0;
  color: #312d29;
  font-weight: 680;
  line-height: 1.7;
}
.prose-points {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
  display: grid;
  gap: 8px;
}
.prose-points li {
  position: relative;
  padding: 8px 10px 8px 26px;
  border-radius: 9px;
  background: rgba(255, 255, 255, .7);
  color: #504a45;
  line-height: 1.6;
}
.prose-points li::before {
  content: "";
  position: absolute;
  left: 10px;
  top: 18px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #a8846c;
}
.relation-card {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  gap: 12px;
}
.relation-icon {
  width: 35px;
  height: 35px;
  display: grid;
  place-content: center;
  border-radius: 50%;
  color: white;
  font-size: 19px;
  font-weight: 850;
}
.fit .relation-icon { background: var(--good); }
.conflict .relation-icon { background: var(--warn); }
.secondary-details,
.profile-details {
  margin-top: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #faf9f7;
  overflow: hidden;
}
.secondary-details summary,
.profile-details summary {
  cursor: pointer;
  padding: 15px 18px;
  font-weight: 750;
}
.secondary-details > div,
.profile-details-body {
  padding: 17px;
  border-top: 1px solid var(--line);
}
.chart-source-audit {
  margin: 13px 0 0;
  padding: 10px 13px;
  border-left: 4px solid var(--blue);
  border-radius: 9px;
  background: var(--blue-soft);
  color: #4c5963;
  font-size: 13.5px;
}
.solar-time-note {
  margin-top: 13px;
  padding: 10px 13px;
  border-left: 4px solid var(--blue);
  border-radius: 9px;
  background: var(--blue-soft);
  color: #4c5963;
  font-size: 13.5px;
}
.empty-text {
  color: var(--muted);
  font-style: italic;
}

@media (max-width: 980px) {
  .profile-layout,
  .insight-grid.three { grid-template-columns: 1fr; }
  .quick-glance { grid-template-columns: 1fr 1fr; }
  .meta-strip { grid-template-columns: 1fr 1fr; }
  .detail-columns { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  body { padding: 12px; font-size: 16px; }
  .page-header, .compare, .candidate-card { padding: 18px; border-radius: 16px; }
  .candidate-heading { flex-direction: column; }
  .score-bubble { width: 86px; height: 86px; flex-basis: 86px; }
  .insight-grid.two,
  .relationship-grid,
  .pros-cons,
  .note-grid { grid-template-columns: 1fr; }
  .meta-strip { grid-template-columns: 1fr; }
  .quick-glance { grid-template-columns: 1fr; }
  .star-item { grid-template-columns: 76px 1fr; }
}
"""

    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{html.escape(report.title)}</title>
  <style>{css}</style>
</head>
<body>
<header class="page-header">
  <h1>{html.escape(report.title)}</h1>
  {_person_info_html(user_born, user_chart.year_pillar)}
  <div class="profile-layout">
    {_chart_html(
        f"{_honorific_name(profile.name)}의 사주 원국",
        user_chart,
    )}
    {_special_stars_html(
        f"{_honorific_name(profile.name)}의 신살·길성",
        _user_facts(profile),
        owner="user",
        missing_message=(
            f"{_honorific_name(profile.name)}의 포스텔러 신살·길성 "
        "자료가 아직 없습니다. "
            "collect 실행 시 한 번만 수집됩니다."
        ),
    )}
  </div>
  {_chart_source_audit_html(user_chart, _user_facts(profile))}
</header>

<section class="compare">
  <h2>TOP 10 비교표</h2>
  <p>
    각 생년월일의 12시진을 모두 계산한 뒤 최고점 시주 1개만 공식 후보로 선정했습니다.
    같은 생일의 다른 시주는 포스텔러 수집과 AI 순위에서 제외하고 참고표에만 표시합니다.
  </p>
  <nav class="candidate-nav">{''.join(nav_links)}</nav>
  <div class="table-scroll">
  <table>
    <thead>
      <tr>
        <th>순위</th>
        <th>생년월일시</th>
        <th>만 나이</th>
        <th>띠</th>
        <th>별자리</th>
        <th>구조 점수</th>
        <th>해석 확실성</th>
        <th>유형</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</section>

{''.join(cards)}
</body>
</html>
"""
    html_path.write_text(html_doc, encoding="utf-8")
    return md_path, html_path


def write_local_top10_fallback(
    profile: BirthProfile,
    user_chart: Chart,
    candidates: list[Candidate],
    reason: str,
    all_candidates: list[Candidate] | None = None,
) -> tuple[Path, Path]:
    all_candidates = all_candidates or candidates
    root = project_dir(profile)
    md_path = root / "top10_local_fallback.md"
    html_path = root / "top10_local_fallback.html"
    user_born = _profile_solar_date(profile)

    md = [
        "# 로컬 점수 기반 TOP 10 임시 보고서",
        "",
        f"> AI 미생성 사유: {reason}",
        "",
        "> 이 임시 보고서는 포스텔러 상세 해석이 아니라 "
        "로컬 규칙 점수만 보여줍니다.",
    ]
    rows: list[str] = []
    cards: list[str] = []

    for rank, candidate in enumerate(candidates[:10], 1):
        born = date.fromisoformat(candidate.birth_date)
        source_label, source_note = _source_note(candidate)

        md.extend([
            "",
            f"## {rank}위 — {candidate.birth_date} {candidate.birth_time}",
            f"- 만 나이: {_full_age(born)}세 ({_age_gap(user_born, born)})",
            f"- 띠: {zodiac_from_year_pillar(_effective_candidate_chart(candidate).year_pillar)}",
            f"- 별자리: {western_zodiac_from_date(born)}",
            f"- 로컬 점수: {candidate.local_score:.1f}/1000",
            f"- 분석 자료: {source_label} — {source_note}",
        ])
        md.extend(_markdown_alternatives(candidate))

        rows.append(
            "<tr>"
            f"<td>{rank}</td>"
            f"<td>{candidate.birth_date} {candidate.birth_time}</td>"
            f"<td>{_full_age(born)}세</td>"
            f"<td>{zodiac_from_year_pillar(_effective_candidate_chart(candidate).year_pillar)}</td>"
            f"<td>{western_zodiac_from_date(born)}</td>"
            f"<td>{candidate.local_score:.1f}</td>"
            f"<td>{html.escape(source_label)}</td>"
            "</tr>"
        )
        cards.append(f"""
<section class="card">
  <h2>{rank}위 — {candidate.birth_date} {candidate.birth_time}</h2>
  {_person_info_html(born, _effective_candidate_chart(candidate).year_pillar, user_born)}
  {_chart_html("후보 포스텔러 원국", _effective_candidate_chart(candidate))}
  {_special_stars_html(
      "후보의 신살·길성",
      _candidate_facts(candidate),
      owner="candidate",
    )}
  <p><b>로컬 점수:</b> {candidate.local_score:.1f}/1000</p>
  <p><b>분석 자료:</b> {html.escape(source_label)} — {html.escape(source_note)}</p>
  {_alternatives_html(candidate)}
</section>
""")

    md_path.write_text("\n".join(md), encoding="utf-8")
    html_path.write_text(
        f"""<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><title>로컬 TOP 10</title></head>
<body>
<h1>로컬 점수 기반 TOP 10 임시 보고서</h1>
{_person_info_html(user_born, user_chart.year_pillar)}
{_chart_html(
        f"{_honorific_name(profile.name)}의 사주 원국",
        user_chart,
    )}
{_special_stars_html(
  f"{_honorific_name(profile.name)}의 신살·길성",
  _user_facts(profile),
  owner="user",
  missing_message="내 신살·길성 자료가 아직 수집되지 않았습니다.",
)}
<p>{html.escape(reason)}</p>
<table>
<thead>
<tr>
  <th>순위</th><th>생년월일시</th><th>나이</th><th>띠</th>
  <th>별자리</th><th>로컬 점수</th><th>분석 자료</th>
</tr>
</thead>
<tbody>{''.join(rows)}</tbody>
</table>
{''.join(cards)}
</body>
</html>
""",
        encoding="utf-8",
    )
    return md_path, html_path
