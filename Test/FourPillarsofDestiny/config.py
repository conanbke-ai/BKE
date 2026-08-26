from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent
if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"환경변수 {name}는 정수여야 합니다: {raw!r}"
        ) from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"환경변수 {name}는 숫자여야 합니다: {raw!r}"
        ) from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(
        f"환경변수 {name}는 0/1 또는 true/false여야 합니다: {raw!r}"
    )


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    data_root: Path = PROJECT_ROOT / "data"
    profiles_root: Path = data_root / "profiles"
    candidates_root: Path = data_root / "candidates"
    runs_root: Path = data_root / "runs"
    legacy_output_root: Path = PROJECT_ROOT / "output"
    browser_profile_dir: Path = PROJECT_ROOT / ".browser-profile"
    log_dir: Path = PROJECT_ROOT / "logs"

    forceteller_edit_url: str = (
        "https://pro.forceteller.com/profile/edit"
    )
    fixed_location_text: str = os.getenv(
        "FIXED_LOCATION_TEXT",
        "서울특별시, 대한민국",
    )
    fixed_location_id: str = os.getenv(
        "FIXED_LOCATION_ID",
        "1835848",
    )

    # 후보 예선 계산에만 사용하는 위치 보정값.
    # 표준시 기준 경도 135도와 서울 경도 126.978도의 차이를
    # 1도당 4분으로 환산하면 약 -32분이다.
    fixed_location_longitude: float = _env_float(
        "FIXED_LOCATION_LONGITUDE",
        126.9780,
    )
    standard_meridian_longitude: float = _env_float(
        "STANDARD_MERIDIAN_LONGITUDE",
        135.0,
    )
    solar_time_extra_minutes: int = _env_int(
        "SOLAR_TIME_EXTRA_MINUTES",
        0,
    )
    candidate_location_correction_enabled: bool = _env_bool(
        "CANDIDATE_LOCATION_CORRECTION_ENABLED",
        True,
    )

    # 사용자 출생연도 기준 후보 탐색 범위.
    max_younger_years: int = _env_int("MAX_YOUNGER_YEARS", 5)
    max_older_years: int = _env_int("MAX_OLDER_YEARS", 15)

    # 전체 날짜 × 12시진을 모두 계산한다.
    full_range_time_scan: bool = _env_bool(
        "FULL_RANGE_TIME_SCAN",
        True,
    )
    scan_progress_every_dates: int = _env_int(
        "SCAN_PROGRESS_EVERY_DATES",
        250,
    )

    # 최종 로컬 TOP 10만 포스텔러에서 조회한다.
    ai_top_n: int = 10
    collect_count: int = _env_int("COLLECT_COUNT", 10)

    collector_version: str = "6.2-four-pillar-strict-match"
    parser_version: str = "7.0-structured-chart-table"
    scoring_version: str = "4.1-audited-four-pillars"
    run_schema_version: str = "4.2-local-engine-audited"
    candidate_selection_version: str = (
        "full-age-range-all-times-location-corrected-v2-audited"
    )

    strict_local_forceteller_chart_match: bool = _env_bool(
        "STRICT_LOCAL_FORCETELLER_CHART_MATCH",
        True,
    )

    collection_retry_count: int = _env_int(
        "COLLECTION_RETRY_COUNT",
        3,
    )
    browser_restart_every: int = _env_int(
        "BROWSER_RESTART_EVERY",
        20,
    )
    polite_delay_ms: int = _env_int("POLITE_DELAY_MS", 700)

    screenshot_min_bytes: int = 15_000
    html_min_bytes: int = 3_000
    text_min_chars: int = 100
    required_result_markers: tuple[str, ...] = (
        "생년",
        "생월",
        "생일",
        "생시",
    )

    forceteller_section_max_lines: int = _env_int(
        "FORCETELLER_SECTION_MAX_LINES",
        24,
    )
    forceteller_section_max_chars: int = _env_int(
        "FORCETELLER_SECTION_MAX_CHARS",
        1_200,
    )
    forceteller_max_special_stars: int = _env_int(
        "FORCETELLER_MAX_SPECIAL_STARS",
        20,
    )
    forceteller_star_excerpt_chars: int = _env_int(
        "FORCETELLER_STAR_EXCERPT_CHARS",
        260,
    )
    forceteller_ai_section_chars: int = _env_int(
        "FORCETELLER_AI_SECTION_CHARS",
        260,
    )
    forceteller_ai_max_special_stars: int = _env_int(
        "FORCETELLER_AI_MAX_SPECIAL_STARS",
        8,
    )
    forceteller_ai_star_meaning_chars: int = _env_int(
        "FORCETELLER_AI_STAR_MEANING_CHARS",
        120,
    )
    forceteller_ai_star_excerpt_chars: int = _env_int(
        "FORCETELLER_AI_STAR_EXCERPT_CHARS",
        100,
    )

    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    ai_include_images: bool = _env_bool("AI_INCLUDE_IMAGES", False)
    ai_prompt_version: str = "top10-v9.1-zodiac-source-locked"
    ai_schema_version: str = "top10-report-v9.1-zodiac-source-locked"
    max_source_text_chars: int = _env_int(
        "MAX_SOURCE_TEXT_CHARS",
        900,
    )
    max_image_width: int = _env_int("MAX_IMAGE_WIDTH", 1_600)
    max_image_height: int = _env_int("MAX_IMAGE_HEIGHT", 12_000)
    max_image_bytes: int = _env_int("MAX_IMAGE_BYTES", 4_000_000)
    jpeg_quality: int = _env_int("JPEG_QUALITY", 72)

    # TOP 10 전체를 한 번의 Responses API 호출로 생성한다.
    ai_max_output_tokens: int = _env_int(
        "AI_MAX_OUTPUT_TOKENS",
        18_000,
    )


SETTINGS = Settings()
for directory in (
    SETTINGS.data_root,
    SETTINGS.profiles_root,
    SETTINGS.candidates_root,
    SETTINGS.runs_root,
    SETTINGS.log_dir,
):
    directory.mkdir(parents=True, exist_ok=True)
