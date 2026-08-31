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


def _env_path(name: str, default: Path) -> Path:
    value = str(os.getenv(name) or '').strip()
    return Path(value or default).expanduser().resolve()


STATE_DIR = _env_path('STATE_DIR', ROOT)
DATA_DIR = _env_path('DATA_DIR', STATE_DIR / 'data')
BROWSER_PROFILE_DIR = _env_path('BROWSER_PROFILE_DIR', STATE_DIR / '.browser-profile')


@dataclass(frozen=True)
class Settings:
    # 서비스 화면에는 내부 버전명을 노출하지 않는다.
    app_name: str = '나의 사주 리포트'
    root: Path = ROOT
    state_dir: Path = STATE_DIR
    data_dir: Path = DATA_DIR
    cache_dir: Path = data_dir / 'cache'
    report_dir: Path = data_dir / 'reports'
    forceteller_dir: Path = data_dir / 'forceteller'
    browser_profile_dir: Path = BROWSER_PROFILE_DIR

    host: str = os.getenv('HOST', '127.0.0.1')
    port: int = _env_int('PORT', 8787)
    debug: bool = _env_bool('DEBUG', False)
    public_deployment: bool = _env_bool('PUBLIC_DEPLOYMENT', False)
    persist_user_data: bool = _env_bool('PERSIST_USER_DATA', True)
    external_source_enabled: bool = _env_bool('EXTERNAL_SOURCE_ENABLED', True)
    rate_limit_enabled: bool = _env_bool('RATE_LIMIT_ENABLED', True)
    max_request_bytes: int = max(32_768, _env_int('MAX_REQUEST_BYTES', 524_288))
    max_group_members: int = max(2, _env_int('MAX_GROUP_MEMBERS', 20))
    analysis_queue_timeout_seconds: int = max(0, _env_int('ANALYSIS_QUEUE_TIMEOUT_SECONDS', 2))
    browser_queue_timeout_seconds: int = max(1, _env_int('BROWSER_QUEUE_TIMEOUT_SECONDS', 900))

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
if SETTINGS.public_deployment and SETTINGS.debug:
    raise RuntimeError('PUBLIC_DEPLOYMENT=1에서는 DEBUG=1을 사용할 수 없습니다.')
for directory in (
    SETTINGS.data_dir,
    SETTINGS.cache_dir,
    SETTINGS.report_dir,
    SETTINGS.forceteller_dir,
    SETTINGS.browser_profile_dir,
):
    directory.mkdir(parents=True, exist_ok=True)
