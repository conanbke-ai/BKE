from __future__ import annotations

import importlib
import sys
import types


def _load_explain(monkeypatch):
    stub = types.ModuleType('bazi_engine')
    stub.ten_god = lambda *_args, **_kwargs: '정인'
    monkeypatch.setitem(sys.modules, 'bazi_engine', stub)
    sys.modules.pop('scoring', None)
    sys.modules.pop('explain', None)
    return importlib.import_module('explain')


def _facts(explain, *, name: str, day_pillar: str, stars: list[str], positions: dict[str, list[str]]):
    models = importlib.import_module('models')
    profile = models.BirthProfile(
        name=name, gender='F', calendar_type='solar',
        year=1994, month=12, day=7, hour=5, minute=30,
    )
    chart = models.Chart(
        year_pillar='甲戌', month_pillar='乙亥', day_pillar=day_pillar,
        hour_pillar='壬寅', day_master=day_pillar[0], spouse_palace=day_pillar[1],
        stems=['甲', '乙', day_pillar[0], '壬'], branches=['戌', '亥', day_pillar[1], '寅'],
        element_percent_local={'木':25,'火':25,'土':25,'金':0,'水':25},
    )
    return models.ForcetellerFacts(
        profile=profile, chart=chart,
        element_percent={'木':25,'火':25,'土':25,'金':0,'水':25},
        special_stars=stars, special_star_positions=positions,
    )


def test_same_star_is_personalized_by_day_pillar_and_position(monkeypatch):
    explain = _load_explain(monkeypatch)
    fire = _facts(explain, name='화일간', day_pillar='丁亥', stars=['도화살'], positions={'일주':['도화살']})
    water = _facts(explain, name='수일간', day_pillar='壬子', stars=['도화살'], positions={'월주':['도화살']})

    a = explain._star_rows(fire)[0]
    b = explain._star_rows(water)[0]

    assert a['meaning'] == b['meaning']  # star dictionary meaning itself can be the same
    assert a['personal_note'] != b['personal_note']
    assert a['practical'] != b['practical']
    assert '丁亥' in a['personal_note'] and '일주' in a['personal_note']
    assert '壬子' in b['personal_note'] and '월주' in b['personal_note']
    assert a['day_element'] == '火'
    assert b['day_element'] == '水'


def test_day_pillar_relation_exposes_element_flow(monkeypatch):
    explain = _load_explain(monkeypatch)
    wood = _facts(explain, name='목', day_pillar='甲寅', stars=[], positions={})
    fire = _facts(explain, name='화', day_pillar='丙午', stars=[], positions={})
    rel = explain._day_pillar_relation_summary(wood, fire)

    assert rel['a_element'] == '木'
    assert rel['b_element'] == '火'
    assert rel['stem_kind'] == 'support'
    assert '생(生)' in rel['element_relation_label']
