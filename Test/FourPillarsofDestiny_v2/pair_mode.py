from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ai_reporter import AIQuotaError, AIReportFormatError
from collector import ensure_profiles_forceteller_charts
from group_mode import (
    _GROUP_MODE_NAMES,
    build_group_rankings,
    create_group_definition,
    group_path,
    load_group_definition,
    load_group_rankings,
    load_single_profile_file,
    parse_single_profile_lines,
    profiles_from_definition,
)
from models import BirthProfile
from pair_ai_reporter import (
    generate_pair_ai_report,
    load_cached_pair_ai_report,
)
from pair_reporting import (
    pair_report_basename,
    write_pair_reports,
)
from storage import profile_dir, profile_id, write_json
from unknown_time_pair import (
    build_unknown_time_pair_rankings,
    pair_has_unknown_time,
)


_PAIR_MODE_ALIASES = {
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


def _normalize_pair_mode(value: object) -> str:
    normalized = _PAIR_MODE_ALIASES.get(
        str(value or "").strip().lower()
    )
    if normalized is None:
        raise ValueError(
            f"지원하지 않는 1:1 관계 모드입니다: {value!r}"
        )
    return normalized


def _choose_pair_mode(value: object = None) -> str:
    if value:
        return _normalize_pair_mode(value)
    while True:
        raw = input(
            "지정 1인 분석 모드 L=연인 / F=친구 (기본 L): "
        ).strip() or "L"
        try:
            return _normalize_pair_mode(raw)
        except ValueError as exc:
            print(exc)




def _choose_user_source() -> str:
    print("=== 기준 사용자 선택 방식 ===")
    print("S. 저장된 프로필 목록에서 기준 사용자 선택")
    print("N. 기준 사용자 출생정보를 새로 입력")

    while True:
        raw = input(
            "기준 사용자 선택 방식 S=저장 프로필 / N=새 입력 "
            "(기본 S): "
        ).strip().upper() or "S"
        if raw in {"S", "N"}:
            return raw
        print("허용값: N, S")


def _collect_user_interactive(mode: str) -> BirthProfile:
    print("=== 기준 사용자 출생정보 ===")
    print(
        "한 줄에 이름|성별(F/M)|양력/음력(S/L)|"
        "YYYY-MM-DD|HH:MM 또는 UNKNOWN|윤달(Y/N) 순서로 입력하세요."
    )
    print("예: 배경은|F|S|1994-12-07|05:30|N")
    print("시간을 모르면: 배경은|F|S|1994-12-07|UNKNOWN|N")
    raw = input("기준 사용자 정보: ").strip()
    return parse_single_profile_lines([raw], mode)


def _save_pair_profile(profile: BirthProfile) -> None:
    """새로 입력한 프로필도 다음 실행부터 저장 목록에서 선택할 수 있게 한다."""
    write_json(
        profile_dir(profile) / "profile.json",
        {"profile": asdict(profile)},
    )



def _choose_target_source() -> str:
    print("=== 지정 상대방 선택 방식 ===")
    print("S. 저장된 프로필 목록에서 한 명 선택")
    print("N. 상대방 출생정보를 새로 입력")

    while True:
        raw = input(
            "상대방 선택 방식 S=저장 프로필 / N=새 입력 (기본 S): "
        ).strip().upper() or "S"
        if raw in {"S", "N"}:
            return raw
        print("허용값: N, S")


def _select_saved_target(
    profile_loader: Callable[..., BirthProfile],
    user_profile: BirthProfile,
    requested_target_profile_id: str | None = None,
) -> BirthProfile:
    return profile_loader(
        requested_target_profile_id,
        exclude_profile_id=profile_id(user_profile),
        selection_title="저장된 상대방 프로필",
        selection_prompt="상대방 프로필 번호",
    )


def _collect_target_interactive(mode: str) -> BirthProfile:
    print("=== 지정 상대방 출생정보 ===")
    print(
        "한 줄에 이름|성별(F/M)|양력/음력(S/L)|"
        "YYYY-MM-DD|HH:MM 또는 UNKNOWN|윤달(Y/N) 순서로 입력하세요."
    )
    print("예: 홍길동|M|S|1992-04-19|15:00|N")
    print("시간을 모르면: 홍길동|M|S|1992-04-19|UNKNOWN|N")
    raw = input("상대방 정보: ").strip()
    return parse_single_profile_lines([raw], mode)


def _pair_definition(
    user_profile: BirthProfile,
    target_profile: BirthProfile,
    mode: str,
) -> dict[str, Any]:
    user_profile = replace(
        user_profile,
        relationship_mode=mode,
        partner_gender=target_profile.gender,
    )
    target_profile = replace(
        target_profile,
        relationship_mode=mode,
        partner_gender=user_profile.gender,
    )

    if profile_id(user_profile) == profile_id(target_profile):
        raise ValueError(
            "기준 사용자와 지정 상대방의 출생정보가 동일합니다."
        )

    # 기존 저장 프로필이 아니어도 정상 실행되며,
    # 성공한 입력은 이후 재사용할 수 있도록 저장한다.
    _save_pair_profile(user_profile)
    _save_pair_profile(target_profile)

    definition = create_group_definition(
        f"{user_profile.name}-{target_profile.name} 1대1 궁합",
        mode,
        [user_profile, target_profile],
    )
    members = definition.get("members", [])
    definition.update({
        "execution_type": "pair",
        "pair_id": definition["group_id"],
        "user_member_id": members[0]["member_id"],
        "target_member_id": members[1]["member_id"],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    write_json(
        group_path(definition["group_id"]) / "group.json",
        definition,
    )
    return definition


def _load_pair_definition(pair_id: str | None) -> dict[str, Any]:
    definition = load_group_definition(pair_id)
    if definition.get("execution_type") != "pair":
        raise RuntimeError(
            "지정한 ID는 1:1 궁합 결과가 아닙니다. "
            "pair 명령으로 생성한 pair ID를 사용하세요."
        )
    if len(definition.get("members", [])) != 2:
        raise RuntimeError("1:1 궁합 구성원이 정확히 두 명이 아닙니다.")
    return definition


def _new_pair_definition(
    args: Any,
    profile_loader: Callable[..., BirthProfile],
) -> dict[str, Any]:
    mode = _choose_pair_mode(getattr(args, "pair_mode", None))

    requested_profile_id = getattr(args, "profile_id", None)
    user_file = getattr(args, "user_file", None)

    if requested_profile_id and user_file:
        raise ValueError(
            "--profile-id와 --user-file은 동시에 사용할 수 없습니다."
        )

    if user_file:
        user_profile = load_single_profile_file(
            Path(user_file),
            mode,
        )
    elif requested_profile_id:
        # 명시적으로 지정한 ID가 없으면 오류를 숨기지 않는다.
        user_profile = profile_loader(requested_profile_id)
    else:
        user_source = _choose_user_source()
        if user_source == "S":
            try:
                user_profile = profile_loader(
                    None,
                    selection_title="저장된 기준 사용자 프로필",
                    selection_prompt="기준 사용자 프로필 번호",
                )
            except RuntimeError as exc:
                print(f"저장 프로필 선택 불가: {exc}")
                print(
                    "저장된 기준 사용자 프로필이 없어 "
                    "출생정보를 새로 입력합니다."
                )
                user_profile = _collect_user_interactive(mode)
        else:
            user_profile = _collect_user_interactive(mode)

    target_file = getattr(args, "target_file", None)
    target_profile_id = getattr(
        args,
        "target_profile_id",
        None,
    )

    if target_file and target_profile_id:
        raise ValueError(
            "--target-file과 --target-profile-id는 "
            "동시에 사용할 수 없습니다."
        )

    if target_file:
        target_profile = load_single_profile_file(
            Path(target_file),
            mode,
        )
    elif target_profile_id:
        target_profile = _select_saved_target(
            profile_loader,
            user_profile,
            target_profile_id,
        )
    else:
        source = _choose_target_source()
        if source == "S":
            try:
                target_profile = _select_saved_target(
                    profile_loader,
                    user_profile,
                )
            except RuntimeError as exc:
                print(f"저장 프로필 선택 불가: {exc}")
                print(
                    "선택 가능한 상대방 프로필이 없어 "
                    "상대방 출생정보를 새로 입력합니다."
                )
                target_profile = _collect_target_interactive(mode)
        else:
            target_profile = _collect_target_interactive(mode)

    return _pair_definition(
        user_profile,
        target_profile,
        mode,
    )


def run_pair_command(
    args: Any,
    profile_loader: Callable[..., BirthProfile],
) -> None:
    command = str(args.mode)

    if command == "pair" and not getattr(args, "pair_id", None):
        definition = _new_pair_definition(args, profile_loader)
    else:
        definition = _load_pair_definition(
            getattr(args, "pair_id", None)
        )

    pair_id = definition["group_id"]
    members = profiles_from_definition(definition)
    names = [profile.name for _, profile in members]

    print("1:1 궁합 ID:", pair_id)
    print("기준 사용자:", names[0])
    print("지정 상대방:", names[1])
    print(
        "분석 모드:",
        _GROUP_MODE_NAMES[definition["relationship_mode"]],
    )

    if command == "pair-status":
        root = group_path(pair_id)
        rankings = root / "group_rankings.json"
        basename = pair_report_basename(definition)
        pair_html = root / f"{basename}.html"
        ai_cache = root / "pair_ai_report.json"
        ai_html = pair_html
        print(
            "궁합 계산:",
            "완료" if rankings.exists() and pair_html.exists() else "미완료",
        )
        print(
            "AI 상세 해설:",
            "완료" if ai_cache.exists() and ai_html.exists() else "미완료",
        )
        print("결과 폴더:", root)
        return

    if command == "pair":
        profiles = [profile for _, profile in members]
        if pair_has_unknown_time(definition):
            unknown_count = sum(
                1
                for profile in profiles
                if not profile.birth_time_known
            )
            combination_count = 12 if unknown_count == 1 else 144
            lookup_maximum = 13 if unknown_count == 1 else 24
            print(
                "출생시간 미상 분석:",
                f"{combination_count}개 궁합 조합을 로컬 계산하고 ",
                f"포스텔러 원국은 최대 {lookup_maximum}개 조회합니다.",
            )
            print("OpenAI 상세 해설은 집계 결과 전체를 1회 호출합니다.")
            rankings = build_unknown_time_pair_rankings(
                definition
            )
        else:
            charts = ensure_profiles_forceteller_charts(profiles)
            rankings = build_group_rankings(definition, charts)

        # AI가 실패하더라도 원국·점수 결과는 남도록 로컬 간략본을 먼저 만든다.
        fallback_md, fallback_html = write_pair_reports(
            definition,
            rankings,
        )

        if bool(getattr(args, "no_ai", False)):
            print("1:1 궁합 Markdown:", fallback_md)
            print("1:1 궁합 HTML:", fallback_html)
            print(
                "AI 상세 해설을 생략했습니다. "
                "이 파일은 포스텔러 원국과 점수 근거를 정리한 간략본입니다."
            )
            return

        try:
            report = generate_pair_ai_report(
                definition,
                rankings,
                force=bool(getattr(args, "force_ai", False)),
            )
        except Exception:
            print(
                "AI 상세 해설 생성에 실패했습니다. "
                "로컬 간략본은 다음 경로에 저장했습니다:"
            )
            print("1:1 간략 HTML:", fallback_html)
            raise

        md_path, html_path = write_pair_reports(
            definition,
            rankings,
            ai_report=report,
        )
        print("1:1 상세 AI Markdown:", md_path)
        print("1:1 상세 AI HTML:", html_path)
        print(
            "OpenAI 호출 방식: 지정한 두 사람 전체 1회 "
            "(동일 캐시가 있으면 호출 없이 재사용)"
        )
        return

    rankings = load_group_rankings(definition)
    if command == "pair-report":
        report = generate_pair_ai_report(
            definition,
            rankings,
            force=bool(getattr(args, "force_ai", False)),
        )
    elif command == "pair-render":
        report = load_cached_pair_ai_report(
            definition,
            rankings,
        )
    else:
        raise RuntimeError(
            f"지원하지 않는 1:1 궁합 명령입니다: {command}"
        )

    md_path, html_path = write_pair_reports(
        definition,
        rankings,
        ai_report=report,
    )
    print("1:1 AI Markdown:", md_path)
    print("1:1 AI HTML:", html_path)
    print("OpenAI 호출 방식: 두 사람 전체 1회")
