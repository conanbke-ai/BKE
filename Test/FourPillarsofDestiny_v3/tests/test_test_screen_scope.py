from app import app
from pathlib import Path


def test_regular_screen_never_exposes_local_test_fixture():
    client = app.test_client()
    response = client.get('/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-test-mode="false"' in html
    assert 'data-test-fixture-available="false"' in html
    assert 'id="quickTestFixtureButton"' not in html
    assert 'id="testFixtureData"' not in html


def test_local_test_screen_exposes_complete_fixture_summary():
    client = app.test_client()
    response = client.get('/test', environ_base={'REMOTE_ADDR': '127.0.0.1'})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-test-mode="true"' in html
    assert 'id="quickTestFixtureButton"' in html
    assert 'id="testFixtureData"' in html
    assert '그룹 14명' in html
    assert '총 16명' in html
    assert '<body class="intro-active"' in html
    assert 'id="introSplash" class="intro-splash"' in html
    assert 'id="onboarding" class="onboarding input-screen card bunny-surface hidden"' in html


def test_information_edit_can_return_to_the_existing_report():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    html = (root / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'function returnFromInput()' in js
    assert "$('#resetButton').onclick=()=>showInputScreen({fromReport:true})" in js
    assert "$('#inputBackButton').onclick=returnFromInput" in js
    assert 'state.reportReturnPage=state.activePage' in js
    assert 'id="inputBackLabel"' in html


def test_test_fixture_waits_until_the_shared_intro_is_started():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')

    assert 'function startFromIntro()' in js
    assert "$('#introStartButton').onclick=startFromIntro" in js
    assert "document.body.dataset.testMode==='true'&&!state.testFixtureApplied" in js
    assert "setInputBackMode(false);if(document.body.dataset.testMode==='true')applyTestFixture()" not in js


def test_rainbow_pink_theme_keeps_mobile_title_bunny_and_buttons_aligned():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'templates' / 'index.html').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')

    assert 'class="intro-mobile-copy"' in html
    assert '20260827-rainbow-cloud-09' in html
    assert 'cute rainbow-pink visual system and responsive control alignment' in css
    assert '--violet:#e65b99' in css
    assert 'assets/input-header-rainbow-v2.png' in html
    assert "url('/static/assets/app-background-clouds-v2.png')" in css
    assert '.compact-submit{display:grid;width:min(100%,326px)' in css
    assert '.input-header-static-image{position:absolute;right:-4px;top:-6%;width:auto;height:112%' in css
    assert '.intro-mobile-copy{display:block' in css
    assert '.compact-submit{width:min(100%,306px)' in css
    assert '.compact-submit::after{content:"→"' in css
    assert 'id="bunnyCursor" class="bunny-cursor"' in html
    assert 'class="ui-icon cta-bunny-icon"' in html
    assert '.bunny-cursor.is-boing .bunny-cursor-paw' in css
    assert '@keyframes cursorBoing' in css
    assert 'function initBunnyCursor()' in js
    assert 'initBunnyCursor();bindBirthPickers()' in js
    assert 'function memberAddButton(attribute)' in js
    assert 'class="ghost-button member-add-button"' in js
    assert '새 사람의 출생정보를 입력해요' in js
    assert '.member-add-row{display:flex;margin:24px 0 8px;padding-top:20px' in css
    assert '.member-add-bunny::before,.member-add-bunny::after' in css
    assert 'mask-image:linear-gradient(90deg,transparent 0%' in css
    assert 'background:linear-gradient(105deg,#ef4f8e 0%,#f36f98 62%,#f69a88 100%)' in css


def test_profile_dashboard_separates_plain_language_from_special_star_evidence():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')

    assert "const ELEMENT_META={木:" in js
    for element in ('木', '火', '土', '金', '水'):
        assert f"{element}:{{name:" in js
    assert 'function elementOverview(' in js
    assert 'const DOMAIN_META={' in js
    assert 'function plainLifeText(' in js
    assert 'function profileKeyPointBoard(' in js
    assert 'function domainCardHtml(' in js
    assert "elementOverview(p,f)" in js
    assert 'function starEvidenceCard(' in js
    assert '신살 · 길성 뜻풀이' in js
    assert 'data-open-evidence' in js
    assert 'function starOverview(' not in js


def test_group_dashboard_reads_member_facts_and_visualizes_scores_by_tone():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')

    assert 'function groupMemberFacts(data,r)' in js
    assert 'data?.members' in js
    assert 'state.result?.initial_group?.members' in js
    assert 'groupNetworkHtml(r,data)' in js
    assert 'function matrixTone(score)' in js
    assert 'matrix-score ${matrixTone(score)}' in js
    assert 'function groupedRoleCards(roles=[]' in js
    assert '같은 역할은 한 번만 설명하고' in js


def test_loading_and_pair_score_are_information_dashboards():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    html = (root / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'loading-step-copy' in js
    assert "status==='done'?'완료'" in js
    assert 'function compatibilityScorePanel(' in js
    assert 'compat-mini-axes' in js
    assert 'role="progressbar"' in html
    assert 'loading-rainbow' in html
    assert 'loading-aurora' in html
