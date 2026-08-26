from __future__ import annotations

import re
import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
JS = (ROOT / 'static/app.js').read_text(encoding='utf-8')
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SERVICES = (ROOT / 'services.py').read_text(encoding='utf-8')
PROGRESS = (ROOT / 'progress_tracker.py').read_text(encoding='utf-8')
CSS = (ROOT / 'static/styles.css').read_text(encoding='utf-8')
EXPLAIN = (ROOT / 'explain.py').read_text(encoding='utf-8')
FORTUNE = (ROOT / 'fortune.py').read_text(encoding='utf-8')

checks: list[tuple[str, bool, str]] = []

def check(name: str, condition: bool, detail: str = '') -> None:
    checks.append((name, bool(condition), detail))

# 1) Navigation DOM ↔ renderer page ids
pages = ['profile', 'fortune', 'auto', 'pair', 'group', 'details']
for page in pages:
    check(
        f'nav/page mapping: {page}',
        f'data-page="{page}"' in HTML and f'id="page-{page}"' in HTML,
        'nav button and target page section must both exist',
    )

# 2) JS fetch endpoints ↔ Flask routes
route_pairs = [
    ('/api/config', "@app.get('/api/config')"),
    ('/api/progress/estimate', "@app.post('/api/progress/estimate')"),
    ('/api/progress/start', "@app.post('/api/progress/start')"),
    ('/api/initial', "@app.post('/api/initial')"),
    ('/api/pair', "@app.post('/api/pair')"),
    ('/api/group', "@app.post('/api/group')"),
]
for endpoint, decorator in route_pairs:
    check(f'endpoint mapping: {endpoint}', endpoint in JS and decorator in APP)
check('progress poll route', '/api/progress/${encodeURIComponent(jobId)}' in JS and "@app.get('/api/progress/<job_id>')" in APP)
check('progress cancel route', '/api/progress/${encodeURIComponent(current.jobId)}/cancel' in JS and "@app.post('/api/progress/<job_id>/cancel')" in APP)

# 3) Flask imports ↔ service function definitions
for fn in ['birth_profile_from_dict', 'initial_analysis', 'pair_analysis', 'group_analysis']:
    check(
        f'function mapping: {fn}',
        re.search(rf'from services import[^\n]*\b{fn}\b', APP) is not None
        and re.search(rf'^def {fn}\s*\(', SERVICES, re.M) is not None,
    )

# 4) Main profile payload keys ↔ BirthProfile parser consumption
profile_keys = [
    'name','gender','calendar_type','is_leap_month','year','month','day','hour','minute',
    'time_known','country_code','country','city','location_id','partner_gender',
]
submit_block = JS[JS.index("$('#profileForm').addEventListener('submit'"):]
for key in profile_keys:
    payload_has = re.search(rf'\b{re.escape(key)}\s*:', submit_block) is not None or re.search(rf'[,{{]\s*{re.escape(key)}\s*[,}}]', submit_block) is not None
    check(f'main profile payload key: {key}', payload_has)
    service_has = (
        f"data.get('{key}'" in SERVICES
        or f'data.get("{key}"' in SERVICES
        or f"_required_int(data, '{key}'" in SERVICES
    )
    check(f'service accepts profile key: {key}', service_has)

# 5) Dynamic pair/group person builder uses same contract
for key in profile_keys:
    # partner_gender is parameter-derived; the rest should appear in dataFromForm.
    dynamic_block = JS[JS.index('function dataFromForm'):JS.index('function readTestFixture')]
    dynamic_has = f'{key}:' in dynamic_block or re.search(rf'[,{{]\s*{re.escape(key)}\s*[,}}]', dynamic_block) is not None
    check(f'dynamic profile payload key: {key}', dynamic_has)

# 6) Initial orchestration keys UI ↔ Flask ↔ services
for key in ['profile','build_matches','pair_request','group_request','ai_cache_only']:
    check(f'initial request key: {key}', key in submit_block and f"data.get('{key}'" in APP)
for key in ['pair_request','group_request']:
    check(f'initial service mapping: {key}', f'{key}=data.get' in APP and key in SERVICES)

# 7) Pair/group endpoint payloads
for key in ['user','target','mode']:
    check(f'pair request key: {key}', key in JS[JS.index('async function submitPair'):JS.index('function memberForm')] and f"data.get('{key}'" in APP)
for key in ['members','context']:
    check(f'group request key: {key}', key in JS[JS.index('async function submitGroup'):JS.index('function registerGroupPairs')] and f"data.get('{key}'" in APP)

# 8) Initial response schema ↔ renderers
initial_keys = ['profile','facts','profile_local','fortunes','auto_matches','request_options','ideal_love','ideal_friend','pair_reports','ai','initial_pair','initial_group','glossary']
for key in initial_keys:
    check(f'initial response schema: {key}', f"'{key}':" in SERVICES)
    # Some are read through d.foo, some state.initial.foo.
    check(f'initial renderer consumes: {key}', f'.{key}' in JS or f"['{key}']" in JS)

# 9) Pair/group response schema ↔ renderers
for key in ['user_facts','target_facts','result','report','synthesis']:
    check(f'pair response schema: {key}', f"'{key}':" in SERVICES)
for key in ['members','analysis','synthesis']:
    check(f'group response schema: {key}', f"'{key}':" in SERVICES)

# 10) Loading UI DOM ↔ progress JS
for element_id in ['loading','loadingTitle','loadingText','loadingStage','loadingPercent','loadingProgressFill','loadingExpected','loadingRemaining','loadingSteps','cancelAnalysisButton']:
    check(f'loading DOM id: {element_id}', f'id="{element_id}"' in HTML and f"#{element_id}" in JS)
check('single cohesive loading bunny scene', 'loading-bunny-sprite' in HTML and 'assets/loading-bunny-hop.webp' in HTML and (ROOT / 'static/assets/loading-bunny-hop.webp').is_file())
check('legacy loading frame sequence removed', 'frame-1' not in HTML and 'frame-5' not in HTML)

# 11) Actual fixture -> BirthProfile parser roundtrip (solar rows do not need lunar calculation)
try:
    try:
        import lunar_python  # type: ignore  # noqa: F401
    except Exception:
        import sys, types
        stub = types.ModuleType('lunar_python')
        class _DummyLunarSolar:
            @classmethod
            def fromYmdHms(cls, *args, **kwargs):
                return cls()
        stub.Lunar = _DummyLunarSolar
        stub.Solar = _DummyLunarSolar
        sys.modules['lunar_python'] = stub
    from test_fixture import FULL_TEST_FIXTURE
    from services import birth_profile_from_dict
    fixture_rows = [FULL_TEST_FIXTURE['profile'], FULL_TEST_FIXTURE['pair']['profile'], *FULL_TEST_FIXTURE['group']['members']]
    parsed_rows = [birth_profile_from_dict(row).as_dict() for row in fixture_rows]
    check('fixture BirthProfile roundtrip: all 16', len(parsed_rows) == 16 and all(isinstance(row['year'], int) and row['gender'] in {'F','M'} for row in parsed_rows))
    unknown_rows = [row for row in parsed_rows if row['time_known'] is False]
    check('unknown birth time contract', len(unknown_rows) == 1 and unknown_rows[0]['hour'] == 12 and unknown_rows[0]['minute'] == 0)
    group_total = 1 + len(FULL_TEST_FIXTURE['group']['members'])
    check('group fixture relation count', group_total == 15 and group_total * (group_total - 1) // 2 == 105)
except Exception as exc:
    check('fixture BirthProfile roundtrip: all 16', False, str(exc))
    check('unknown birth time contract', False, str(exc))
    check('group fixture relation count', False, str(exc))

# 12) Synthetic structuring audit: calculation objects -> user-facing structured data
try:
    from datetime import datetime
    from models import BirthProfile, Chart, ForcetellerFacts
    from explain import build_pair_report, build_profile_report
    from scoring import score_pair
    from group import analyze_group
    import fortune as fortune_module
    from quality import validate_fortunes, validate_group_analysis, validate_pair_report, validate_profile_report

    def _synthetic_facts(name, gender, pillars, dm, spouse, elements, *, time_known=True):
        p = BirthProfile(name=name, gender=gender, calendar_type='solar', year=1994, month=12, day=7, hour=5 if time_known else 12, minute=30 if time_known else 0, time_known=time_known)
        c = Chart(
            year_pillar=pillars[0], month_pillar=pillars[1], day_pillar=pillars[2], hour_pillar=pillars[3] if time_known else '',
            day_master=dm, spouse_palace=spouse,
            stems=[x[0] for x in pillars], branches=[x[1] for x in pillars], element_percent_local=elements,
        )
        return ForcetellerFacts(
            p, c, elements,
            ten_gods={'비견':12.5,'겁재':0.0,'식신':12.5,'상관':12.5,'정재':12.5,'편재':0.0,'정관':12.5,'편관':12.5,'정인':12.5,'편인':12.5},
            strength_label='중화신강', useful_elements=['火'], useful_element_detail='화(억부용신)',
            special_stars=['도화살','월덕귀인'], special_star_positions={'시주':['도화살'],'일주':['월덕귀인']},
            daewoon=[{'age':3,'pillar':'戊子'},{'age':13,'pillar':'己丑'},{'age':23,'pillar':'庚寅'}],
            source_quality=95, source='forceteller_cache',
        )

    fa=_synthetic_facts('A','F',['甲戌','乙亥','丁卯','壬寅'],'丁','卯',{'木':50.0,'火':12.5,'土':12.5,'金':0.0,'水':25.0})
    fb=_synthetic_facts('B','M',['戊寅','壬戌','乙巳','庚辰'],'乙','巳',{'木':25.0,'火':25.0,'土':25.0,'金':12.5,'水':12.5})
    fc=_synthetic_facts('C','F',['辛未','丁酉','癸丑','甲寅'],'癸','丑',{'木':12.5,'火':12.5,'土':25.0,'金':25.0,'水':25.0},time_known=False)

    profile_report=build_profile_report(fa)
    profile_issues=validate_profile_report(profile_report,path='synthetic.profile')
    check('structured profile data populated', not profile_issues, '; '.join(x.reason for x in profile_issues[:3]))
    check('profile pillar mapping order/value', [x.get('key') for x in profile_report['chart']['pillars']]==['hour','day','month','year'] and all(x.get('value') for x in profile_report['chart']['pillars']))

    pair_result=score_pair(fa,fb,'love')
    pair_report=build_pair_report(fa,fb,pair_result)
    pair_issues=validate_pair_report(pair_report,expected_a='A',expected_b='B',path='synthetic.pair')
    check('structured pair data populated', not pair_issues, '; '.join(x.reason for x in pair_issues[:3]))
    check('pair practical content populated', len(pair_report.get('reality_checks') or [])>=3 and all(pair_report['analysis'].get(k) for k in ('fit','friction_scene','communication','role_split','daily_life','long_term')))

    group=analyze_group([fa,fb,fc],'friend',context='work')
    group_issues=validate_group_analysis(group,member_names=['A','B','C'],path='synthetic.group')
    check('structured group data populated', not group_issues, '; '.join(x.reason for x in group_issues[:3]))
    check('group people/pair/matrix mapping', group.get('names')==['A','B','C'] and len(group.get('pairwise') or [])==3 and len(group.get('matrix') or [])==3)
    check('work group practical non-romance content', group.get('context')=='work' and group.get('mode')=='friend' and bool(group.get('team_actions')) and all(row.get('report',{}).get('analysis',{}).get('decision') for row in group.get('pairwise',[])))

    original_period_pillars=fortune_module.period_pillars
    fortune_module.period_pillars=lambda _moment:{'year':'丙午','month':'甲申','day':'壬子','hour':'戊申'}
    try:
        fortunes=fortune_module.build_fortunes(fa,datetime(2026,8,18,12,0,0))
    finally:
        fortune_module.period_pillars=original_period_pillars
    fortune_issues=validate_fortunes(fortunes,path='synthetic.fortunes')
    check('structured fortune data populated', not fortune_issues, '; '.join(x.reason for x in fortune_issues[:3]))
    check('year/month/day fortune content distinct', len({fortunes['yearly']['summary'],fortunes['monthly']['summary'],fortunes['daily']['summary']})==3)
except Exception as exc:
    for name in ('structured profile data populated','profile pillar mapping order/value','structured pair data populated','pair practical content populated','structured group data populated','group people/pair/matrix mapping','work group practical non-romance content','structured fortune data populated','year/month/day fortune content distinct'):
        check(name, False, str(exc))

# 13) Known regression guards
check('group 12-person limit absent', 'Math.min(12' not in JS and '12명까' not in JS and '최대 12' not in JS)
check('work context is non-romance', "r.context==='work'" in JS and "analyze_group(\n        facts,\n        'friend'" in SERVICES)
check('user-facing internal source name absent', '포스텔러' not in HTML and '포스텔러' not in JS)
check('pink-rainbow launcher present', 'candy-launcher' in HTML and '--rainbow-soft:' in (ROOT / 'static/styles.css').read_text(encoding='utf-8'))
check('splash artwork asset present', 'assets/intro-splash.png' in HTML and (ROOT / 'static/assets/intro-splash.png').is_file())
check('splash start -> input DOM mapping', all(x in HTML for x in ('id="introSplash"','id="introStartButton"','id="onboarding"','id="inputBackButton"')) and all(x in JS for x in ('showInputScreen','showIntroScreen','#introStartButton','#inputBackButton')))
check('legacy split hero removed', 'approved-bunny-hero' not in HTML)
check('dynamic pair/group forms preserve target ids', 'id="initialPairFields"' in HTML and 'id="initialGroupFields"' in HTML and "optionToggle('include_pair','#initialPairFields'" in JS and "optionToggle('include_group','#initialGroupFields'" in JS)
check('intro does not replace functional input form', 'id="profileForm"' in HTML and 'name="year"' in HTML and 'name="month"' in HTML and 'name="day"' in HTML and "$('#profileForm').addEventListener('submit'" in JS)

# 14) R26 ETA/UI regression guards
check('timing metrics use clean live_v2 namespace', "_METRIC_NAMESPACE = 'live_v2'" in PROGRESS)
check('fixture/test runs disable timing learning', 'disable_timing_learning' in JS and "record_metrics = timing_profile == 'live' and not disable_learning" in PROGRESS)
check('cache shortcuts do not train ETA', '_CACHE_HINTS' in PROGRESS and 'not self.cache_shortcut' in PROGRESS)
check('standalone group baseline matches initial collection cost', "fallback_per_unit=4.0" in PROGRESS and "def _group_stages" in PROGRESS)
check('uncalibrated ETA renders friendly range', 'friendlyEstimateRange' in JS and 'value.calibrated===false' in JS)
check('main option colors map pink violet blue', ('--r27-pink' in CSS or '--r28-pink' in CSS) and ('--r27-violet' in CSS or '--r28-lav' in CSS) and ('--r27-blue' in CSS or '--r28-sky' in CSS) and '.option-card:nth-child(3)' in CSS)
check('group chooser uses concise descriptions', "short:'역할 분담 · 의사결정 · 실행 속도'" in JS and 'ui.short||row.desc' in JS)

check('special stars include personal pillar context', '_star_personal_note' in EXPLAIN and "'personal_note'" in EXPLAIN and 'starPositionMapHtml' in JS)
check('special stars use actual position and day element', '_star_position_tip' in EXPLAIN and '_day_element_tip' in EXPLAIN and 'star-chart-signature' in JS)
check('daewoon exposes clickable period detail', "'periods': periods" in FORTUNE and 'data-daewoon-index' in JS and 'daewoonPeriodDetailHtml' in JS)
check('group day element visual contract', 'element_relation_label' in EXPLAIN and 'dayRelationVisual' in JS and 'groupElementLegend' in JS)
check('auto-match empty state still gives profile-based relationship guide', 'compatibilityGuideFromProfile' in JS and 'romance_dimensions' in JS)

check('recommendation rows carry explicit candidate key', "payload['candidate_key'] = _candidate_key(c.profile)" in (ROOT / 'search_engine.py').read_text(encoding='utf-8'))
check('candidate detail uses server candidate key', 'row.candidate_key||profileKey(row.profile)' in JS)
check('recommendation cache accepts source-backed partial facts', '_facts_recommendation_usable' in (ROOT / 'search_engine.py').read_text(encoding='utf-8') and "cache_policy': 'cache_first_manual_refresh'" in (ROOT / 'search_engine.py').read_text(encoding='utf-8'))
check('partial Forceteller cache is not retried by default', "RETRY_PARTIAL_FACTS', False" in (ROOT / 'config.py').read_text(encoding='utf-8'))
check('markdown emphasis markers are stripped before display', r"replace(/\*\*/g,'')" in JS and "function richText(v=''){return esc(plainText(v))" in JS)
check('legacy output candidate cache is searched', "SETTINGS.root / 'output'" in (ROOT / 'forceteller.py').read_text(encoding='utf-8') and "raw.get('condition')" in (ROOT / 'forceteller.py').read_text(encoding='utf-8'))
check('ranked recommendation cache ignores failed losers', '_ranked_sources_reusable' in (ROOT / 'search_engine.py').read_text(encoding='utf-8') and 'unusable_shortlist_profiles' in (ROOT / 'search_engine.py').read_text(encoding='utf-8'))
check('result cache separates reusable from complete sources', "'reusable_sources': reusable" in SERVICES and "cache_policy': 'source-cache-first-no-network-refresh'" in SERVICES)
check('loading hopping bunny asset present', 'assets/loading-bunny-hop.webp' in HTML and (ROOT / 'static/assets/loading-bunny-hop.webp').is_file() and (ROOT / 'static/assets/loading-bunny-hop-fallback.png').is_file())
check('header uses one static fused illustration layer', 'input-header-static-image' in HTML and 'assets/input-header-art.jpg' in HTML and 'input-header-bunny' not in HTML and 'input-deco-rainbow' not in HTML)
check('loading uses animated hop sprite instead of sticker mascot', 'loading-bunny-sprite' in HTML and 'loading-mascot-img' not in HTML)
check('input subtitle removed', '확실히 아는 정보만 입력해도 됩니다.' not in HTML)
check('page background persists during scroll', 'background-attachment:fixed!important' in CSS and 'body:not(.intro-active)' in CSS)
check('css escaped-newline corruption absent', '\\n' not in CSS)
check('canonical source cache has fast path before legacy scan', 'Fast path: most repeat requests should stop here' in (ROOT / 'forceteller.py').read_text(encoding='utf-8'))
check('same birth identity is collected once per request', 'identity_rows' in (ROOT / 'forceteller.py').read_text(encoding='utf-8') and '_clone_facts_for_profile' in (ROOT / 'forceteller.py').read_text(encoding='utf-8'))
check('partial raw cache reparse is bounded per parser revision', 'reparse_parser_version' in (ROOT / 'forceteller.py').read_text(encoding='utf-8') and 'partial_already_tried' in (ROOT / 'forceteller.py').read_text(encoding='utf-8'))
check('optional source gaps never authorize automatic external refresh', 'Only an explicit' in (ROOT / 'forceteller.py').read_text(encoding='utf-8') and 'force=True' in (ROOT / 'forceteller.py').read_text(encoding='utf-8'))
check('example env keeps partial retry disabled', 'RETRY_PARTIAL_FACTS=0' in (ROOT / '.env.example').read_text(encoding='utf-8'))

failed = [row for row in checks if not row[1]]
for name, ok, detail in checks:
    print(('PASS' if ok else 'FAIL').ljust(4), '-', name, (f'({detail})' if detail and not ok else ''))
print(f'\nTOTAL: {len(checks)} checks / PASS {len(checks)-len(failed)} / FAIL {len(failed)}')
if failed:
    raise SystemExit(1)
print('CONTRACT AUDIT OK')
