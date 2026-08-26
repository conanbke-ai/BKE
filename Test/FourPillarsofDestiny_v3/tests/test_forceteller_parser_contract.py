from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_forceteller_parser(monkeypatch):
    stub = types.ModuleType('bazi_engine')
    stub.calculate_chart = lambda profile: None
    stub.derive_ten_gods = lambda chart: {}
    monkeypatch.setitem(sys.modules, 'bazi_engine', stub)
    path = Path(__file__).resolve().parents[1] / 'forceteller.py'
    spec = importlib.util.spec_from_file_location('forceteller_contract_module', path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_strength_useful_stars_and_daewoon_dom_contract(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    html = '''
    <section data-test-id="singang"><p>홍길동님은 <b>신강</b>한 사주입니다.</p></section>
    <p>나의 용신: 화(火) (억부용신)</p>
    <section>신살과 길성</section>
    <div><b>생시</b><span>도화살</span></div>
    <div><b>생일</b><span>월덕귀인</span></div>
    <div><b>생월</b><span>역마살</span></div>
    <div><b>생년</b><span>천덕귀인</span></div>
    <section>오행과 십성 분석</section>
    <div data-test-id="daeun0top">3세 편재 戊</div>
    <div data-test-id="daeun0bottom">목욕 정인 子</div>
    <div data-test-id="daeun1top">13세 정재 己</div>
    <div data-test-id="daeun1bottom">관대 정재 丑</div>
    <div data-test-id="daeun2top">23세 편관 庚</div>
    <div data-test-id="daeun2bottom">건록 편재 寅</div>
    '''
    assert ft._parse_strength([], html, html)[0] == '신강'
    assert ft._parse_useful_elements([], html) == ['火']
    assert {'도화살', '월덕귀인', '역마살', '천덕귀인'} <= set(ft._parse_special_stars(html))
    positions = ft._parse_special_star_positions(html, html)
    assert positions['시주'] == ['도화살']
    assert positions['일주'] == ['월덕귀인']
    rows = ft._parse_daewoon(html, html)
    assert [row['pillar'] for row in rows[:3]] == ['戊子', '己丑', '庚寅']
    assert [row['age'] for row in rows[:3]] == [3, 13, 23]


def test_actual_guardian_and_strength_factor_contract(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    html = '''
    <div data-test-id="singang">
      <p>득령</p><img src="https://static.forceteller.com/images/pro/icon_yes.svg" alt="득령">
      <p>득지</p><img src="https://static.forceteller.com/images/pro/icon_no.svg" alt="득지">
      FT님은 <b>중화신강</b>한 사주입니다.
    </div>
    <div data-test-id="guardian"><p><b>화</b>(억부용신)</p></div>
    '''
    assert ft._parse_strength([], '', html)[0] == '중화신강'
    assert ft._parse_strength_factors(html)['득령'] is True
    assert ft._parse_strength_factors(html)['득지'] is False
    assert ft._parse_useful_elements([], '', html) == ['火']
    assert ft._parse_useful_element_detail('', html) == '화(억부용신)'


def test_legacy_nested_chart_cache_is_migrated(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    data = {
        'profile': {
            'name': '테스트', 'gender': 'F', 'calendar_type': 'solar',
            'year': 1995, 'month': 11, 'day': 29, 'hour': 6, 'minute': 35,
        },
        'chart': {
            'year_pillar': '乙亥', 'month_pillar': '丁亥', 'day_pillar': '甲子', 'hour_pillar': '丁卯',
            'day_master': '甲', 'spouse_palace': '子',
            'stems': ['乙','丁','甲','丁'], 'branches': ['亥','亥','子','卯'],
            'element_percent': {'木': 37.5, '火': 25.0, '土': 0.0, '金': 0.0, '水': 37.5},
            'strength_label': '신강', 'useful_elements': ['火'],
        },
        'ten_gods': {},
        'source': 'forceteller', 'source_quality': 80,
    }
    facts = ft._facts_from_dict(data)
    assert facts.strength_label == '신강'
    assert facts.useful_elements == ['火']
    assert facts.element_percent['木'] == 37.5
    assert facts.chart.day_pillar == '甲子'


def test_pillars_recover_from_rendered_special_star_grid(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    html = '''
    <p>신살과 길성</p>
    <div><b>생시</b><span>정丁</span><span>묘卯</span><span>도화살</span></div>
    <div><b>생일</b><span>갑甲</span><span>자子</span><span>월덕귀인</span></div>
    <div><b>생월</b><span>정丁</span><span>해亥</span></div>
    <div><b>생년</b><span>을乙</span><span>해亥</span></div>
    <p>오행과 십성 분석</p>
    '''
    assert ft._parse_pillars_from_html(html) == {'hour':'丁卯','day':'甲子','month':'丁亥','year':'乙亥'}


def test_parse_facts_prefers_rendered_forceteller_pillars_and_core_cards(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    local = ft.Chart(
        year_pillar='甲戌', month_pillar='乙亥', day_pillar='丁卯', hour_pillar='壬寅',
        day_master='丁', spouse_palace='卯', stems=['甲','乙','丁','壬'], branches=['戌','亥','卯','寅'],
        element_percent_local={'木':50.0,'火':12.5,'土':12.5,'金':0.0,'水':25.0},
    )
    ft.calculate_chart = lambda profile: local
    ft.derive_ten_gods = lambda chart: {}
    profile = ft.BirthProfile(name='테스트', gender='F', calendar_type='solar', year=1995, month=11, day=29, hour=6, minute=35)
    html = '''
    <p>신살과 길성</p>
    <div><b>생시</b><span>정丁</span><span>묘卯</span><span>도화살</span></div>
    <div><b>생일</b><span>갑甲</span><span>자子</span><span>월덕귀인</span></div>
    <div><b>생월</b><span>정丁</span><span>해亥</span><span>역마살</span></div>
    <div><b>생년</b><span>을乙</span><span>해亥</span><span>천덕귀인</span></div>
    <p>오행과 십성 분석</p>
    <div data-test-id="singang">득령 <img src="icon_yes.svg"> 테스트님은 <b>신강</b>한 사주입니다.</div>
    <div data-test-id="guardian"><b>화</b>(억부용신)</div>
    <div data-test-id="daeun0top">3 편재 戊</div><div data-test-id="daeun0bottom">목욕 정인 子</div>
    <div data-test-id="daeun1top">13 정재 己</div><div data-test-id="daeun1bottom">관대 정재 丑</div>
    <div data-test-id="daeun2top">23 편관 庚</div><div data-test-id="daeun2bottom">건록 편재 寅</div>
    '''
    facts = ft.parse_facts(profile, html, html, [], 'test')
    assert facts.chart.day_pillar == '甲子'
    assert facts.chart.hour_pillar == '丁卯'
    assert facts.strength_label == '신강'
    assert facts.useful_elements == ['火']
    assert '도화살' in facts.special_stars
    assert len(facts.daewoon) == 3


def test_v2_manifest_birth_date_time_can_be_reused(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    row = ft._legacy_profile_mapping({
        'birth_date': '1995-11-29',
        'birth_time': '06:35',
        'gender': 'F',
        'data_dir': r'C:\\old\\candidate',
    })
    assert row is not None
    assert (row['year'], row['month'], row['day']) == (1995, 11, 29)
    assert (row['hour'], row['minute'], row['time_known']) == (6, 35, True)
    assert row['calendar_type'] == 'solar'
    assert row['country_code'] == 'KR'


def test_legacy_inverse_star_position_mapping_is_migrated(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    result = ft._normalize_star_positions({'도화살': ['시주'], '월덕귀인': ['일주', '연주']})
    assert result['시주'] == ['도화살']
    assert result['일주'] == ['월덕귀인']
    assert result['연주'] == ['월덕귀인']


def test_legacy_chart_source_marks_verified_cache_without_losing_core_fields(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    data = {
        'profile': {'name':'테스트','gender':'F','calendar_type':'solar','year':1995,'month':11,'day':29,'hour':6,'minute':35},
        'chart_source': 'forceteller',
        'chart': {
            'year_pillar':'乙亥','month_pillar':'丁亥','day_pillar':'甲子','hour_pillar':'丁卯',
            'day_master':'甲','spouse_palace':'子','stems':['乙','丁','甲','丁'],'branches':['亥','亥','子','卯'],
            'strength_label':'신강','useful_elements':['火'],
        },
        'element_percent': {'木':37.5,'火':25,'土':0,'金':0,'水':37.5},
    }
    facts = ft._facts_from_dict(data)
    assert facts.source.startswith('forceteller')
    assert facts.source_quality >= ft.SETTINGS.min_verified_source_quality
    assert facts.strength_label == '신강'
    assert facts.useful_elements == ['火']


def test_generic_special_star_names_are_not_dropped(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    html = '''
    <section>신살과 길성</section>
    <div><b>생시</b><span>천희성</span><span>원진살</span></div>
    <div><b>생일</b><span>장성살</span><span>암록</span></div>
    <div><b>생월</b><span>문곡귀인</span></div>
    <div><b>생년</b><span>육해살</span></div>
    <section>오행과 십성 분석</section>
    '''
    names = ft._parse_special_stars(html)
    assert {'천희성','원진살','장성살','암록','문곡귀인','육해살'} <= set(names)
    positions = ft._parse_special_star_positions(html, html)
    assert {'천희성','원진살'} <= set(positions['시주'])
    assert {'장성살','암록'} <= set(positions['일주'])
    assert positions['월주'] == ['문곡귀인']
    assert positions['연주'] == ['육해살']


def test_legacy_cache_index_has_stable_hash_dependency(monkeypatch):
    ft = _load_forceteller_parser(monkeypatch)
    assert callable(ft.stable_hash)
