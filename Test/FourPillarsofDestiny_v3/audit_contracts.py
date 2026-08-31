from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
HTML = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
JS = (ROOT / 'static/app.js').read_text(encoding='utf-8')
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SERVICES = (ROOT / 'services.py').read_text(encoding='utf-8')
CSS = (ROOT / 'static/styles.css').read_text(encoding='utf-8')


def function_body(name: str) -> str:
    match = re.search(rf'\b(?:async\s+)?function\s+{re.escape(name)}\s*\(', JS)
    if not match:
        return ''
    next_match = re.search(r'\n\s*(?:async\s+)?function\s+\w+\s*\(', JS[match.end():])
    end = match.end() + next_match.start() if next_match else len(JS)
    return JS[match.start():end]


checks: list[tuple[str, bool]] = []


def check(label: str, condition: bool) -> None:
    checks.append((label, bool(condition)))


for page in ['profile', 'fortune', 'auto', 'pair', 'group', 'details']:
    check(f'nav/page mapping: {page}', f'data-page="{page}"' in HTML and f'id="page-{page}"' in HTML)

routes = {
    '/api/config': "@app.get('/api/config')",
    '/api/progress/estimate': "@app.post('/api/progress/estimate')",
    '/api/progress/start': "@app.post('/api/progress/start')",
    '/api/initial': "@app.post('/api/initial')",
    '/api/pair': "@app.post('/api/pair')",
    '/api/group': "@app.post('/api/group')",
}
for endpoint, decorator in routes.items():
    check(f'endpoint mapping: {endpoint}', endpoint in JS and decorator in APP)

for fn in ['birth_profile_from_dict', 'initial_analysis', 'pair_analysis', 'group_analysis']:
    check(
        f'service mapping: {fn}',
        re.search(rf'from services import[^\n]*\b{fn}\b', APP) is not None
        and re.search(rf'^def {fn}\s*\(', SERVICES, re.M) is not None,
    )

profile_keys = ['name', 'gender', 'calendar_type', 'is_leap_month', 'year', 'month', 'day',
                'hour', 'minute', 'time_known', 'country_code', 'country', 'city', 'partner_gender']
main_profile = function_body('mainProfile')
dynamic_profile = function_body('profileFromPrefix')
for key in profile_keys:
    check(f'main profile key: {key}', key in main_profile)
for key in [x for x in profile_keys if x != 'partner_gender']:
    check(f'dynamic profile key: {key}', key in dynamic_profile or (key in {'year', 'month', 'day'} and 'parseDate' in dynamic_profile))

initial = function_body('submitInitial')
for key in ['profile', 'build_matches', 'pair_request', 'group_request', 'ai_cache_only']:
    check(f'initial request key: {key}', key in initial and f"data.get('{key}'" in APP)

for name in ['renderProfile', 'renderFortune', 'renderAuto', 'renderPair', 'renderGroup',
             'bindBirthPickers', 'postWithProgress', 'cancelActiveRequest']:
    check(f'frontend function: {name}', bool(function_body(name)))

for element_id in ['loading', 'loadingStage', 'loadingPercent', 'loadingProgressFill',
                   'loadingRemaining', 'loadingSteps', 'cancelAnalysisButton']:
    check(f'loading mapping: {element_id}', f'id="{element_id}"' in HTML and f'#{element_id}' in JS)

check('loading image exists', (ROOT / 'static/assets/loading-bunny-hop.webp').is_file())
check('loading motion exists', '@keyframes loadingBunnyHop' in CSS and '@keyframes loadingBunnyShadow' in CSS and '.loading-bunny-sprite' in CSS)
check('responsive layout exists', '@media(max-width:620px)' in CSS)
check('reduced motion fallback exists', 'prefers-reduced-motion:reduce' in CSS)
check('keyboard group exploration exists', "addEventListener('keydown'" in JS)

failed = [label for label, ok in checks if not ok]
if failed:
    print('CONTRACT AUDIT FAILED')
    for label in failed:
        print(f'  - {label}')
    raise SystemExit(1)

print(f'CONTRACT AUDIT OK ({len(checks)} checks)')
