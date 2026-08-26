from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_reporter import (
    AIQuotaError,
    AIReportFormatError,
    generate_top10_ai_report,
    load_cached_top10_report,
)
from bazi_engine import (
    validate_double_hour_grid,
    validate_local_engine_against_forceteller,
)
from collector import (
    collect_top_candidates,
    ensure_user_forceteller_chart,
)
from config import SETTINGS
from logging_utils import LOGGER
from models import (
    BirthProfile,
    Candidate,
    Chart,
    RelationEvidence,
    ScoreBreakdown,
)
from progress import ProgressTracker
from ranking import (
    build_date_pool,
    expand_times,
    local_ranking_diagnostics,
    select_diverse_dates,
    select_final_top10,
)
from reporting import (
    write_ai_reports,
    write_local_top10_fallback,
)
from storage import (
    profile_dir,
    project_dir,
    read_json,
    write_json,
)
from validation import validate_candidate_directory


def ask_choice(
    prompt: str,
    allowed: set[str],
    default: str,
) -> str:
    allowed_upper = {item.upper() for item in allowed}
    while True:
        raw = input(f"{prompt} (기본 {default}): ").strip().upper()
        value = raw or default.upper()
        if value in allowed_upper:
            return value
        print(f"허용값: {', '.join(sorted(allowed_upper))}")


def ask_int(
    prompt: str,
    low: int,
    high: int,
    default: int | None = None,
) -> int:
    while True:
        suffix = f" (기본 {default})" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("정수를 입력하세요.")
            continue
        if low <= value <= high:
            return value
        print(f"범위: {low}~{high}")


def collect_profile() -> BirthProfile:
    print("=== 사용자 출생정보 ===")
    name = input("이름 또는 식별명: ").strip() or "사용자"
    gender = ask_choice("성별 F/M", {"F", "M"}, "F")
    calendar_type = (
        "solar"
        if ask_choice("양력 S / 음력 L", {"S", "L"}, "S") == "S"
        else "lunar"
    )
    is_leap_month = False
    if calendar_type == "lunar":
        is_leap_month = (
            ask_choice("윤달 여부 Y/N", {"Y", "N"}, "N") == "Y"
        )

    year = ask_int("출생연도", 1900, 2100)
    month = ask_int("출생월", 1, 12)
    day = ask_int("출생일", 1, 31)
    hour = ask_int("출생시", 0, 23, 12)
    minute = ask_int("출생분", 0, 59, 0)
    partner_gender = ask_choice(
        "찾는 상대 성별 F/M",
        {"F", "M"},
        "M" if gender == "F" else "F",
    )

    return BirthProfile(
        name=name,
        gender=gender,
        calendar_type=calendar_type,
        is_leap_month=is_leap_month,
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        location=SETTINGS.fixed_location_text,
        timezone="Asia/Seoul",
        partner_gender=partner_gender,
    )


def _chart_from_dict(data: dict | None) -> Chart | None:
    if not isinstance(data, dict):
        return None
    try:
        return Chart(**data)
    except (TypeError, ValueError):
        return None


def _candidate_from_dict(data: dict) -> Candidate:
    chart = _chart_from_dict(data.get("chart"))
    if chart is None:
        raise RuntimeError(
            f"후보 로컬 원국 복원 실패: {data.get('candidate_id')}"
        )

    score = ScoreBreakdown(**data.get("score", {}))
    evidence = [
        RelationEvidence(**item)
        for item in data.get("evidence", [])
    ]
    return Candidate(
        candidate_id=data["candidate_id"],
        birth_date=data["birth_date"],
        birth_time=data["birth_time"],
        time_label=data["time_label"],
        chart=chart,
        stage1_score=data.get("stage1_score", 0.0),
        local_score=data.get("local_score", score.total),
        score=score,
        evidence=evidence,
        forceteller_chart=_chart_from_dict(
            data.get("forceteller_chart")
        ),
        chart_source=data.get(
            "chart_source",
            "local_location_corrected",
        ),
        chart_difference=list(data.get("chart_difference", [])),
        local_calculation_audit=dict(
            data.get("local_calculation_audit", {})
        ),
        data_dir=data.get("data_dir", ""),
        screenshot_path=data.get("screenshot_path", ""),
        html_path=data.get("html_path", ""),
        text_path=data.get("text_path", ""),
        network_path=data.get("network_path", ""),
        metadata_path=data.get("metadata_path", ""),
        collection_status=data.get(
            "collection_status",
            "not_requested",
        ),
        collection_error=data.get("collection_error", ""),
        result_url=data.get("result_url", ""),
        forceteller_facts_path=data.get(
            "forceteller_facts_path",
            "",
        ),
        alternate_times=list(data.get("alternate_times", [])),
        time_top3_average=data.get("time_top3_average", 0.0),
        time_score_range=data.get("time_score_range", 0.0),
    )


def save_state(
    profile: BirthProfile,
    user_chart: Chart,
    candidates: list[Candidate],
) -> None:
    root = project_dir(profile)
    write_json(
        root / "local_ranking.json",
        {
            "profile": asdict(profile),
            "user_chart": asdict(user_chart),
            "user_chart_source": "forceteller",
            "candidate_selection_version": (
                SETTINGS.candidate_selection_version
            ),
            "candidates": [asdict(candidate) for candidate in candidates],
        },
    )
    write_json(
        profile_dir(profile) / "profile.json",
        {"profile": asdict(profile)},
    )


def load_state(
    profile: BirthProfile,
) -> tuple[Chart, list[Candidate]] | None:
    data = read_json(project_dir(profile) / "local_ranking.json")
    if not isinstance(data, dict):
        return None
    if data.get("user_chart_source") != "forceteller":
        return None
    if data.get("candidate_selection_version") != (
        SETTINGS.candidate_selection_version
    ):
        return None

    user_chart = _chart_from_dict(data.get("user_chart"))
    if user_chart is None:
        return None
    try:
        candidates = [
            _candidate_from_dict(item)
            for item in data.get("candidates", [])
        ]
    except (KeyError, TypeError, RuntimeError):
        return None
    return user_chart, candidates


def run_local(
    profile: BirthProfile,
) -> tuple[Chart, list[Candidate]]:
    # 사용자 원국은 포스텔러가 최종 원본이다.
    user_chart = ensure_user_forceteller_chart(profile)

    # 후보 전체 계산에 사용할 로컬 엔진이 같은 입력에서 포스텔러와
    # 네 기둥 모두 일치하는지 먼저 검증한다. 불일치하면 9만여 개
    # 후보 계산을 시작하지 않는다.
    root = project_dir(profile)
    engine_validation = validate_local_engine_against_forceteller(
        profile,
        user_chart,
    )
    engine_validation["double_hour_grid"] = validate_double_hour_grid()
    write_json(root / "bazi_engine_validation.json", engine_validation)

    date_pool = build_date_pool(profile, user_chart)
    all_dates = select_diverse_dates(date_pool, profile.year)
    candidates = expand_times(profile, user_chart, all_dates)
    top10 = select_final_top10(candidates, SETTINGS.ai_top_n)

    write_json(
        root / "final_top10_candidates.json",
        {
            "selection_rule": (
                "전체 연령 범위 모든 날짜 × 12시진 위치 보정 로컬 계산; "
                "같은 날짜 최고 시주 1개; 전체 로컬 TOP 10 선확정"
            ),
            "candidate_ids": [
                candidate.candidate_id for candidate in top10
            ],
            "candidates": [asdict(candidate) for candidate in top10],
        },
    )
    write_json(
        root / "local_ranking_diagnostics.json",
        local_ranking_diagnostics(candidates, SETTINGS.ai_top_n),
    )
    save_state(profile, user_chart, candidates)

    print("사용자 원국: 포스텔러 자료 사용")
    print(
        "로컬 후보 계산:",
        f"{len(all_dates)}개 날짜 × 12시진",
    )
    print("최종 TOP 10: 서로 다른 생년월일시 10개 선확정")
    return user_chart, candidates


def _has_usable_forceteller_source(candidate: Candidate) -> bool:
    if candidate.forceteller_chart is None:
        return False
    if not candidate.data_dir:
        return False
    path = Path(candidate.data_dir)
    return path.exists() and validate_candidate_directory(path).valid


def _select_report_candidates(
    candidates: list[Candidate],
) -> list[Candidate]:
    selected = select_final_top10(candidates, SETTINGS.ai_top_n)
    missing = [
        candidate.candidate_id
        for candidate in selected
        if not _has_usable_forceteller_source(candidate)
    ]
    if missing:
        raise RuntimeError(
            "선확정 TOP 10 중 포스텔러 상세 자료가 없는 후보가 있습니다: "
            + ", ".join(missing)
            + ". `python app.py collect` 또는 `python app.py retry`를 "
            "실행하세요. 11위 이하 후보로 교체하지 않습니다."
        )

    mismatched = {
        candidate.candidate_id: candidate.chart_difference
        for candidate in selected
        if candidate.chart_difference
    }
    if mismatched:
        detail = "; ".join(
            f"{candidate_id} -> {', '.join(differences)}"
            for candidate_id, differences in mismatched.items()
        )
        raise RuntimeError(
            "로컬 후보 원국과 포스텔러 원국이 일치하지 않아 AI 분석을 "
            "중단합니다. 현재 TOP 10 순위의 근거가 달라질 수 있습니다: "
            + detail
        )
    return selected


def _report_candidates_from_cache(
    report,
    candidates: list[Candidate],
) -> list[Candidate]:
    candidate_map = {
        candidate.candidate_id: candidate
        for candidate in candidates
    }
    selected: list[Candidate] = []
    for item in report.candidates:
        candidate = candidate_map.get(item.candidate_id)
        if candidate is None:
            raise RuntimeError(
                "저장된 AI 보고서 후보가 현재 로컬 순위에 없습니다: "
                f"{item.candidate_id}"
            )
        selected.append(candidate)
    return selected


def _saved_profile_records() -> list[tuple[str, BirthProfile, float]]:
    records: list[tuple[str, BirthProfile, float]] = []
    for path in SETTINGS.profiles_root.glob("*/profile.json"):
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        profile_data = payload.get("profile")
        if not isinstance(profile_data, dict):
            continue
        try:
            profile = BirthProfile(**profile_data)
        except (TypeError, ValueError):
            continue
        records.append((path.parent.name, profile, path.stat().st_mtime))
    records.sort(key=lambda item: item[2], reverse=True)
    return records


def _profile_description(
    profile_id_text: str,
    profile: BirthProfile,
) -> str:
    calendar_name = (
        "양력" if profile.calendar_type == "solar" else "음력"
    )
    gender_name = "여성" if profile.gender == "F" else "남성"
    partner_name = (
        "여성" if profile.partner_gender == "F" else "남성"
    )
    return (
        f"{profile.name} | {gender_name} | {calendar_name} "
        f"{profile.year:04d}-{profile.month:02d}-{profile.day:02d} "
        f"{profile.hour:02d}:{profile.minute:02d} | "
        f"상대 {partner_name} | ID {profile_id_text}"
    )


def load_saved_profile(
    requested_profile_id: str | None = None,
) -> BirthProfile:
    records = _saved_profile_records()
    if requested_profile_id:
        for profile_id_text, profile, _ in records:
            if profile_id_text == requested_profile_id:
                print(
                    "저장된 프로필 사용:",
                    _profile_description(profile_id_text, profile),
                )
                return profile
        raise RuntimeError(
            f"지정한 프로필 ID를 찾을 수 없습니다: {requested_profile_id}"
        )

    if not records:
        raise RuntimeError(
            "저장된 사용자 프로필이 없습니다. 먼저 `python app.py local`을 "
            "실행하세요."
        )
    if len(records) == 1:
        profile_id_text, profile, _ = records[0]
        print(
            "저장된 프로필 자동 선택:",
            _profile_description(profile_id_text, profile),
        )
        return profile

    print("=== 저장된 사용자 프로필 ===")
    for index, (profile_id_text, profile, _) in enumerate(records, 1):
        print(f"{index}. {_profile_description(profile_id_text, profile)}")
    selected_index = ask_int("사용할 프로필 번호", 1, len(records), 1)
    return records[selected_index - 1][1]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        nargs="?",
        choices=[
            "all",
            "local",
            "collect",
            "retry",
            "report",
            "render",
            "status",
        ],
        default="all",
    )
    parser.add_argument("--force-ai", action="store_true")
    parser.add_argument("--profile-id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        if args.profile_id:
            profile = load_saved_profile(args.profile_id)
        elif args.mode in {"local", "all"}:
            profile = collect_profile()
            write_json(
                profile_dir(profile) / "profile.json",
                {"profile": asdict(profile)},
            )
        else:
            profile = load_saved_profile()
    except RuntimeError as exc:
        LOGGER.error("프로필 선택 실패: %s", exc)
        print(f"ERROR | {exc}")
        return

    root = project_dir(profile)
    if args.mode == "status":
        tracker = ProgressTracker(root / "progress.json")
        print("진행 단계:", tracker.data.get("stage"))
        print("상태 집계:", tracker.summary())
        return

    state = load_state(profile)
    if args.mode in {"local", "all"}:
        user_chart, candidates = run_local(profile)
    elif state is None:
        print(
            "ERROR | 현재 계산 기준에 맞는 local_ranking.json이 없습니다. "
            "먼저 local 모드를 실행하세요."
        )
        return
    else:
        user_chart, candidates = state

    if args.mode in {"all", "collect", "retry"}:
        collect_top_candidates(
            profile,
            user_chart,
            candidates,
            retry_failed_only=args.mode == "retry",
        )
        save_state(profile, user_chart, candidates)

    if args.mode in {"all", "report", "render"}:
        try:
            if args.mode == "render":
                report = load_cached_top10_report(profile)
                top10 = _report_candidates_from_cache(
                    report,
                    candidates,
                )
            else:
                top10 = _select_report_candidates(candidates)
                write_json(
                    root / "report_candidates.json",
                    {
                        "selection_rule": (
                            "로컬 전체 범위 계산에서 선확정한 TOP 10; "
                            "각 후보 상세 원국은 포스텔러"
                        ),
                        "candidate_ids": [
                            candidate.candidate_id
                            for candidate in top10
                        ],
                        "ai_generation_mode": "single_call_top10",
                    },
                )
                report = generate_top10_ai_report(
                    profile,
                    user_chart,
                    top10,
                    force=args.force_ai,
                )

            md_path, html_path = write_ai_reports(
                profile,
                user_chart,
                report,
                top10,
                all_candidates=candidates,
            )
            print("AI Markdown 보고서:", md_path)
            print("AI HTML 보고서:", html_path)

        except AIQuotaError as exc:
            LOGGER.error("AI 보고서 생성 중단: %s", exc)
            fallback = select_final_top10(
                candidates,
                SETTINGS.ai_top_n,
            )
            md_path, html_path = write_local_top10_fallback(
                profile,
                user_chart,
                fallback,
                str(exc),
                all_candidates=candidates,
            )
            print(f"ERROR | {exc}")
            print("로컬 임시 보고서:", md_path)
            print("로컬 임시 HTML:", html_path)
            return

        except AIReportFormatError as exc:
            LOGGER.error("AI 단일 응답 형식 오류: %s", exc)
            print(f"ERROR | {exc}")
            print(
                "동일 요청을 자동 재호출하지 않았으므로 추가 중복 호출은 "
                "발생하지 않았습니다."
            )
            return

        except RuntimeError as exc:
            LOGGER.error("보고서 생성 조건 미충족: %s", exc)
            print(f"ERROR | {exc}")
            return

        except Exception as exc:
            LOGGER.exception("AI 보고서 생성 중 예기치 않은 오류")
            print(f"ERROR | AI 보고서 생성 중 예기치 않은 오류: {exc}")
            return

    print("프로젝트 폴더:", root)


if __name__ == "__main__":
    main()
