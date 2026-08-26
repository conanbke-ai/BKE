from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from bazi_engine import chart_differences, profile_to_solar
from candidate_summary import write_candidate_summary
from config import SETTINGS
from logging_utils import LOGGER
from forceteller_parser import (
    chart_from_facts,
    ensure_forceteller_facts,
)
from models import BirthProfile, Candidate, Chart, ScoreBreakdown
from progress import ProgressTracker
from storage import (
    candidate_dir,
    profile_dir,
    profile_id,
    project_dir,
    read_json,
    write_json,
)
from validation import validate_candidate_directory
from ranking import (
    reorder_with_verified_top10,
    select_verified_final_top10,
    verified_forceteller_candidates,
)
from scoring import score_compatibility

try:
    from playwright.sync_api import BrowserContext, Page, Response, sync_playwright
except ImportError:
    BrowserContext = Any
    Page = Any
    Response = Any
    sync_playwright = None


class PreAIValidationError(RuntimeError):
    """OpenAI 호출 전에 포스텔러 원국 검증이 실패한 경우."""


def _signature(profile: BirthProfile, candidate: Candidate) -> dict[str, Any]:
    """
    전역 원본 캐시는 생년월일시·성별·지역을 기준으로 공유한다.

    candidate_id는 화면 표시용 식별자이므로 캐시 서명에서 제외한다.
    같은 출생정보를 사용자 본인과 후보가 각각 참조해도 재수집하지 않는다.
    """
    return {
        "collector_version": SETTINGS.collector_version,
        "parser_version": SETTINGS.parser_version,
        "birth_date": candidate.birth_date,
        "birth_time": candidate.birth_time,
        "gender": profile.partner_gender,
        "calendar": "solar",
        "location_text": SETTINGS.fixed_location_text,
        "location_id": SETTINGS.fixed_location_id,
    }


def _signature_hash(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable_signature_matches(
    metadata: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    """
    parser_version만 바뀐 기존 캐시는 원본을 다시 수집하지 않고
    result.txt/html/network.json으로 facts 파일을 재생성해 승격한다.
    """
    stable_keys = (
        "birth_date",
        "birth_time",
        "gender",
        "calendar",
        "location_text",
        "location_id",
    )
    return all(metadata.get(key) == expected.get(key) for key in stable_keys)




def _result_name_token(candidate: Candidate) -> str:
    """이름 칸에 넣을 12자 식별자: FT + YYMMDD + HHMM."""
    date_token = candidate.birth_date.replace("-", "")[2:]
    time_token = candidate.birth_time.replace(":", "")
    return f"FT{date_token}{time_token}"


def _result_identity(
    path: Path,
    candidate: Candidate,
) -> dict[str, Any]:
    """저장된 결과가 현재 입력한 생년월일시의 페이지인지 확인한다."""
    text_path = path / "result.txt"
    if not text_path.exists():
        return {
            "valid": False,
            "date_match": False,
            "time_match": False,
            "name_match": False,
            "reason": "result.txt 없음",
        }

    text = text_path.read_text(encoding="utf-8", errors="ignore")
    year, month, day = map(int, candidate.birth_date.split("-"))
    hour, minute = map(int, candidate.birth_time.split(":"))

    date_match = bool(
        re.search(
            rf"(?<!\d){year}\D{{0,4}}0?{month}\D{{0,4}}0?{day}(?!\d)",
            text,
        )
    )
    time_match = bool(
        re.search(
            rf"(?<!\d)0?{hour}\D{{0,3}}{minute:02d}(?!\d)",
            text,
        )
    )
    expected_name = _result_name_token(candidate)
    name_match = expected_name.lower() in text.lower()

    # 새 캐시는 고유 이름 토큰만으로도 날짜·시간을 모두 검증할 수 있다.
    # 과거 캐시는 날짜와 시간이 모두 명시된 경우에 한해 재사용한다.
    valid = name_match or (date_match and time_match)
    return {
        "valid": valid,
        "date_match": date_match,
        "time_match": time_match,
        "name_match": name_match,
        "expected_birth_date": candidate.birth_date,
        "expected_birth_time": candidate.birth_time,
        "expected_name_token": expected_name,
        "reason": "matched" if valid else "입력한 생년월일시와 결과 페이지 식별값 불일치",
    }


def _facts_chart_metadata(facts: dict[str, Any]) -> dict[str, Any]:
    chart = facts.get("chart") if isinstance(facts, dict) else None
    return chart if isinstance(chart, dict) else {}


def _validate_source_chart(
    candidate: Candidate,
    facts: dict[str, Any],
    source_chart: Chart | None,
) -> None:
    """
    포스텔러 원국 자체가 완전하고 신뢰도 있게 파싱됐는지만 검증한다.

    로컬 예선 원국과 다른 것은 수집 실패가 아니다. 차이가 있으면
    포스텔러 원국으로 궁합 점수를 다시 계산하고 최종 순위를 재정렬한다.
    """
    del candidate
    if source_chart is None:
        raise RuntimeError(
            "포스텔러 결과에서 검증 가능한 연주·월주·일주·시주를 "
            "확정하지 못했습니다."
        )

    chart_meta = _facts_chart_metadata(facts)
    if chart_meta.get("confidence") not in {"high", "medium"}:
        raise RuntimeError(
            "포스텔러 원국 파싱 근거의 신뢰도가 충분하지 않습니다."
        )


def _attach_candidate_paths(
    candidate: Candidate,
    path: Path,
    metadata: dict[str, Any],
    status: str,
) -> None:
    candidate.data_dir = str(path)
    candidate.screenshot_path = str(path / "result.png")
    candidate.html_path = str(path / "result.html")
    candidate.text_path = str(path / "result.txt")
    candidate.network_path = str(path / "network.json")
    candidate.metadata_path = str(path / "metadata.json")
    candidate.forceteller_facts_path = str(path / "forceteller_facts.json")
    candidate.collection_status = status
    candidate.result_url = metadata.get("result_url", "")

    facts = ensure_forceteller_facts(path)
    source_chart = chart_from_facts(facts)
    _validate_source_chart(candidate, facts, source_chart)
    assert source_chart is not None
    candidate.forceteller_chart = source_chart
    candidate.chart_source = "forceteller"
    candidate.chart_difference = chart_differences(
        candidate.chart,
        source_chart,
    )


def _rescore_candidate_from_forceteller(
    profile: BirthProfile,
    user_chart: Chart,
    candidate: Candidate,
) -> None:
    source_chart = candidate.forceteller_chart
    if source_chart is None:
        raise RuntimeError(
            f"포스텔러 원국이 없어 재평가할 수 없습니다: "
            f"{candidate.candidate_id}"
        )

    if candidate.prefilter_score <= 0:
        candidate.prefilter_score = candidate.local_score

    score, evidence = score_compatibility(
        user_chart,
        source_chart.year_pillar,
        source_chart.month_pillar,
        source_chart.day_pillar,
        source_chart.hour_pillar,
        profile.gender,
        profile.relationship_mode,
        candidate_chart=source_chart,
    )
    candidate.local_score = score.total
    candidate.selected_time_score = score.total
    candidate.score = score
    candidate.evidence = evidence
    candidate.chart_source = "forceteller_rescored"
    candidate.final_score_source = "forceteller_rescored"
    candidate.forceteller_rescored_at = datetime.now().isoformat(
        timespec="seconds"
    )
    candidate.chart_difference = chart_differences(
        candidate.chart,
        source_chart,
    )


def _candidate_is_verified(candidate: Candidate) -> bool:
    return (
        candidate.forceteller_chart is not None
        and candidate.final_score_source == "forceteller_rescored"
        and bool(candidate.data_dir)
        and Path(candidate.data_dir).exists()
    )



def cache_valid(profile: BirthProfile, candidate: Candidate) -> bool:
    path = candidate_dir(profile, candidate)
    metadata_path = path / "metadata.json"
    metadata = read_json(metadata_path)
    if not metadata:
        return False

    expected_signature = _signature(profile, candidate)
    expected_hash = _signature_hash(expected_signature)

    if metadata.get("signature_hash") != expected_hash:
        # 수집 대상 자체는 같고 파서 버전만 달라진 경우 재크롤링하지 않는다.
        if not _stable_signature_matches(metadata, expected_signature):
            return False

        quality = validate_candidate_directory(path)
        if not quality.valid:
            LOGGER.warning(
                "기존 캐시 승격 불가 %s: %s",
                candidate.candidate_id,
                quality.warnings,
            )
            return False

        identity = _result_identity(path, candidate)
        if not identity["valid"]:
            LOGGER.warning(
                "기존 캐시 결과 식별 실패 %s: %s",
                candidate.candidate_id,
                identity,
            )
            return False

        facts = ensure_forceteller_facts(path, force=True)
        source_chart = chart_from_facts(facts)
        try:
            _validate_source_chart(candidate, facts, source_chart)
        except RuntimeError as exc:
            LOGGER.warning(
                "기존 캐시 원국 검증 실패 %s: %s",
                candidate.candidate_id,
                exc,
            )
            return False

        metadata.update(expected_signature)
        metadata.update(
            {
                "signature_hash": expected_hash,
                "facts_file": "forceteller_facts.json",
                "facts_summary": facts.get("summary", {}),
                "result_identity": identity,
                "chart_source": facts.get("chart", {}).get("source", ""),
                "chart_confidence": facts.get("chart", {}).get("confidence", ""),
                "parser_upgraded_at": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }
        )
        write_json(metadata_path, metadata)
        LOGGER.info(
            "기존 포스텔러 원본을 재사용해 파서만 승격: %s",
            candidate.candidate_id,
        )

    quality = validate_candidate_directory(path)
    if not quality.valid:
        LOGGER.warning(
            "캐시 무효 %s: %s",
            candidate.candidate_id,
            quality.warnings,
        )
        return False

    identity = _result_identity(path, candidate)
    if not identity["valid"]:
        LOGGER.warning(
            "캐시 결과 페이지가 현재 후보와 다름 %s: %s",
            candidate.candidate_id,
            identity,
        )
        return False

    facts = ensure_forceteller_facts(path)
    if not facts:
        LOGGER.warning("포스텔러 facts 생성 실패: %s", candidate.candidate_id)
        return False
    try:
        _validate_source_chart(
            candidate,
            facts,
            chart_from_facts(facts),
        )
    except RuntimeError as exc:
        LOGGER.warning(
            "포스텔러 원국 검증 실패 %s: %s",
            candidate.candidate_id,
            exc,
        )
        return False

    _attach_candidate_paths(
        candidate,
        path,
        metadata,
        "skipped_existing",
    )
    return True



def _chart_summary(chart: Chart) -> dict[str, str]:
    return {
        "year": chart.year_pillar,
        "month": chart.month_pillar,
        "day": chart.day_pillar,
        "hour": chart.hour_pillar,
    }


def _expected_user_solar_birth(
    profile: BirthProfile,
) -> tuple[str, str]:
    solar = profile_to_solar(profile)
    return (
        f"{solar.getYear():04d}-{solar.getMonth():02d}-{solar.getDay():02d}",
        f"{solar.getHour():02d}:{solar.getMinute():02d}",
    )


def validate_top10_before_ai(
    profile: BirthProfile,
    user_chart: Chart,
    candidates: list[Candidate],
) -> dict[str, Any]:
    """
    OpenAI 클라이언트 생성 전에 사용자 원국과 최종 TOP 10의
    포스텔러 원본·재평가 상태를 검증한다.

    로컬 예선 원국과 포스텔러 원국의 차이는 오류가 아니다.
    단, 최종 점수가 포스텔러 원국으로 다시 계산되어 있어야 한다.
    """
    root = project_dir(profile)
    manifest_path = root / "pre_ai_validation.json"
    checked_at = datetime.now().isoformat(timespec="seconds")
    errors: list[str] = []
    candidate_results: list[dict[str, Any]] = []

    if len(candidates) != SETTINGS.ai_top_n:
        errors.append(
            f"검증 후보 수가 {SETTINGS.ai_top_n}명이 아닙니다: "
            f"{len(candidates)}명"
        )

    user_result: dict[str, Any] = {
        "status": "failed",
        "current_chart": _chart_summary(user_chart),
        "source_chart": None,
        "differences": [],
    }
    try:
        expected_date, expected_time = _expected_user_solar_birth(profile)
        manifest = read_json(
            profile_dir(profile) / USER_FORCETELLER_MANIFEST
        )
        if not isinstance(manifest, dict):
            raise RuntimeError("사용자 포스텔러 manifest가 없습니다.")

        manifest_date = str(manifest.get("birth_date", "")).strip()
        manifest_time = str(manifest.get("birth_time", "")).strip()
        if manifest_date != expected_date or manifest_time != expected_time:
            raise RuntimeError(
                "사용자 포스텔러 자료의 생년월일시가 현재 프로필과 "
                f"다릅니다: 예상 {expected_date} {expected_time}, "
                f"저장 {manifest_date} {manifest_time}"
            )

        data_dir = Path(str(manifest.get("data_dir", "")).strip())
        if not data_dir.exists():
            raise RuntimeError("사용자 포스텔러 원본 폴더가 없습니다.")

        quality = validate_candidate_directory(data_dir)
        if not quality.valid:
            raise RuntimeError(
                "사용자 포스텔러 원본 검증 실패: "
                + ", ".join(quality.warnings)
            )

        facts = ensure_forceteller_facts(data_dir)
        source_chart = chart_from_facts(facts)
        if source_chart is None:
            raise RuntimeError(
                "사용자 포스텔러 결과에서 네 기둥을 확정하지 못했습니다."
            )
        if _facts_chart_metadata(facts).get("confidence") not in {
            "high",
            "medium",
        }:
            raise RuntimeError(
                "사용자 포스텔러 원국 파싱 신뢰도가 충분하지 않습니다."
            )

        differences = chart_differences(user_chart, source_chart)
        user_result["source_chart"] = _chart_summary(source_chart)
        user_result["differences"] = differences
        if differences:
            raise RuntimeError(
                "현재 사용자 원국과 저장된 포스텔러 원국이 다릅니다: "
                + "; ".join(differences)
            )
        user_result["status"] = "passed"

    except Exception as exc:
        errors.append(f"사용자 원국 검증 실패: {exc}")
        user_result["error"] = str(exc)

    for rank, candidate in enumerate(candidates, 1):
        result: dict[str, Any] = {
            "rank": rank,
            "candidate_id": candidate.candidate_id,
            "birth_date": candidate.birth_date,
            "birth_time": candidate.birth_time,
            "status": "failed",
            "local_prefilter_chart": _chart_summary(candidate.chart),
            "forceteller_chart": None,
            "chart_difference": [],
            "prefilter_score": candidate.prefilter_score,
            "final_score": candidate.local_score,
            "final_score_source": candidate.final_score_source,
        }
        try:
            if not candidate.data_dir:
                raise RuntimeError("포스텔러 원본 경로가 없습니다.")
            path = Path(candidate.data_dir)
            if not path.exists():
                raise RuntimeError(
                    f"포스텔러 원본 폴더가 없습니다: {path}"
                )

            quality = validate_candidate_directory(path)
            if not quality.valid:
                raise RuntimeError(
                    "포스텔러 원본 파일 검증 실패: "
                    + ", ".join(quality.warnings)
                )

            identity = _result_identity(path, candidate)
            result["result_identity"] = identity
            if not identity["valid"]:
                raise RuntimeError(
                    "포스텔러 결과 페이지가 현재 후보 생년월일시와 "
                    f"일치하지 않습니다: {identity}"
                )

            facts = ensure_forceteller_facts(path)
            source_chart = chart_from_facts(facts)
            _validate_source_chart(candidate, facts, source_chart)
            assert source_chart is not None

            result["forceteller_chart"] = _chart_summary(source_chart)
            result["chart_difference"] = chart_differences(
                candidate.chart,
                source_chart,
            )
            result["chart_confidence"] = (
                _facts_chart_metadata(facts).get("confidence", "")
            )

            if candidate.forceteller_chart is None:
                raise RuntimeError(
                    "후보 객체에 포스텔러 원국이 반영되지 않았습니다."
                )
            if chart_differences(candidate.forceteller_chart, source_chart):
                raise RuntimeError(
                    "후보 객체의 포스텔러 원국과 저장 원본이 다릅니다."
                )
            if candidate.final_score_source != "forceteller_rescored":
                raise RuntimeError(
                    "최종 점수가 포스텔러 원국으로 재계산되지 않았습니다."
                )

            expected_score, _ = score_compatibility(
                user_chart,
                source_chart.year_pillar,
                source_chart.month_pillar,
                source_chart.day_pillar,
                source_chart.hour_pillar,
                profile.gender,
                profile.relationship_mode,
                candidate_chart=source_chart,
            )
            result["recalculated_score"] = expected_score.total
            if abs(expected_score.total - candidate.local_score) > 0.05:
                raise RuntimeError(
                    "저장된 최종 점수와 포스텔러 원국 재계산 점수가 "
                    f"다릅니다: 저장 {candidate.local_score}, "
                    f"재계산 {expected_score.total}"
                )

            candidate.forceteller_chart = source_chart
            candidate.chart_difference = chart_differences(
                candidate.chart,
                source_chart,
            )
            result["status"] = "passed"

        except Exception as exc:
            result["error"] = str(exc)
            errors.append(
                f"{rank}순위 후보({candidate.candidate_id}) 검증 실패: "
                f"{exc}"
            )

        candidate_results.append(result)

    adaptive_manifest = read_json(
        root / "forceteller_adaptive_selection.json"
    )
    if not isinstance(adaptive_manifest, dict):
        errors.append("적응형 포스텔러 후보 선정 결과가 없습니다.")
    elif adaptive_manifest.get("status") != "completed":
        errors.append(
            "적응형 포스텔러 후보 선정이 완료 상태가 아닙니다."
        )
    else:
        expected_ids = list(
            adaptive_manifest.get("final_top10_candidate_ids", [])
        )
        actual_ids = [candidate.candidate_id for candidate in candidates]
        if expected_ids != actual_ids:
            errors.append(
                "AI 입력 후보가 적응형 포스텔러 최종 TOP 10과 다릅니다."
            )

    passed = not errors
    validation_manifest: dict[str, Any] = {
        "checked_at": checked_at,
        "status": "passed" if passed else "failed",
        "api_call_authorized": passed,
        "validation_stage": "before_openai_client_creation",
        "openai_api_called": False,
        "user": user_result,
        "candidates": candidate_results,
        "errors": errors,
    }
    write_json(manifest_path, validation_manifest)

    if not passed:
        raise PreAIValidationError(
            "AI 호출 전 포스텔러 검증에 실패했습니다. "
            "OpenAI API는 호출되지 않았습니다. "
            f"검증 결과: {manifest_path}. "
            + " | ".join(errors)
        )

    LOGGER.info(
        "AI 호출 전 검증 통과: 사용자 원국 + 포스텔러 재평가 TOP %s",
        len(candidates),
    )
    return validation_manifest


def _close_dialog(page: Page) -> None:
    dialogs = page.locator('[role="dialog"]:visible, .MuiDialog-root:visible')
    if not dialogs.count():
        return
    dialog = dialogs.last
    for locator in (
        dialog.get_by_role("button", name=re.compile(r"닫기|close", re.I)).first,
        dialog.locator('button[aria-label*="close" i]').first,
        dialog.locator("button").first,
    ):
        try:
            if locator.count() and locator.is_visible():
                locator.click(force=True, timeout=3_000)
                page.wait_for_timeout(200)
                return
        except Exception:
            pass
    page.keyboard.press("Escape")


def _wait_enabled(locator, timeout_ms: int = 10_000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if locator.is_visible() and locator.is_enabled():
            return
        time.sleep(0.2)
    raise RuntimeError("버튼이 활성화되지 않았습니다.")


def _fill_input(page: Page, selector: str, value: str) -> None:
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=10_000)
    locator.click()
    locator.fill(value)
    locator.press("Tab")
    if locator.input_value().strip() != value:
        locator.click()
        locator.press("Control+A")
        locator.type(value, delay=25)
        locator.press("Tab")
    if locator.input_value().strip() != value:
        raise RuntimeError(f"입력값 반영 실패: {selector}={value}")


def _set_gender(page: Page, gender: str) -> None:
    value = "M" if gender == "M" else "F"
    radio = page.locator(f'input[name="gender"][value="{value}"]').first
    if radio.is_checked():
        return
    label = page.locator(f'label:has(input[name="gender"][value="{value}"])').first
    try:
        label.click(timeout=5_000)
    except Exception:
        radio.evaluate("(el) => el.click()")
    if not radio.is_checked():
        radio.click(force=True)


def _set_calendar_solar(page: Page) -> None:
    select = page.locator('select[name="calendar"]').first
    if select.count():
        select.select_option("S")
        return
    radio = page.locator('input[name="calendar"][value="S"]').first
    if not radio.count():
        radio = page.locator('input[name="calendar"][value="solar"]').first
    if not radio.count():
        raise RuntimeError("양력 선택 요소를 찾지 못했습니다.")
    if not radio.is_checked():
        radio.click(force=True)


def _set_native_input(page: Page, selector: str, value: str) -> None:
    page.evaluate(
        """
        ({selector, value}) => {
            const el = document.querySelector(selector);
            if (!el) throw new Error(`요소 없음: ${selector}`);
            const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
            descriptor.set.call(el, value);
            el.dispatchEvent(new Event("input", {bubbles:true}));
            el.dispatchEvent(new Event("change", {bubbles:true}));
        }
        """,
        {"selector": selector, "value": value},
    )


def _set_seoul(page: Page) -> None:
    # 기존 함수명은 호환을 위해 유지하되 실제 검색어는 설정값을 사용한다.
    location_name = SETTINGS.fixed_location_text.split(",")[0].strip()
    visible = page.locator("#locationId").first
    hidden = page.locator('input[type="hidden"][name="locationId"]').first
    try:
        if location_name in visible.input_value() and hidden.input_value().strip():
            return
    except Exception:
        pass

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
        page.get_by_role("option", name=re.compile(re.escape(location_name))).first,
        page.locator(f'[role="option"]:has-text("{location_name}")').first,
        page.locator(f'li:has-text("{location_name}")').first,
        page.get_by_text(re.compile(re.escape(location_name)), exact=False).first,
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
    page.wait_for_timeout(500)

    if not hidden.input_value().strip():
        _set_native_input(page, 'input[type="hidden"][name="locationId"]', SETTINGS.fixed_location_id)
        try:
            _set_native_input(page, "#locationId", SETTINGS.fixed_location_text)
        except Exception:
            pass
    _close_dialog(page)


def _submit(page: Page, birth_date: str, birth_time: str) -> None:
    first = page.locator(
        'button[data-event-action="만세력 보러가기"]'
        '[data-event-category="pro_프로필입력"]'
    ).first
    if not first.count():
        first = page.get_by_role("button", name=re.compile(r"만세력\s*보러가기")).first
    _wait_enabled(first)
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
    _wait_enabled(second)
    try:
        second.click(timeout=8_000)
    except Exception:
        try:
            second.click(force=True, timeout=8_000)
        except Exception:
            second.evaluate("(button) => button.click()")
    page.wait_for_url(re.compile("/result"), timeout=20_000)
    page.wait_for_timeout(1_000)


def _wait_result_text_stable(
    page: Page,
    *,
    interval_ms: int = 500,
    stable_rounds: int = 3,
    timeout_ms: int = 12_000,
) -> None:
    """
    결과 페이지의 지연 로딩이 끝난 뒤 저장한다.
    신살과 길성 등 아래쪽 섹션이 늦게 렌더링되는 경우를 줄인다.
    """
    deadline = time.time() + timeout_ms / 1000
    previous = ""
    stable = 0

    while time.time() < deadline:
        try:
            current = page.locator("body").inner_text(timeout=3_000)
        except Exception:
            current = ""

        if current and current == previous:
            stable += 1
            if stable >= stable_rounds:
                return
        else:
            stable = 0
            previous = current

        page.wait_for_timeout(interval_ms)



def collect_one(
    page: Page,
    profile: BirthProfile,
    user_chart: Chart | None,
    candidate: Candidate,
    *,
    write_summary: bool = True,
) -> None:
    path = candidate_dir(profile, candidate)
    responses: list[dict[str, Any]] = []

    def on_response(response: Response) -> None:
        try:
            if response.request.resource_type not in {"fetch", "xhr"}:
                return
            if "json" not in response.headers.get("content-type", "").lower():
                return
            responses.append({"url": response.url, "status": response.status, "payload": response.json()})
        except Exception:
            pass

    page.on("response", on_response)
    try:
        page.goto(SETTINGS.forceteller_edit_url, wait_until="domcontentloaded", timeout=30_000)
        page.locator("#name").wait_for(state="visible", timeout=20_000)
        _close_dialog(page)
        page.locator("#name").fill(_result_name_token(candidate))
        _set_gender(page, profile.partner_gender)
        _set_calendar_solar(page)
        _fill_input(page, "#birthday", candidate.birth_date.replace("-", "/"))
        _fill_input(page, "#birthtime", candidate.birth_time)
        _set_seoul(page)
        _submit(page, candidate.birth_date.replace("-", "/"), candidate.birth_time)
        _wait_result_text_stable(page)

        screenshot = path / "result.png"
        html_file = path / "result.html"
        text_file = path / "result.txt"
        network_file = path / "network.json"
        metadata_file = path / "metadata.json"
        facts_file = path / "forceteller_facts.json"

        page.screenshot(path=str(screenshot), full_page=True)
        html_file.write_text(page.locator("#root").inner_html(), encoding="utf-8")
        text_file.write_text(page.locator("body").inner_text(), encoding="utf-8")
        write_json(network_file, responses)

        identity = _result_identity(path, candidate)
        if not identity["valid"]:
            raise RuntimeError(
                "포스텔러 결과 페이지가 입력한 후보와 일치하지 않습니다: "
                + str(identity)
            )

        facts = ensure_forceteller_facts(path, force=True)
        source_chart = chart_from_facts(facts)
        _validate_source_chart(candidate, facts, source_chart)
        assert source_chart is not None
        candidate.forceteller_chart = source_chart
        candidate.chart_source = "forceteller"
        candidate.chart_difference = chart_differences(
            candidate.chart,
            source_chart,
        )

        signature = _signature(profile, candidate)
        metadata = {
            **signature,
            "signature_hash": _signature_hash(signature),
            "completed": True,
            "result_url": page.url,
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "facts_file": facts_file.name,
            "facts_summary": facts.get("summary", {}),
            "result_identity": identity,
            "chart_source": facts.get("chart", {}).get("source", ""),
            "chart_confidence": facts.get("chart", {}).get("confidence", ""),
            "chart_pillars": {
                key: facts.get("chart", {}).get(key, "")
                for key in (
                    "year_pillar",
                    "month_pillar",
                    "day_pillar",
                    "hour_pillar",
                )
            },
        }
        write_json(metadata_file, metadata)

        quality = validate_candidate_directory(path)
        metadata.update({
            "quality": quality.__dict__,
            "html_sha256": quality.html_sha256,
        })
        write_json(metadata_file, metadata)
        if not quality.valid:
            raise RuntimeError("수집 결과 품질 검증 실패: " + "; ".join(quality.warnings))

        _attach_candidate_paths(
            candidate,
            path,
            metadata,
            "collected",
        )
        if write_summary and user_chart is not None:
            write_candidate_summary(
                path,
                profile,
                user_chart,
                candidate,
                quality.score,
                quality.warnings,
            )
    finally:
        page.remove_listener("response", on_response)



USER_FORCETELLER_MANIFEST = "forceteller_profile.json"


def _empty_chart() -> Chart:
    return Chart(
        year_pillar="甲子",
        month_pillar="甲子",
        day_pillar="甲子",
        hour_pillar="甲子",
        day_master="甲",
        spouse_palace="子",
        stems=["甲", "甲", "甲", "甲"],
        branches=["子", "子", "子", "子"],
        element_counts={"木": 4, "火": 0, "土": 0, "金": 0, "水": 4},
        element_percent={"木": 50.0, "火": 0.0, "土": 0.0, "金": 0.0, "水": 50.0},
    )


def _build_user_forceteller_subject(
    profile: BirthProfile,
) -> tuple[BirthProfile, Candidate]:
    """사용자 원국은 포스텔러 조회 결과만 최종 원본으로 사용한다."""
    solar = profile_to_solar(profile)
    birth_date = (
        f"{solar.getYear():04d}-"
        f"{solar.getMonth():02d}-"
        f"{solar.getDay():02d}"
    )
    birth_time = f"{solar.getHour():02d}:{solar.getMinute():02d}"

    subject_profile = replace(
        profile,
        partner_gender=profile.gender,
    )
    subject = Candidate(
        candidate_id=(
            f"user_{birth_date}_{birth_time.replace(':', '')}"
        ),
        birth_date=birth_date,
        birth_time=birth_time,
        time_label="사용자 출생시",
        chart=_empty_chart(),
        stage1_score=0.0,
        local_score=0.0,
        score=ScoreBreakdown(),
        evidence=[],
        chart_source="forceteller_required",
    )
    return subject_profile, subject


def _write_user_forceteller_manifest(
    profile: BirthProfile,
    subject: Candidate,
) -> None:
    if subject.forceteller_chart is None:
        raise RuntimeError("사용자 포스텔러 원국이 없습니다.")

    write_json(
        profile_dir(profile) / USER_FORCETELLER_MANIFEST,
        {
            "birth_date": subject.birth_date,
            "birth_time": subject.birth_time,
            "gender": profile.gender,
            "data_dir": subject.data_dir,
            "forceteller_facts_path": subject.forceteller_facts_path,
            "result_url": subject.result_url,
            "collection_status": subject.collection_status,
            "chart_source": "forceteller",
            "parser_version": SETTINGS.parser_version,
            "chart": asdict(subject.forceteller_chart),
        },
    )


def load_user_forceteller_chart(
    profile: BirthProfile,
) -> Chart | None:
    manifest = read_json(
        profile_dir(profile) / USER_FORCETELLER_MANIFEST
    )
    if not isinstance(manifest, dict):
        return None

    data_dir = str(manifest.get("data_dir", "")).strip()
    if data_dir:
        path = Path(data_dir)
        if path.exists():
            facts = ensure_forceteller_facts(path)
            chart = chart_from_facts(facts)
            if chart is not None:
                return chart

    # data_dir가 있는데 재파싱에 실패한 경우 오래된 manifest 원국으로 되돌아가지 않는다.
    # 잘못 파싱된 연주·월주가 계속 살아남는 문제를 막기 위한 조치다.
    if data_dir:
        return None

    chart_data = manifest.get("chart")
    if (
        manifest.get("parser_version") == SETTINGS.parser_version
        and isinstance(chart_data, dict)
    ):
        try:
            return Chart(**chart_data)
        except (TypeError, ValueError):
            return None
    return None


def collect_user_forceteller_profile(
    page: Page,
    profile: BirthProfile,
) -> Chart:
    subject_profile, subject = _build_user_forceteller_subject(profile)

    if cache_valid(subject_profile, subject):
        LOGGER.info("사용자 포스텔러 원본 캐시 재사용")
    else:
        collect_one(
            page,
            subject_profile,
            None,
            subject,
            write_summary=False,
        )
        LOGGER.info("사용자 포스텔러 원본 수집 완료")

    if subject.forceteller_chart is None:
        raise RuntimeError(
            "사용자 포스텔러 결과에서 원국을 읽지 못했습니다."
        )
    _write_user_forceteller_manifest(profile, subject)
    return subject.forceteller_chart


def ensure_user_forceteller_chart(
    profile: BirthProfile,
) -> Chart:
    """
    local 계산 전에 사용자 원국을 포스텔러에서 확보한다.

    기존 캐시가 있으면 브라우저를 열지 않는다. 사용자의 사주 원국은
    Python 재계산값으로 대체하지 않는다.
    """
    cached = load_user_forceteller_chart(profile)
    if cached is not None:
        LOGGER.info("사용자 원국: 포스텔러 캐시 사용")
        return cached

    if sync_playwright is None:
        raise RuntimeError("Playwright가 설치되어 있지 않습니다.")

    with sync_playwright() as playwright:
        context = _launch_context(playwright)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                SETTINGS.forceteller_edit_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            print("사용자 원국 확인을 위해 포스텔러 로그인을 완료하세요.")
            input("입력 폼이 보이면 Enter: ")
            return collect_user_forceteller_profile(page, profile)
        finally:
            context.close()



def ensure_profiles_forceteller_charts(
    profiles: list[BirthProfile],
) -> dict[str, Chart]:
    """
    그룹 모드에서 여러 사람의 포스텔러 원국을 한 번의 브라우저
    세션으로 확보한다.

    반환 키는 profile_id(profile)이다. 이미 정상 캐시가 있는 사람은
    브라우저 조회 없이 재사용하고, 누락된 사람만 순차 수집한다.
    """
    if not profiles:
        return {}

    unique_profiles: dict[str, BirthProfile] = {}
    for profile in profiles:
        unique_profiles.setdefault(profile_id(profile), profile)

    charts: dict[str, Chart] = {}
    missing: list[tuple[str, BirthProfile]] = []

    for profile_id_text, profile in unique_profiles.items():
        chart = load_user_forceteller_chart(profile)
        if chart is None:
            missing.append((profile_id_text, profile))
        else:
            charts[profile_id_text] = chart
            LOGGER.info(
                "그룹 구성원 원국 캐시 사용: %s (%s)",
                profile.name,
                profile_id_text,
            )

    if not missing:
        return charts

    if sync_playwright is None:
        raise RuntimeError("Playwright가 설치되어 있지 않습니다.")

    with sync_playwright() as playwright:
        context = _launch_context(playwright)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                SETTINGS.forceteller_edit_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            print(
                "그룹 구성원 원국 확인을 위해 포스텔러 로그인을 "
                "완료하세요."
            )
            input("입력 폼이 보이면 Enter: ")

            for index, (profile_id_text, profile) in enumerate(
                missing,
                1,
            ):
                print(
                    f"[{index}/{len(missing)}] "
                    f"{profile.name} 포스텔러 원국 조회"
                )
                chart = collect_user_forceteller_profile(page, profile)
                charts[profile_id_text] = chart
                page.wait_for_timeout(SETTINGS.polite_delay_ms)
        finally:
            context.close()

    return charts


def _launch_context(playwright) -> BrowserContext:
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(SETTINGS.browser_profile_dir),
        headless=False,
        viewport={"width": 1440, "height": 1100},
        locale="ko-KR",
    )



def select_collection_targets(
    profile: BirthProfile,
    candidates: list[Candidate],
) -> list[Candidate]:
    del profile
    reserve = sorted(
        candidates,
        key=lambda candidate: (
            candidate.prefilter_rank
            if candidate.prefilter_rank > 0
            else 10**9,
            -candidate.prefilter_score,
        ),
    )
    reserve = reserve[: SETTINGS.adaptive_max_count]
    LOGGER.info(
        "포스텔러 적응형 검증 예비군: 로컬 상위 %s명",
        len(reserve),
    )
    return reserve


def _write_adaptive_manifest(
    profile: BirthProfile,
    *,
    status: str,
    reserve: list[Candidate],
    queried_count: int,
    stable_rounds: int,
    stability_reached: bool,
    final_top10: list[Candidate],
    batch_history: list[dict[str, Any]],
    errors: list[str],
) -> None:
    write_json(
        project_dir(profile) / "forceteller_adaptive_selection.json",
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "strategy": {
                "initial_count": SETTINGS.adaptive_initial_count,
                "step_count": SETTINGS.adaptive_step_count,
                "max_count": SETTINGS.adaptive_max_count,
                "required_stability_rounds": (
                    SETTINGS.adaptive_stability_rounds
                ),
                "require_stability_before_ai": (
                    SETTINGS.adaptive_require_stability
                ),
            },
            "reserve_candidate_ids": [
                candidate.candidate_id for candidate in reserve
            ],
            "queried_count": queried_count,
            "verified_count": len(
                verified_forceteller_candidates(reserve)
            ),
            "stable_rounds": stable_rounds,
            "stability_reached": stability_reached,
            "final_top10_candidate_ids": [
                candidate.candidate_id for candidate in final_top10
            ],
            "final_top10": [
                {
                    "rank": rank,
                    "candidate_id": candidate.candidate_id,
                    "birth_date": candidate.birth_date,
                    "birth_time": candidate.birth_time,
                    "prefilter_rank": candidate.prefilter_rank,
                    "prefilter_score": candidate.prefilter_score,
                    "forceteller_rescored_score": candidate.local_score,
                    "local_chart": _chart_summary(candidate.chart),
                    "forceteller_chart": _chart_summary(
                        candidate.forceteller_chart
                    )
                    if candidate.forceteller_chart
                    else None,
                    "chart_difference": candidate.chart_difference,
                }
                for rank, candidate in enumerate(final_top10, 1)
            ],
            "batch_history": batch_history,
            "errors": errors,
        },
    )


def _collect_candidate_with_retries(
    page: Page,
    profile: BirthProfile,
    user_chart: Chart,
    candidate: Candidate,
    progress: ProgressTracker,
) -> bool:
    if cache_valid(profile, candidate):
        _rescore_candidate_from_forceteller(
            profile,
            user_chart,
            candidate,
        )
        candidate.collection_status = "cached"
        progress.mark(candidate.candidate_id, "cached")
        LOGGER.info(
            "전역 포스텔러 원본 재사용·재평가: %s",
            candidate.candidate_id,
        )
        return True

    last_error: Exception | None = None
    for attempt in range(1, SETTINGS.collection_retry_count + 1):
        progress.mark(
            candidate.candidate_id,
            "running",
            attempt=attempt,
        )
        try:
            collect_one(
                page,
                profile,
                user_chart,
                candidate,
            )
            _rescore_candidate_from_forceteller(
                profile,
                user_chart,
                candidate,
            )
            progress.mark(
                candidate.candidate_id,
                "completed",
                attempt=attempt,
            )
            LOGGER.info(
                "수집·포스텔러 재평가 완료: %s "
                "(로컬 예선 %.1f → 포스텔러 원국 구조화 %.1f)",
                candidate.candidate_id,
                candidate.prefilter_score,
                candidate.local_score,
            )
            return True
        except Exception as exc:
            last_error = exc
            LOGGER.error(
                "수집 실패 %s (%s/%s): %s",
                candidate.candidate_id,
                attempt,
                SETTINGS.collection_retry_count,
                exc,
                exc_info=True,
            )
            page.wait_for_timeout(1_000 * attempt)
            try:
                page.goto(
                    SETTINGS.forceteller_edit_url,
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
            except Exception:
                pass

    candidate.collection_status = "error"
    candidate.collection_error = (
        f"{type(last_error).__name__}: {last_error}"
    )
    progress.mark(
        candidate.candidate_id,
        "failed",
        error=candidate.collection_error,
    )
    return False


def collect_top_candidates(
    profile: BirthProfile,
    user_chart: Chart,
    candidates: list[Candidate],
    retry_failed_only: bool = False,
) -> None:
    """
    로컬 상위 예비군을 포스텔러로 순차 검증하고 포스텔러 원국으로
    재평가한다. TOP 10이 지정된 횟수만큼 유지되면 조기 종료하며,
    실패 후보는 자동으로 건너뛰고 다음 예비 후보를 조회한다.
    """
    if sync_playwright is None:
        raise RuntimeError("Playwright가 설치되어 있지 않습니다.")

    progress = ProgressTracker(project_dir(profile) / "progress.json")
    progress.set_stage("adaptive_forceteller_collecting")
    reserve = select_collection_targets(profile, candidates)

    if len(reserve) < SETTINGS.ai_top_n:
        raise RuntimeError(
            "포스텔러 검증 예비군이 TOP 10보다 적습니다."
        )

    initial = max(
        SETTINGS.ai_top_n,
        SETTINGS.adaptive_initial_count,
    )
    step = max(1, SETTINGS.adaptive_step_count)
    maximum = min(
        len(reserve),
        max(initial, SETTINGS.adaptive_max_count),
    )

    queried_count = 0
    current_limit = min(initial, maximum)
    previous_top10_ids: tuple[str, ...] | None = None
    stable_rounds = 0
    stability_reached = False
    batch_history: list[dict[str, Any]] = []
    errors: list[str] = []
    final_top10: list[Candidate] = []
    processed_in_context = 0

    with sync_playwright() as playwright:
        context = _launch_context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(
            SETTINGS.forceteller_edit_url,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        print("포스텔러 로그인이 필요하면 완료하세요.")
        input("입력 폼이 보이면 Enter: ")

        while queried_count < maximum:
            batch_end = current_limit
            batch = reserve[queried_count:batch_end]
            if not batch:
                break

            for candidate in batch:
                # retry 모드에서도 이미 정상 검증된 후보는 다시 조회하지 않는다.
                if _candidate_is_verified(candidate):
                    continue

                success = _collect_candidate_with_retries(
                    page,
                    profile,
                    user_chart,
                    candidate,
                    progress,
                )
                if not success:
                    errors.append(
                        f"{candidate.candidate_id}: "
                        f"{candidate.collection_error}"
                    )

                processed_in_context += 1
                page.wait_for_timeout(SETTINGS.polite_delay_ms)
                if (
                    processed_in_context
                    >= SETTINGS.browser_restart_every
                    and candidate is not batch[-1]
                ):
                    context.close()
                    context = _launch_context(playwright)
                    page = (
                        context.pages[0]
                        if context.pages
                        else context.new_page()
                    )
                    page.goto(
                        SETTINGS.forceteller_edit_url,
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    processed_in_context = 0

            queried_count = batch_end
            verified = verified_forceteller_candidates(
                reserve[:queried_count]
            )
            top10_ids: tuple[str, ...] = tuple(
                candidate.candidate_id
                for candidate in verified[: SETTINGS.ai_top_n]
            )

            if len(top10_ids) == SETTINGS.ai_top_n:
                if previous_top10_ids == top10_ids:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                previous_top10_ids = top10_ids

            batch_history.append(
                {
                    "queried_count": queried_count,
                    "verified_count": len(verified),
                    "top10_candidate_ids": list(top10_ids),
                    "stable_rounds": stable_rounds,
                }
            )

            LOGGER.info(
                "포스텔러 적응형 검증: 조회 %s명 / 검증 %s명 / "
                "안정화 %s/%s",
                queried_count,
                len(verified),
                stable_rounds,
                SETTINGS.adaptive_stability_rounds,
            )

            if (
                len(top10_ids) == SETTINGS.ai_top_n
                and stable_rounds
                >= SETTINGS.adaptive_stability_rounds
            ):
                stability_reached = True
                break

            if queried_count >= maximum:
                break
            current_limit = min(
                maximum,
                queried_count + step,
            )

        context.close()

    verified = verified_forceteller_candidates(
        reserve[:queried_count]
    )
    if len(verified) < SETTINGS.ai_top_n:
        _write_adaptive_manifest(
            profile,
            status="failed",
            reserve=reserve,
            queried_count=queried_count,
            stable_rounds=stable_rounds,
            stability_reached=False,
            final_top10=[],
            batch_history=batch_history,
            errors=errors,
        )
        progress.set_stage("adaptive_selection_failed")
        raise RuntimeError(
            "포스텔러 원국으로 재평가된 정상 후보가 "
            f"{len(verified)}명뿐이라 TOP 10을 구성할 수 없습니다. "
            "`python app.py retry`를 실행하세요."
        )

    final_top10 = select_verified_final_top10(
        verified,
        SETTINGS.ai_top_n,
    )

    if (
        SETTINGS.adaptive_require_stability
        and not stability_reached
    ):
        _write_adaptive_manifest(
            profile,
            status="failed",
            reserve=reserve,
            queried_count=queried_count,
            stable_rounds=stable_rounds,
            stability_reached=False,
            final_top10=final_top10,
            batch_history=batch_history,
            errors=errors,
        )
        progress.set_stage("adaptive_selection_not_stable")
        raise RuntimeError(
            "최대 포스텔러 검증 인원까지 확인했지만 TOP 10이 "
            "설정된 횟수만큼 안정되지 않았습니다."
        )

    reorder_with_verified_top10(candidates, final_top10)

    root = project_dir(profile)
    write_json(
        root / "final_top10_candidates.json",
        {
            "selection_status": "forceteller_rescored_final",
            "selection_rule": (
                "전체 범위 로컬 계산 예비순위 → 상위 예비군 포스텔러 "
                "원국 검증 → 포스텔러 원국으로 궁합 점수 재계산 → "
                "검증 후보 중 최종 TOP 10"
            ),
            "stability_reached": stability_reached,
            "queried_count": queried_count,
            "candidate_ids": [
                candidate.candidate_id for candidate in final_top10
            ],
            "candidates": [
                asdict(candidate) for candidate in final_top10
            ],
        },
    )
    _write_adaptive_manifest(
        profile,
        status="completed",
        reserve=reserve,
        queried_count=queried_count,
        stable_rounds=stable_rounds,
        stability_reached=stability_reached,
        final_top10=final_top10,
        batch_history=batch_history,
        errors=errors,
    )
    progress.set_stage("adaptive_selection_completed")

    LOGGER.info(
        "최종 TOP 10 확정: 포스텔러 검증 %s명 중 재평가 상위 10명",
        len(verified),
    )

