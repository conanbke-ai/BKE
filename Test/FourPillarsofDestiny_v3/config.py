from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(ROOT / '.env', override=False)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


@dataclass(frozen=True)
class Settings:
    # 서비스 화면에는 내부 버전명을 노출하지 않는다.
    app_name: str = '나의 사주 리포트'
    root: Path = ROOT
    data_dir: Path = ROOT / 'data'
    cache_dir: Path = data_dir / 'cache'
    report_dir: Path = data_dir / 'reports'
    forceteller_dir: Path = data_dir / 'forceteller'
    browser_profile_dir: Path = ROOT / '.browser-profile'

    host: str = os.getenv('HOST', '127.0.0.1')
    port: int = _env_int('PORT', 8787)
    debug: bool = _env_bool('DEBUG', False)

    forceteller_edit_url: str = os.getenv('FORCETELLER_EDIT_URL', 'https://pro.forceteller.com/profile/edit')
    default_location_text: str = os.getenv('FORCETELLER_LOCATION_TEXT', '서울특별시, 대한민국')
    default_location_id: str = os.getenv('FORCETELLER_LOCATION_ID', '1835848')
    headless: bool = _env_bool('HEADLESS', False)
    browser_timeout_ms: int = _env_int('BROWSER_TIMEOUT_MS', 30000)
    polite_delay_ms: int = _env_int('POLITE_DELAY_MS', 900)

    # 추천 탐색. 연령 범위는 예전 프로그램과 동일하게 사용자 연령대별 자동 범위를 사용한다.
    # 19~24세: 연상 5 / 연하 3, 25~39세: 연상 8 / 연하 5,
    # 40~49세: 연상 10 / 연하 8, 50세 이상: 연상 12 / 연하 10.
    top_n: int = _env_int('TOP_N', 10)
    ideal_top_n: int = _env_int('IDEAL_TOP_N', 5)
    auto_shortlist_per_year: int = max(1, _env_int('AUTO_SHORTLIST_PER_YEAR', 2))
    min_partner_age: int = _env_int('MIN_PARTNER_AGE', 20)
    min_verified_source_quality: int = _env_int('MIN_VERIFIED_SOURCE_QUALITY', 60)
    # Local raw-source reparse retry only. It never authorizes an automatic external revisit.
    retry_partial_facts: bool = _env_bool('RETRY_PARTIAL_FACTS', False)

    openai_api_key: str | None = os.getenv('OPENAI_API_KEY')
    openai_model: str = os.getenv('OPENAI_MODEL', 'gpt-5.6')
    ai_enabled: bool = _env_bool('AI_ENABLED', True)
    ai_max_output_tokens: int = _env_int('AI_MAX_OUTPUT_TOKENS', 30000)
    # 동일 입력 재테스트 중 실수로 유료 AI를 다시 호출하지 않게 한다.
    # 강제 재생성은 명시적으로 환경변수를 켠 경우에만 허용한다.
    allow_force_ai_regeneration: bool = _env_bool('ALLOW_FORCE_AI_REGENERATION', False)

    # 내부 캐시 무효화용 revision. 사용자 화면에는 노출하지 않는다.
    ai_prompt_version: str = 'user-first-relations-r13-20260818'
    scoring_version: str = 'compatibility-core-r3-20260816'
    parser_version: str = 'source-facts-r15-20260818'
    report_revision: str = 'user-first-service-r30-20260818'

    build_auto_matches_on_first_run: bool = _env_bool('BUILD_AUTO_MATCHES', True)


SETTINGS = Settings()
for directory in (
    SETTINGS.data_dir,
    SETTINGS.cache_dir,
    SETTINGS.report_dir,
    SETTINGS.forceteller_dir,
    SETTINGS.browser_profile_dir,
):
    directory.mkdir(parents=True, exist_ok=True)
