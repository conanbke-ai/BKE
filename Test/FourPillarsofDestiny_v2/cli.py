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
    PreAIValidationError,
    collect_top_candidates,
    ensure_user_forceteller_chart,
    load_user_forceteller_chart,
)
from config import SETTINGS
from logging_utils import LOGGER
from group_mode import run_group_command
from pair_mode import run_pair_command
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
    select_verified_final_top10,
)
from reporting import (
    write_ai_reports,
    write_local_top10_fallback,
)
from storage import (
    migrate_profile_roots,
    profile_dir,
    profile_id,
    project_dir,
    read_json,
    safe_filename_component,
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



def choose_execution_scope() -> str:
    """
    명령행에 세부 모드를 지정하지 않고 app.py만 실행했을 때
    가장 먼저 개인/그룹 실행 유형을 선택한다.

    반환값은 기존 명령 체계와 연결된다.
    - 개인 모드 -> all
    - 그룹 모드 -> group
    """
    print("=== 실행 유형 선택 ===")
    print("P. 개인 후보 탐색: 조건에 맞는 전체 후보군에서 TOP 10 분석")
    print("O. 지정 1인 궁합: 원하는 사람 한 명과 연인·친구 궁합 분석")
    print("G. 그룹 모드: 여러 사주를 입력해 구성원별 궁합 순위 계산")

    selected = ask_choice(
        "실행 유형 P=개인 후보 탐색 / O=지정 1인 / G=그룹",
        {"P", "O", "G"},
        "P",
    )
    if selected == "P":
        return "all"
    if selected == "O":
        return "pair"
    return "group"


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
    mode_key = ask_choice(
        "분석 모드 L=연인 / F=친구",
        {"L", "F"},
        "L",
    )
    relationship_mode = (
        "lover" if mode_key == "L" else "friend"
    )
    target_label = (
        "찾는 연인 성별 F/M"
        if relationship_mode == "lover"
        else "찾는 친구 성별 F/M"
    )
    partner_gender = ask_choice(
        target_label,
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
        relationship_mode=relationship_mode,
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
        prefilter_rank=int(data.get("prefilter_rank", 0)),
        prefilter_score=float(
            data.get(
                "prefilter_score",
                data.get("local_score", 0.0),
            )
        ),
        final_score_source=data.get(
            "final_score_source",
            "local_prefilter",
        ),
        forceteller_rescored_at=data.get(
            "forceteller_rescored_at",
            "",
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
        time_median_score=data.get("time_median_score", 0.0),
        selected_time_score=data.get(
            "selected_time_score",
            data.get("local_score", score.total),
        ),
        robust_prefilter_score=data.get(
            "robust_prefilter_score",
            data.get("prefilter_score", 0.0),
        ),
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
            "parser_version": SETTINGS.parser_version,
            "collector_version": SETTINGS.collector_version,
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
    if data.get("parser_version") != SETTINGS.parser_version:
        return None
    if data.get("collector_version") != SETTINGS.collector_version:
        return None
    if data.get("candidate_selection_version") != (
        SETTINGS.candidate_selection_version
    ):
        return None

    user_chart = _chart_from_dict(data.get("user_chart"))
    if user_chart is None:
        return None

    current_user_chart = load_user_forceteller_chart(profile)
    if current_user_chart is None:
        return None

    stored_pillars = (
        user_chart.year_pillar,
        user_chart.month_pillar,
        user_chart.day_pillar,
        user_chart.hour_pillar,
    )
    current_pillars = (
        current_user_chart.year_pillar,
        current_user_chart.month_pillar,
        current_user_chart.day_pillar,
        current_user_chart.hour_pillar,
    )
    if stored_pillars != current_pillars:
        LOGGER.warning(
            "저장된 사용자 원국과 현재 포스텔러 원국이 달라 "
            "기존 local_ranking.json을 폐기합니다: %s -> %s",
            stored_pillars,
            current_pillars,
        )
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
    preliminary_top10 = select_final_top10(
        candidates,
        SETTINGS.ai_top_n,
    )
    reserve = candidates[: SETTINGS.adaptive_max_count]

    write_json(
        root / "final_top10_candidates.json",
        {
            "selection_status": "local_prefilter_preliminary",
            "selection_rule": (
                "로컬 예선 TOP 10이며 아직 최종 후보가 아님. "
                "collect 단계에서 포스텔러 원국으로 재평가 후 교체 가능"
            ),
            "candidate_ids": [
                candidate.candidate_id
                for candidate in preliminary_top10
            ],
            "candidates": [
                asdict(candidate)
                for candidate in preliminary_top10
            ],
        },
    )
    write_json(
        root / "reserve_candidates.json",
        {
            "selection_rule": (
                "전체 범위 로컬 예선 상위 후보. 포스텔러 적응형 검증 대상"
            ),
            "max_count": SETTINGS.adaptive_max_count,
            "candidate_ids": [
                candidate.candidate_id for candidate in reserve
            ],
            "candidates": [
                asdict(candidate) for candidate in reserve
            ],
        },
    )
    write_json(
        root / "local_ranking_diagnostics.json",
        local_ranking_diagnostics(candidates, SETTINGS.ai_top_n, profile),
    )
    save_state(profile, user_chart, candidates)

    print("사용자 원국: 포스텔러 자료 사용")
    print(
        "로컬 후보 계산:",
        f"{len(all_dates)}개 날짜 × 12시진",
    )
    print(
        "로컬 예선 완료:",
        f"상위 {SETTINGS.adaptive_max_count}명을 포스텔러 검증 예비군으로 저장",
    )
    print(
        "최종 TOP 10은 collect 단계에서 포스텔러 원국 재평가 후 확정됩니다."
    )
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
    selected = select_verified_final_top10(
        candidates,
        SETTINGS.ai_top_n,
    )
    missing = [
        candidate.candidate_id
        for candidate in selected
        if not _has_usable_forceteller_source(candidate)
    ]
    if missing:
        raise RuntimeError(
            "최종 TOP 10 중 포스텔러 상세 자료가 없는 후보가 있습니다: "
            + ", ".join(missing)
            + ". `python app.py collect` 또는 `python app.py retry`를 "
            "실행하세요."
        )

    invalid_score_source = [
        candidate.candidate_id
        for candidate in selected
        if candidate.final_score_source != "forceteller_rescored"
    ]
    if invalid_score_source:
        raise RuntimeError(
            "포스텔러 원국으로 최종 재평가되지 않은 후보가 있습니다: "
            + ", ".join(invalid_score_source)
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


def _birth_profile_from_dict(data: dict) -> BirthProfile:
    """이전 profile.json의 불필요한 필드를 무시해 호환 로드한다."""
    allowed = {
        "name",
        "gender",
        "calendar_type",
        "is_leap_month",
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "location",
        "timezone",
        "partner_gender",
        "relationship_mode",
        "birth_time_known",
    }
    cleaned = {key: value for key, value in data.items() if key in allowed}

    if "birth_time_known" not in cleaned:
        cleaned["birth_time_known"] = True

    if "partner_gender" not in cleaned:
        gender = str(cleaned.get("gender", "F")).upper()
        cleaned["partner_gender"] = "M" if gender == "F" else "F"

    raw_mode = str(
        cleaned.get("relationship_mode", "lover")
    ).strip().lower()
    mode_aliases = {
        "lover": "lover",
        "love": "lover",
        "l": "lover",
        "연인": "lover",
        "연애": "lover",
        "friend": "friend",
        "friendship": "friend",
        "f": "friend",
        "친구": "friend",
        "우정": "friend",
    }
    cleaned["relationship_mode"] = mode_aliases.get(
        raw_mode,
        "lover",
    )

    cleaned.setdefault("name", "사용자")
    cleaned.setdefault("location", SETTINGS.fixed_location_text)
    cleaned.setdefault("timezone", "Asia/Seoul")
    cleaned.setdefault("is_leap_month", False)
    return BirthProfile(**cleaned)


def _saved_profile_records() -> list[tuple[str, BirthProfile, float]]:
    records: list[tuple[str, BirthProfile, float]] = []
    seen_profile_ids: set[str] = set()

    for path in list(SETTINGS.profiles_root.glob("*/profile.json")):
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        profile_data = payload.get("profile")
        if not isinstance(profile_data, dict):
            continue
        try:
            profile = _birth_profile_from_dict(profile_data)
        except (TypeError, ValueError):
            continue

        logical_id = profile_id(profile)
        if logical_id in seen_profile_ids:
            continue

        migrate_profile_roots(profile)
        migrated_root = profile_dir(profile)
        migrated_profile_path = migrated_root / "profile.json"
        effective_path = (
            migrated_profile_path
            if migrated_profile_path.exists()
            else path
        )
        records.append(
            (
                migrated_root.name,
                profile,
                effective_path.stat().st_mtime,
            )
        )
        seen_profile_ids.add(logical_id)

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
    mode_name = (
        "연인 모드"
        if profile.relationship_mode == "lover"
        else "친구 모드"
    )
    time_text = (
        f"{profile.hour:02d}:{profile.minute:02d}"
        if profile.birth_time_known
        else "출생시간 미상"
    )
    return (
        f"{profile.name} | {gender_name} | {calendar_name} "
        f"{profile.year:04d}-{profile.month:02d}-{profile.day:02d} "
        f"{time_text} | "
        f"{mode_name} | 상대 {partner_name} | ID {profile_id_text}"
    )


def load_saved_profile(
    requested_profile_id: str | None = None,
    *,
    exclude_profile_id: str | None = None,
    selection_title: str = "저장된 사용자 프로필",
    selection_prompt: str = "사용할 프로필 번호",
) -> BirthProfile:
    records = _saved_profile_records()

    if exclude_profile_id:
        records = [
            record
            for record in records
            if record[0] != exclude_profile_id
            and profile_id(record[1]) != exclude_profile_id
        ]

    if requested_profile_id:
        for profile_id_text, profile, _ in records:
            if (
                profile_id_text == requested_profile_id
                or profile_id(profile) == requested_profile_id
            ):
                print(
                    "저장된 프로필 사용:",
                    _profile_description(profile_id_text, profile),
                )
                return profile
        raise RuntimeError(
            f"지정한 프로필 ID를 찾을 수 없습니다: {requested_profile_id}"
        )

    if not records:
        if exclude_profile_id:
            raise RuntimeError(
                "기준 사용자를 제외하면 선택할 수 있는 저장 프로필이 "
                "없습니다. 상대방 정보를 새로 입력하세요."
            )
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

    print(f"=== {selection_title} ===")
    for index, (profile_id_text, profile, _) in enumerate(records, 1):
        print(f"{index}. {_profile_description(profile_id_text, profile)}")
    selected_index = ask_int(
        selection_prompt,
        1,
        len(records),
        1,
    )
    return records[selected_index - 1][1]



def _migrate_existing_group_report_names() -> None:
    """
    기존 group_rankings.html도 앱 시작 시
    <그룹이름>_<모드>.html로 바로 변경한다.
    """
    mode_names = {
        "lover": "연인",
        "friend": "친구",
    }
    for group_json in SETTINGS.groups_root.glob(
        "*/group.json"
    ):
        definition = read_json(group_json)
        if not isinstance(definition, dict):
            continue
        if definition.get("execution_type") == "pair":
            continue

        group_name = safe_filename_component(
            definition.get("group_name"),
            default="그룹",
        )
        mode_name = mode_names.get(
            str(
                definition.get(
                    "relationship_mode",
                    "",
                )
            ),
            "모드",
        )
        root = group_json.parent
        legacy = root / "group_rankings.html"
        named = root / f"{group_name}_{mode_name}.html"
        if legacy.exists() and not named.exists():
            legacy.replace(named)
        elif legacy.exists() and named.exists():
            legacy.unlink()


def _migrate_existing_readable_names() -> None:
    _saved_profile_records()
    _migrate_existing_group_report_names()



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
            "pair",
            "pair-report",
            "pair-render",
            "pair-status",
            "group",
            "group-report",
            "group-render",
            "group-status",
        ],
        default=None,
    )
    parser.add_argument("--force-ai", action="store_true")
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="지정 1인 모드에서 AI 상세 해설 호출을 생략합니다.",
    )
    parser.add_argument("--profile-id")
    parser.add_argument(
        "--user-file",
        help=(
            "지정 1인 궁합의 기준 사용자 한 명을 입력한 "
            "CSV/TXT 파일 경로"
        ),
    )
    parser.add_argument("--pair-id")
    parser.add_argument("--target-file")
    parser.add_argument("--target-profile-id")
    parser.add_argument(
        "--pair-mode",
        choices=["lover", "friend", "L", "F", "연인", "친구"],
    )
    parser.add_argument("--group-id")
    parser.add_argument("--group-file")
    parser.add_argument("--group-name")
    parser.add_argument(
        "--group-mode",
        choices=["lover", "friend", "L", "F", "연인", "친구"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _migrate_existing_readable_names()

    # `python app.py`처럼 세부 명령 없이 실행한 경우에만
    # 개인/그룹 유형을 먼저 선택한다. local, collect, group-report 등
    # 명시적 명령은 기존처럼 바로 실행한다.
    if args.mode is None:
        args.mode = choose_execution_scope()

    if args.mode in {
        "pair",
        "pair-report",
        "pair-render",
        "pair-status",
    }:
        try:
            run_pair_command(args, load_saved_profile)
        except AIQuotaError as exc:
            LOGGER.error("1:1 AI 보고서 생성 중단: %s", exc)
            print(f"ERROR | {exc}")
        except AIReportFormatError as exc:
            LOGGER.error("1:1 AI 단일 응답 형식 오류: %s", exc)
            print(f"ERROR | {exc}")
            print("동일 요청을 자동 재호출하지 않았습니다.")
        except (RuntimeError, ValueError) as exc:
            LOGGER.error("지정 1인 궁합 실행 실패: %s", exc)
            print(f"ERROR | {exc}")
        except Exception as exc:
            LOGGER.exception("지정 1인 궁합 실행 중 예기치 않은 오류")
            print(f"ERROR | 지정 1인 궁합 실행 중 예기치 않은 오류: {exc}")
        return

    if args.mode in {
        "group",
        "group-report",
        "group-render",
        "group-status",
    }:
        try:
            run_group_command(args)
        except AIQuotaError as exc:
            LOGGER.error("그룹 AI 보고서 생성 중단: %s", exc)
            print(f"ERROR | {exc}")
        except AIReportFormatError as exc:
            LOGGER.error("그룹 AI 단일 응답 형식 오류: %s", exc)
            print(f"ERROR | {exc}")
            print("동일 요청을 자동 재호출하지 않았습니다.")
        except (RuntimeError, ValueError) as exc:
            LOGGER.error("그룹 모드 실행 실패: %s", exc)
            print(f"ERROR | {exc}")
        except Exception as exc:
            LOGGER.exception("그룹 모드 실행 중 예기치 않은 오류")
            print(f"ERROR | 그룹 모드 실행 중 예기치 않은 오류: {exc}")
        return

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
                            "로컬 상위 예비군을 포스텔러 원국으로 "
                            "재평가한 최종 TOP 10"
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
            fallback = select_verified_final_top10(
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

        except PreAIValidationError as exc:
            LOGGER.error("AI 호출 전 검증 실패: %s", exc)
            print(f"ERROR | {exc}")
            print(
                "포스텔러 비교가 끝나기 전에 중단되었으므로 "
                "OpenAI API 요청과 토큰 비용은 발생하지 않았습니다."
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
