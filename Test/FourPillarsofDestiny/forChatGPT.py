
from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from lunar_python import Lunar, Solar

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
ERROR_DIR = OUTPUT_DIR / "errors"
PROFILE_DIR = PROJECT_DIR / ".browser-profile"

ANALYSIS_FILE = OUTPUT_DIR / "for_chatgpt_analysis.json"
TOP10_HTML_FILE = OUTPUT_DIR / "top10_report.html"
LOCAL_RANK_FILE = OUTPUT_DIR / "local_ranked_candidates.json"

FORCETELLER_EDIT_URL = "https://pro.forceteller.com/profile/edit"

OLDER_YEARS = 8
YOUNGER_YEARS = 5
STAGE1_DATE_COUNT = 40
FINAL_CRAWL_COUNT = 30
FINAL_TOP_N = 10
VALID_SCREENSHOT_MIN_BYTES = 15_000

FIXED_LOCATION_TEXT = "서울특별시, 대한민국"
FIXED_LOCATION_ID = "1835848"

DOUBLE_HOURS = [
    ("자시", 0, 30, "子"),
    ("축시", 1, 30, "丑"),
    ("인시", 3, 30, "寅"),
    ("묘시", 5, 30, "卯"),
    ("진시", 7, 30, "辰"),
    ("사시", 9, 30, "巳"),
    ("오시", 11, 30, "午"),
    ("미시", 13, 30, "未"),
    ("신시", 15, 30, "申"),
    ("유시", 17, 30, "酉"),
    ("술시", 19, 30, "戌"),
    ("해시", 21, 30, "亥"),
]

STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}
ELEMENTS = ("木", "火", "土", "金", "水")
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

LIUHE = {
    frozenset(("子", "丑")), frozenset(("寅", "亥")),
    frozenset(("卯", "戌")), frozenset(("辰", "酉")),
    frozenset(("巳", "申")), frozenset(("午", "未")),
}
CHONG = {
    frozenset(("子", "午")), frozenset(("丑", "未")),
    frozenset(("寅", "申")), frozenset(("卯", "酉")),
    frozenset(("辰", "戌")), frozenset(("巳", "亥")),
}
HAI = {
    frozenset(("子", "未")), frozenset(("丑", "午")),
    frozenset(("寅", "巳")), frozenset(("卯", "辰")),
    frozenset(("申", "亥")), frozenset(("酉", "戌")),
}
PO = {
    frozenset(("子", "酉")), frozenset(("丑", "辰")),
    frozenset(("寅", "亥")), frozenset(("卯", "午")),
    frozenset(("巳", "申")), frozenset(("未", "戌")),
}
XING = {
    frozenset(("子", "卯")), frozenset(("寅", "巳")),
    frozenset(("巳", "申")), frozenset(("寅", "申")),
    frozenset(("丑", "戌")), frozenset(("戌", "未")),
    frozenset(("丑", "未")),
}
SANHE = [
    {"申", "子", "辰"},
    {"亥", "卯", "未"},
    {"寅", "午", "戌"},
    {"巳", "酉", "丑"},
]


@dataclass
class BirthInput:
    name: str
    gender: Literal["F", "M"]
    calendar_type: Literal["solar", "lunar"]
    year: int
    month: int
    day: int
    hour: int
    minute: int
    location: str
    partner_gender: Literal["F", "M"]


@dataclass
class Chart:
    year_pillar: str
    month_pillar: str
    day_pillar: str
    hour_pillar: str
    day_master: str
    spouse_palace: str
    stems: list[str]
    branches: list[str]
    element_counts: dict[str, int]
    element_percent: dict[str, float]


@dataclass
class RelationSummary:
    strengths: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    complements: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    candidate_id: str
    birth_date: str
    birth_time: str
    time_label: str
    chart: Chart
    stage1_score: float
    final_local_score: float
    zodiac_score: float
    month_score: float
    relation: RelationSummary
    screenshot_path: str = ""
    screenshot_status: str = "not_requested"
    forceteller_result_url: str = ""
    collection_error: str = ""


def ensure_dirs() -> None:
    for path in (OUTPUT_DIR, SCREENSHOT_DIR, ERROR_DIR, PROFILE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def ask_choice(prompt: str, allowed: set[str], default: str) -> str:
    while True:
        raw = input(f"{prompt} (기본 {default}): ").strip().upper()
        if not raw:
            return default
        if raw in allowed:
            return raw
        print("허용값:", ", ".join(sorted(allowed)))


def ask_int(prompt: str, low: int, high: int, default: int | None = None) -> int:
    while True:
        raw = input(f"{prompt}" + (f" (기본 {default})" if default is not None else "") + ": ").strip()
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
            if low <= value <= high:
                return value
        except ValueError:
            pass
        print(f"{low}~{high} 범위의 정수를 입력하세요.")


def collect_user_input() -> BirthInput:
    print("\n=== 사용자 정보 ===")
    name = input("이름 또는 식별명: ").strip() or "사용자"
    gender = ask_choice("성별 F=여성, M=남성", {"F", "M"}, "F")
    cal = ask_choice("달력 S=양력, L=음력", {"S", "L"}, "S")
    year = ask_int("출생연도", 1900, datetime.now().year)
    month = ask_int("출생월", 1, 12)
    day = ask_int("출생일", 1, calendar.monthrange(year, month)[1])
    hour = ask_int("출생 시", 0, 23, 12)
    minute = ask_int("출생 분", 0, 59, 0)
    location = input(f"출생지 (기본 {FIXED_LOCATION_TEXT}): ").strip() or FIXED_LOCATION_TEXT
    default_partner = "M" if gender == "F" else "F"
    partner = ask_choice("찾는 상대 성별 F/M", {"F", "M"}, default_partner)

    return BirthInput(
        name=name,
        gender=gender,  # type: ignore[arg-type]
        calendar_type="solar" if cal == "S" else "lunar",
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        location=location,
        partner_gender=partner,  # type: ignore[arg-type]
    )


def to_solar(data: BirthInput) -> Solar:
    if data.calendar_type == "solar":
        return Solar.fromYmdHms(data.year, data.month, data.day, data.hour, data.minute, 0)
    lunar = Lunar.fromYmdHms(data.year, data.month, data.day, data.hour, data.minute, 0)
    return lunar.getSolar()


def calculate_chart(year: int, month: int, day: int, hour: int, minute: int) -> Chart:
    eight = Solar.fromYmdHms(year, month, day, hour, minute, 0).getLunar().getEightChar()
    pillars = [eight.getYear(), eight.getMonth(), eight.getDay(), eight.getTime()]
    stems = [p[0] for p in pillars]
    branches = [p[1] for p in pillars]
    counts = {e: 0 for e in ELEMENTS}
    for stem in stems:
        counts[STEM_ELEMENT[stem]] += 1
    for branch in branches:
        counts[BRANCH_ELEMENT[branch]] += 1
    total = sum(counts.values())
    percent = {e: round(counts[e] / total * 100, 1) for e in ELEMENTS}
    return Chart(
        year_pillar=pillars[0],
        month_pillar=pillars[1],
        day_pillar=pillars[2],
        hour_pillar=pillars[3],
        day_master=pillars[2][0],
        spouse_palace=pillars[2][1],
        stems=stems,
        branches=branches,
        element_counts=counts,
        element_percent=percent,
    )


def stem_score(a: str, b: str) -> tuple[float, list[str]]:
    combinations = {
        frozenset(("甲", "己")): "갑기합",
        frozenset(("乙", "庚")): "을경합",
        frozenset(("丙", "辛")): "병신합",
        frozenset(("丁", "壬")): "정임합",
        frozenset(("戊", "癸")): "무계합",
    }
    pair = frozenset((a, b))
    if pair in combinations:
        return 8.0, [combinations[pair]]
    ea, eb = STEM_ELEMENT[a], STEM_ELEMENT[b]
    if GENERATES[eb] == ea:
        return 4.0, ["상대 일간이 사용자 일간을 생함"]
    if GENERATES[ea] == eb:
        return 2.0, ["사용자 일간이 상대 일간을 생함"]
    if CONTROLS[eb] == ea:
        return -2.0, ["상대 일간이 사용자 일간을 극함"]
    if CONTROLS[ea] == eb:
        return -1.0, ["사용자 일간이 상대 일간을 극함"]
    if ea == eb:
        return 1.0, ["일간 오행 동일"]
    return 0.0, []


def zodiac_score(user_branch: str, candidate_branch: str) -> float:
    pair = frozenset((user_branch, candidate_branch))
    score = 0.0
    if pair in LIUHE:
        score += 5
    if any(user_branch in group and candidate_branch in group for group in SANHE):
        score += 4
    if pair in CHONG:
        score -= 4
    if pair in HAI:
        score -= 2
    if pair in XING:
        score -= 2
    return score


def spouse_star_elements(day_master: str, gender: str) -> set[str]:
    dm = STEM_ELEMENT[day_master]
    if gender == "F":
        return {element for element, target in CONTROLS.items() if target == dm}
    return {CONTROLS[dm]}


def analyze_relations(user: Chart, candidate: Chart, gender: str) -> tuple[RelationSummary, float]:
    result = RelationSummary()
    score = 50.0

    value, notes = stem_score(user.day_master, candidate.day_master)
    score += value
    result.strengths.extend(notes)

    pair = frozenset((user.spouse_palace, candidate.spouse_palace))
    if pair in LIUHE:
        score += 18
        result.strengths.append(f"배우자궁 육합 {user.spouse_palace}{candidate.spouse_palace}")
    if pair in CHONG:
        score -= 18
        result.risks.append(f"배우자궁 충 {user.spouse_palace}{candidate.spouse_palace}")
    if pair in HAI:
        score -= 8
        result.risks.append(f"배우자궁 해 {user.spouse_palace}{candidate.spouse_palace}")
    if pair in PO:
        score -= 5
        result.risks.append(f"배우자궁 파 {user.spouse_palace}{candidate.spouse_palace}")
    if pair in XING:
        score -= 8
        result.risks.append(f"배우자궁 형 {user.spouse_palace}{candidate.spouse_palace}")

    for ub in user.branches:
        for cb in candidate.branches:
            pair = frozenset((ub, cb))
            label = f"{ub}{cb}"
            if pair in LIUHE:
                score += 1.5
                result.strengths.append(f"육합 {label}")
            if pair in CHONG:
                score -= 1.8
                result.risks.append(f"충 {label}")
            if pair in HAI:
                score -= 0.8
                result.risks.append(f"해 {label}")
            if pair in PO:
                score -= 0.5
                result.risks.append(f"파 {label}")
            if pair in XING:
                score -= 0.8
                result.risks.append(f"형 {label}")

    combined = set(user.branches + candidate.branches)
    for group in SANHE:
        if group.issubset(combined):
            score += 5
            result.strengths.append("삼합 " + "".join(sorted(group)))

    deficient = sorted(user.element_counts, key=user.element_counts.get)[:2]
    for element in deficient:
        count = candidate.element_counts[element]
        if count:
            add = min(count * 2.5, 7.5)
            score += add
            result.complements.append(f"부족 오행 {element} 보완 +{add:g}")

    max_count = max(user.element_counts.values())
    excessive = {
        e for e, count in user.element_counts.items()
        if count == max_count and count >= 3
    }
    for element in excessive:
        if candidate.element_counts[element] >= 3:
            score -= 4
            result.risks.append(f"과다 오행 {element} 추가 강화")

    spouse_elements = spouse_star_elements(user.day_master, gender)
    spouse_count = sum(candidate.element_counts[e] for e in spouse_elements)
    if spouse_count:
        add = min(spouse_count * 2, 6)
        score += add
        result.complements.append(f"배우자성 오행 {','.join(spouse_elements)} 포함 +{add:g}")

    result.strengths = list(dict.fromkeys(result.strengths))
    result.risks = list(dict.fromkeys(result.risks))
    result.complements = list(dict.fromkeys(result.complements))
    return result, round(max(0, min(100, score)), 1)


def month_score(user: Chart, candidate: Chart) -> float:
    month_element = BRANCH_ELEMENT[candidate.month_pillar[1]]
    user_count = user.element_counts[month_element]
    if user_count == min(user.element_counts.values()):
        return 4.0
    if user_count == max(user.element_counts.values()) and user_count >= 3:
        return -2.0
    return 1.0


def iter_dates(start_year: int, end_year: int):
    for year in range(start_year, end_year + 1):
        current = date(year, 1, 1)
        while current.year == year:
            yield current
            current = date.fromordinal(current.toordinal() + 1)


def build_stage1(user: BirthInput, user_chart: Chart):
    start_year = user.year - OLDER_YEARS
    end_year = user.year + YOUNGER_YEARS
    ranked = []

    print(
        f"\n자동 나이 범위: {start_year}~{end_year}년생 "
        f"(연상 {OLDER_YEARS}세~연하 {YOUNGER_YEARS}세)"
    )
    print("출생월은 제외하지 않고 1~12월 전체를 로컬 계산합니다.")

    for current in iter_dates(start_year, end_year):
        chart = calculate_chart(current.year, current.month, current.day, 12, 0)
        relation, base = analyze_relations(user_chart, chart, user.gender)
        z = zodiac_score(user_chart.year_pillar[1], chart.year_pillar[1])
        m = month_score(user_chart, chart)
        ranked.append((current, round(max(0, min(100, base + z + m)), 1), chart, relation, z, m))

    ranked.sort(key=lambda row: row[1], reverse=True)
    return ranked[:STAGE1_DATE_COUNT]


def expand_times(user: BirthInput, user_chart: Chart, selected_dates) -> list[Candidate]:
    result: list[Candidate] = []
    for current, stage1, _, _, _, _ in selected_dates:
        for label, hour, minute, _ in DOUBLE_HOURS:
            chart = calculate_chart(current.year, current.month, current.day, hour, minute)
            relation, base = analyze_relations(user_chart, chart, user.gender)
            z = zodiac_score(user_chart.year_pillar[1], chart.year_pillar[1])
            m = month_score(user_chart, chart)
            score = round(max(0, min(100, base + z + m)), 1)
            result.append(
                Candidate(
                    candidate_id=f"{current.isoformat()}_{hour:02d}{minute:02d}_{label}",
                    birth_date=current.isoformat(),
                    birth_time=f"{hour:02d}:{minute:02d}",
                    time_label=label,
                    chart=chart,
                    stage1_score=stage1,
                    final_local_score=score,
                    zodiac_score=z,
                    month_score=m,
                    relation=relation,
                )
            )
    result.sort(key=lambda item: item.final_local_score, reverse=True)
    return result


def screenshot_valid(path: Path) -> bool:
    return path.exists() and path.stat().st_size >= VALID_SCREENSHOT_MIN_BYTES


def find_existing_screenshot(candidate: Candidate) -> Path | None:
    """
    동일한 생년월일·시간 조합의 유효한 스크린샷이 이미 있으면 반환한다.

    우선순위
    1. 현재 표준 파일명
       YYYY-MM-DD_HHMM_시진.png
    2. 과거 코드에서 만들었을 수 있는 동일 날짜·시간 파일
       YYYY-MM-DD_HHMM*.png

    파일 크기가 너무 작으면 오류 캡처나 빈 이미지일 수 있으므로
    VALID_SCREENSHOT_MIN_BYTES 이상인 파일만 재사용한다.
    """
    standard = SCREENSHOT_DIR / f"{candidate.candidate_id}.png"

    if screenshot_valid(standard):
        return standard

    date_part = candidate.birth_date
    time_part = candidate.birth_time.replace(":", "")

    for existing in sorted(
        SCREENSHOT_DIR.glob(f"{date_part}_{time_part}*.png")
    ):
        if screenshot_valid(existing):
            return existing

    return None


def close_dialog(page) -> None:
    dialog = page.locator('[role="dialog"]:visible, .MuiDialog-root:visible').last
    if not dialog.count():
        return
    for locator in (
        dialog.get_by_role("button", name=re.compile(r"닫기|close", re.I)).first,
        dialog.locator('button[aria-label*="close" i]').first,
        dialog.locator("button").first,
    ):
        try:
            if locator.count() and locator.is_visible():
                locator.click(force=True, timeout=3_000)
                return
        except Exception:
            pass
    page.keyboard.press("Escape")


def set_gender(page, gender: str) -> None:
    value = "M" if gender == "M" else "F"
    radio = page.locator(f'input[name="gender"][value="{value}"]').first
    if radio.is_checked():
        return
    label = page.locator(f'label:has(input[name="gender"][value="{value}"])').first
    try:
        label.click(timeout=5_000)
    except Exception:
        radio.evaluate("(el) => el.click()")


def fill_input(page, selector: str, value: str) -> None:
    locator = page.locator(selector).first
    locator.click()
    locator.fill(value)
    locator.press("Tab")
    if locator.input_value().strip() != value:
        locator.click()
        locator.press("Control+A")
        locator.type(value, delay=30)
        locator.press("Tab")


def set_seoul(page) -> None:
    visible = page.locator("#locationId").first
    hidden = page.locator('input[type="hidden"][name="locationId"]').first
    if "서울특별시" in visible.input_value() and hidden.input_value().strip():
        return

    visible.click()
    page.wait_for_timeout(300)
    inputs = page.locator('[role="dialog"] input[type="text"], .MuiDialog-root input[type="text"]')
    if not inputs.count():
        raise RuntimeError("도시 검색창을 찾지 못했습니다.")
    search = inputs.last
    search.fill("대한민국")
    buttons = page.locator('[role="dialog"] button:has(svg), .MuiDialog-root button:has(svg)')
    if buttons.count():
        buttons.last.click()
    page.wait_for_timeout(1_000)

    selected = False
    for option in (
        page.get_by_role("option", name=re.compile("서울특별시")).first,
        page.locator('[role="option"]:has-text("서울특별시")').first,
        page.locator('li:has-text("서울특별시")').first,
        page.get_by_text(re.compile("서울특별시"), exact=False).first,
    ):
        try:
            if option.count() and option.is_visible():
                option.click(force=True)
                selected = True
                break
        except Exception:
            pass

    if not selected:
        search.press("ArrowDown")
        search.press("Enter")

    page.wait_for_timeout(400)

    if not hidden.input_value().strip():
        page.evaluate(
            """
            ({textValue, hiddenValue}) => {
                const d = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, "value"
                );
                const t = document.querySelector("#locationId");
                const h = document.querySelector(
                    'input[type="hidden"][name="locationId"]'
                );
                d.set.call(h, hiddenValue);
                h.dispatchEvent(new Event("input", {bubbles:true}));
                h.dispatchEvent(new Event("change", {bubbles:true}));
                if (t) {
                    d.set.call(t, textValue);
                    t.dispatchEvent(new Event("input", {bubbles:true}));
                    t.dispatchEvent(new Event("change", {bubbles:true}));
                }
            }
            """,
            {"textValue": FIXED_LOCATION_TEXT, "hiddenValue": FIXED_LOCATION_ID},
        )
    close_dialog(page)


def wait_enabled(locator, timeout_ms: int = 10_000) -> None:
    end = time.time() + timeout_ms / 1000
    while time.time() < end:
        if locator.is_visible() and locator.is_enabled():
            return
        time.sleep(0.2)
    raise RuntimeError("버튼이 활성화되지 않았습니다.")


def submit_forceteller(page, birth_date: str, birth_time: str) -> None:
    first = page.locator(
        'button[data-event-action="만세력 보러가기"]'
        '[data-event-category="pro_프로필입력"]'
    ).first
    if not first.count():
        first = page.get_by_role("button", name=re.compile(r"만세력\s*보러가기")).first

    wait_enabled(first)
    first.click()
    page.wait_for_url(re.compile("/profile/confirm"), timeout=15_000)

    if page.locator("#birthday").input_value().strip() != birth_date:
        raise RuntimeError("확인 화면 생년월일 불일치")
    if page.locator("#birthtime").input_value().strip() != birth_time:
        raise RuntimeError("확인 화면 출생시간 불일치")

    second = page.locator(
        'button[data-event-action="만세력 보러가기"]'
        '[data-event-category="pro_프로필확인"]'
    )
    second.wait_for(state="visible", timeout=15_000)
    if second.count() != 1:
        raise RuntimeError(f"2차 제출 버튼 {second.count()}개 발견")
    wait_enabled(second)

    try:
        second.click(timeout=8_000)
    except Exception:
        try:
            second.click(force=True, timeout=8_000)
        except Exception:
            second.evaluate("(button) => button.click()")

    page.wait_for_url(re.compile("/result"), timeout=20_000)
    page.wait_for_timeout(800)


def collect_screenshots(user: BirthInput, candidates: list[Candidate]) -> None:
    if sync_playwright is None:
        raise RuntimeError("Playwright가 설치되어 있지 않습니다.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1440, "height": 1100},
            locale="ko-KR",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(FORCETELLER_EDIT_URL, wait_until="domcontentloaded", timeout=60_000)
        print("\n로그인이 필요하면 완료하세요.")
        input("포스텔러 입력 폼이 보이면 Enter: ")

        for index, candidate in enumerate(candidates[:FINAL_CRAWL_COUNT], 1):
            screenshot = SCREENSHOT_DIR / f"{candidate.candidate_id}.png"

            existing_screenshot = find_existing_screenshot(candidate)

            if existing_screenshot is not None:
                candidate.screenshot_path = str(existing_screenshot)
                candidate.screenshot_status = "skipped_existing"

                print(
                    f"[{index}] 기존 스크린샷 존재 - 검색·입력 생략: "
                    f"{candidate.birth_date} {candidate.birth_time} "
                    f"({existing_screenshot.name})"
                )
                continue

            candidate.screenshot_path = str(screenshot)

            try:
                page.goto(FORCETELLER_EDIT_URL, wait_until="domcontentloaded", timeout=30_000)
                page.locator("#name").wait_for(state="visible", timeout=20_000)
                close_dialog(page)
                page.locator("#name").fill(f"후보{index:02d}")
                set_gender(page, user.partner_gender)
                page.locator('select[name="calendar"]').select_option("S")
                fill_input(page, "#birthday", candidate.birth_date.replace("-", "/"))
                fill_input(page, "#birthtime", candidate.birth_time)
                set_seoul(page)
                submit_forceteller(
                    page,
                    candidate.birth_date.replace("-", "/"),
                    candidate.birth_time,
                )
                page.screenshot(path=str(screenshot), full_page=True)
                candidate.screenshot_status = "collected"
                candidate.forceteller_result_url = page.url
                print(f"[{index}] 수집 완료: {candidate.birth_date} {candidate.birth_time}")
            except Exception as exc:
                candidate.screenshot_status = "error"
                candidate.collection_error = f"{type(exc).__name__}: {exc}"
                (ERROR_DIR / f"{candidate.candidate_id}.txt").write_text(
                    candidate.collection_error,
                    encoding="utf-8",
                )
                try:
                    page.screenshot(
                        path=str(ERROR_DIR / f"{candidate.candidate_id}.png"),
                        full_page=True,
                    )
                except Exception:
                    pass
                print(f"[{index}] 오류: {candidate.collection_error}")

        context.close()


def analysis_text(candidate: Candidate) -> dict[str, list[str]]:
    strengths = list(dict.fromkeys(
        candidate.relation.strengths + candidate.relation.complements
    ))[:10] or ["전체 오행 균형으로 점수를 확보한 후보"]
    risks = list(dict.fromkeys(candidate.relation.risks))[:10] or [
        "원국 교차관계에서 두드러진 충·형·해가 적음"
    ]
    checks = [
        "갈등 시 상대를 비하하거나 통제하지 않는지",
        "근거를 확인하고 잘못을 인정할 수 있는지",
        "금전·직업·생활 리듬이 안정적인지",
        "음주·혐오표현·과도한 음모론 성향이 없는지",
        "애정과 책임을 말이 아니라 행동으로 보이는지",
    ]
    return {"strengths": strengths, "risks": risks, "reality_checks": checks}


def write_outputs(user: BirthInput, user_chart: Chart, stage1, candidates: list[Candidate]) -> None:
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": "전통 명리학 기반 참고용 휴리스틱이며 과학적 예측이 아닙니다.",
        "settings": {
            "automatic_age_range": {
                "start_year": user.year - OLDER_YEARS,
                "end_year": user.year + YOUNGER_YEARS,
                "older_years": OLDER_YEARS,
                "younger_years": YOUNGER_YEARS,
            },
            "birth_month_policy": "1~12월 전체 로컬 계산 후 자동 월령 점수 반영",
            "stage1_date_count": STAGE1_DATE_COUNT,
            "final_crawl_count": FINAL_CRAWL_COUNT,
            "final_top_n": FINAL_TOP_N,
        },
        "user": {"input": asdict(user), "chart": asdict(user_chart)},
        "stage1_dates": [
            {
                "date": row[0].isoformat(),
                "score": row[1],
                "chart": asdict(row[2]),
                "relation": asdict(row[3]),
                "zodiac_score": row[4],
                "month_score": row[5],
            }
            for row in stage1
        ],
        "candidates": [
            {**asdict(c), "analysis": analysis_text(c)}
            for c in candidates
        ],
        "top10": [
            {**asdict(c), "analysis": analysis_text(c)}
            for c in candidates[:FINAL_TOP_N]
        ],
    }
    ANALYSIS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOCAL_RANK_FILE.write_text(
        json.dumps([asdict(c) for c in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cards = []
    for rank, candidate in enumerate(candidates[:FINAL_TOP_N], 1):
        analysis = analysis_text(candidate)
        strengths = "".join(f"<li>{html.escape(v)}</li>" for v in analysis["strengths"])
        risks = "".join(f"<li>{html.escape(v)}</li>" for v in analysis["risks"])
        checks = "".join(f"<li>{html.escape(v)}</li>" for v in analysis["reality_checks"])
        chart = candidate.chart
        screenshot_link = ""
        path = Path(candidate.screenshot_path) if candidate.screenshot_path else None
        if path and path.exists():
            relative = path.relative_to(OUTPUT_DIR)
            screenshot_link = f'<p><a href="{html.escape(str(relative))}">포스텔러 스크린샷 열기</a></p>'
        cards.append(f"""
<section class="card">
<h2>{rank}위 — {candidate.birth_date} {candidate.birth_time} ({candidate.time_label})</h2>
<div class="score">{candidate.final_local_score:.1f}점</div>
<table>
<tr><th>연주</th><td>{chart.year_pillar}</td><th>월주</th><td>{chart.month_pillar}</td></tr>
<tr><th>일주</th><td>{chart.day_pillar}</td><th>시주</th><td>{chart.hour_pillar}</td></tr>
<tr><th>일간</th><td>{chart.day_master}</td><th>배우자궁</th><td>{chart.spouse_palace}</td></tr>
<tr><th>띠 가중치</th><td>{candidate.zodiac_score:+.1f}</td><th>월령 점수</th><td>{candidate.month_score:+.1f}</td></tr>
</table>
<h3>잘 맞는 요소</h3><ul>{strengths}</ul>
<h3>갈등 가능성</h3><ul>{risks}</ul>
<h3>현실에서 확인할 항목</h3><ul>{checks}</ul>
<p><b>오행 분포:</b> {html.escape(str(chart.element_percent))}</p>
<p><b>스크린샷 상태:</b> {html.escape(candidate.screenshot_status)}</p>
{screenshot_link}
</section>
""")

    report = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>궁합 후보 TOP 10</title>
<style>
body{{font-family:Arial,"Malgun Gothic",sans-serif;max-width:1000px;margin:auto;padding:32px;background:#f5f5f5;line-height:1.65}}
header,.card{{background:#fff;padding:24px;border-radius:14px;margin-bottom:24px;box-shadow:0 3px 16px #0001}}
.card{{position:relative}}.score{{position:absolute;right:24px;top:24px;font-size:24px;font-weight:bold}}
table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #ddd;padding:9px}}th{{background:#f0f0f0}}
</style></head><body>
<header><h1>{html.escape(user.name)} 기준 사주 궁합 후보 TOP 10</h1>
<p>사용자 원국: {user_chart.year_pillar} · {user_chart.month_pillar} · {user_chart.day_pillar} · {user_chart.hour_pillar}</p>
<p>자동 검색 범위: {user.year - OLDER_YEARS}~{user.year + YOUNGER_YEARS}년생, 1~12월 전체 로컬 계산</p>
<p>전통 명리학적 참고 결과이며 실제 관계에서는 존중·안전·가치관·책임감이 우선합니다.</p></header>
{''.join(cards)}
</body></html>"""
    TOP10_HTML_FILE.write_text(report, encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--crawl", action="store_true")
    group.add_argument("--no-crawl", action="store_true")
    return parser.parse_args()


def main() -> None:
    ensure_dirs()
    args = parse_args()
    user = collect_user_input()
    solar = to_solar(user)
    user_chart = calculate_chart(
        solar.getYear(), solar.getMonth(), solar.getDay(),
        solar.getHour(), solar.getMinute()
    )

    print("\n사용자 원국:", user_chart.year_pillar, user_chart.month_pillar, user_chart.day_pillar, user_chart.hour_pillar)
    print("오행:", user_chart.element_percent)

    print("\n1차 날짜 전수 계산 중...")
    stage1 = build_stage1(user, user_chart)
    print(f"상위 날짜 {len(stage1)}개 선정")

    print("\n12시진 확장 계산 중...")
    candidates = expand_times(user, user_chart, stage1)
    print(f"총 {len(candidates)}개 조합 계산")

    crawl = args.crawl
    if not args.crawl and not args.no_crawl:
        crawl = input(f"상위 {FINAL_CRAWL_COUNT}개를 포스텔러에서 수집할까요? [y/N]: ").strip().lower() in {"y", "yes", "예"}

    if crawl:
        collect_screenshots(user, candidates)

    write_outputs(user, user_chart, stage1, candidates)

    print("\n완료")
    print("ChatGPT 전달용:", ANALYSIS_FILE)
    print("TOP 10 보고서:", TOP10_HTML_FILE)
    print("전체 로컬 순위:", LOCAL_RANK_FILE)


if __name__ == "__main__":
    main()
