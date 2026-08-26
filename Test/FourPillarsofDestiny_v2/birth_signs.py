from __future__ import annotations

from datetime import date

# Gregorian birth-year based zodiac requested by the project owner.
# 4 CE is a Rat year, so (year - 4) % 12 maps directly to this order.
ZODIAC_ANIMALS = (
    "쥐띠",
    "소띠",
    "호랑이띠",
    "토끼띠",
    "용띠",
    "뱀띠",
    "말띠",
    "양띠",
    "원숭이띠",
    "닭띠",
    "개띠",
    "돼지띠",
)

ZODIAC_BRANCHES = (
    "子",
    "丑",
    "寅",
    "卯",
    "辰",
    "巳",
    "午",
    "未",
    "申",
    "酉",
    "戌",
    "亥",
)


def zodiac_index_by_year(year: int) -> int:
    if year < 1:
        raise ValueError("출생연도는 1 이상이어야 합니다.")
    return (year - 4) % 12


def zodiac_animal_by_year(year: int) -> str:
    return ZODIAC_ANIMALS[zodiac_index_by_year(year)]


def zodiac_branch_by_year(year: int) -> str:
    return ZODIAC_BRANCHES[zodiac_index_by_year(year)]


def western_zodiac(month: int, day: int) -> str:
    """Return the Western sun sign for a valid Gregorian month/day."""
    # A leap year validates February 29 without rejecting any legal birth date.
    date(2000, month, day)

    if (month, day) >= (12, 22) or (month, day) <= (1, 19):
        return "염소자리"
    if (month, day) <= (2, 18):
        return "물병자리"
    if (month, day) <= (3, 20):
        return "물고기자리"
    if (month, day) <= (4, 19):
        return "양자리"
    if (month, day) <= (5, 20):
        return "황소자리"
    if (month, day) <= (6, 21):
        return "쌍둥이자리"
    if (month, day) <= (7, 22):
        return "게자리"
    if (month, day) <= (8, 22):
        return "사자자리"
    if (month, day) <= (9, 22):
        return "처녀자리"
    if (month, day) <= (10, 22):
        return "천칭자리"
    if (month, day) <= (11, 22):
        return "전갈자리"
    return "사수자리"


def birth_signs(born: date) -> dict[str, str]:
    return {
        "zodiac": zodiac_animal_by_year(born.year),
        "zodiac_basis": "양력 출생연도 기준",
        "western_zodiac": western_zodiac(born.month, born.day),
        "western_zodiac_basis": "양력 생월일 기준",
    }
