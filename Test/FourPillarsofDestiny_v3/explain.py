from __future__ import annotations

from itertools import combinations
from typing import Any

from bazi_engine import ten_god
from config import SETTINGS
from constants import (
    BRANCH_ELEMENT,
    BRANCH_READING,
    CONTROLS,
    ELEMENT_PLAIN,
    ELEMENT_READING,
    GENERATES,
    HIDDEN_STEMS,
    STEM_COMBINE,
    STEM_ELEMENT,
    STEM_READING,
    TEN_GODS,
    SPECIAL_STAR_PLAIN,
    TERM_DICTIONARY,
)
from models import CompatibilityResult, ForcetellerFacts
from scoring import branch_relations


TEN_GOD_HANJA = {
    '비견': '比肩', '겁재': '劫財', '식신': '食神', '상관': '傷官', '편재': '偏財',
    '정재': '正財', '편관': '偏官', '정관': '正官', '편인': '偏印', '정인': '正印',
}
TEN_GOD_PLAIN = {
    '비견': '자기주도성·동료성·독립성',
    '겁재': '경쟁·주도권·함께 움직이는 힘',
    '식신': '표현·생산·기술·생활의 여유',
    '상관': '창의적 표현·문제 발견·비판성',
    '편재': '기회·대외 활동·유동적인 현실 자원',
    '정재': '안정적 관리·현실 감각·계획적인 재물',
    '편관': '압박·도전·규율·강한 실행력',
    '정관': '책임·규칙·조직적 역할',
    '편인': '직관·비정형 학습·전문 몰입',
    '정인': '학습·보호·자격·정서적 지원',
}
POSITION_LABELS = ('연주', '월주', '일주', '시주')
STEM_SYMBOLISM = {
    '甲': '큰 나무처럼 방향을 잡고 위로 뻗는 성질',
    '乙': '풀과 덩굴처럼 환경을 읽고 유연하게 연결되는 성질',
    '丙': '햇빛처럼 넓게 비추고 밖으로 드러나는 성질',
    '丁': '등불처럼 한 지점에 집중하고 섬세하게 온도를 조절하는 성질',
    '戊': '큰 땅처럼 버티고 기반을 만드는 성질',
    '己': '밭과 흙처럼 세부를 돌보고 실용적으로 다듬는 성질',
    '庚': '단단한 쇠처럼 잘라내고 결론을 내리는 성질',
    '辛': '정교한 금속처럼 기준을 세우고 세밀하게 다듬는 성질',
    '壬': '큰 물처럼 넓게 움직이고 정보를 연결하는 성질',
    '癸': '비와 이슬처럼 세밀하게 스며들고 상황을 관찰하는 성질',
}
RELATION_PLAIN = {
    '육합': '서로 연결점을 만들기 쉬운 관계',
    '삼합계열': '여러 지지가 같은 흐름으로 묶일 수 있는 관계',
    '삼회계열': '같은 계절 방향의 기운이 모이는 관계',
    '충': '방향 차이가 커 변화와 긴장을 만드는 관계',
    '형': '반응 방식의 마찰이나 압박이 반복될 수 있는 관계',
    '파': '작은 기대 차이와 생활 어긋남이 누적될 수 있는 관계',
    '해': '직접 충돌보다 서운함이나 오해가 생기기 쉬운 관계',
}


def term(key: str, suffix: str = '') -> str:
    reading, plain, _ = TERM_DICTIONARY.get(key, (key, '', ''))
    base = f'{key}({reading}·{plain})' if plain else f'{key}({reading})'
    return base + (f' {suffix}' if suffix else '')


def stem_text(stem: str) -> str:
    element = STEM_ELEMENT[stem]
    polarity = '양' if stem in {'甲', '丙', '戊', '庚', '壬'} else '음'
    return f'{stem}({STEM_READING[stem]}·{polarity}의 {ELEMENT_READING[element]}, {ELEMENT_PLAIN[element]})'


def branch_text(branch: str) -> str:
    element = BRANCH_ELEMENT[branch]
    return f'{branch}({BRANCH_READING[branch]}·{ELEMENT_READING[element]} 기운, {ELEMENT_PLAIN[element]})'


def ten_god_text(name: str) -> str:
    hanja = TEN_GOD_HANJA.get(name, name)
    return f'{hanja}({name}·{TEN_GOD_PLAIN.get(name, "십성 관계")})'


def element_text(element: str) -> str:
    return f'{element}({ELEMENT_READING[element]}·{ELEMENT_PLAIN[element]})'


def _source_status(facts: ForcetellerFacts) -> dict[str, Any]:
    verified = facts.source.startswith('forceteller') and facts.source_quality >= SETTINGS.min_verified_source_quality
    return {
        'verified': verified,
        'label': '세부 원국 자료 확인 완료' if verified else '기본 원국 계산 기준',
        'description': (
            '원국·오행·십성·강약의 세부 자료를 함께 반영했습니다.'
            if verified else
            '세부 원국 자료가 일부 확인되지 않아 현재는 확정 가능한 원국과 계산값을 중심으로 보수적으로 해석합니다.'
        ),
    }


def chart_explanation(facts: ForcetellerFacts) -> dict[str, Any]:
    c = facts.chart
    # 화면 전체에서 Forceteller 결과와 같은 순서로 통일: 시주 → 일주 → 월주 → 연주.
    return {
        'pillars': [
            {
                'key': 'hour', 'label': '시주',
                'meaning': ('내면의 계획·장기 관심사·세부 표현을 보조적으로 보는 기둥' if facts.profile.time_known else '출생시간을 몰라 확정할 수 없는 기둥입니다. 시주를 임의로 만들지 않습니다.'),
                'value': c.hour_pillar if facts.profile.time_known else '출생시간 모름 · 시주 미확정',
            },
            {'key': 'day', 'label': '일주', 'meaning': '본인의 중심 성향과 가까운 관계를 보는 핵심 기둥', 'value': c.day_pillar},
            {'key': 'month', 'label': '월주', 'meaning': '태어난 계절과 사회생활·직업 환경의 핵심 배경을 보는 기둥', 'value': c.month_pillar},
            {'key': 'year', 'label': '연주', 'meaning': '초기 환경·가족·사회적 배경을 보조적으로 살피는 기둥', 'value': c.year_pillar},
        ],
        'day_master': stem_text(c.day_master),
        'spouse_palace': branch_text(c.spouse_palace),
    }

def _axis_totals(facts: ForcetellerFacts) -> dict[str, float]:
    tg = facts.ten_gods
    return {
        'peer': float(tg.get('비견', 0)) + float(tg.get('겁재', 0)),
        'output': float(tg.get('식신', 0)) + float(tg.get('상관', 0)),
        'wealth': float(tg.get('정재', 0)) + float(tg.get('편재', 0)),
        'officer': float(tg.get('정관', 0)) + float(tg.get('편관', 0)),
        'resource': float(tg.get('정인', 0)) + float(tg.get('편인', 0)),
    }


STYLE_LIBRARY = {
    'peer': {
        'label':'자기 기준과 자율', 'need':'내 선택권과 개인 영역이 존중되는 것',
        'talk':'결론을 일방적으로 통보하기보다 선택 과정에 참여시키는 대화',
        'work':'담당 영역을 스스로 결정하고 끝까지 책임지는 역할',
        'conflict':'주도권이나 책임 경계가 겹치는',
    },
    'output': {
        'label':'표현과 결과물', 'need':'생각과 감정에 실제 반응이 돌아오는 것',
        'talk':'핵심을 빨리 말하고 피드백을 주고받는 대화',
        'work':'아이디어를 제안하고 문제를 개선해 결과물로 만드는 역할',
        'conflict':'답답함이 쌓여 말이 빨라지거나 날카로워지는',
    },
    'wealth': {
        'label':'현실성과 실행', 'need':'약속이 말에 그치지 않고 일정·행동으로 이어지는 것',
        'talk':'누가 언제 무엇을 할지 구체적으로 정하는 대화',
        'work':'일정·자원·마감과 실제 성과를 챙기는 역할',
        'conflict':'시간·돈·책임 배분이 모호한',
    },
    'officer': {
        'label':'기준과 책임', 'need':'관계나 역할의 기준이 일관되고 약속이 지켜지는 것',
        'talk':'기준과 이유를 분명히 하고 합의한 규칙을 지키는 대화',
        'work':'기준·품질·책임선을 정리하고 운영을 안정시키는 역할',
        'conflict':'기준이 자주 바뀌거나 책임만 떠넘겨지는',
    },
    'resource': {
        'label':'이해와 검토', 'need':'충분히 이해하고 생각을 정리할 시간과 안정감이 주어지는 것',
        'talk':'배경과 이유를 설명하고 생각할 시간을 주는 대화',
        'work':'정보를 모으고 검토해 전문성·근거를 보강하는 역할',
        'conflict':'충분한 설명 없이 재촉받는',
    },
}


def _plain_user_text(text: str) -> str:
    """Keep primary UI prose natural; technical labels stay in evidence only."""
    out = str(text or '')
    phrase_replacements = [
        ('비겁이 높을수록 자율성은 장점이지만', '자기 주도성이 두드러질수록 스스로 결정하는 힘은 장점이지만'),
        ('인성은 문서·학습·자격·지원과 연결해 봅니다.', '배우고 검토하는 힘은 문서·학습·자격·전문성으로 이어질 수 있습니다.'),
        ('식상 비중이 높다면', '생각을 밖으로 표현하고 결과물을 만드는 성향이 두드러진다면'),
        ('관성과 식상이 함께 강하면', '규칙을 중시하면서도 문제를 직접 표현하는 성향이 함께 두드러지면'),
        ('재성 비중이 낮아도 식상·인성·관성이 강하면', '돈 자체를 직접 다루는 성향이 약하더라도 생산·학습·책임을 맡는 힘이 뚜렷하면'),
        ('비겁은 공동 이해관계, 식상은 활동·표현과 연결하므로', '사람과 이해관계가 얽히거나 활동·경험 지출이 늘어날 때는'),
        ('명리에서 재성은 “돈이 들어온다”보다 “내가 현실 자원을 감당하고 관리하는 방식”으로 보는 것이 정확합니다.', '재물 해석은 “돈이 저절로 들어온다”가 아니라 내가 수입·지출·자원을 어떻게 감당하고 관리하는지를 보는 편이 정확합니다.'),
        ('현재 원국의 강점과 용신 방향을 기준으로', '현재 잘 쓰는 강점과 균형을 위해 보완할 방향을 기준으로'),
        ('원국보다 현재 운에서 재성·식상·비겁이 어떻게 들어오는지가 시기별 차이를 만듦', '타고난 성향만으로 정해지기보다 시기마다 생산·수입·지출·사람 관계의 압력이 달라질 수 있음'),
    ]
    for old, new in phrase_replacements:
        out = out.replace(old, new)
    # 메인 생활 해설에는 전통 용어를 그대로 노출하지 않는다. 원래 용어와
    # 수치 근거는 profile_local의 evidence 및 해석 근거 화면에 보존된다.
    word_replacements = [
        ('비견·겁재', '자기주도·동료 성향'), ('정인·편인', '학습·검토 성향'),
        ('식신·상관', '표현·생산 성향'), ('정재·편재', '현실·자원 관리 성향'),
        ('정관·편관', '책임·규칙 성향'), ('비겁', '자기주도·동료 성향'),
        ('식상', '표현·생산 성향'), ('재성', '현실·자원 관리 성향'),
        ('관성', '책임·규칙 성향'), ('인성', '학습·검토 성향'),
        ('신강·신약', '에너지를 쓰는 방식'), ('용신', '균형을 위해 보완할 방향'),
        ('일간', '나의 기본 반응'), ('일지', '가까운 관계에서의 생활 반응'),
        ('십성', '생활 역할'), ('원국', '타고난 성향 구성'),
        ('명리학', '전통 해석'), ('명리', '전통 해석'),
    ]
    for old, new in word_replacements:
        out = out.replace(old, new)
    return out

def _plain_dimensions(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        for key in ('assessment', 'practical'):
            if item.get(key):
                item[key] = _plain_user_text(item[key])
        cleaned.append(item)
    return cleaned

def _dominant_style(facts: ForcetellerFacts) -> tuple[str, dict[str, str]]:
    totals = _axis_totals(facts)
    key = max(totals, key=totals.get)
    return key, STYLE_LIBRARY[key]

def _secondary_style(facts: ForcetellerFacts) -> tuple[str, dict[str, str]]:
    totals = sorted(_axis_totals(facts).items(), key=lambda kv: kv[1], reverse=True)
    key = totals[1][0] if len(totals) > 1 else totals[0][0]
    return key, STYLE_LIBRARY[key]

def _plain_profile_summary(facts: ForcetellerFacts) -> str:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    name = facts.profile.name or '이 사람'
    return (
        f'{name}은 중요한 일을 판단할 때 **{first["need"]}**이 먼저 필요하고, 그다음 **{second["need"]}**까지 확인해야 마음이 정리되는 편입니다. '
        f'일에서는 **{first["work"]}**에서 강점이 잘 드러나고, 대화에서는 {first["talk"]} 방식이 잘 맞습니다. '
        f'반대로 {first["conflict"]} 상황이 반복되면 내용 자체보다 과정에서 더 피로해질 수 있습니다.'
    )

_STAR_HELP = {'천을귀인','천덕귀인','월덕귀인','태극귀인','문창귀인','문곡귀인','학당귀인','천희귀인','암록','금여성','금여록','천사성'}
_STAR_ATTRACTION = {'도화살','홍염살','천희성','천희귀인','년살'}
_STAR_LEARNING = {'문창귀인','문곡귀인','학당귀인','태극귀인','천문성','화개살','귀문관살','천의성'}
_STAR_MOVEMENT = {'역마살','지살'}
_STAR_INDEPENDENCE = {'고신살','과숙살','화개살','심성'}
_STAR_FORCE = {'양인살','괴강살','백호살','백호대살','장성살','현침살'}
_STAR_FRICTION = {'원진살','육해살','망신살','겁살','재살','천살','월살'}

def _star_category(name: str) -> tuple[str, str]:
    if name in _STAR_ATTRACTION: return '관계·표현', 'accent'
    if name in _STAR_LEARNING: return '학습·몰입', 'sky'
    if name in _STAR_HELP: return '도움·완충', 'positive'
    if name in _STAR_MOVEMENT: return '이동·변화', 'mint'
    if name in _STAR_INDEPENDENCE: return '독립·내면', 'lav'
    if name in _STAR_FORCE: return '주도·긴장', 'peach'
    if name in _STAR_FRICTION: return '조율·주의', 'caution'
    return '보조 기운', 'neutral'

def _star_position_context(positions: list[str]) -> str:
    parts=[]
    for pos in positions:
        if pos == '일주': parts.append('일주 · 나의 기본 반응과 가까운 관계에서 체감되기 쉬운 자리')
        elif pos == '월주': parts.append('월주 · 직장·사회생활과 반복되는 일상에서 드러나기 쉬운 자리')
        elif pos == '연주': parts.append('연주 · 초기 환경과 바깥 관계에서 보조적으로 드러나는 자리')
        elif pos == '시주': parts.append('시주 · 내면의 계획·장기 관심과 후반 생활을 보조해서 보는 자리')
    return ' · '.join(parts)


def _star_position_tip(positions: list[str]) -> str:
    tips=[]
    for pos in positions:
        if pos == '일주': tips.append('가까운 관계나 즉각적인 반응에서 실제로 반복되는지')
        elif pos == '월주': tips.append('직장·업무·사회생활에서 반복되는지')
        elif pos == '연주': tips.append('바깥 관계나 익숙하지 않은 환경에서 드러나는지')
        elif pos == '시주': tips.append('혼자 계획할 때나 장기 관심사에서 나타나는지')
    if not tips:
        return '어느 생활 장면에서 반복되는지'
    return ' / '.join(dict.fromkeys(tips))


def _day_element_tip(facts: ForcetellerFacts) -> str:
    day_master = str(facts.chart.day_master or '')
    elem = STEM_ELEMENT.get(day_master, '')
    return {
        '木': '방향을 넓히거나 관계를 이어 갈 때',
        '火': '표현의 속도와 강도를 조절할 때',
        '土': '기준을 세우고 꾸준히 유지할 때',
        '金': '판단 기준과 경계를 분명히 할 때',
        '水': '정보와 감정의 흐름을 충분히 확인할 때',
    }.get(elem, '실제 선택과 행동을 정리할 때')


def _star_practical(name: str, positions: list[str], facts: ForcetellerFacts) -> str:
    if name in {'도화살','홍염살','천희성','천희귀인','년살'}:
        base = '사람의 반응이나 호감을 비교적 빨리 감지할 수 있지만, 관심을 받는 것과 안정적인 관계인지는 따로 확인하는 편이 좋습니다.'
    elif name in {'월덕귀인','천덕귀인','천을귀인','천사성'}:
        base = '갈등이나 막히는 일이 생겼을 때 혼자 버티기보다 도움을 요청하고 대화의 완충 지점을 찾는 방식이 잘 맞을 수 있습니다.'
    elif name in {'문창귀인','문곡귀인','학당귀인','태극귀인','천문성'}:
        base = '배운 내용을 말·문서·전문지식으로 정리할 때 강점을 쓰기 쉬우므로, 생각을 머릿속에만 두지 말고 결과물로 남기는 편이 좋습니다.'
    elif name in {'천의성'}:
        base = '돌봄·회복·몸과 마음의 상태를 세심하게 살피는 관심으로 나타날 수 있어, 실제 생활에서는 도움을 주는 것과 내 몫까지 떠안는 것을 구분하는 편이 좋습니다.'
    elif name in {'화개살','귀문관살'}:
        base = '혼자 깊이 생각하고 몰입하는 시간이 필요할 수 있으므로, 과몰입 뒤에는 현실 일정과 사람 관계로 다시 연결하는 루틴이 도움이 됩니다.'
    elif name in {'역마살','지살'}:
        base = '환경 변화나 이동이 있을 때 에너지가 살아날 수 있으나, 변화 자체를 목표로 삼기보다 무엇을 배우고 얻을지 기준을 정하는 편이 좋습니다.'
    elif name in {'현침살'}:
        base = '세부를 잘 보고 표현이 날카로워질 수 있어, 정확한 지적은 강점이지만 사람을 평가하는 말처럼 들리지 않게 표현을 다듬는 것이 좋습니다.'
    elif name in {'양인살','괴강살','백호살','백호대살','장성살'}:
        base = '주도권과 버티는 힘이 강점이 될 수 있지만, 중요한 관계에서는 혼자 결론내리기보다 상대의 선택권과 속도를 확인하는 것이 좋습니다.'
    elif name in {'고신살','과숙살'}:
        base = '가까운 관계에서도 혼자 정리할 시간이 필요할 수 있으므로, 거리를 두는 시간을 상대에 대한 거절로 오해받지 않게 미리 설명하는 편이 좋습니다.'
    elif name in {'원진살','육해살'}:
        base = '큰 싸움보다 작은 서운함이 누적되는지를 먼저 살피고, 애매한 감정을 오래 추측하기보다 구체적인 행동과 기대를 확인하는 편이 좋습니다.'
    elif name in {'암록','금여성','금여록'}:
        base = '겉으로 드러나는 성과만 보지 말고 실제 생활을 안정시키는 도움·자원·환경을 꾸준히 활용하는 편이 좋습니다.'
    else:
        base = '이 항목 하나만으로 결론내리지 않고, 실제 생활에서 반복되는 패턴이 있는지 확인할 때 보조적으로 활용합니다.'
    return f'{base} 특히 {_star_position_tip(positions)} 확인하고, {_day_element_tip(facts)} 이 기운이 과하거나 부족하게 쓰이지 않는지 함께 보는 편이 좋습니다.'


def _star_personal_note(name: str, positions: list[str], facts: ForcetellerFacts) -> str:
    day = str(facts.chart.day_pillar or '')
    reading = _pillar_reading(day) if day else '일주 미확인'
    if not positions:
        if day:
            return f'{facts.profile.name}의 일주는 {day}({reading}주)이고, {name}은 원국 전체 참고 항목으로 표시되어 있습니다. 특정 기둥 하나에 고정하지 않고 실제 생활에서 반복되는 장면이 있는지 보조적으로 확인합니다.'
        return f'{name}은 원국 전체 참고 항목입니다. 특정 기둥 하나에 고정하지 않고 실제 생활에서 반복되는 장면이 있는지 보조적으로 확인합니다.'
    pos = ' · '.join(positions)
    if day:
        return f'{facts.profile.name}의 일주는 {day}({reading}주)이고, {name}은 {pos}에서 확인됩니다. 같은 {name}이라도 어느 기둥에 놓였는지에 따라 체감되는 생활 영역을 다르게 봅니다.'
    return f'{name}은 {pos}에서 확인됩니다. 신살 이름만 보지 않고 어느 기둥에서 확인되는지를 함께 봅니다.'


def _star_rows(facts: ForcetellerFacts) -> list[dict[str, Any]]:
    rows=[]
    for name in facts.special_stars:
        positions=[label for label in ('일주','월주','연주','시주') if name in facts.special_star_positions.get(label, [])]
        category,tone=_star_category(name)
        day_master = str(facts.chart.day_master or '')
        rows.append({
            'name': name,
            'meaning': SPECIAL_STAR_PLAIN.get(name, '원국 전체와 함께 참고하는 전통적 보조 기운입니다.'),
            'positions': positions,
            'category': category,
            'tone': tone,
            'position_context': _star_position_context(positions),
            'practical': _star_practical(name, positions, facts),
            'personal_note': _star_personal_note(name, positions, facts),
            'day_pillar': facts.chart.day_pillar,
            'day_master': day_master,
            'day_element': STEM_ELEMENT.get(day_master, ''),
        })
    return rows

def _star_domain_insights(facts: ForcetellerFacts, domain: str, limit: int = 4) -> list[dict[str, Any]]:
    domain_sets={
        'personality': _STAR_LEARNING|_STAR_INDEPENDENCE|_STAR_FORCE|_STAR_ATTRACTION|_STAR_FRICTION,
        'career': _STAR_LEARNING|_STAR_MOVEMENT|_STAR_FORCE|_STAR_HELP,
        'wealth': _STAR_HELP|_STAR_MOVEMENT|{'반안살','장성살','암록','금여성','금여록'},
        'relationships': _STAR_ATTRACTION|_STAR_HELP|_STAR_INDEPENDENCE|_STAR_FRICTION|{'현침살'},
        'romance': _STAR_ATTRACTION|_STAR_HELP|_STAR_INDEPENDENCE|_STAR_FRICTION|{'현침살'},
        'study': _STAR_LEARNING|_STAR_HELP|{'현침살'},
    }
    preferred=domain_sets.get(domain,set())
    rows=_star_rows(facts)
    ranked=sorted(rows,key=lambda r:(0 if r['name'] in preferred else 1, 0 if r['positions'] else 1))
    result=[]
    for row in ranked:
        if preferred and row['name'] not in preferred and len(result)>=2:
            continue
        result.append({
            'name': row['name'], 'category': row['category'], 'tone': row['tone'],
            'positions': row['positions'], 'summary': row['meaning'],
            'position_context': row['position_context'], 'practical': row['practical'],
            'personal_note': row.get('personal_note',''), 'day_pillar': row.get('day_pillar',''),
            'day_master': row.get('day_master',''), 'day_element': row.get('day_element',''),
        })
        if len(result)>=limit: break
    return result

def _pair_star_interplay(a: ForcetellerFacts, b: ForcetellerFacts, *, love: bool, context: str = '') -> str:
    domain='romance' if love else ('career' if context=='work' else 'relationships')
    a_rows=_star_domain_insights(a,domain,2)
    b_rows=_star_domain_insights(b,domain,2)
    if not a_rows and not b_rows:
        return ''
    bits=[]
    if a_rows:
        names=' · '.join(r['name'] for r in a_rows)
        bits.append(f'{a.profile.name}은 {names} 같은 보조 기운을 함께 보면 {a_rows[0]["practical"]}')
    if b_rows:
        names=' · '.join(r['name'] for r in b_rows)
        bits.append(f'{b.profile.name}은 {names} 같은 보조 기운을 함께 보면 {b_rows[0]["practical"]}')
    if love:
        bits.append('둘 사이에서는 끌림 자체보다 연락·약속·개인시간·표현 속도를 실제로 맞출 수 있는지가 더 중요합니다.')
    elif context=='work':
        bits.append('업무에서는 이 보조 기운을 성격 꼬리표로 쓰지 않고, 피드백 방식·역할 분담·변화 대응에서 실제로 반복되는지를 확인하는 정도로 활용합니다.')
    else:
        bits.append('관계에서는 상대를 단정하는 근거가 아니라, 서운함·거리감·도움 요청 방식에서 반복되는 패턴이 있는지 확인하는 참고점으로 봅니다.')
    return ' '.join(bits)


def _top_elements(facts: ForcetellerFacts) -> list[tuple[str, float]]:
    return sorted(((e, float(facts.element_percent.get(e, 0))) for e in ('木', '火', '土', '金', '水')), key=lambda kv: kv[1], reverse=True)


def _top_ten_gods(facts: ForcetellerFacts, n: int = 4) -> list[tuple[str, float]]:
    values = [(k, float(facts.ten_gods.get(k, 0))) for k in TEN_GODS]
    return sorted(values, key=lambda kv: kv[1], reverse=True)[:n]


def _visible_ten_gods(facts: ForcetellerFacts) -> list[dict[str, str]]:
    rows = []
    dm = facts.chart.day_master
    for pos, stem in zip(POSITION_LABELS, facts.chart.stems):
        rows.append({'position': pos, 'stem': stem, 'ten_god': ten_god(dm, stem)})
    return rows


def _hidden_ten_god_hits(facts: ForcetellerFacts, names: set[str]) -> list[str]:
    hits: list[str] = []
    for pos, branch in zip(POSITION_LABELS, facts.chart.branches):
        stems = facts.hidden_stems.get(branch) or HIDDEN_STEMS.get(branch, [])
        for stem in stems:
            tg = ten_god(facts.chart.day_master, stem)
            if tg in names:
                hits.append(f'{pos} {branch_text(branch)} 속 {stem_text(stem)}가 {ten_god_text(tg)}으로 작용')
    return hits


def _self_relations(facts: ForcetellerFacts) -> list[str]:
    rows: list[str] = []
    for (i, ba), (j, bb) in combinations(list(enumerate(facts.chart.branches)), 2):
        rels = branch_relations(ba, bb)
        if rels:
            rows.append(
                f'{POSITION_LABELS[i]}의 {branch_text(ba)}와 {POSITION_LABELS[j]}의 {branch_text(bb)} 사이에 '
                + ', '.join(f'{r}({RELATION_PLAIN.get(r, "지지 관계")})' for r in rels)
                + '가 있습니다.'
            )
    return rows


def _level(value: float) -> str:
    if value >= 30:
        return '매우 두드러짐'
    if value >= 20:
        return '두드러짐'
    if value >= 12:
        return '중간'
    if value > 0:
        return '낮은 편'
    return '표시 비율상 없음'




_MONTH_SEASON = {
    '寅': ('초봄', '木'), '卯': ('봄', '木'), '辰': ('봄의 마무리', '土'),
    '巳': ('초여름', '火'), '午': ('여름', '火'), '未': ('여름의 마무리', '土'),
    '申': ('초가을', '金'), '酉': ('가을', '金'), '戌': ('가을의 마무리', '土'),
    '亥': ('초겨울', '水'), '子': ('겨울', '水'), '丑': ('겨울의 마무리', '土'),
}

_PILLAR_LIFE_SCOPE = {
    '시주': '속으로 세우는 계획, 장기 관심사, 후반의 생활 방향을 보조해서 봅니다.',
    '일주': '내가 기본적으로 반응하는 방식과 아주 가까운 관계·생활 습관을 중심으로 봅니다.',
    '월주': '직장·사회생활에서 쓰는 방식과 태어난 계절이 원국 전체에 주는 배경을 봅니다.',
    '연주': '초기 환경, 가족·사회적 배경, 처음 사람들에게 보이는 바깥 인상을 보조해서 봅니다.',
}


def _pillar_reading(pillar: str) -> str:
    value = str(pillar or '')
    if len(value) < 2:
        return '미확정'
    return f'{STEM_READING.get(value[0], value[0])}{BRANCH_READING.get(value[1], value[1])}'


def _pillar_detail_rows(facts: ForcetellerFacts) -> list[dict[str, Any]]:
    """Build a deep natal explanation that is intentionally different from the preview.

    The preview answers "what kind of person am I?".  This block answers
    "which pillar contributes what, and how do the parts work together?".
    """
    c = facts.chart
    dm = c.day_master
    raw = [
        ('시주', c.hour_pillar if facts.profile.time_known else '', 'hour'),
        ('일주', c.day_pillar, 'day'),
        ('월주', c.month_pillar, 'month'),
        ('연주', c.year_pillar, 'year'),
    ]
    rows: list[dict[str, Any]] = []
    for label, pillar, key in raw:
        if not pillar or len(pillar) < 2:
            rows.append({
                'key': key, 'label': label, 'pillar': '', 'reading': '미확정',
                'life_scope': _PILLAR_LIFE_SCOPE[label],
                'outer': '출생시간이 확인되지 않아 이 기둥은 임의로 만들지 않습니다.' if key == 'hour' else '이 기둥의 세부 자료가 확인되지 않았습니다.',
                'foundation': '', 'evidence': '',
            })
            continue
        stem, branch = pillar[0], pillar[1]
        stem_tg = ten_god(dm, stem) if stem != dm or key != 'day' else ''
        hidden = facts.hidden_stems.get(branch) or HIDDEN_STEMS.get(branch, [])
        main_hidden = hidden[0] if hidden else ''
        branch_tg = ten_god(dm, main_hidden) if main_hidden else ''
        if key == 'day':
            outer = f'천간 {stem_text(stem)}은 바로 나를 대표하는 글자라, 판단의 출발점과 기본 반응을 보는 기준이 됩니다.'
        else:
            plain = TEN_GOD_PLAIN.get(stem_tg, '이 기둥에서 겉으로 드러나는 역할')
            outer = f'겉으로는 **{plain}** 쪽 역할이 드러나기 쉬운 자리입니다.'
        foundation = ''
        if main_hidden:
            foundation_plain = TEN_GOD_PLAIN.get(branch_tg, '생활 속에서 반복되는 바탕 역할')
            foundation = f'지지 {branch_text(branch)}의 바탕에서는 **{foundation_plain}** 쪽 반응을 함께 참고합니다.'
        evidence_bits = [f'{label} {pillar}({_pillar_reading(pillar)}주)', f'천간 {stem_text(stem)}']
        if stem_tg:
            evidence_bits.append(f'{ten_god_text(stem_tg)}')
        evidence_bits.append(f'지지 {branch_text(branch)}')
        if main_hidden:
            evidence_bits.append(f'주된 지장간 {stem_text(main_hidden)} · {ten_god_text(branch_tg)}')
        rows.append({
            'key': key, 'label': label, 'pillar': pillar, 'reading': _pillar_reading(pillar),
            'life_scope': _PILLAR_LIFE_SCOPE[label], 'outer': outer, 'foundation': foundation,
            'evidence': ' · '.join(evidence_bits),
        })
    return rows


def _chart_relation_rows(facts: ForcetellerFacts) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    branches = list(facts.chart.branches)
    for (i, ba), (j, bb) in combinations(list(enumerate(branches)), 2):
        rels = branch_relations(ba, bb)
        for rel in rels:
            plain = RELATION_PLAIN.get(rel, '두 자리가 서로 영향을 주는 관계')
            result.append({
                'title': f'{POSITION_LABELS[i]} ↔ {POSITION_LABELS[j]} · {rel}',
                'meaning': f'{branch_text(ba)}와 {branch_text(bb)}가 만나 **{plain}**로 읽습니다. 이 관계 하나만으로 좋고 나쁨을 정하지 않고, 어느 생활 영역에서 반복되는지를 함께 봅니다.',
                'evidence': f'{POSITION_LABELS[i]} {ba} ↔ {POSITION_LABELS[j]} {bb} · {rel}',
            })
    return result


def _chart_balance_report(facts: ForcetellerFacts) -> dict[str, str]:
    c = facts.chart
    month_branch = c.month_pillar[1] if len(c.month_pillar or '') >= 2 else ''
    season, season_elem = _MONTH_SEASON.get(month_branch, ('태어난 계절', ''))
    dm_elem = STEM_ELEMENT.get(c.day_master, '')
    if facts.strength_label:
        if '신강' in facts.strength_label:
            strength_plain = '내 중심 기운이 비교적 힘을 받는 편이라, 스스로 판단하고 밀고 나가는 힘을 장점으로 쓰기 쉽습니다. 다만 확신이 커질 때는 다른 사람의 속도와 관점을 확인하는 과정이 도움이 됩니다.'
        elif '신약' in facts.strength_label:
            strength_plain = '내 중심 기운이 주변 영향에 민감한 편이라, 혼자 버티기보다 환경·사람·루틴의 도움을 잘 받는 것이 중요합니다. 안정적인 조건을 만들면 오히려 섬세함과 적응력이 장점이 될 수 있습니다.'
        else:
            strength_plain = '한쪽으로 크게 치우치기보다 상황에 따라 힘을 쓰고 조절하는 균형을 중요하게 보는 편입니다.'
    else:
        strength_plain = '신강·신약 상세 판정은 저장된 원문과 캐시를 다시 확인하는 항목입니다. 판정이 없을 때 임의로 강약을 만들어 해석하지 않습니다.'
    useful = ', '.join(element_text(e) for e in facts.useful_elements) if facts.useful_elements else ''
    useful_plain = (
        f'균형을 보완할 때는 {useful} 방향을 우선 참고합니다. 이것은 “무조건 많이 가져야 하는 요소”라기보다, 원국이 한쪽 방식에 치우칠 때 어떤 성질을 더 쓰면 편해지는지를 보는 기준입니다.'
        if useful else
        '균형을 돕는 기운이 확인되지 않은 상태에서는 특정 오행을 임의로 추천하지 않습니다.'
    )
    season_plain = (
        f'태어난 달의 지지는 {branch_text(month_branch)}로 **{season}**의 배경을 가집니다. {season_elem}({ELEMENT_READING.get(season_elem, season_elem)}) 기운이 계절의 바탕이 되어, 나를 대표하는 {stem_text(c.day_master)}({ELEMENT_READING.get(dm_elem, dm_elem)})가 실제로 얼마나 힘을 받는지 판단할 때 중요한 기준이 됩니다.'
        if month_branch else '태어난 달의 계절 배경이 확인되지 않았습니다.'
    )
    return {
        'season': season_plain,
        'strength': strength_plain,
        'useful': useful_plain,
        'technical': f'월지 {branch_text(month_branch) if month_branch else "미확인"} · 신강·신약 {facts.strength_label or "미확인"} · 용신/균형 기운 {useful or "미확인"}',
    }


def _chart_detail_report(facts: ForcetellerFacts) -> dict[str, Any]:
    c = facts.chart
    relations = _chart_relation_rows(facts)
    stars = _star_rows(facts)
    top_elements = _top_elements(facts)
    element_summary = ', '.join(f'{ELEMENT_READING[e]} {pct:.1f}%' for e, pct in top_elements[:3])
    return {
        'intro': {
            'title': '원국 전체 해설은 “성격 요약”이 아니라 네 기둥이 맡는 역할을 풀어봅니다.',
            'text': f'해석의 중심은 일주 {c.day_pillar or "미확인"}({_pillar_reading(c.day_pillar)}주)이고, 월주가 태어난 계절과 사회생활의 배경을 더합니다. 시주·연주는 각각 장기 관심과 초기 환경을 보조해서 봅니다.',
        },
        'pillars': _pillar_detail_rows(facts),
        'balance': _chart_balance_report(facts),
        'relations': relations,
        'stars': stars,
        'element_context': {
            'summary': f'오행 비율에서 상대적으로 먼저 눈에 들어오는 세 축은 {element_summary}입니다. 숫자 자체보다 어떤 역할이 반복되고 어떤 역할이 상대적으로 덜 쓰이는지를 확인하는 데 사용합니다.',
            'evidence': ' · '.join(f'{element_text(e)} {pct:.1f}%' for e, pct in top_elements),
        },
    }

def _profile_key_points(facts: ForcetellerFacts) -> list[dict[str, str]]:
    c = facts.chart
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    top_elements = _top_elements(facts)
    points: list[dict[str, str]] = [
        {
            'title': '판단할 때 먼저 필요한 것',
            'evidence': f'{term("日干")} = {stem_text(c.day_master)} · 주된 역할 성향 {first["label"]}',
            'meaning': f'중요한 일을 결정할 때는 **{first["need"]}**이 확보되어야 생각이 정리되고 판단도 빨라지는 편입니다.',
        },
        {
            'title': '일할 때 강점이 살아나는 방식',
            'evidence': f'주된 역할 성향 {first["label"]} · 보조 역할 성향 {second["label"]}',
            'meaning': f'기본적으로 **{first["work"]}**에서 강점이 잘 드러나고, 필요할 때 **{second["work"]}**을 보완 역할로 쓰면 결과가 안정적입니다.',
        },
        {
            'title': '사람과 대화할 때 편한 방식',
            'evidence': '십성 역할 분포를 생활 언어로 환산',
            'meaning': f'상대가 **{first["talk"]}** 방식으로 이야기해 주면 방어적으로 되기보다 내 생각을 분명하게 설명하기 쉽습니다.',
        },
    ]
    if facts.strength_label:
        if '신강' in facts.strength_label:
            strength_meaning = '스스로 기준을 잡고 밀어붙이는 힘이 장점이 되기 쉽습니다. 다만 확신이 강해질수록 **상대가 따라올 시간과 다른 관점을 확인하는 과정**을 일부러 넣는 편이 좋습니다.'
        elif '신약' in facts.strength_label:
            strength_meaning = '환경과 주변 사람의 영향을 세밀하게 받는 편이라 **안정적인 루틴·역할·지원 환경을 먼저 만드는 것**이 힘을 쓰는 데 도움이 됩니다.'
        else:
            strength_meaning = '상황에 따라 힘을 밀고 당기는 균형이 중요한 편이라 **무조건 버티거나 무조건 기대기보다 필요한 순간에 방식을 바꾸는 것**이 중요합니다.'
        points.append({
            'title': '힘을 쓰고 조절하는 방식',
            'evidence': f'{term("身强身弱")} = {facts.strength_label}',
            'meaning': strength_meaning,
        })
    if facts.useful_elements:
        useful = ', '.join(element_text(e) for e in facts.useful_elements)
        points.append({
            'title': '한쪽으로 치우칠 때 보완하는 방향',
            'evidence': f'{term("用神")} = {useful}',
            'meaning': f'평소 잘하는 방식만 반복해 답답해질 때는 **{useful}이 상징하는 역할을 의식적으로 더 쓰는 것**이 균형을 잡는 데 도움이 됩니다.',
        })
    elif top_elements:
        points.append({
            'title': '원국에서 많이 쓰는 역할',
            'evidence': f'오행 상위 {element_text(top_elements[0][0])} {top_elements[0][1]:.1f}%',
            'meaning': f'현재 원국에서는 **{ELEMENT_PLAIN[top_elements[0][0]]}** 쪽 역할을 반복해서 쓰기 쉬운 편입니다. 강점으로 쓰되 모든 상황을 같은 방식으로 해결하려 하지는 않는 것이 좋아요.',
        })
    return points

def _personality_dimensions(facts: ForcetellerFacts) -> list[dict[str, str]]:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    return [
        {
            'title': '편안함을 느끼는 조건',
            'assessment': first['need'],
            'evidence': f'주된 생활 반응 축: {first["label"]}',
            'practical': f'{first["need"]}이 보장될 때 판단과 표현이 자연스럽습니다. 반대로 이 조건이 무너지면 평소보다 예민해질 수 있습니다.',
        },
        {
            'title': '생각을 정리하는 방식',
            'assessment': second['label'] + ' 방식으로 보완하는 편',
            'evidence': f'보조 반응 축: {second["label"]}',
            'practical': f'첫 반응만 보고 성격을 단정하기보다, 중요한 결정에서는 {second["need"]}도 함께 필요하다는 점을 고려하는 편이 좋습니다.',
        },
        {
            'title': '대화할 때 편한 방식',
            'assessment': first['talk'],
            'evidence': '십성 역할의 상대적 분포를 생활 언어로 환산',
            'practical': f'상대가 {first["talk"]} 방식으로 말해 줄 때 오해가 줄고, 필요한 의견을 더 분명하게 내기 쉽습니다.',
        },
        {
            'title': '스트레스를 받기 쉬운 상황',
            'assessment': first['conflict'],
            'evidence': f'주된 반응 축 {first["label"]}이 막힐 때의 그림자',
            'practical': '스트레스 상황에서는 원래 장점이 과해질 수 있으므로, 즉시 결론을 내리기보다 내가 지금 무엇 때문에 불편한지 조건을 먼저 분리해 보는 편이 좋습니다.',
        },
        {
            'title': '회복하는 방법',
            'assessment': '강한 반응을 더 밀어붙이기보다 반대 역할을 잠깐 빌리는 방식',
            'evidence': '원국의 강한 축과 보완 축을 함께 고려',
            'practical': f'{first["conflict"]} 상황에서는 {second["talk"]}처럼 평소보다 한 단계 다른 방식을 의식적으로 써 보는 것이 도움이 될 수 있습니다.',
        },
    ]


def _personality_text(facts: ForcetellerFacts) -> str:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    return (
        f'기본적으로 {first["label"]}을 중요하게 여기고, {second["label"]}이 그 방식을 보완하는 편입니다. '
        f'단순히 내향적·외향적이라고 나누기보다 “어떤 조건에서 마음이 편해지는가”가 더 분명한 사람에 가깝습니다. '
        f'{first["need"]}이 확보되면 장점이 잘 살아나고, 반대로 {first["conflict"]} 상황이 반복되면 평소보다 방어적이거나 예민해질 수 있습니다. '
        f'이럴 때는 성격이 나쁘다고 판단하기보다, 먼저 필요한 조건이 무엇인지 말로 정리하는 편이 도움이 됩니다.'
    )

def _career_dimensions(facts: ForcetellerFacts) -> list[dict[str, str]]:
    t = _axis_totals(facts)
    top = max(t, key=t.get)
    top_name = {'peer':'자율·동료','output':'표현·생산','wealth':'현실·성과','officer':'책임·규칙','resource':'학습·전문성'}[top]
    rows: list[dict[str, str]] = []
    rows.append({'title':'조직 적합도','assessment':('규칙과 역할이 명확한 조직에서 장점을 쓰기 쉬운 편' if t['officer'] >= 18 else '규칙 자체보다 실무 자율성과 역할 명확성이 더 중요한 편'), 'evidence':f'관성 계열 {t["officer"]:.1f}% · 인성 계열 {t["resource"]:.1f}%', 'practical':'상사 지시가 모호하거나 책임만 크고 권한이 없는 환경보다, 기준·권한·성과 기대가 분명한 환경이 맞는지 확인하는 것이 중요합니다.'})
    rows.append({'title':'독립 업무와 자기주도성','assessment':('혼자 기준을 잡고 맡은 영역을 끝까지 가져가는 방식이 잘 맞을 가능성' if t['peer'] >= 15 else '완전 독립형보다는 역할이 연결된 협업 구조에서 안정적인 편'), 'evidence':f'비견·겁재 계열 {t["peer"]:.1f}%', 'practical':'비겁이 높을수록 자율성은 장점이지만 동료와 권한이 겹치면 피로가 커질 수 있어 책임 경계를 명확히 두는 편이 좋습니다.'})
    rows.append({'title':'전문성·자격·학습','assessment':('배우고 체계화한 것을 전문성으로 쌓는 축이 강한 편' if t['resource'] >= 18 else '이론을 오래 쌓기보다 필요한 지식을 실무에 바로 적용하는 편이 효율적'), 'evidence':f'정인·편인 계열 {t["resource"]:.1f}%', 'practical':'인성은 문서·학습·자격·지원과 연결해 봅니다. 자격증 자체보다 배운 지식을 반복해서 쓰는 직무인지가 더 중요합니다.'})
    rows.append({'title':'창의·문제해결·산출','assessment':('문제를 발견하고 결과물로 바꾸는 힘이 눈에 띄는 편' if t['output'] >= 18 else '표현보다 구조·검증·안정성을 먼저 잡는 편'), 'evidence':f'식신·상관 계열 {t["output"]:.1f}%', 'practical':'식상 비중이 높다면 개선안·문서·코드·설계·기획처럼 “무언가를 만들어 내는 업무”에서 답답함이 덜할 수 있습니다.'})
    rows.append({'title':'리더십·관리','assessment':('권한과 책임이 함께 주어질 때 관리 역할을 소화하기 쉬운 편' if t['officer'] + t['wealth'] >= 35 else '사람을 관리하기보다 전문 영역을 맡아 영향력을 갖는 방식이 더 자연스러울 수 있음'), 'evidence':f'관성 {t["officer"]:.1f}% + 재성 {t["wealth"]:.1f}%', 'practical':'리더십을 “사람을 통제하는 힘”이 아니라 일정·기준·자원·책임을 정리하는 능력으로 보는 것이 적합합니다.'})
    rows.append({'title':'상사와의 관계','assessment':('기준이 일관된 상사와는 안정적이지만 불합리한 통제에는 민감할 수 있음' if t['officer'] >= 12 or t['output'] >= 18 else '지시와 지원의 균형이 있는 관계가 중요'), 'evidence':f'관성 {t["officer"]:.1f}% · 식상 {t["output"]:.1f}%', 'practical':'관성과 식상이 함께 강하면 “규칙은 필요하지만 납득되지 않는 규칙에는 질문하는” 양상이 생기기 쉬우므로 의사결정 근거가 투명한 환경이 유리합니다.'})
    rows.append({'title':'동료와의 관계','assessment':('협업에서 역할 중복과 주도권이 핵심 변수' if t['peer'] >= 15 else '동료 경쟁보다는 역할 보완이 더 중요'), 'evidence':f'비견·겁재 {t["peer"]:.1f}%', 'practical':'같은 일을 두 사람이 동시에 책임지는 구조보다 담당 범위가 명확한 협업이 피로를 줄이는 데 유리합니다.'})
    rows.append({'title':'안정 조직 vs 프로젝트형','assessment':('프로젝트·문제해결형 업무와 궁합이 좋은 편' if t['output'] + t['peer'] > t['officer'] + t['resource'] else '지속적인 전문성 축적과 안정적 조직 구조가 더 잘 맞는 편'), 'evidence':f'표현·자율 {t["output"]+t["peer"]:.1f}% vs 규칙·학습 {t["officer"]+t["resource"]:.1f}%', 'practical':'완전한 안정/변화를 이분법으로 보지 말고, “안정된 기반 안에서 프로젝트를 맡는 형태”처럼 두 장점을 결합할 수 있습니다.'})
    rows.append({'title':'스트레스가 큰 환경','assessment':'자신의 핵심 역할축과 반대로 일해야 하는 환경에서 소모가 커질 수 있음', 'evidence':f'가장 두드러지는 역할축: {top_name} {t[top]:.1f}%', 'practical':'예를 들어 표현·생산 축이 강한데 반복 승인만 많은 환경, 관성 축이 강한데 책임과 절차가 전혀 없는 환경처럼 강점이 봉쇄되는 구조를 주의합니다.'})
    rows.append({'title':'장기 성장 방식','assessment':'한 번의 이직운보다 “어떤 역할을 반복해서 강화하느냐”가 중요', 'evidence':f'용신 {", ".join(facts.useful_elements) if facts.useful_elements else "미확인"} · {facts.strength_label or "강약 미확인"}', 'practical':'현재 원국의 강점과 용신 방향을 기준으로 전문성·성과·책임 중 어떤 축을 의도적으로 키울지 정하면 경력의 일관성이 생깁니다.'})
    return rows


def _career_text(facts: ForcetellerFacts) -> str:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    return (
        f'직장에서는 {first["work"]}을 맡을 때 강점을 쓰기 쉽습니다. '
        f'여기에 {second["work"]}이 보완 역할로 붙으면 더 안정적입니다. '
        f'반대로 {first["conflict"]} 조직에서는 실력과 별개로 소모가 커질 수 있으므로, 직무명보다 권한·책임·피드백 방식이 나와 맞는지 확인하는 편이 중요합니다.'
    )

def _wealth_dimensions(facts: ForcetellerFacts) -> list[dict[str, str]]:
    t = _axis_totals(facts)
    strong = facts.strength_label or '강약 미확인'
    return [
        {'title':'돈을 버는 방식','assessment':('성과와 자원을 직접 다루는 방식이 비교적 선명' if t['wealth'] >= 18 else '재물 자체보다 기술·전문성·역할을 통해 수입으로 연결하는 방식이 더 중요'), 'evidence':f'재성 {t["wealth"]:.1f}% · 식상 {t["output"]:.1f}%', 'practical':'재성 비중이 낮아도 식상·인성·관성이 강하면 전문성이나 역할을 통해 안정적인 수입 구조를 만들 수 있습니다.'},
        {'title':'수입 안정성','assessment':('고정적인 관리와 계획을 선호할 가능성' if facts.ten_gods.get('정재',0) >= facts.ten_gods.get('편재',0) else '기회·변동·대외 활동에서 수입 가능성을 찾는 성향이 더 두드러질 수 있음'), 'evidence':f'정재 {facts.ten_gods.get("정재",0):.1f}% vs 편재 {facts.ten_gods.get("편재",0):.1f}%', 'practical':'실제 소득 형태는 직업 환경의 영향을 훨씬 크게 받으므로 이 항목은 “돈을 다루는 선호 방식”으로 보는 편이 좋습니다.'},
        {'title':'현금흐름·지출','assessment':('사람·활동·경험에 자원이 분산될 때 관리가 필요' if t['peer'] + t['output'] >= 30 else '지출보다 계획과 보유 쪽이 상대적으로 중요'), 'evidence':f'비겁 {t["peer"]:.1f}% + 식상 {t["output"]:.1f}%', 'practical':'비겁은 공동 이해관계, 식상은 활동·표현과 연결하므로 자동저축·예산 구획처럼 의사결정을 미리 구조화하면 안정성이 높아집니다.'},
        {'title':'저축·자산 축적','assessment':'한 번의 큰 기회보다 반복 가능한 수입·저축 규칙을 만드는 편이 안전', 'evidence':f'일간 세력 판정 {strong} · 재성 {t["wealth"]:.1f}%', 'practical':'명리에서 재성은 “돈이 들어온다”보다 “내가 현실 자원을 감당하고 관리하는 방식”으로 보는 것이 정확합니다.'},
        {'title':'투자·위험 감수','assessment':('변동성에 끌리기보다 검증·기준을 세우는 편이 적합' if t['resource'] + t['officer'] >= t['wealth'] + t['output'] else '기회를 빠르게 보는 장점이 있지만 손실 한도를 먼저 정하는 것이 중요'), 'evidence':f'인성+관성 {t["resource"]+t["officer"]:.1f}% vs 재성+식상 {t["wealth"]+t["output"]:.1f}%', 'practical':'이 항목은 투자 추천이 아니라 위험을 다루는 습관에 대한 전통적 해석입니다.'},
        {'title':'사람과 돈','assessment':('동료·지인과 금전 경계를 명확히 하는 것이 중요' if t['peer'] >= 15 else '공동자금보다 개인 기준을 세우는 것이 중요'), 'evidence':f'비견·겁재 {t["peer"]:.1f}%', 'practical':'대여·공동구매·공동투자처럼 관계와 돈이 섞일 때는 계약과 분담 기준을 먼저 정하는 것이 좋습니다.'},
        {'title':'커리어와 재물의 연결','assessment':'돈만 따로 보기보다 직업에서 어떤 결과물을 반복 생산하는지가 핵심', 'evidence':f'식상 {t["output"]:.1f}% → 재성 {t["wealth"]:.1f}% 흐름', 'practical':'기술·아이디어·생산이 재성으로 이어지는 구조가 충분한지 현재 운과 함께 볼 때 현실적인 재물 해석이 됩니다.'},
        {'title':'장기 자산 형성','assessment':'원국보다 현재 운에서 재성·식상·비겁이 어떻게 들어오는지가 시기별 차이를 만듦', 'evidence':f'용신 {", ".join(facts.useful_elements) if facts.useful_elements else "미확인"}', 'practical':'장기 자산은 명리 점수보다 실제 소득률·저축률·부채·투자원칙의 영향이 더 크므로 운세는 보조 타이밍으로만 활용합니다.'},
    ]


def _wealth_text(facts: ForcetellerFacts) -> str:
    _, first = _dominant_style(facts)
    t = _axis_totals(facts)
    if t['wealth'] >= max(t['resource'], t['officer']):
        core = '돈과 자원을 직접 관리하고 결과를 확인하는 방식이 비교적 자연스러운 편입니다.'
    elif t['output'] >= 18:
        core = '돈 자체를 좇기보다 기술·아이디어·결과물을 만들고 그것을 수입으로 연결하는 방식이 더 자연스러운 편입니다.'
    else:
        core = '단기 기회보다 전문성·역할을 안정적으로 쌓아 수입 구조를 만드는 방식이 더 잘 맞는 편입니다.'
    return (
        core + ' 실제 자산 형성에서는 사주 비율보다 수입·저축·부채 관리가 훨씬 직접적입니다. '
        f'특히 {first["conflict"]} 상황에서는 사람과 돈, 책임이 한꺼번에 얽히지 않도록 기준을 미리 정하는 편이 좋습니다.'
    )

def _relationship_dimensions(facts: ForcetellerFacts) -> list[dict[str, str]]:
    t = _axis_totals(facts)
    return [
        {'title':'친구 관계','assessment':('가깝게 지내도 각자의 영역과 주도권이 필요' if t['peer'] >= 15 else '친구와 역할이 겹치기보다 서로 다른 장점을 주고받는 방식이 편할 수 있음'), 'evidence':f'비견·겁재 {t["peer"]:.1f}%', 'practical':'친밀함과 경계가 동시에 필요하므로 연락 빈도보다 존중 방식과 약속 이행을 보는 편이 중요합니다.'},
        {'title':'직장 동료','assessment':('업무 기준을 명확히 나눈 협업에서 강점' if t['peer'] + t['officer'] >= 25 else '공동 목표보다 자신의 전문 역할이 명확할 때 편함'), 'evidence':f'비겁 {t["peer"]:.1f}% · 관성 {t["officer"]:.1f}%', 'practical':'책임 소재가 흐리면 같은 일에 대한 기대가 달라질 수 있으므로 누가 무엇을 결정하는지 명확한 구조가 좋습니다.'},
        {'title':'선배·상사','assessment':('근거와 기준이 있는 조언은 잘 활용하지만 일방적인 통제는 피로할 수 있음' if t['resource'] + t['output'] >= 25 else '일관된 기준과 안정적인 피드백이 중요'), 'evidence':f'인성 {t["resource"]:.1f}% · 식상 {t["output"]:.1f}%', 'practical':'배우는 관계인지 통제받는 관계인지에 따라 체감이 크게 달라질 수 있습니다.'},
        {'title':'아주 가까운 관계','assessment':'관계의 양보다 “안전하게 솔직해질 수 있는가”가 중요', 'evidence':f'{term("日支")} = {branch_text(facts.chart.spouse_palace)}', 'practical':'일지는 가까운 생활 관계의 자리이므로 상대의 일지와 만났을 때 합·충·형·파·해가 어떻게 생기는지를 1:1 궁합에서 따로 보는 것이 정확합니다.'},
    ]


def _relationship_text(facts: ForcetellerFacts) -> str:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    return (
        f'관계에서는 {first["need"]}을 중요하게 느끼는 편입니다. 친해졌다고 해서 모든 시간을 공유하기보다, '
        f'{first["talk"]} 방식이 지켜질 때 편안함이 오래갑니다. {second["label"]} 성향도 함께 있어 관계가 깊어질수록 '
        f'{second["need"]} 역시 중요해질 수 있습니다. 그래서 “연락을 많이 하느냐”보다 약속·경계·피드백 방식이 맞는지가 실제 체감에 더 크게 작용합니다.'
    )

def _romance_dimensions(facts: ForcetellerFacts) -> list[dict[str, str]]:
    t = _axis_totals(facts)
    spouse_names = ('정관', '편관') if facts.profile.gender == 'F' else ('정재', '편재')
    spouse_amount = sum(float(facts.ten_gods.get(k, 0)) for k in spouse_names)
    spouse_visible = [r for r in _visible_ten_gods(facts) if r['ten_god'] in spouse_names]
    spouse_hidden = _hidden_ten_god_hits(facts, set(spouse_names))

    if t['officer'] >= 15:
        relationship_expectation = (
            '좋아한다는 말만큼 **약속을 지키는 태도, 관계를 애매하게 끌지 않는 태도, 문제가 생겼을 때 책임 있게 대화하는 것**에서 신뢰를 느끼기 쉬운 편입니다.'
        )
        expectation_tip = '상대의 마음을 추측하기보다 연락·약속·독점성·장기 계획처럼 관계의 기준을 말로 합의할수록 편합니다.'
    else:
        relationship_expectation = (
            '**서로의 개인시간과 생활을 존중하면서도 필요할 때 확실히 연결되는 관계**를 편하게 느끼기 쉽습니다. 관계의 형식보다 실제로 함께 있을 때 편안한지가 중요할 수 있습니다.'
        )
        expectation_tip = '연락 횟수나 정형화된 연애 규칙보다 서로 부담 없이 유지할 수 있는 리듬을 직접 정하는 편이 좋습니다.'

    if t['output'] >= 15:
        affection = '호감이 생기면 **대화·행동·함께하는 시간처럼 밖으로 드러나는 방식**으로 표현하기 쉬운 편입니다.'
    else:
        affection = '호감이 생겨도 바로 크게 표현하기보다 **상대가 안전한 사람인지 확인한 뒤 행동으로 보여주는 방식**이 더 자연스러울 수 있습니다.'

    if spouse_visible:
        relationship_action = '연애 감정을 마음속에만 두기보다 **상대와의 관계를 현실적인 선택이나 행동으로 연결하려는 면**이 겉으로 드러나기 쉬운 편입니다.'
    elif spouse_hidden:
        relationship_action = '연애에 관심이 없다는 뜻이 아니라, **마음이 생겨도 충분히 확신하기 전에는 관계를 겉으로 확정하지 않는 편**으로 나타날 수 있습니다.'
    else:
        relationship_action = '연애나 결혼을 삶의 유일한 기준으로 두기보다, **상대와 실제 생활이 맞는지를 확인하면서 관계를 정하는 편**이 더 자연스러울 수 있습니다.'

    return [
        {
            'title':'연애에서 가장 중요하게 느끼는 것',
            'assessment': relationship_expectation,
            'evidence':f'관성 {t["officer"]:.1f}% · 비겁 {t["peer"]:.1f}%',
            'practical': expectation_tip,
        },
        {
            'title':'호감과 애정 표현',
            'assessment': affection,
            'evidence':f'식신·상관 {t["output"]:.1f}%',
            'practical':'상대가 주는 애정 표현이 내 방식과 다를 수 있으므로 “좋아하면 당연히 이렇게 해야 한다”보다 받고 싶은 표현을 구체적으로 말하는 편이 좋습니다.',
        },
        {
            'title':'마음이 실제 관계로 이어지는 방식',
            'assessment': relationship_action,
            'evidence':f'전통 배우자성 참고: {"/".join(spouse_names)} · 천간 노출 {len(spouse_visible)}회 · 지장간 보조 {len(spouse_hidden)}회',
            'practical':'이 항목은 결혼 시기나 횟수를 단정하는 지표가 아닙니다. 실제 상대와 만났을 때 관계를 어떻게 결정하고 유지하는지 보는 보조 근거로만 사용합니다.',
        },
        {
            'title':'가까워질수록 중요해지는 생활 궁합',
            'assessment':'연애가 깊어질수록 **연락 빈도, 약속 변경, 혼자 쉬는 시간, 함께 쓰는 공간, 돈을 쓰는 기준**처럼 반복되는 일상에서 궁합을 더 크게 체감할 수 있습니다.',
            'evidence':f'{term("日支")} = {branch_text(facts.chart.spouse_palace)}',
            'practical':'초반의 설렘보다 실제로 피곤한 날·바쁜 날·돈을 써야 하는 상황에서 서로를 어떻게 대하는지 확인하는 것이 장기 관계 판단에 더 유용합니다.',
        },
        {
            'title':'갈등이 생겼을 때',
            'assessment':('감정이나 문제를 **말로 꺼내 빨리 정리하려는 쪽**으로 기울 수 있습니다.' if t['output'] >= t['resource'] else '바로 답하기보다 **먼저 혼자 생각을 정리하고 안전해진 뒤 대화하는 쪽**이 자연스러울 수 있습니다.'),
            'evidence':f'식상 {t["output"]:.1f}% · 인성 {t["resource"]:.1f}%',
            'practical':'상대가 반대 속도라면 한쪽은 재촉받고 다른 쪽은 무시당한다고 느끼기 쉽습니다. “지금 10분 이야기할지, 오늘 저녁에 다시 이야기할지”처럼 대화 시점을 합의하는 편이 좋습니다.',
        },
        {
            'title':'상처가 오래 남기 쉬운 지점',
            'assessment':'단순한 의견 차이보다 **약속을 반복해서 어기거나, 책임을 한쪽에 미루거나, 관계의 기준을 상황마다 바꾸는 행동**에서 실망이 커질 수 있습니다.',
            'evidence':f'관성 {t["officer"]:.1f}% · 재성 {t["wealth"]:.1f}%',
            'practical':'궁합 점수가 높아도 거짓말·무시·일방적인 통제처럼 존중을 해치는 행동은 좋은 관계의 근거가 되지 않습니다.',
        },
        {
            'title':'배우자로 함께 살 때 확인할 것',
            'assessment':'감정적 끌림과 별개로 **돈, 집안일, 주거, 가족과의 경계, 개인시간, 아플 때의 돌봄, 큰 결정을 누가 어떻게 내리는지**가 결혼 만족도를 크게 좌우합니다.',
            'evidence':f'일지 {branch_text(facts.chart.spouse_palace)} · 전통 배우자성 참고량 {spouse_amount:.1f}%',
            'practical':'결혼 전에는 “사랑하느냐”뿐 아니라 생활비·집안일·부모님과의 거리·주말 사용·커리어 이동 같은 현실 질문을 실제로 이야기해 보는 편이 좋습니다.',
        },
        {
            'title':'잘 맞는 상대의 특징',
            'assessment':'내 소통 속도와 생활 기준을 존중하면서, 내가 놓치기 쉬운 부분은 보완하고 **서로 다른 강점을 경쟁이 아니라 역할 분담으로 연결할 수 있는 사람**과 편안함이 커지기 쉽습니다.',
            'evidence':'용신·일지·십성·천간·전체 지지 관계를 함께 평가',
            'practical':'“특정 일주라서 무조건 잘 맞는다”보다 실제로 서로 원하는 관계, 생활 리듬, 갈등 회복 방식이 맞는지 함께 확인합니다.',
        },
    ]

def _romance_text(facts: ForcetellerFacts) -> str:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    return (
        f'연애에서는 {first["need"]}이 충족될 때 안정감을 느끼기 쉽고, {second["need"]}도 장기 관계에서 중요해질 수 있습니다. '
        f'갈등이 생기면 {first["conflict"]} 패턴을 특히 조심해야 합니다. 잘 맞는 상대는 단순히 특정 오행이 많은 사람이 아니라, '
        f'내가 필요로 하는 소통 속도·생활 방식·책임감과 상대의 실제 반응 방식이 맞고, 갈등 뒤 다시 연결되는 규칙을 함께 만들 수 있는 사람입니다.'
    )

def _study_dimensions(facts: ForcetellerFacts) -> list[dict[str, str]]:
    t = _axis_totals(facts)
    research_first = t['resource'] >= t['output']
    return [
        {
            'title': '배우는 순서',
            'assessment': ('원리를 이해하고 구조를 잡은 뒤 적용하는 방식이 편한 편' if research_first else '직접 해 보고 결과를 확인하면서 원리를 붙이는 방식이 편한 편'),
            'evidence': f'학습·지원 축 {t["resource"]:.1f}% · 표현·결과 축 {t["output"]:.1f}%',
            'practical': ('교재나 개념도를 먼저 정리한 뒤 문제·프로젝트로 넘어가면 효율이 좋습니다.' if research_first else '짧은 예제나 문제를 먼저 풀고, 막힌 부분을 다시 개념으로 돌아가 보완하는 방식이 잘 맞습니다.'),
        },
        {
            'title': '자격증·시험 준비',
            'assessment': ('범위와 기준이 명확한 시험에서 계획을 세워 누적하는 방식이 유리' if t['officer'] + t['resource'] >= 28 else '문제 유형을 빠르게 익히고 반복 적용하는 방식이 유리'),
            'evidence': f'기준·책임 축 {t["officer"]:.1f}% · 학습·지원 축 {t["resource"]:.1f}%',
            'practical': '시험일을 기준으로 역산해 개념 학습·문제풀이·오답 재풀이를 분리하고, 한 번 본 내용을 실제 문제에서 다시 꺼내 쓰는 루틴이 중요합니다.',
        },
        {
            'title': '전문성으로 만드는 방식',
            'assessment': ('깊게 이해한 내용을 체계화해 전문 영역으로 쌓는 힘을 쓰기 좋은 편' if t['resource'] >= 18 else '실제 결과물과 경험을 반복해 전문성을 증명하는 방식이 더 중요'),
            'evidence': f'학습·지원 축 {t["resource"]:.1f}% · 표현·결과 축 {t["output"]:.1f}%',
            'practical': '자격증 개수보다 배운 내용을 업무·프로젝트·문서·코드·포트폴리오처럼 다시 사용할 수 있는 형태로 남기는 편이 좋습니다.',
        },
        {
            'title': '집중이 잘 되는 환경',
            'assessment': ('자료를 충분히 확인할 수 있고 방해가 적은 환경' if t['resource'] >= t['peer'] else '내가 속도와 순서를 조절할 수 있는 자율적인 환경'),
            'evidence': f'학습·지원 {t["resource"]:.1f}% · 자기주도·동료 {t["peer"]:.1f}%',
            'practical': '집중이 깨질 때 의지 문제로 보기보다, 정보 부족·방해·과도한 통제 중 무엇이 원인인지 나눠서 환경을 조정해 보세요.',
        },
        {
            'title': '학습에서 막히기 쉬운 지점',
            'assessment': ('이해가 완벽해질 때까지 시작을 미루는 것' if research_first else '빨리 해보는 대신 복습과 체계화가 뒤로 밀리는 것'),
            'evidence': '학습 축과 산출 축의 상대적 차이',
            'practical': ('70% 이해되면 문제나 프로젝트로 넘어가 실제 빈틈을 확인하는 규칙이 좋습니다.' if research_first else '실습 후 10분이라도 왜 그렇게 동작했는지 메모해 지식을 체계화하는 규칙이 좋습니다.'),
        },
    ]


def _study_text(facts: ForcetellerFacts) -> str:
    t = _axis_totals(facts)
    if t['resource'] >= t['output']:
        core = '학습에서는 원리와 배경을 이해하고 체계를 잡아야 오래 기억되는 편입니다.'
    else:
        core = '학습에서는 설명만 오래 듣기보다 문제·실습·프로젝트로 바로 써 볼 때 이해가 빨라지는 편입니다.'
    return core + ' 가장 효율적인 방식은 “배운 내용을 다시 꺼내 쓰는 것”까지 한 세트로 만드는 것입니다. 자격증·시험은 합격 자체보다 이후 업무에서 반복 사용할 수 있는 지식으로 연결할 때 강점이 오래갑니다.'


def _element_sections(facts: ForcetellerFacts) -> list[dict[str, Any]]:
    rows = []
    day_e = STEM_ELEMENT[facts.chart.day_master]
    for e in ('木', '火', '土', '金', '水'):
        pct = float(facts.element_percent.get(e, 0.0))
        if pct >= 40: state = '상대적으로 매우 강함'
        elif pct >= 25: state = '상대적으로 강함'
        elif pct >= 12: state = '중간'
        elif pct > 0: state = '낮은 편'
        else: state = '표시 비율상 0%'
        if e in facts.useful_elements:
            role = '현재 원국의 균형에 도움이 되는 용신으로 확인된 기운이라, 단순 비율보다 “어떻게 활용되는가”가 중요합니다.'
        elif e == day_e:
            role = '본인을 대표하는 일간과 같은 오행이라 자기 에너지·동료성의 바탕을 봅니다.'
        elif GENERATES[e] == day_e:
            role = '일간을 생해 주는 오행이라 학습·지원·회복의 배경으로 해석할 수 있습니다.'
        elif GENERATES[day_e] == e:
            role = '일간이 생해 주는 오행이라 표현·생산·결과물을 만드는 방향과 연결됩니다.'
        elif CONTROLS[day_e] == e:
            role = '일간이 제어하는 오행이라 현실 자원·성과·재물과 연결해 봅니다.'
        else:
            role = '일간을 제어하는 오행이라 규칙·책임·압박과 연결해 봅니다.'
        rows.append({'element':e,'label':element_text(e),'percent':pct,'state':state,'explanation':f'{element_text(e)}는 {pct:.1f}%로 {state}입니다. {role} 비율이 낮다고 무조건 보충할 기운은 아니며 용신과 강약이 우선입니다.'})
    return rows


def _ten_god_sections(facts: ForcetellerFacts) -> list[dict[str, Any]]:
    visible = _visible_ten_gods(facts)
    rows = []
    for name in TEN_GODS:
        pct = float(facts.ten_gods.get(name, 0.0))
        positions = [r['position'] for r in visible if r['ten_god'] == name]
        pos_text = ', '.join(positions) if positions else '천간에 직접 드러나지 않음'
        rows.append({'name':name,'label':ten_god_text(name),'percent':pct,'state':_level(pct),'explanation':f'{ten_god_text(name)}은 {TEN_GOD_PLAIN[name]}를 보는 역할축입니다. 현재 비율 {pct:.1f}%로 {_level(pct)}이며, 위치는 {pos_text}입니다. 0%여도 삶의 해당 영역이 없다는 뜻은 아니고 운이나 상대 원국에서 새롭게 들어올 수 있습니다.'})
    return rows


def _deep_synthesis(facts: ForcetellerFacts) -> dict[str, str]:
    _, first = _dominant_style(facts)
    _, second = _secondary_style(facts)
    return {
        'personality': f'핵심은 {first["label"]}과 {second["label"]}이 같이 작동한다는 점입니다. 평소에는 {first["talk"]} 방식이 편하지만 상황에 따라 {second["talk"]} 방식도 필요합니다. 한쪽만 강요되는 환경보다 두 방식을 번갈아 쓸 수 있을 때 훨씬 자연스럽습니다.',
        'career': f'직장에서는 {first["work"]}을 중심 역할로 두고, {second["work"]}을 보조 역할로 배치하면 강점을 쓰기 쉽습니다. 직무명보다 실제로 어떤 권한을 받고 어떤 방식으로 평가받는지 확인하는 것이 더 중요합니다.',
        'wealth': '재물은 “돈복”보다 돈을 벌게 만드는 일의 구조, 반복 지출, 저축 규칙, 사람과 돈이 섞일 때의 경계를 따로 보는 편이 유용합니다. 기술이나 전문성이 수입으로 연결되는 경로를 만드는 것이 핵심입니다.',
        'relationships': f'사람 관계에서는 {first["need"]}이 기본 욕구에 가깝습니다. 상대가 이 부분을 존중하면 편안하지만, 반대로 {first["conflict"]} 상황이 반복되면 작은 일도 누적될 수 있습니다.',
        'romance': f'연애에서는 {first["need"]}과 {second["need"]}을 둘 다 충족할 수 있는 관계가 편합니다. 끌림 자체보다 연락·약속·개인시간·돈·갈등 회복처럼 반복되는 생활 규칙이 실제 장기 궁합을 좌우합니다.',
    }

def build_profile_report(facts: ForcetellerFacts) -> dict[str, Any]:
    c = facts.chart
    top_elements = _top_elements(facts)
    top_tg = _top_ten_gods(facts)
    overview = _plain_profile_summary(facts)

    personality_dims = _plain_dimensions(_personality_dimensions(facts))
    career_dims = _plain_dimensions(_career_dimensions(facts))
    wealth_dims = _plain_dimensions(_wealth_dimensions(facts))
    relationship_dims = _plain_dimensions(_relationship_dimensions(facts))
    romance_dims = _plain_dimensions(_romance_dimensions(facts))
    study_dims = _plain_dimensions(_study_dimensions(facts))
    deep = _deep_synthesis(facts)

    strengths = [
        f'{r["assessment"]}. {r["practical"]}' for r in career_dims[:2]
    ]
    if facts.special_stars:
        star_rows = _star_rows(facts)[:3]
        strengths.append(' · '.join(r['name'] for r in star_rows) + '을 함께 보면, ' + star_rows[0]['practical'])
    strengths.append('강점은 특정 오행의 양 자체보다 실제 생활에서 어떤 역할을 반복해서 잘 수행하는지로 확인하는 편이 유용합니다.')

    self_rel = _self_relations(facts)
    cautions = [
        '사주 수치나 신살 하나를 성격 점수처럼 보지 않습니다. 실제 선택과 경험이 더 직접적인 변수입니다.',
        '잘하는 방식이 다른 사람에게도 당연하다고 생각하면 소통에서 마찰이 생길 수 있으므로 상대가 정보를 처리하는 속도를 확인하는 편이 좋습니다.',
    ]
    if self_rel:
        cautions.append('원국 내부 관계에서는 ' + self_rel[0])
    if not facts.profile.time_known:
        cautions.append('출생시간이 없어 시주는 제외했습니다. 시간에 따라 달라지는 세부 해석은 확정하지 않습니다.')
    # 수집기/외부 페이지 경고는 개발 상태이며 사용자 해설 문장에 섞지 않는다.

    return {
        'overview': overview,
        'personality': _plain_user_text(_personality_text(facts)),
        'study': _plain_user_text(_study_text(facts)),
        'career': _plain_user_text(_career_text(facts)),
        'wealth': _plain_user_text(_wealth_text(facts)),
        'relationships': _plain_user_text(_relationship_text(facts)),
        'romance': _plain_user_text(_romance_text(facts)),
        'key_points': [dict(x, meaning=_plain_user_text(x.get('meaning', ''))) for x in _profile_key_points(facts)],
        'personality_dimensions': personality_dims,
        'career_dimensions': career_dims,
        'wealth_dimensions': wealth_dims,
        'relationship_dimensions': relationship_dims,
        'romance_dimensions': romance_dims,
        'study_dimensions': study_dims,
        'deep_synthesis': {key: _plain_user_text(value) for key, value in deep.items()},
        'elements': _element_sections(facts),
        'ten_gods': _ten_god_sections(facts),
        'visible_ten_gods': _visible_ten_gods(facts),
        'self_relations': self_rel,
        'special_stars': _star_rows(facts),
        'star_insights': {
            key: _star_domain_insights(facts, key)
            for key in ('personality','career','wealth','relationships','romance','study')
        },
        'strength_label': facts.strength_label,
        'useful_elements': list(facts.useful_elements),
        'strengths': strengths,
        'cautions': cautions,
        'chart': chart_explanation(facts),
        'chart_detail': _chart_detail_report(facts),
        'source_status': _source_status(facts),
        'source_quality': facts.source_quality,
        'source': facts.source,
        'time_accuracy': {
            'known': facts.profile.time_known,
            'label': '출생시간 확인' if facts.profile.time_known else '출생시간 모름 · 시주 제외',
            'description': (
                '시주까지 포함한 네 기둥을 기준으로 해석합니다.'
                if facts.profile.time_known else
                '시주를 임의로 가정하지 않고 연주·월주·일주만 사용합니다. 시간에 따라 달라지는 부분은 미확정으로 남겨 둡니다.'
            ),
        },
    }


def _relation_sentence(a: ForcetellerFacts, b: ForcetellerFacts) -> tuple[str, list[str]]:
    rels = branch_relations(a.chart.spouse_palace, b.chart.spouse_palace)
    if not rels:
        return '두 사람의 일지 사이에는 뚜렷한 육합·충·형·파·해가 없어 이 축 자체는 중립에 가깝습니다.', []
    text = ', '.join(f'{r}({RELATION_PLAIN.get(r, "지지 관계")})' for r in rels)
    return f'두 사람의 {term("日支")} {branch_text(a.chart.spouse_palace)}와 {branch_text(b.chart.spouse_palace)} 사이에는 {text}가 확인됩니다.', rels


def _branch_network_facts(a: ForcetellerFacts, b: ForcetellerFacts, exclude_day_day: bool) -> list[str]:
    rows=[]
    for i, ba in enumerate(a.chart.branches):
        for j, bb in enumerate(b.chart.branches):
            if exclude_day_day and i==2 and j==2:
                continue
            rels=branch_relations(ba,bb)
            if rels:
                rows.append(f'{a.profile.name} {POSITION_LABELS[i]} {branch_text(ba)} ↔ {b.profile.name} {POSITION_LABELS[j]} {branch_text(bb)}: '+', '.join(f'{r}({RELATION_PLAIN.get(r,"지지 관계")})' for r in rels))
    return rows


def _useful_support_text(owner: ForcetellerFacts, giver: ForcetellerFacts) -> str:
    if not owner.useful_elements:
        return f'{owner.profile.name}의 용신이 명확히 확인되지 않아 용신 보완은 단정하지 않습니다.'
    counts={e:0 for e in owner.useful_elements}
    for s in giver.chart.stems:
        e=STEM_ELEMENT[s]
        if e in counts: counts[e]+=1
    for br in giver.chart.branches:
        e=BRANCH_ELEMENT[br]
        if e in counts: counts[e]+=1
    parts=', '.join(f'{element_text(e)} {n}자리' for e,n in counts.items())
    return f'{owner.profile.name}의 {term("用神")}은 {", ".join(element_text(e) for e in owner.useful_elements)}이고, {giver.profile.name} 원국의 겉글자 기준 해당 기운은 {parts}입니다.'


def _stem_relation_text(a: ForcetellerFacts,b:ForcetellerFacts)->str:
    sa,sb=a.chart.day_master,b.chart.day_master
    ea,eb=STEM_ELEMENT[sa],STEM_ELEMENT[sb]
    pair=frozenset((sa,sb))
    if pair in STEM_COMBINE:
        name,result=STEM_COMBINE[pair]
        return f'두 {term("日干")} {stem_text(sa)}과 {stem_text(sb)}은 {name}(천간이 짝을 이루는 관계)을 이루며 전통적으로 {element_text(result)} 방향의 연결을 참고합니다.'
    if GENERATES[ea]==eb:
        return f'{a.profile.name}의 {stem_text(sa)}가 {b.profile.name}의 {stem_text(sb)}를 생하는 오행 관계라 A→B 방향에서 에너지를 내어 주는 구조가 생깁니다.'
    if GENERATES[eb]==ea:
        return f'{b.profile.name}의 {stem_text(sb)}가 {a.profile.name}의 {stem_text(sa)}를 생하는 오행 관계라 B→A 방향에서 에너지를 내어 주는 구조가 생깁니다.'
    if CONTROLS[ea]==eb or CONTROLS[eb]==ea:
        return f'두 일간 {stem_text(sa)}과 {stem_text(sb)} 사이에는 오행의 제어 관계가 있어 기준·속도·주도권을 조율하는 방식이 중요합니다.'
    if ea==eb:
        return f'두 일간이 모두 {element_text(ea)} 계열이라 기본 반응 방식에 공통점이 생길 수 있지만 비슷함이 경쟁이나 고집으로 바뀌지 않는지 함께 봅니다.'
    return f'두 일간 {stem_text(sa)}과 {stem_text(sb)} 사이에는 강한 합이나 직접적인 생극 한 가지로만 정리되지 않아 다른 천간·지지 관계를 함께 보는 편이 중요합니다.'


def _day_pillar_relation_summary(a: ForcetellerFacts, b: ForcetellerFacts) -> dict[str, Any]:
    """일주 두 글자만 따로 봤을 때의 연결을 사용자용 요약으로 만든다.

    전체 궁합 점수를 대체하지 않고, 관계도/Inspector에서 '이 두 일주가 왜 이렇게
    보이는지'를 빠르게 훑는 보조 정보다.
    """
    sa, sb = a.chart.day_master, b.chart.day_master
    ea, eb = STEM_ELEMENT[sa], STEM_ELEMENT[sb]
    stem_pair = frozenset((sa, sb))
    branch_rels = branch_relations(a.chart.spouse_palace, b.chart.spouse_palace)
    positive_branches = [r for r in branch_rels if r in {'육합', '삼합계열', '삼회계열'}]
    caution_branches = [r for r in branch_rels if r in {'충', '형', '파', '해'}]

    stem_kind = 'neutral'
    if stem_pair in STEM_COMBINE:
        stem_kind = 'harmony'
    elif GENERATES[ea] == eb or GENERATES[eb] == ea:
        stem_kind = 'support'
    elif CONTROLS[ea] == eb or CONTROLS[eb] == ea:
        stem_kind = 'control'
    elif ea == eb:
        stem_kind = 'similar'

    if positive_branches and not caution_branches and stem_kind in {'harmony', 'support', 'similar'}:
        tone, label = 'natural', '일주 호흡이 자연스러운 편'
    elif caution_branches and positive_branches:
        tone, label = 'mixed', '끌림과 조율 포인트가 함께 있음'
    elif caution_branches or stem_kind == 'control':
        tone, label = 'adjust', '일주 차이를 조율하면 좋은 편'
    elif stem_kind in {'harmony', 'support'}:
        tone, label = 'support', '서로 보완하기 쉬운 일주'
    elif stem_kind == 'similar':
        tone, label = 'similar', '반응 방식이 비슷한 일주'
    else:
        tone, label = 'neutral', '일주만 보면 중립에 가까움'

    relation_names = [*positive_branches, *caution_branches]
    if stem_kind == 'harmony':
        element_relation_label = '천간 합 · 서로 묶이는 연결'
    elif stem_kind == 'support':
        if GENERATES[ea] == eb:
            element_relation_label = f'{element_text(ea)} → {element_text(eb)} · 생(生) 관계'
        else:
            element_relation_label = f'{element_text(eb)} → {element_text(ea)} · 생(生) 관계'
    elif stem_kind == 'control':
        if CONTROLS[ea] == eb:
            element_relation_label = f'{element_text(ea)} → {element_text(eb)} · 극(克) 관계'
        else:
            element_relation_label = f'{element_text(eb)} → {element_text(ea)} · 극(克) 관계'
    elif stem_kind == 'similar':
        element_relation_label = f'{element_text(ea)} ↔ {element_text(eb)} · 같은 오행'
    else:
        element_relation_label = f'{element_text(ea)} ↔ {element_text(eb)} · 직접 생극은 약함'
    return {
        'a': a.chart.day_pillar,
        'b': b.chart.day_pillar,
        'a_day_master': sa,
        'b_day_master': sb,
        'a_element': ea,
        'b_element': eb,
        'stem_kind': stem_kind,
        'element_relation_label': element_relation_label,
        'label': label,
        'tone': tone,
        'relations': relation_names,
        'positive_relations': positive_branches,
        'caution_relations': caution_branches,
        'stem_relation': _stem_relation_text(a, b),
        'branch_relation': _relation_sentence(a, b)[0],
        'note': '일주 두 글자만 본 보조 요약이며, 실제 관계 해석은 원국 전체와 관계 유형을 함께 봅니다.',
    }


def _five_strengths(result: CompatibilityResult, a: ForcetellerFacts, b: ForcetellerFacts) -> list[str]:
    _, sa = _dominant_style(a)
    _, sb = _dominant_style(b)
    _, sa2 = _secondary_style(a)
    _, sb2 = _secondary_style(b)
    rows = [
        f'{a.profile.name}은 {sa["need"]}을 중요하게 여기고, {b.profile.name}은 {sb["need"]}을 중요하게 여깁니다. 서로 이 차이를 알고 맞춰 주면 관계가 훨씬 편해질 수 있습니다.',
        f'{a.profile.name}은 {sa["work"]}, {b.profile.name}은 {sb["work"]} 쪽이 자연스러워 같은 일을 두고 경쟁하기보다 역할을 나누면 서로의 빈틈을 메우기 좋습니다.',
        f'대화할 때 {a.profile.name}에게는 {sa["talk"]}, {b.profile.name}에게는 {sb["talk"]} 방식이 효과적입니다. 상대가 편한 방식으로 전달할수록 불필요한 오해가 줄어듭니다.',
        f'두 사람의 두 번째 성향인 「{sa2["label"]}」과 「{sb2["label"]}」까지 함께 보면 한 가지 모습으로만 고정되지 않아 상황에 따라 서로 보완할 여지가 있습니다.',
    ]
    return rows


def _five_risks(result: CompatibilityResult, a: ForcetellerFacts, b: ForcetellerFacts) -> list[str]:
    _, sa = _dominant_style(a)
    _, sb = _dominant_style(b)
    rows = [
        f'{a.profile.name}에게는 {sa["conflict"]} 상황이, {b.profile.name}에게는 {sb["conflict"]} 상황이 특히 피로하게 느껴질 수 있습니다. 두 상황이 동시에 생기면 내용보다 대응 방식 때문에 갈등이 커질 수 있습니다.',
        '상대가 원하는 설명의 양과 결정 속도를 추측하지 말고, 결론이 필요한 시점과 확인해야 할 정보를 먼저 맞추는 편이 좋습니다.',
        '서로 잘 맞는 부분이 있어도 돈·시간·약속·책임 분담처럼 현실에서 반복되는 규칙은 별도로 합의해야 합니다.',
    ]
    _, rels = _relation_sentence(a, b)
    if any(r in {'충', '형', '파', '해'} for r in rels):
        rows.append('가까이 지낼수록 일정 변경, 표현 방식, 생활 리듬처럼 반복되는 작은 상황에서 같은 마찰이 되풀이되는지 확인해 보세요. 문제가 반복된다면 사람의 성격보다 규칙을 바꾸는 편이 효과적입니다.')
    else:
        rows.append('원국에서 큰 충돌 관계가 두드러지지 않더라도 실제 관계에서는 경계·권한·연락 방식처럼 사주에 직접 적히지 않는 기준을 따로 맞춰야 합니다.')
    return rows


def _love_practical_sections(a: ForcetellerFacts, b: ForcetellerFacts, sa: dict[str, str], sb: dict[str, str], sa2: dict[str, str], sb2: dict[str, str]) -> dict[str, str]:
    """Relationship-first explanations for LOVE mode.

    These are practical tendencies, not predictions of fertility, marriage success, or
    sexual behaviour. Technical chart evidence is kept in the collapsed evidence zone.
    """
    ta, tb = _axis_totals(a), _axis_totals(b)
    a_name, b_name = a.profile.name, b.profile.name

    emotional = (
        f'**{a_name}**은 {sa["need"]}에서 안정감을 느끼기 쉽고, **{b_name}**은 {sb["need"]}이 중요합니다. '
        f'한쪽이 애정을 주고 있다고 생각해도 상대가 원하는 방식과 다르면 서운함이 생길 수 있으므로, 힘들 때 원하는 반응과 혼자 있고 싶은 시간을 직접 말하는 편이 좋습니다.'
    )
    communication_daily = (
        f'**{a_name}에게는** {sa["talk"]} 방식이 잘 맞고, **{b_name}에게는** {sb["talk"]} 방식이 잘 맞습니다. '
        '평소 연락은 횟수보다 답장이 늦을 때 어떻게 이해할지, 바쁜 날 최소한 어떤 신호를 줄지, 약속 변경은 언제까지 알려줄지를 맞추는 것이 실제 체감에 중요합니다.'
    )
    physical = (
        '신체적 친밀감은 사주만으로 성적 취향이나 행동을 단정할 수 없습니다. 다만 가까워지는 **속도, 스킨십을 애정으로 느끼는 정도, 정서적 안전감이 먼저 필요한지, 혼자 쉴 공간이 필요한지** 같은 친밀감 리듬은 비교해 볼 수 있습니다. '
        f'{a_name}은 {sa["need"]}이 확보될 때 더 편하게 가까워지기 쉽고, {b_name}은 {sb["need"]}이 확보될 때 안정되기 쉬우므로 서로의 동의와 속도를 확인하는 것이 핵심입니다.'
    )
    cohabitation = (
        f'함께 살면 **{a_name}의 {sa2["label"]} 성향**과 **{b_name}의 {sb2["label"]} 성향**이 연애할 때보다 더 자주 드러날 수 있습니다. '
        '집안일·수면과 휴식·정리 기준·혼자 있는 시간·친구를 집에 부르는 기준을 “알아서 맞겠지”라고 두지 말고 담당과 빈도를 구체적으로 합의하는 편이 좋습니다.'
    )
    money = (
        '돈 문제는 사랑의 크기와 별개로 반복 갈등이 되기 쉽습니다. **데이트비, 큰 지출의 사전 합의, 저축 목표, 각자 자유롭게 쓸 돈, 가족에게 쓰는 돈**을 나눠 이야기하는 방식이 좋습니다. '
        f'{a_name}과 {b_name} 모두 자신의 현실 감각을 당연한 기준으로 두지 말고 숫자와 한도를 합의해야 합니다.'
    )
    marriage = (
        f'배우자로서는 {a_name}이 원하는 “{sa["need"]}”과 {b_name}이 원하는 “{sb["need"]}”을 **생활 규칙으로 동시에 구현할 수 있는지**가 중요합니다. '
        '결혼 여부보다 책임을 미루지 않는지, 큰 결정을 함께 논의하는지, 한 사람의 커리어·돌봄 부담만 자동으로 우선되지 않는지를 확인하는 편이 좋습니다.'
    )
    family_boundaries = (
        '가족·친인척 문제에서는 “우리 부모니까 당연히”보다 **방문 빈도, 명절·행사, 경제적 지원, 가족에게 둘의 사생활을 어디까지 공유할지**를 둘 사이에서 먼저 합의하는 것이 중요합니다. '
        '상대가 가족과 가깝다는 사실보다 둘의 경계를 서로 지켜 줄 수 있는지가 장기 안정성에 더 직접적입니다.'
    )
    parenting = (
        '자녀와 관련해서는 임신 가능성·자녀 수·성별을 사주로 확정하지 않습니다. 대신 두 사람이 부모가 되었을 때 **규칙과 훈육, 공부 기대, 자율성, 감정 돌봄, 실제 육아 분담**을 어떻게 생각할지 확인하는 관점으로 봅니다. '
        f'{a_name}은 {sa["label"]} 성향, {b_name}은 {sb["label"]} 성향을 양육에서도 반복할 수 있으므로 한쪽만 원칙을 세우고 다른 쪽만 돌봄을 맡는 구조가 고착되지 않도록 역할을 정기적으로 조정하는 편이 좋습니다.'
    )
    conflict_repair = (
        f'{a_name}에게 {sa["conflict"]} 상황과 {b_name}에게 {sb["conflict"]} 상황이 겹치면 말의 내용보다 대응 방식 때문에 싸움이 커질 수 있습니다. '
        '싸운 뒤에는 사실 확인 → 각자 받은 영향 → 필요한 사과나 수정 → 다음에 같은 일이 생겼을 때의 규칙 순으로 이야기하면 “누가 더 잘못했는가”만 반복하는 것을 줄일 수 있습니다.'
    )
    long_check = (
        '장기 관계에서는 **연락, 돈, 집안일, 개인시간, 성적·신체적 경계, 양가 가족, 커리어 이동, 자녀·양육관, 갈등 후 회복**을 실제로 대화해 보는 것이 좋습니다. '
        '두 사람이 모든 항목에서 같을 필요는 없지만, 차이를 말했을 때 조정할 수 있어야 합니다.'
    )
    return {
        'emotional_needs': emotional,
        'communication_daily': communication_daily,
        'physical_intimacy': physical,
        'cohabitation': cohabitation,
        'money_style': money,
        'marriage_partner': marriage,
        'family_boundaries': family_boundaries,
        'parenting': parenting,
        'conflict_repair': conflict_repair,
        'long_term_checklist': long_check,
    }


def _pair_sections(a: ForcetellerFacts, b: ForcetellerFacts, result: CompatibilityResult, context: str = "") -> dict[str, Any]:
    mode_love = result.mode == 'love'
    _, sa = _dominant_style(a)
    _, sb = _dominant_style(b)
    _, sa2 = _secondary_style(a)
    _, sb2 = _secondary_style(b)
    day_sentence, day_rels = _relation_sentence(a, b)
    branchfacts = _branch_network_facts(a, b, exclude_day_day=mode_love)
    strong = max(result.axes, key=lambda x: x.score)
    weak = min(result.axes, key=lambda x: x.score)

    shared = sa['label'] == sb['label']
    if shared:
        fit = f'두 사람 모두 「{sa["label"]}」을 중요하게 여겨 상대가 왜 그렇게 행동하는지 이해하기 쉬운 편입니다. 다만 같은 강점이 겹치면 {sa["conflict"]} 문제가 두 사람 모두에게 동시에 생길 수 있습니다.'
    else:
        fit = f'{a.profile.name}은 「{sa["label"]}」을 먼저 쓰고, {b.profile.name}은 「{sb["label"]}」을 먼저 쓰는 편입니다. 방식은 다르지만 {a.profile.name}의 {sa["work"]}과 {b.profile.name}의 {sb["work"]}이 서로 다른 빈틈을 메울 수 있습니다.'

    wants = (
        f'{a.profile.name}은 {sa["need"]}을 원하고, {b.profile.name}은 {sb["need"]}을 더 중요하게 느끼는 편입니다. '
        f'그래서 같은 상황에서도 한쪽은 “{sa["talk"]}”을 편하게 느끼고 다른 쪽은 “{sb["talk"]}”을 원할 수 있습니다.'
    )
    friction = (
        f'마찰은 {a.profile.name}에게 {sa["conflict"]} 상황과 {b.profile.name}에게 {sb["conflict"]} 상황이 겹칠 때 커지기 쉽습니다. '
        f'예를 들어 한쪽이 빨리 결론을 내리려는 순간 다른 쪽이 설명이나 생각할 시간을 원하면, 내용보다 속도 차이 때문에 감정이 상할 수 있습니다.'
    )
    communication = (
        f'{a.profile.name}에게는 {sa["talk"]} 방식이 효과적이고, {b.profile.name}에게는 {sb["talk"]} 방식이 효과적입니다. '
        '갈등 때는 “누가 맞는가”부터 정하지 말고, 각자 원하는 결론·필요한 정보·결정 시점을 한 문장씩 확인한 뒤 합의하는 방식이 좋습니다.'
    )
    role_split = (
        f'{a.profile.name}은 {sa["work"]}, {b.profile.name}은 {sb["work"]}을 맡을 때 서로의 강점을 살리기 쉽습니다. '
        '둘 다 같은 일을 동시에 책임지기보다 최종 결정권과 검토 책임을 분리하면 불필요한 주도권 충돌을 줄일 수 있습니다.'
    )

    if mode_love:
        one_line = (
            f'{fit} 가까워질수록 연락·약속·개인시간처럼 반복되는 생활 기준을 직접 맞추는 것이 중요합니다.'
        )
    elif context == 'work':
        one_line = (
            f'{fit} 실제 협업에서는 역할·결정권·마감 기준을 먼저 합의하면 방식 차이를 강점으로 쓰기 쉽습니다.'
        )
    elif context == 'family':
        one_line = (
            f'{fit} 가까운 사이일수록 돌봄·비용·개인시간 같은 생활 책임을 당연하게 추측하지 않는 것이 중요합니다.'
        )
    elif context == 'hobby':
        one_line = (
            f'{fit} 활동 강도·일정·준비 역할을 미리 맞추면 재미를 유지하면서 운영 피로를 줄이기 쉽습니다.'
        )
    else:
        one_line = (
            f'{fit} 연락·약속·경계처럼 자주 반복되는 기준을 직접 말하면 관계가 훨씬 편해질 수 있습니다.'
        )

    common = {
        'one_line': one_line,
        'each_needs': wants,
        'fit': fit,
        'friction_scene': friction,
        'communication': communication,
        'role_split': role_split,
        'day_stem': _stem_relation_text(a, b),
        'day_pillar_relation': _day_pillar_relation_summary(a, b),
        'element_useful': _useful_support_text(a, b) + ' ' + _useful_support_text(b, a),
        'branch_network': (' '.join(branchfacts[:8]) if branchfacts else '두 원국 전체에서 큰 충돌 관계가 반복적으로 겹치지는 않아 이 부분은 중립에 가깝습니다.'),
        'conflict': friction,
        'technical_focus': f'상대적으로 편한 축은 {strong.label}, 조율이 더 필요한 축은 {weak.label}입니다.',
        'branch_facts': branchfacts,
        'star_interplay': _pair_star_interplay(a, b, love=mode_love, context=context),
    }
    if mode_love:
        common.update({
            'why_attracted': f'{fit} 서로가 필요로 하는 안정감과 표현 방식이 어느 정도 맞는지가 실제 끌림 이후의 만족도를 좌우합니다.',
            'intimacy': day_sentence + ' 가까워질수록 연락 빈도, 개인시간, 약속 변경, 스킨십과 정서 표현의 속도처럼 반복되는 생활 반응에서 이 차이가 체감될 수 있습니다.',
            'affection': f'{a.profile.name}은 애정을 느낄 때 {sa["need"]}을 중요하게 보고, {b.profile.name}은 {sb["need"]}을 중요하게 보는 편입니다. 상대가 원하는 방식과 내가 주는 방식이 다를 수 있으므로 “좋아하면 당연히 이렇게 해야지”보다 원하는 표현을 직접 말하는 편이 좋습니다.',
            'daily_life': f'생활에서는 {a.profile.name}의 {sa2["label"]} 성향과 {b.profile.name}의 {sb2["label"]} 성향도 함께 작동합니다. 평일 연락, 데이트 계획, 돈 쓰는 기준, 혼자 쉬는 시간, 가족·친구와의 경계를 미리 맞추는 것이 장기 만족도에 중요합니다.',
            'long_term': f'장기적으로는 {a.profile.name}이 원하는 “{sa["need"]}”과 {b.profile.name}이 원하는 “{sb["need"]}”을 둘 다 관계 규칙에 넣을 수 있는지가 핵심입니다. 강한 끌림보다 갈등 뒤 설명·사과·재조정이 반복 가능해야 관계가 안정됩니다.',
            'ten_gods': '전통적인 배우자성은 참고 근거로만 사용하고, 실제 해설에서는 두 사람이 서로 무엇을 원하고 어떤 방식으로 반응하는지를 우선 설명합니다.',
        })
        common.update(_love_practical_sections(a, b, sa, sb, sa2, sb2))
    else:
        common.update({
            'why_attracted': fit,
            'intimacy': day_sentence.replace('배우자', '가까운 관계') + ' 비연인 관계에서는 이를 생활 반응과 협업 리듬의 참고축으로만 봅니다.',
            'affection': '',
            'daily_life': f'함께 일하거나 활동할 때 {a.profile.name}은 {sa["work"]}, {b.profile.name}은 {sb["work"]}이 자연스럽습니다. 일정 공유, 결정권, 검토 시점을 미리 정하면 서로의 방식 차이가 장점으로 바뀌기 쉽습니다.',
            'long_term': '오래 함께 일하려면 친밀감보다 역할과 기대치가 예측 가능해야 합니다. 누가 제안하고, 누가 검토하고, 누가 최종 결정하며, 문제가 생기면 누구에게 먼저 알릴지를 정해 두는 것이 좋습니다.',
            'ten_gods': '십성은 협업·표현·지원·책임·현실 실행의 차이를 보는 보조 근거로만 사용합니다.',
            'decision': f'의사결정에서는 {a.profile.name}에게는 {sa["talk"]} 방식이, {b.profile.name}에게는 {sb["talk"]} 방식이 필요합니다. 큰 결정을 할 때는 제안자와 최종 결정자를 분리하고 검토 시간을 명시하면 좋습니다.',
            'feedback': f'피드백은 {a.profile.name}에게 {sa["talk"]}, {b.profile.name}에게 {sb["talk"]} 방식으로 전달하는 편이 좋습니다. 공개석상에서 즉흥적으로 교정하기보다 기대 결과와 수정 시점을 함께 말하면 갈등을 줄일 수 있습니다.',
        })
        if context == 'work':
            common.update({
                'why_attracted': f'{a.profile.name}은 업무에서 {sa["work"]} 쪽이 자연스럽고, {b.profile.name}은 {sb["work"]} 쪽이 자연스럽습니다. 같은 방식으로 경쟁하기보다 서로 다른 강점을 연결할 때 협업 효율이 좋아질 수 있습니다.',
                'intimacy': day_sentence.replace('배우자', '업무 관계').replace('친밀감', '협업 리듬') + ' 가까이 협업할 때 반복되기 쉬운 반응 속도와 기준 차이를 참고하는 항목입니다.',
                'daily_life': f'실무에서는 {a.profile.name}에게 {sa["work"]}, {b.profile.name}에게 {sb["work"]}을 우선 배치해 보세요. 요청할 때는 목적·마감·완료 기준을 한 번에 전달하고, 중간 검토가 필요한 사람과 최종 결정자를 미리 구분하는 편이 좋습니다.',
                'long_term': '장기 협업에서는 책임선과 피드백 규칙을 예측 가능하게 만드는 것이 중요합니다. 누가 초안을 만들고, 누가 검토하고, 누가 최종 승인하는지 고정하면 반복 갈등을 줄일 수 있습니다.',
                'decision': f'{a.profile.name}은 결정을 받을 때 {sa["talk"]} 방식이 편하고, {b.profile.name}은 {sb["talk"]} 방식이 편합니다. 회의에서는 결론·근거·담당자·마감 네 가지를 분리해 확인하는 방식이 효과적입니다.',
                'feedback': f'{a.profile.name}에게는 {sa["talk"]}, {b.profile.name}에게는 {sb["talk"]} 방식으로 피드백하는 편이 좋습니다. 사람 평가처럼 들리지 않게 현재 결과물에서 바꿀 부분과 다음 확인 시점을 함께 말해 주세요.',
            })
        elif context == 'family':
            common.update({
                'daily_life': f'가족 안에서는 {a.profile.name}이 {sa["need"]}을 편안함의 기준으로 느끼고, {b.profile.name}은 {sb["need"]}을 더 중요하게 느낄 수 있습니다. 집안일·연락·돌봄·개인시간을 당연한 것으로 두지 말고 구체적으로 나누는 편이 좋습니다.',
                'long_term': '가족 관계는 끊고 다시 시작하기보다 반복해서 조정해야 하는 경우가 많습니다. 갈등의 결론보다 평소 책임 분담과 경계를 예측 가능하게 만드는 것이 중요합니다.',
                'decision': '가족의 큰 결정은 한 사람이 대신 결정하기보다 각자 영향을 받는 부분과 양보 가능한 부분을 먼저 나눠 말하는 방식이 좋습니다.',
                'feedback': '서운함을 오래 쌓았다가 한꺼번에 말하기보다 행동 하나와 원하는 변화 하나를 연결해서 말하는 편이 관계 회복에 도움이 됩니다.',
            })
        elif context == 'hobby':
            common.update({
                'daily_life': f'모임에서는 {a.profile.name}은 {sa["work"]}, {b.profile.name}은 {sb["work"]} 쪽을 맡을 때 부담이 덜합니다. 일정 잡기·준비물·회비·진행 역할을 미리 나누면 재미를 유지하면서 운영 피로를 줄일 수 있습니다.',
                'long_term': '동호회나 취미 관계는 의무감이 커지면 피로해질 수 있으므로 참여 강도를 강요하지 않고 역할을 순환하는 편이 오래가기 좋습니다.',
                'decision': '활동 계획은 원하는 강도와 가능한 시간을 먼저 확인한 뒤 다수결보다 참여 가능한 선택지를 만드는 방식이 좋습니다.',
                'feedback': '취미 실력이나 참여도를 사람 평가로 연결하지 말고, 다음 활동에서 바라는 행동을 구체적으로 말하는 편이 좋습니다.',
            })
        elif context == 'friends':
            common.update({
                'daily_life': f'친구 관계에서는 {a.profile.name}이 편하게 느끼는 소통 방식은 {sa["talk"]}, {b.profile.name}은 {sb["talk"]}에 가깝습니다. 연락 빈도·약속 방식·혼자 쉬는 시간을 서로 다르게 생각할 수 있다는 점만 알고 있어도 오해가 줄어듭니다.',
                'long_term': '오래 가는 친구 관계에서는 자주 연락하는 것보다 서로가 부담 없이 유지할 수 있는 연락·약속 리듬을 찾는 것이 중요합니다.',
                'decision': '여행이나 모임 계획처럼 함께 결정할 일에서는 먼저 각자의 필수 조건과 양보 가능한 조건을 나눠 말하는 편이 좋습니다.',
                'feedback': '친구에게 조언할 때는 해결책부터 주기보다 지금 공감을 원하는지 의견을 원하는지 먼저 확인하는 편이 좋습니다.',
            })
    return common

def _contextual_pair_label(score: float, mode: str, context: str) -> str:
    if mode == 'love':
        if score >= 90: return '매우 뛰어난 구조적 궁합'
        if score >= 80: return '매우 잘 맞는 편'
        if score >= 70: return '잘 맞는 편'
        if score >= 60: return '대체로 맞는 편'
        if score >= 50: return '장단점이 함께 있는 관계'
        if score >= 40: return '조율이 꽤 필요한 관계'
        if score >= 30: return '구조적 마찰이 큰 편'
        return '맞춰 갈 규칙이 많이 필요한 관계'

    prefix = {
        'work': '협업 호흡',
        'family': '생활 호흡',
        'hobby': '활동 호흡',
        'mixed': '관계 호흡',
    }.get(context, '관계 호흡')
    if score >= 90: return f'{prefix}이 매우 좋은 편'
    if score >= 80: return f'{prefix}이 아주 잘 맞는 편'
    if score >= 70: return f'{prefix}이 잘 맞는 편'
    if score >= 60: return f'{prefix}이 대체로 편한 편'
    if score >= 50: return '편한 점과 차이가 함께 있는 관계'
    if score >= 40: return '기준을 맞추는 노력이 필요한 관계'
    if score >= 30: return '반복 마찰을 관리할 필요가 큰 관계'
    return '역할과 경계를 분명히 정해야 하는 관계'


def build_pair_report(a: ForcetellerFacts, b: ForcetellerFacts, result: CompatibilityResult, context: str = "") -> dict[str, Any]:
    mode_label = {
        'work': '직장·협업',
        'family': '가족',
        'hobby': '동호회·취미',
        'mixed': '그룹 관계',
        'friends': '친구·지인',
    }.get(context, '친구·지인') if result.mode != 'love' else '연인'
    sections = _pair_sections(a, b, result, context=context)
    axes = [{'key':axis.key,'label':axis.label,'score':axis.score,'weight':axis.weight,'summary':axis.explanation,'evidence':[e.__dict__ for e in axis.evidence]} for axis in result.axes]
    terms = [{'term':k,'label':term(k),'detail':TERM_DICTIONARY[k][2]} for k in ('日干','日支','用神','身强身弱')]
    time_unknown_names = [x.profile.name for x in (a, b) if not x.profile.time_known]
    time_note = '' if not time_unknown_names else f' {", ".join(time_unknown_names)}의 출생시간은 몰라 시주에 따라 달라지는 세부 부분은 확정하지 않았습니다.'
    overview = (
        f'{sections["each_needs"]} {sections["fit"]} '
        f'이 관계에서 가장 중요한 것은 점수 자체보다 “어디서 편하고, 어디서 반복적으로 엇갈리는지”를 구분하는 것입니다.' + time_note
    )
    if result.mode == 'love':
        reality = [
            '서로가 원하는 연락 빈도, 바쁜 날의 최소 연락, 혼자 있는 시간을 직접 말해 봅니다.',
            '애정을 주는 방식과 받고 싶은 방식, 신체적 친밀감의 속도와 경계를 서로 동의 가능한 수준에서 이야기합니다.',
            '데이트비·저축·큰 지출·각자 자유롭게 쓰는 돈의 기준을 실제 숫자로 이야기해 봅니다.',
            '함께 살 경우 집안일·휴식·개인공간·주거 선택을 어떻게 나눌지 확인합니다.',
            '갈등이 생겼을 때 바로 대화할지, 시간을 두고 이야기할지 회복 방식을 합의합니다.',
            '양가 가족과의 거리, 명절·경제 지원·사생활 공유 범위를 둘 사이에서 먼저 정할 수 있는지 확인합니다.',
            '자녀 계획이 있다면 임신 예측이 아니라 훈육·교육·자율성·돌봄·육아 분담에 대한 생각을 비교합니다.',
            '커리어 이동이나 장기 주거 같은 큰 결정에서 한쪽의 희생을 당연하게 두지 않는지 확인합니다.',
        ]
    else:
        if context == 'work':
            reality = [
                '누가 제안하고 누가 최종 결정할지 역할을 먼저 정합니다.',
                '업무 요청은 목적·마감·완료 기준을 함께 전달합니다.',
                '의견이 다를 때 사람의 태도보다 쟁점과 근거를 분리해 확인합니다.',
                '동일 업무를 두 사람이 동시에 책임지지 않도록 책임선을 명확히 합니다.',
                '피드백 방식과 수정 시점을 미리 합의해 불필요한 감정 소모를 줄입니다.',
            ]
        elif context == 'family':
            reality = [
                '집안일·돌봄·비용처럼 반복되는 책임을 누가 얼마나 맡는지 구체적으로 말합니다.',
                '가까운 사이라는 이유로 개인시간과 경계를 당연히 침범하지 않는지 확인합니다.',
                '서운한 일을 쌓아 두기보다 행동 하나와 원하는 변화 하나를 연결해서 말합니다.',
                '가족의 큰 결정은 영향받는 사람 모두가 자신의 필수 조건을 말할 기회를 갖게 합니다.',
                '갈등 뒤 다시 평소 생활로 돌아가는 방식이 서로에게 납득 가능한지 확인합니다.',
            ]
        elif context == 'hobby':
            reality = [
                '일정·회비·준비물·운영 역할을 몇 사람에게만 몰아주지 않습니다.',
                '참여 강도와 친밀도를 같은 것으로 보지 않고 각자의 가능한 범위를 존중합니다.',
                '활동 계획은 각자의 필수 조건과 가능한 시간을 먼저 확인합니다.',
                '실력이나 참여도를 사람 평가처럼 말하지 않고 다음 활동에서 바라는 행동을 구체적으로 말합니다.',
                '운영 역할을 순환해 재미보다 의무감이 커지지 않도록 합니다.',
            ]
        else:
            reality = [
                '서로 편한 연락 빈도와 답장이 늦을 때 받아들이는 기준이 비슷한지 확인합니다.',
                '약속을 잡고 변경하는 방식, 혼자 쉬고 싶은 시간에 대한 기대를 직접 말합니다.',
                '조언이 필요한지 공감이 필요한지 먼저 확인한 뒤 대화합니다.',
                '여행·모임·돈처럼 함께 결정할 일에서는 필수 조건과 양보 가능한 조건을 나눠 말합니다.',
                '친한 사이라도 부담스러운 부탁이나 경계를 거절할 수 있는 분위기인지 확인합니다.',
            ]
    return {
        'title': f'{a.profile.name} × {b.profile.name} {mode_label} 궁합',
        'mode': result.mode,
        'score': result.total,
        'label': _contextual_pair_label(result.total, result.mode, context),
        'overview': overview,
        'person_a': build_profile_report(a),
        'person_b': build_profile_report(b),
        'axes': axes,
        'analysis': sections,
        'strengths': _five_strengths(result, a, b),
        'risks': _five_risks(result, a, b),
        'evidence': [sections['day_stem'], sections['element_useful'], sections['intimacy']] + sections['branch_facts'][:6],
        'reality_checks': reality,
        'technical_notes': result.technical_notes,
        'terms': terms,
        'daily_examples': reality,
        'source_status': {'a': _source_status(a), 'b': _source_status(b)},
        'time_accuracy': {
            'all_known': not time_unknown_names,
            'unknown_names': time_unknown_names,
            'label': '시주 포함 분석' if not time_unknown_names else '출생시간 미상 포함 · 시주 제외 분석',
            'description': ('두 사람 모두 출생시간이 확인되어 시주까지 포함했습니다.' if not time_unknown_names else '출생시간이 없는 사람은 시주를 임의로 생성하지 않았습니다. 확인 가능한 구조만 사용했습니다.'),
        },
    }
