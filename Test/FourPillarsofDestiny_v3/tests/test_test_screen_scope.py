from app import app
from pathlib import Path
import re


def _effective_css_property(css: str, selector: str, property_name: str) -> str | None:
    """Return the last source-order declaration for a simple selector."""
    source = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    value = None
    for selector_group, body in re.findall(r'([^{}]+)\{([^{}]*)\}', source):
        if selector not in {item.strip() for item in selector_group.split(',')}:
            continue
        for declaration in body.split(';'):
            name, separator, current = declaration.partition(':')
            if separator and name.strip() == property_name:
                value = current.strip()
    return value


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
    assert html.count('20260828-rainbow-cloud-49') == 9
    assert '<h1>나만의 사주 이야기</h1>' in html
    assert '.input-screen-title{z-index:3;margin-left:92px}' in css
    assert '.input-screen-title{max-width:165px;margin-left:45px}' in css
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
    assert 'cta-bunny-charm' in html
    assert 'compact-submit-label' in html
    assert 'class="ui-icon cta-bunny-icon"' in html
    assert 'width:36px;height:38px' in css
    assert '.bunny-cursor.is-interactive{opacity:1!important' in css
    assert 'html,body{cursor:none!important}' in css
    assert 'button,input,textarea,select,summary' in js
    assert '.bunny-cursor.is-boing .bunny-cursor-paw' in css
    assert '@keyframes cursorBoing' in css
    assert 'function initBunnyCursor()' in js
    assert 'document.elementFromPoint(lastX,lastY)' in js
    assert "label=$('.compact-submit-label',button)" in js
    assert 'initBunnyCursor();initScrollTopButton();bindBirthPickers()' in js
    assert 'function memberAddButton(attribute)' in js
    assert 'class="ghost-button member-add-button"' in js
    assert '새 사람의 출생정보를 입력해요' in js
    assert '.member-add-row{display:flex;margin:24px 0 8px;padding-top:20px' in css
    assert 'width:min(100%,318px)' in css
    assert '.member-add-bunny::before,.member-add-bunny::after' in css
    assert 'background-position:right 17px center' in css
    assert '.input-back-button{display:inline-flex;width:auto;min-width:0;height:40px;gap:7px;padding:0 14px}' in css
    assert '.input-back-button .ui-icon{width:15px;height:15px;padding:0;background:transparent' in css
    assert '.member-remove-button{' in css
    assert 'data-remove-member' in js
    assert 'function bindMemberRemoval(' in js
    assert 'const memberUndoHistory=[]' in js
    assert 'function undoLastMemberRemoval()' in js
    assert 'memberUndoHistory.push({card,parent,next,index,root,minimum,onChange})' in js
    assert '...memberUndoHistory.map(item=>item.card.dataset.personPrefix' in js
    assert "`되돌리기 (${count})`" in js
    assert "parent.insertBefore(card" in js
    assert '.toast-action' in css
    assert 'd.expected_seconds??d.estimated_seconds??d.seconds' in js
    assert 'include_pair:f.elements.include_pair.checked' in js
    assert 'group_members:groupExtra?groupExtra+1:0' in js
    assert "value.name||pairName||value.label" in js
    assert "pairName&&value.label?value.label:''" in js
    assert 'mask-image:linear-gradient(90deg,transparent 0%' in css
    assert 'background:linear-gradient(105deg,#ef4f8e 0%,#f36f98 62%,#f69a88 100%)' in css
    assert 'rgba(255,226,239,.9)' in css
    assert 'linear-gradient(145deg,#fff7fb 0%,#ffe9f2 100%)' in css


def test_report_readability_redesign_keeps_cute_icons_and_structured_content():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    assert 'const CUTE_PATHS=' in js
    assert 'function cuteIcon(' in js
    assert 'class="pillar-part ${position} ${visual.tone}"' in js
    assert 'class="fortune-full-copy"' in js
    assert '/static/assets/report-bunny-badge.png' not in js
    assert '님의 성향과 흐름을' in js
    assert '생활 언어로 읽어드려요' not in js
    assert '/* calm, readable report system */' in css
    assert 'border-image:none' in css
    assert '.plain-key-grid article{display:grid;grid-template-columns:36px' in css
    assert '.fortune-card:has(details[open])' in css
    assert '.score-ring strong::before{content:"그룹 균형"' in css
    assert '.test-mode-badge,.test-fixture-summary{display:none}' in css
    assert 'function compactNatalChart(' in js
    assert 'return reportNatalChart(facts,profile.chart_detail||{},label)' in js
    assert "compactNatalChart(row.facts,report.person_b||{},'후보 원국')" in js
    assert "section('상대의 원국'" in js
    assert "section('상대의 신살·길성 참고'" in js
    assert 'class="target-star-reference"' in js
    assert 'class="target-domain-grid"' in js
    assert 'class="pair-person-grid"' in js
    assert js.index("section('상대의 원국'") < js.index('class="hero-summary pair-hero card"')
    pair = js[js.index('function renderPair('):js.index('async function submitPair(')]
    assert pair.index("section('생활 속에서 미리 확인할 것'") < pair.index("section('상대의 신살·길성 참고'")
    assert pair.index("section('상대의 신살·길성 참고'") < pair.index("section('궁합 점수가 나온 이유'")
    assert 'strong.reading-highlight{display:inline!important' in css
    assert 'class="fortune-detail-groups"' in js
    assert 'function activeDaewoonIndex(' in js
    assert 'class="daewoon-period-button' in js
    assert 'function periodPillarVisual(' in js
    assert '<div><h3>${label}</h3><small>' in js
    assert 'const honorificName=' in js
    assert 'function applyReportNameHonorifics(' in js
    assert "new RegExp(`${escaped}(?!님)`" in js
    assert 'installHonorificObserver()' in js
    assert 'aria-current="true"' in js
    assert 'class="daewoon-selected-marker"' in js
    assert 'id="daewoonSelected"' in js
    assert 'daewoonDetail(periods[currentIndex]||{},currentIndex,true)' in js
    assert '.daewoon-timeline{position:relative;display:flex' in css
    assert '.daewoon-selected-card' in css
    assert '.period-character.water' in css
    assert '.period-character.metal' in css
    assert '.daewoon-period-button.active:not(.current)' in css
    assert '.daewoon-period-button.current.active' in css
    assert 'class="daewoon-overview"' in js
    assert '10년의 흐름을 생활 언어로 보면' in js
    assert 'class="daewoon-selected-summary"' not in js
    assert '.fortune-detail-block li::before' in css
    assert 'function friendlyStarText(' in js
    assert "replace(/위치 미확인/g,'원국 전체 참고')" in js


def test_cute_icon_language_connects_report_scores_and_relationship_tones():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    assert 'const RELATION_MOOD=' in js
    for icon in ('🥕', '💗', '⭐', '☁️', '🌧️'):
        assert icon in js
        assert icon in css
    assert 'function sectionIcon(' in js
    assert 'class="pillar-cute-icon"' in js
    assert 'class="relation-mood-icon"' in js
    assert 'class="metric-label"' in js
    assert '.matrix-score.excellent small::before{content:"🥕"}' in css
    assert '.matrix-score.friction small::before{content:"🌧️"}' in css
    assert '.matrix-legend .friction,.matrix-score.friction{--matrix:#ef9ba6' in css
    assert '.matrix-legend .excellent,.matrix-score.excellent{--matrix:#48c883' in css
    assert '.workspace,.page-shell{grid-template-columns:minmax(0,1fr)}' in css
    assert '.report-header{display:grid;grid-template-columns:minmax(0,1fr) auto' in css
    assert '.candy-launcher{border-radius:18px;overflow-x:hidden}' in css


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
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    assert 'function groupMemberFacts(data,r)' in js
    assert 'data?.members' in js
    assert 'state.result?.initial_group?.members' in js
    assert 'groupNetworkHtml(r,data)' in js
    assert 'class="group-map-layout"' in js
    assert 'function elementLink(' in js
    assert 'function groupPairInspector(' in js
    assert 'function personRelationList(' in js
    assert "box.classList.add('person-selected')" in js
    assert 'relatedRows.slice(0,3)' in js
    assert 'relatedRows.slice(-2)' in js
    assert 'data-group-score=' in js
    assert 'class="pair-inspector-at-glance"' in js
    assert '.group-network-map.person-selected .group-connection.connected' in css
    assert '.group-network-map .group-node.dimmed' in css
    assert '.group-connection.balanced .connection-line{stroke:#d2a92d;stroke-dasharray:5 2}' in css
    assert '.group-connection.friction .connection-line{stroke:#df607b;stroke-dasharray:.7 1.8}' in css
    assert '.pair-inspector-details{grid-template-columns:1fr}' in css
    assert "readingCard('잘 맞는 점'" in js
    assert "readingCard('조율할 점'" in js
    assert "readingCard('대화 방법'" in js
    assert 'class="pair-inspector-details"' in js
    assert '.pair-inspector-details .reading-card p' in css
    assert 'font-size:13px;line-height:1.76' in css
    assert 'class="group-map-reading-guide"' in js
    assert '선이 없어도 관계가 없는 것은 아니에요' in js
    assert '편안한 연결 3개' in js
    assert '조율할 연결 2개' in js
    assert 'aria-label="${esc(point.name)}님의 대표 관계 확인"' in js
    assert "toolbar.className='group-map-toolbar'" in js
    assert 'data-group-reset hidden' in js
    assert 'let pendingPerson=null' in js
    assert 'pendingPerson!==null&&pendingPerson!==index' in js
    assert 'resetButton?.addEventListener(\'click\',resetView)' in js
    assert '.group-map-toolbar{display:flex' in css
    assert '관계 묶음' not in js
    assert 'function matrixTone(score)' in js
    assert 'matrix-score ${matrixTone(score)}' in js


def test_profile_starts_with_visual_natal_chart_before_plain_summary():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    profile = js[js.index('function renderProfile('):js.index('function fortuneDetailBlock(')]
    assert profile.index('top-natal-dashboard') < profile.index('text-only-profile-hero')
    assert 'integrated-bunny' not in profile
    assert 'function pillarPart(' in js
    assert 'class="natal-board-guide"' in js
    assert 'class="pillar-part ${position} ${visual.tone}"' in js
    assert '.top-natal-dashboard' in css
    assert '.text-only-profile-hero{min-height:0;grid-template-columns:minmax(0,1fr)' in css
    assert 'function groupedRoleCards(roles=[]' in js
    assert '같은 역할은 한 번만 설명하고' in js


def test_pair_and_top10_use_calm_structured_emphasis_cards():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    assert 'function emphasisRich(' in js
    assert 'function autoHighlightRich(' in js
    assert 'if(selected.length>=limit)break' in js
    assert 'function readableEmphasisParagraphs(' in js
    assert 'function readingCard(' in js
    assert 'class="candidate-insight-grid"' in js
    assert "readingCard('잘 맞는 이유'" in js
    assert "readingCard('먼저 조율할 부분'" in js
    assert "readingCard('역할을 나누는 방법'" in js
    assert "readingCard('현실에서 확인할 점'" in js
    assert 'class="pair-overview-copy">${readableEmphasisParagraphs' in js
    assert 'function sourceState(' in js
    assert "label:'원국 계산 완료'" in js
    assert 'function recommendationSourceSummary(' in js
    assert "title=key==='personality'?`${honorificName(subjectName)}의 기본 성향`" in js
    assert 'plainLifeText(value,{subject=' in js
    assert 'subject:targetName' in js
    assert 'function relationshipStyleCard(' in js
    assert "readingCard('함께 있을 때 편안한 점'" in js
    assert "readingCard('가까워질수록 맞춰야 할 점'" in js
    assert '.reading-highlight,strong.reading-highlight{display:inline!important;margin:0!important;color:#a84f70' in css
    assert '.candidate-insight-grid{display:grid;grid-template-columns:repeat(3' in css
    candidate_card = js[js.index('function candidateCard('):js.index('function renderAuto(')]
    assert "'연인 궁합':'친구 궁합'" not in candidate_card
    assert 'mood.icon' not in candidate_card
    assert 'aria-label="${kind} 후보 ${rank' in candidate_card


def test_pair_report_uses_distinct_life_scenes_and_hides_technical_terms_by_default():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    pair = js[js.index('function renderPair('):js.index('async function submitPair(')]
    relationship = js[js.index('function relationshipStyleCard('):js.index('function pairAxisStories(')]
    axes = js[js.index('function axisCards('):js.index('const show=')]

    assert '아래에서는 같은 설명을 반복하지 않고' not in js
    assert 'a.technical_focus' not in pair
    assert 'pairOverviewNarrative(r,a,axes,userName,targetName)' in pair
    assert 'a.emotional_needs||a.each_needs' in pair
    assert 'a.communication_daily||a.communication' in pair
    assert 'a.physical_intimacy||a.intimacy' in pair
    assert 'a.long_term_checklist||a.long_term' in pair
    assert pair.count('a.conflict_repair') == 1

    assert 'function relationshipDimension(' in js
    assert 'romance_dimensions' in js
    assert "title:'호감을 표현할 때'" in relationship
    assert "title:'관계를 결정할 때'" in relationship
    assert "title:'갈등이 생겼을 때'" in relationship
    assert 'teaser(relationship)' not in relationship
    assert 'class="relationship-scene-list"' in relationship
    assert '.relationship-scene p{margin:0;color:#5f555a;font-size:14px' in css

    for key in (
        'element_need', 'spouse_palace', 'spouse_star', 'stem_daymaster',
        'stem_communication', 'friend_ten_gods', 'branch_network',
        'month_life', 'month_social', 'conflict_buffer',
    ):
        assert f'{key}:{{label:' in js
    assert 'class="axis-life-tip"' in axes
    assert '<details class="axis-technical-details">' in axes
    assert '<details class="axis-technical-details" open' not in axes
    assert axes.index('<details class="axis-technical-details">') < axes.index('axis.label||axis.key')
    assert '.axis-life-tip{margin-top:12px' in css


def test_loading_scene_and_report_brand_use_soft_pastels():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    assert '/* unified pink-cloud loading scene */' in css
    assert _effective_css_property(css, '.loading', 'background') == (
        "#fff1f7 url('/static/assets/app-background-clouds-v2.png') center/cover no-repeat"
    )
    assert _effective_css_property(css, '.loading', 'backdrop-filter') == 'none'
    assert _effective_css_property(css, '.loading-sky', 'background') == (
        'radial-gradient(circle at 50% 46%,rgba(255,255,255,.82) 0 18%,'
        'rgba(255,255,255,0) 54%),linear-gradient(145deg,rgba(255,209,230,.68),'
        'rgba(240,222,249,.62) 52%,rgba(255,230,239,.58))'
    )
    assert _effective_css_property(css, '.loading-progress-track', 'background') == '#fae4ee'
    assert _effective_css_property(css, '.loading-progress-fill', 'background') == (
        'linear-gradient(90deg,#eb679d 0%,#f28ba6 34%,#f3b77f 57%,#86cab2 79%,#89b4de 100%)'
    )
    assert _effective_css_property(css, '.loading-rainbow', 'display') == 'none'
    assert _effective_css_property(css, '.loading-aurora', 'display') == 'none'
    assert _effective_css_property(css, '.loading-cloud', 'display') == 'none'
    assert _effective_css_property(css, '.loading-step.active .loading-step-index', 'background') == (
        'linear-gradient(135deg,#eb5f99,#f28e9c)'
    )
    assert 'const MINIMUM_LOADING_MS=650;' in js
    assert 'const remaining=MINIMUM_LOADING_MS-(Date.now()-state.startedAt)' in js
    assert 'if(remaining>0)await new Promise(resolve=>setTimeout(resolve,remaining))' in js
    assert '.report-header .approved-bunny-logo{width:54px;height:54px' in css
    assert 'clip-path:circle(49% at 50% 50%)' in css
    assert 'possessiveName(owner)' in js
    assert '`${possessiveName(owner)} 사주 리포트`' in js


def test_fortune_cards_share_reading_lines_and_pages_offer_scroll_top():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'templates' / 'index.html').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')

    assert '.fortune-grid{gap:16px}' in css
    assert '.fortune-card-head{min-height:78px;align-items:flex-start}' in css
    assert '.fortune-card-title small{min-height:44px' in css
    assert '.fortune-card details>summary{display:grid;min-height:64px' in css
    assert '.period-character.fire{--element:#bf5f76;--element-soft:#fff1f5}' in css
    assert '.period-character.earth{--element:#a5793d;--element-soft:#fff8e7}' in css
    assert 'id="scrollTopButton" class="scroll-top-button"' in html
    assert 'function initScrollTopButton()' in js
    assert 'window.scrollY>520' in js
    assert 'initBunnyCursor();initScrollTopButton();bindBirthPickers()' in js


def test_print_button_opens_complete_browser_pdf_layout():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'styles.css').read_text(encoding='utf-8')

    assert 'function printReport()' in js
    assert "closed=$$('details').filter(node=>!node.open)" in js
    assert "$('#printButton').onclick=printReport" in js
    assert 'window.print()' in js
    assert '@page{size:auto;margin:12mm}' in css
    assert '#workspace{display:block!important}' in css
    assert '.page{display:block!important;break-before:page}' in css
    assert 'print-color-adjust:exact' in css


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
