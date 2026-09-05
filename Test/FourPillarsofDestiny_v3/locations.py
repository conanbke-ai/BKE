from __future__ import annotations

# 화면에서 빠르게 선택할 수 있는 국가 목록입니다.
# 목록에 없는 국가는 UI에서 직접 입력할 수 있게 하므로, 이 배열이 지원 국가의 상한은 아닙니다.
COUNTRIES = [
    ('KR', '대한민국'), ('JP', '일본'), ('CN', '중국'), ('TW', '대만'), ('HK', '홍콩'),
    ('MO', '마카오'), ('SG', '싱가포르'), ('TH', '태국'), ('VN', '베트남'), ('PH', '필리핀'),
    ('MY', '말레이시아'), ('ID', '인도네시아'), ('IN', '인도'), ('NP', '네팔'), ('MN', '몽골'),
    ('US', '미국'), ('CA', '캐나다'), ('MX', '멕시코'), ('BR', '브라질'), ('AR', '아르헨티나'),
    ('CL', '칠레'), ('PE', '페루'), ('CO', '콜롬비아'), ('GB', '영국'), ('IE', '아일랜드'),
    ('FR', '프랑스'), ('DE', '독일'), ('IT', '이탈리아'), ('ES', '스페인'), ('PT', '포르투갈'),
    ('NL', '네덜란드'), ('BE', '벨기에'), ('CH', '스위스'), ('AT', '오스트리아'), ('SE', '스웨덴'),
    ('NO', '노르웨이'), ('DK', '덴마크'), ('FI', '핀란드'), ('IS', '아이슬란드'), ('PL', '폴란드'),
    ('CZ', '체코'), ('HU', '헝가리'), ('RO', '루마니아'), ('GR', '그리스'), ('TR', '튀르키예'),
    ('RU', '러시아'), ('UA', '우크라이나'), ('AU', '호주'), ('NZ', '뉴질랜드'), ('AE', '아랍에미리트'),
    ('SA', '사우디아라비아'), ('IL', '이스라엘'), ('EG', '이집트'), ('ZA', '남아프리카공화국'),
]

COUNTRY_NAME_BY_CODE = dict(COUNTRIES)


def country_name(code: str, fallback: str = '') -> str:
    return COUNTRY_NAME_BY_CODE.get((code or '').upper(), fallback or code or '대한민국')


def location_fields(country_code: str, country: str, city: str) -> tuple[str, str]:
    """사용자 입력을 내부 위치 검색 문자열로 바꿉니다.

    대한민국은 사용자에게 시·군 입력을 받지 않고 대표 위치값을 사용합니다.
    해외는 국가만으로 시간대가 확정되지 않는 국가가 많아 도시를 함께 받습니다.
    실제 계산용 위치 ID는 수집 단계에서 검색 결과를 통해 확정됩니다.
    """
    code = (country_code or 'KR').upper()
    name = (country or country_name(code)).strip() or country_name(code)
    city = (city or '').strip()
    if code == 'KR':
        return '서울특별시, 대한민국', ''
    if not city:
        raise ValueError('해외 출생은 정확한 시간 기준을 위해 출생 도시를 입력해 주세요.')
    return f'{city}, {name}', ''
