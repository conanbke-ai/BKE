from __future__ import annotations

from datetime import date


ZODIAC_BY_BRANCH = {
    "子": "쥐띠",
    "丑": "소띠",
    "寅": "호랑이띠",
    "卯": "토끼띠",
    "辰": "용띠",
    "巳": "뱀띠",
    "午": "말띠",
    "未": "양띠",
    "申": "원숭이띠",
    "酉": "닭띠",
    "戌": "개띠",
    "亥": "돼지띠",
}


def zodiac_from_year_pillar(year_pillar: str) -> str:
    """포스텔러 연주의 지지를 기준으로 띠를 반환한다."""
    value = str(year_pillar or "").strip()
    if len(value) != 2 or value[1] not in ZODIAC_BY_BRANCH:
        raise ValueError(f"유효하지 않은 연주입니다: {year_pillar!r}")
    return ZODIAC_BY_BRANCH[value[1]]


def zodiac_basis(year_pillar: str) -> str:
    return (
        f"포스텔러 연주 {year_pillar}의 연지 {year_pillar[1]}"
        f" → {zodiac_from_year_pillar(year_pillar)}"
    )


def western_zodiac_from_date(born: date) -> str:
    """양력 월·일을 기준으로 서양 태양 별자리를 계산한다."""
    month_day = (born.month, born.day)

    if month_day >= (12, 22) or month_day <= (1, 19):
        return "염소자리"
    if month_day <= (2, 18):
        return "물병자리"
    if month_day <= (3, 20):
        return "물고기자리"
    if month_day <= (4, 19):
        return "양자리"
    if month_day <= (5, 20):
        return "황소자리"
    if month_day <= (6, 21):
        return "쌍둥이자리"
    if month_day <= (7, 22):
        return "게자리"
    if month_day <= (8, 22):
        return "사자자리"
    if month_day <= (9, 22):
        return "처녀자리"
    if month_day <= (10, 22):
        return "천칭자리"
    if month_day <= (11, 22):
        return "전갈자리"
    return "사수자리"


def western_zodiac_basis(born: date) -> str:
    return (
        f"양력 {born.month}월 {born.day}일"
        f" → {western_zodiac_from_date(born)}"
    )
