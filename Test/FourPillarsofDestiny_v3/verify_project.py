from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    'app.py',
    'services.py',
    'group.py',
    'forceteller.py',
    'fortune.py',
    'explain.py',
    'ai_reporter.py',
    'models.py',
    'progress_tracker.py',
    'test_fixture.py',
    'reparse_cache.py',
    'templates/index.html',
    'static/app.js',
    'static/styles.css',
    'static/assets/bunny-hero-a1.png',
    'static/assets/intro-splash.png',
    'static/assets/input-header-rainbow-v2.png',
    'static/assets/app-background-clouds-v2.png',
    'static/assets/loading-bunny-hop.webp',
    'static/assets/loading-bunny-hop-fallback.png',
    'audit_contracts.py',
]
REQUIRED_JS_FUNCTIONS = [
    'renderPair',
    'submitPair',
    'renderGroup',
    'submitGroup',
    'bindBirthPickers',
    'bindTimeUnknown',
    'bindCalendarControls',
    'bindCountryControls',
    'validateVisibleForm',
    'postWithProgress',
    'cancelActiveRequest',
    'durationEstimateText',
    'applyTestFixture',
    'reportNatalChart',
    'showAutoCandidate',
    'groupNetworkHtml',
    'starPositionText',
    'natalInline',
    'showInputScreen',
    'showIntroScreen',
    'returnFromInput',
    'startFromIntro',
    'initBunnyCursor',
]


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    notes: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(errors, f'필수 파일 누락: {relative}')

    template_path = ROOT / 'templates/index.html'
    js_path = ROOT / 'static/app.js'
    css_path = ROOT / 'static/styles.css'
    if '\\n' in css_path.read_text(encoding='utf-8'):
        fail(errors, 'CSS에 잘못 저장된 literal \\n escape가 남아 있습니다.')

    if template_path.is_file():
        template = template_path.read_text(encoding='utf-8')

        static_refs = re.findall(
            r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]",
            template,
        )
        for ref in sorted(set(static_refs)):
            if not (ROOT / 'static' / ref).is_file():
                fail(errors, f'템플릿이 참조하지만 존재하지 않는 정적 파일: static/{ref}')

        ids = re.findall(r'\bid=["\']([^"\']+)["\']', template)
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        if duplicates:
            fail(errors, f'중복 HTML id: {", ".join(duplicates)}')

        versions = re.findall(r"v=['\"]([^'\"]+)['\"]", template)
        if versions and len(set(versions)) != 1:
            fail(errors, f'CSS/JS/이미지 캐시 버전이 서로 다름: {sorted(set(versions))}')

        if re.search(r'\bv3\b', template, flags=re.I):
            fail(errors, '사용자 화면 템플릿에 v3 표기가 남아 있습니다.')
        if 'candy-launcher' not in template:
            fail(errors, '핑크+무지개 플로팅 메뉴 구조(candy-launcher)가 누락되어 있습니다.')
        for required in ('id="introSplash"', 'id="introStartButton"', 'id="inputBackButton"', "assets/intro-splash.png"):
            if required not in template:
                fail(errors, f'인트로→입력 화면 전환 UI 계약 누락: {required}')
        if 'approved-bunny-hero' in template:
            fail(errors, '첫 화면에 분리 렌더링하던 구형 hero 토끼 DOM이 다시 포함되어 있습니다.')
        if 'assets/input-header-rainbow-v2.png' not in template or 'input-header-static-image' not in template:
            fail(errors, '입력 화면의 정지형 토끼·무지개 헤더 아트가 누락되어 있습니다.')
        if 'assets/loading-bunny-hop.webp' not in template or 'loading-bunny-sprite' not in template:
            fail(errors, '로딩 전용 깡총 토끼 애니메이션 장면이 누락되어 있습니다.')
        if '확실히 아는 정보만 입력해도 됩니다.' in template:
            fail(errors, '삭제 요청된 내 출생정보 보조 문구가 다시 포함되어 있습니다.')

    if js_path.is_file():
        js = js_path.read_text(encoding='utf-8')
        for name in REQUIRED_JS_FUNCTIONS:
            if not re.search(rf'\bfunction\s+{re.escape(name)}\s*\(', js) and not re.search(rf'\bconst\s+{re.escape(name)}\s*=', js):
                fail(errors, f'필수 JS 함수 누락: {name}')
        if "calendar:'<svg" not in js:
            fail(errors, 'ICONS.calendar 정의가 없습니다.')
        if 'location.reload()' in js:
            fail(errors, '정보 수정에 강제 새로고침(location.reload)이 남아 있습니다.')
        if 'data-time-choice' in js or "[data-time-inputs]" in js:
            fail(errors, '이전 출생시간 UI용 이벤트 코드가 남아 있습니다.')
        if 'Math.min(12' in js or '최대 12' in js or '12명까' in js:
            fail(errors, '그룹 12명 제한으로 보이는 코드/문구가 남아 있습니다.')
        if 'durationRangeText' in js:
            fail(errors, '넓은 범위형 예상시간 표시 함수가 다시 포함되어 있습니다.')
        if 'birth_year:Number' not in js:
            fail(errors, '초기 예상시간 계산에 출생연도 정보가 전달되지 않습니다.')
        if 'shortText(' in js:
            fail(errors, '문장을 글자 수로 잘라 표시하는 shortText 로직이 다시 포함되어 있습니다.')
        if "pillarCard('시주 · 장기 관심'" not in js or "pillarCard('일주 · 나의 중심'" not in js or "pillarCard('월주 · 사회와 계절'" not in js or "pillarCard('연주 · 초기 환경'" not in js:
            fail(errors, '내 원국의 시주→일주→월주→연주 카드가 누락되어 있습니다.')
        if 'ordered=[c.hour_pillar,c.day_pillar,c.month_pillar,c.year_pillar]' not in js:
            fail(errors, '후보/요약 원국의 시주→일주→월주→연주 순서가 누락되어 있습니다.')
        if "'추천 역할 분담'" not in js or 'analysis.role_split' not in js:
            fail(errors, '그룹 1:1 해설의 관계별 역할 분담 표시가 누락되어 있습니다.')
        if 'data-group-jump' not in js or 'groupResultCopy' not in js:
            fail(errors, '그룹 결과 빠른 이동/관계유형별 사용자 문구가 누락되어 있습니다.')
        if 'includeRomance:isLove' not in js:
            fail(errors, '비연인/직장 관계에서 개인 연애 해설을 숨기는 분기가 누락되어 있습니다.')
        for required in ('profileDomainDetail', 'data-group-node', 'data-matrix-pair', 'groupPersonInspector', 'groupPairInspector'):
            if required not in js:
                fail(errors, f'고정 상세 패널/그룹 인터랙티브 탐색 UI 누락: {required}')
        if 'day_pillar' not in js or '일주' not in js:
            fail(errors, '그룹 관계도에서 구성원 일주 표시 계약이 누락되어 있습니다.')
        for required in ('data-leap-for', '${prefix}_is_leap_month', "is_leap_month:fd.get(`${prefix}_is_leap_month`)==='true'"):
            if required not in js:
                fail(errors, f'동적 1:1/그룹 음력 윤달 입력 계약 누락: {required}')
        for dead_name in ('function insightCards(', 'function groupSynthesis('):
            if dead_name in js:
                fail(errors, f'사용하지 않는 과거 JS 함수가 다시 포함되어 있습니다: {dead_name}')
        if "root.addEventListener('keydown'" not in js or "btn.addEventListener('keydown'" not in js:
            fail(errors, '그룹 매트릭스/관계도 키보드 선택 지원이 누락되어 있습니다.')
        for required in ('day_pillar_relation', 'data-group-selection-status'):
            if required not in js:
                fail(errors, f'일주 상성/관계도 선택상태 UI 계약 누락: {required}')

    if css_path.is_file():
        css = css_path.read_text(encoding='utf-8')
        if css.count('{') != css.count('}'):
            fail(errors, f'CSS 중괄호 개수가 맞지 않습니다: {{ {css.count("{")} / }} {css.count("}")}')
        if 'soft-bunny-mascot' in css or 'mini-bunny-svg' in css:
            fail(errors, '폐기한 손그림 토끼 CSS가 다시 포함되어 있습니다.')
        if '--text-control:' not in css or 'button{touch-action:manipulation;font-size:var(--text-control)}' not in css:
            fail(errors, '공통 버튼 글자 크기 토큰/기준이 누락되어 있습니다.')
        for required in ('--rainbow-soft:', '.candy-launcher{', '.loading-sky{', '@keyframes loadingFrame'):
            if required not in css:
                fail(errors, f'핑크+무지개/로딩 UI 스타일 계약 누락: {required}')
        for selector in ('.birth-picker-open{', '.time-choice-button{'):
            start = css.find(selector)
            block = css[start:css.find('}', start)+1] if start >= 0 else ''
            if 'font-size:var(--text-control)' not in block:
                fail(errors, f'입력 보조 컨트롤 글자 크기 기준 누락: {selector[:-1]}')

    for png_name in ('bunny-hero-a1.png', 'intro-splash.png'):
        png_path = ROOT / 'static/assets' / png_name
        if png_path.is_file():
            data = png_path.read_bytes()
            if len(data) < 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                fail(errors, f'{png_name} 파일이 정상 PNG로 보이지 않습니다.')

    audit_path = ROOT / 'audit_contracts.py'
    if audit_path.is_file():
        audit_proc = subprocess.run(
            [sys.executable, '-B', str(audit_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        if audit_proc.returncode != 0:
            fail(errors, 'UI/API/함수/데이터 계약 감사 실패:\n' + (audit_proc.stdout + audit_proc.stderr)[-3000:])
        else:
            match = re.search(r'TOTAL:\s*(\d+) checks / PASS (\d+) / FAIL 0', audit_proc.stdout)
            notes.append(f'UI/API/함수/데이터 매핑 감사 통과: {match.group(1)}개 계약' if match else 'UI/API/함수/데이터 매핑 감사 통과')

    visible_batch = ROOT / 'run_windows.bat'
    if visible_batch.is_file():
        batch_lines = visible_batch.read_text(encoding='utf-8').splitlines()
        visible_lines = '\n'.join(
            line for line in batch_lines if line.strip().lower().startswith('echo ')
        )
        if re.search(r'\bv3\b', visible_lines, flags=re.I):
            fail(errors, 'run_windows.bat 사용자 표시 문구에 v3가 남아 있습니다.')


    progress_text = (ROOT / 'progress_tracker.py').read_text(encoding='utf-8') if (ROOT / 'progress_tracker.py').is_file() else ''
    for required in ('auto_scan_per_year', 'auto_collect_per_candidate', 'SETTINGS.auto_shortlist_per_year', "'state': 'recalculating'", "'seconds': expected_seconds", "'seconds': remaining_seconds", 'job_total:initial'):
        if required not in progress_text:
            fail(errors, f'정밀 예상시간 로직 누락: {required}')
    if 'group_members + 1' in progress_text or "int(summary.get('group_members') or 0) + 1" in progress_text:
        fail(errors, '초기 ETA에서 그룹 인원에 사용자를 두 번 더하는 과거 로직이 남아 있습니다.')
    if "group_total_members = max(0, int(summary.get(\'group_members\') or 0))" not in progress_text:
        fail(errors, 'group_members=본인 포함 총 인원 계약이 progress_tracker에 없습니다.')

    services_text = (ROOT / 'services.py').read_text(encoding='utf-8') if (ROOT / 'services.py').is_file() else ''
    for stage_key in ('auto_scan', 'auto_collect', 'pair_collect', 'pair_score', 'group_collect', 'group_pairwise'):
        if stage_key not in services_text:
            fail(errors, f'초기 리포트 세분화 진행단계 누락: {stage_key}')
    for required in ("cache_path('pair_results'", "cache_path('group_results'", 'canonical_profile_identity'):
        if required not in services_text:
            fail(errors, f'1:1/그룹 결과 캐시 계약 누락: {required}')
    for required in ('_result_cache_usable', "'parser': SETTINGS.parser_version", "'complete_sources': bool(complete_sources)"):
        if required not in services_text:
            fail(errors, f'고수준 캐시 무효화/완전성 계약 누락: {required}')
    if 'and bool(facts.useful_elements)' not in services_text:
        fail(errors, '용신 자료가 비어 있는 결과를 완전한 원국 캐시로 간주하고 있습니다.')
    if re.search(r"(?<!_)\bbool\(data\.get\([\'\"]time_known", services_text):
        fail(errors, '문자열 false를 True로 해석할 수 있는 time_known bool 변환이 남아 있습니다.')
    if 'else bool(build_matches)' in services_text:
        fail(errors, '문자열 false가 자동추천을 켤 수 있는 build_matches bool 변환이 남아 있습니다.')

    search_text = (ROOT / 'search_engine.py').read_text(encoding='utf-8') if (ROOT / 'search_engine.py').is_file() else ''
    if "cache_path('auto_matches'" not in search_text or 'canonical_profile_identity' not in search_text:
        fail(errors, '자동 궁합 추천 결과 캐시 계약이 누락되어 있습니다.')
    for required in ('AUTO_SHORTLIST_PER_YEAR', 'shortlist_per_year', '_facts_recommendation_usable', 'verified_unique_profiles'):
        if required not in ((ROOT / '.env.example').read_text(encoding='utf-8') + search_text):
            fail(errors, f'자동 추천 shortlist/검증 후보 계약 누락: {required}')
    if '연도별 최고 생년월일시만 남겨 비교했을 때' in (ROOT / 'ai_reporter.py').read_text(encoding='utf-8'):
        fail(errors, '자동 추천 해설이 실제 2단계 shortlist 검증 방식과 다르게 설명되고 있습니다.')

    storage_text = (ROOT / 'storage.py').read_text(encoding='utf-8') if (ROOT / 'storage.py').is_file() else ''
    for required in ('canonical_profile_identity', 'legacy_profile_key', "if code != 'KR'"):
        if required not in storage_text:
            fail(errors, f'사람 단위 캐시 정규화 계약 누락: {required}')
    if "if str(profile_dict.get('calendar_type', 'solar')).lower() == 'lunar'" not in storage_text:
        fail(errors, '양력 입력의 stale 윤달 값이 캐시 키를 갈라놓지 않도록 하는 정규화가 누락되어 있습니다.')

    forceteller_text = (ROOT / 'forceteller.py').read_text(encoding='utf-8') if (ROOT / 'forceteller.py').is_file() else ''
    for required in ('_resolve_best_cached_facts', '_read_cached_folder_facts', '_clone_facts_for_profile', 'identity_rows', 'reparse_parser_version'):
        if required not in forceteller_text:
            fail(errors, f'캐시 우선/중복 조회 방지 계약 누락: {required}')
    for required in ('_parse_strength', '_parse_special_stars', '_parse_special_star_positions', '_parse_daewoon', '_reparse_cached_source'):
        if required not in forceteller_text:
            fail(errors, f'원국 상세 파서 기능 누락: {required}')
    for required in ('special_star_positions=star_positions', "'parser_version': SETTINGS.parser_version"):
        if required not in forceteller_text:
            fail(errors, f'원국 캐시 재파싱/신살 위치 저장 계약 누락: {required}')
    for required in ('_legacy_profile_mapping', "raw.get('birth_date')", "raw.get('birth_time')", '_historical_data_roots'):
        if required not in forceteller_text:
            fail(errors, f'과거 캐시/manifest 재사용 계약 누락: {required}')
    for required in ('canonical_profile_identity', 'legacy_profile_key', '_profile_cache_folder'):
        if required not in forceteller_text:
            fail(errors, f'원국 캐시 통합 계약 누락: {required}')
    for required in ('reparsed_data = facts.as_dict()', '_cached_facts_usable(reparsed_data, False)', 'not _cached_facts_need_reparse(reparsed_data, folder)'):
        if required not in forceteller_text:
            fail(errors, f'불완전 재파싱 결과를 성공 캐시로 고정하지 않는 계약 누락: {required}')
    if 'needs_reparse = parser_changed or _cached_facts_need_reparse' not in forceteller_text or 'if needs_reparse:' not in forceteller_text:
        fail(errors, '원문에 핵심 정보가 있는데 구조화 캐시가 비어 있어도 재파싱을 거치지 않는 위험한 경로가 남아 있습니다.')
    for required in ("chart.get('day_pillar')", "_legacy_value(data, 'strength_label'", "_legacy_value(data, 'useful_elements'"):
        if required not in forceteller_text:
            fail(errors, f'Forceteller 캐시 핵심 필드 완전성 검사 누락: {required}')
    if 'singang' not in forceteller_text or '_parse_strength' not in forceteller_text:
        fail(errors, '포스텔러 신강·신약 전용 파서 계약이 누락되어 있습니다.')
    if not (('daeun{idx}{side}' in forceteller_text and 'data-test-id' in forceteller_text) or 'daeun(\\d+)(top|bottom)' in forceteller_text):
        fail(errors, '포스텔러 data-test-id 기반 대운 파서 계약이 누락되어 있습니다.')
    for required in ('stable_hash', '_extract_star_names', '_STAR_TOKEN_RE'):
        if required not in forceteller_text:
            fail(errors, f'과거 캐시 식별/신살 동적 구조화 계약 누락: {required}')

    explain_text = (ROOT / 'explain.py').read_text(encoding='utf-8') if (ROOT / 'explain.py').is_file() else ''
    appjs_text = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8') if (ROOT / 'static' / 'app.js').is_file() else ''
    for required in ('_chart_detail_report', "'chart_detail': _chart_detail_report(facts)"):
        if required not in explain_text:
            fail(errors, f'원국 미리보기와 상세 해설 분리 계약 누락: {required}')
    for required in ('chartDetailHtml', '네 기둥이 맡는 역할', '계절·강약·균형'):
        if required not in appjs_text:
            fail(errors, f'원국 상세 UI 구조 누락: {required}')

    fortune_text = (ROOT / 'fortune.py').read_text(encoding='utf-8') if (ROOT / 'fortune.py').is_file() else ''
    for required in ("PERIOD_SCOPE =", "'year': {", "'month': {", "'day': {", 'current_daewoon'):
        if required not in fortune_text:
            fail(errors, f'기간별 운세/대운 로직 누락: {required}')
    if '현재는 만 {start_age}' in fortune_text:
        fail(errors, '대운표 시작 나이를 서양식 만 나이로 오표기하고 있습니다.')

    explain_text = (ROOT / 'explain.py').read_text(encoding='utf-8') if (ROOT / 'explain.py').is_file() else ''
    if "'key': 'hour', 'label': '시주'" not in explain_text or "{'key': 'day', 'label': '일주'" not in explain_text:
        fail(errors, '원국 상세 보고서의 시주→일주→월주→연주 순서 계약이 누락되어 있습니다.')
    if "'each_needs': wants" not in explain_text or "'role_split': role_split" not in explain_text:
        fail(errors, '궁합의 실생활 비교(각자 원하는 것/역할 분담) 해설이 누락되어 있습니다.')
    if "context: str = \"\"" not in explain_text or "context == 'work'" not in explain_text:
        fail(errors, '관계 유형별 실생활 궁합 해설 분기가 누락되어 있습니다.')
    if '_day_pillar_relation_summary' not in explain_text or "'day_pillar_relation':" not in explain_text:
        fail(errors, '일주 조합 한눈에 보기용 구조화 해설이 누락되어 있습니다.')
    if '_contextual_pair_label' not in explain_text:
        fail(errors, '연인/직장/가족/모임 관계 유형별 사용자용 궁합 라벨이 누락되어 있습니다.')
    for required in ('_star_domain_insights', '_pair_star_interplay', "'star_insights':"):
        if required not in explain_text:
            fail(errors, f'신살·길성을 실제 생활 해설에 연결하는 계약 누락: {required}')

    # 내부 데이터 출처명은 사용자 화면/해설에 노출하지 않는다.
    for visible_path in (ROOT / 'templates', ROOT / 'static'):
        if visible_path.exists():
            for file in visible_path.rglob('*'):
                if file.is_file() and file.suffix.lower() in {'.html','.js','.css'}:
                    text=file.read_text(encoding='utf-8',errors='ignore')
                    if '포스텔러' in text:
                        fail(errors, f'사용자 화면에 내부 데이터 출처명이 남아 있습니다: {file.relative_to(ROOT)}')
    if '포스텔러' in explain_text:
        fail(errors, '사용자 해설 데이터에 내부 데이터 출처명이 남아 있습니다.')

    group_text = (ROOT / 'group.py').read_text(encoding='utf-8') if (ROOT / 'group.py').is_file() else ''
    if "pair_report['context'] = context" not in group_text or "scoring_mode: Mode = 'friend'" not in group_text:
        fail(errors, '그룹 비연인 분석 계약(work context/friend scoring)이 누락되어 있습니다.')
    if "context = context if context in GROUP_CONTEXTS else 'friends'" not in group_text:
        fail(errors, '허용되지 않은 그룹 유형을 friends로 안전하게 정규화하는 계약이 누락되어 있습니다.')
    if "'label': pair_report.get('label', result.label)" not in group_text:
        fail(errors, '그룹 pair 라벨이 친구용 원시 라벨로 회귀할 수 있습니다.')
    if '_group_summary(' not in group_text or "'work':" not in group_text or "'family':" not in group_text or "'hobby':" not in group_text:
        fail(errors, '그룹 유형별 요약 분기가 누락되어 있습니다.')

    ai_text = (ROOT / 'ai_reporter.py').read_text(encoding='utf-8') if (ROOT / 'ai_reporter.py').is_file() else ''
    if 'period_pairs' not in ai_text:
        fail(errors, '올해/이번 달/오늘 AI 문장 중복 방지 로직이 누락되어 있습니다.')
    if '호감·애정표현·배우자·데이트·연애 같은 표현을 절대 사용하지 않는다' not in ai_text:
        fail(errors, '직장 그룹 비연애 해설 프롬프트 계약이 누락되어 있습니다.')

    if 'text(overview)||text(p.personality)' not in js:
        fail(errors, '내 사주 첫 문장이 로컬 사용자 중심 해설보다 AI 문장을 우선하는 과거 순서로 회귀했습니다.')
    if '오행·용신·십성·천간·지지 관계를 하나씩 확인하고 있어요.' in js:
        fail(errors, '대기 화면에 일반 사용자가 바로 이해하기 어려운 명리 전문용어 나열이 남아 있습니다.')

    app_text = (ROOT / 'app.py').read_text(encoding='utf-8') if (ROOT / 'app.py').is_file() else ''
    if '/api/progress/<job_id>/cancel' not in app_text:
        fail(errors, '분석 중단 API가 app.py에 없습니다.')
    if "{'initial', 'pair', 'group'}" not in app_text:
        fail(errors, '진행률 API가 initial/pair/group 세 종류를 모두 지원하는지 확인이 필요합니다.')
    if "@app.get('/test')" not in app_text or '_is_local_request' not in app_text:
        fail(errors, 'localhost 전용 /test 화면 라우팅이 누락되어 있습니다.')
    if "force_ai=bool(data.get('force_ai'" in app_text:
        fail(errors, 'force_ai 문자열 false를 True로 해석할 수 있는 API bool 변환이 남아 있습니다.')

    fixture_path = ROOT / 'test_fixture.py'
    if fixture_path.is_file():
        import runpy
        try:
            fixture_ns = runpy.run_path(str(fixture_path))
            fixture = fixture_ns.get('FULL_TEST_FIXTURE') or {}
            profile = fixture.get('profile') or {}
            pair = (fixture.get('pair') or {}).get('profile') or {}
            group = fixture.get('group') or {}
            members = group.get('members') or []
            names = [profile.get('name'), pair.get('name'), *[row.get('name') for row in members]]
            if any(not name for name in names):
                fail(errors, '테스트 fixture에 이름이 비어 있는 구성원이 있습니다.')
            if len(names) != len(set(names)):
                fail(errors, '테스트 fixture에 중복 이름이 있습니다.')
            if group.get('context') != 'work':
                fail(errors, '통합 테스트 그룹 유형은 work(직장·프로젝트 팀)여야 합니다.')
            if len(members) != 14:
                fail(errors, f'통합 테스트 직장동료 수가 14명이 아닙니다: {len(members)}명')
            if fixture.get('build_matches') is not True:
                fail(errors, '통합 테스트에서 잘 맞는 사람 찾기가 활성화되어 있지 않습니다.')
            if (fixture.get('pair') or {}).get('mode') != 'love':
                fail(errors, '통합 테스트 1:1 궁합 모드는 love여야 합니다.')
            total_group = len(members) + 1
            notes.append(f'통합 테스트 fixture 확인: 전체 {len(names)}명, 그룹 {total_group}명 · {total_group * (total_group - 1) // 2}개 관계')
        except Exception as exc:
            fail(errors, f'테스트 fixture 검증 실패: {exc}')

    dead_python_symbols = {
        'bazi_engine.py': ('calculate_chart_from_solar', 'solar_tuple'),
        'models.py': ('PeriodFortune',),
        'ai_reporter.py': ('_score_number',),
        'explain.py': ('_spouse_star_counts', '_axis_by_key'),
        'search_engine.py': ('search_ideal_birthdates',),
    }
    for filename, symbols in dead_python_symbols.items():
        text = (ROOT / filename).read_text(encoding='utf-8') if (ROOT / filename).is_file() else ''
        for symbol in symbols:
            if re.search(rf'\b(?:def|class)\s+{re.escape(symbol)}\b', text):
                fail(errors, f'사용하지 않는 과거 Python 심볼이 다시 포함되어 있습니다: {filename}:{symbol}')

    # Release hygiene: partial-patch backup/cache files must not be shipped.
    leftovers = []
    for path in ROOT.rglob('*'):
        rel = path.relative_to(ROOT)
        if any(
            part in {'venv', 'data', 'cache'} or part.startswith('.venv')
            for part in rel.parts
        ):
            continue
        if path.is_file() and ('.bak' in path.name or path.suffix == '.pyc'):
            leftovers.append(str(rel))
        elif path.is_dir() and path.name in {'__pycache__', '.pytest_cache'}:
            leftovers.append(str(rel) + '/')
    if leftovers:
        fail(errors, '배포본에 임시 백업/캐시 파일이 남아 있습니다: ' + ', '.join(sorted(leftovers)[:12]))

    # Syntax-check every project Python file without generating __pycache__.
    for path in ROOT.rglob('*.py'):
        if any(
            part in {'venv', '__pycache__', 'data', 'cache'} or part.startswith('.venv')
            for part in path.relative_to(ROOT).parts
        ):
            continue
        try:
            source = path.read_text(encoding='utf-8')
            compile(source, str(path), 'exec')
        except Exception as exc:
            fail(errors, f'Python 문법 오류: {path.relative_to(ROOT)}: {exc}')

    node = shutil.which('node')
    if node and js_path.is_file():
        result = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
        if result.returncode != 0:
            fail(errors, f'JavaScript 문법 오류: {result.stderr.strip()}')
        else:
            notes.append('JavaScript node --check 통과')
    else:
        notes.append('Node.js가 없어 JavaScript 런타임 문법 검사는 건너뜀')

    if errors:
        print('VERIFY FAILED')
        for item in errors:
            print(f'  - {item}')
        if notes:
            print('\n참고:')
            for item in notes:
                print(f'  - {item}')
        return 1

    print('VERIFY OK')
    print('  - 필수 파일/이미지 자산 확인')
    print('  - 템플릿 정적 파일 참조 확인')
    print('  - 중복 HTML id 없음')
    print('  - CSS 구조 확인')
    print('  - Python 문법 검사 통과')
    for item in notes:
        print(f'  - {item}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
