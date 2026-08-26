from __future__ import annotations

import unittest

from bazi_engine import (
    build_chart_from_pillars,
    calculate_chart_with_audit,
    validate_double_hour_grid,
    validate_local_engine_against_forceteller,
)
from models import BirthProfile


class BaziEngineTest(unittest.TestCase):
    def test_forceteller_anchor_baegyeongeun(self) -> None:
        chart, audit = calculate_chart_with_audit(
            1994,
            12,
            7,
            5,
            30,
        )
        self.assertEqual(
            (
                chart.year_pillar,
                chart.month_pillar,
                chart.day_pillar,
                chart.hour_pillar,
            ),
            ("甲戌", "乙亥", "丁卯", "壬寅"),
        )
        self.assertEqual(audit["total_correction_minutes"], -32)
        self.assertEqual(audit["adjusted_datetime"], "1994-12-07T04:58")

    def test_user_local_engine_matches_forceteller_chart(self) -> None:
        profile = BirthProfile(
            name="배경은",
            gender="F",
            calendar_type="solar",
            is_leap_month=False,
            year=1994,
            month=12,
            day=7,
            hour=5,
            minute=30,
            location="서울특별시, 대한민국",
            timezone="Asia/Seoul",
            partner_gender="M",
        )
        forceteller_chart = build_chart_from_pillars(
            "甲戌",
            "乙亥",
            "丁卯",
            "壬寅",
        )
        result = validate_local_engine_against_forceteller(
            profile,
            forceteller_chart,
        )
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["differences"], [])

    def test_twelve_double_hours_are_complete(self) -> None:
        result = validate_double_hour_grid()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(set(result["unique_hour_branches"])), 12)


if __name__ == "__main__":
    unittest.main()
