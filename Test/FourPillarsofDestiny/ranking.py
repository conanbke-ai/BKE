from __future__ import annotations

from collections import Counter
from datetime import date

from bazi_engine import (
    DOUBLE_HOURS,
    automatic_age_range,
    calculate_chart,
    calculate_chart_with_audit,
    calculate_partial_chart,
    candidate_location_correction_minutes,
)
from config import SETTINGS
from logging_utils import LOGGER
from models import BirthProfile, Candidate, Chart, DateCandidate
from scoring import score_compatibility


AGE_BAND_YOUNGER = "younger_1_to_5"
AGE_BAND_SAME_TO_5_OLDER = "same_to_5_older"
AGE_BAND_6_TO_10_OLDER = "older_6_to_10"
AGE_BAND_11_TO_15_OLDER = "older_11_to_15"

AGE_BAND_ORDER = (
    AGE_BAND_YOUNGER,
    AGE_BAND_SAME_TO_5_OLDER,
    AGE_BAND_6_TO_10_OLDER,
    AGE_BAND_11_TO_15_OLDER,
)


def candidate_age_gap(
    user_birth_year: int,
    candidate_birth_year: int,
) -> int:
    """양수는 연상, 0은 동갑, 음수는 연하."""
    return user_birth_year - candidate_birth_year


def age_band(
    user_birth_year: int,
    candidate_birth_year: int,
) -> str | None:
    gap = candidate_age_gap(
        user_birth_year,
        candidate_birth_year,
    )
    if -SETTINGS.max_younger_years <= gap <= -1:
        return AGE_BAND_YOUNGER
    if 0 <= gap <= 5:
        return AGE_BAND_SAME_TO_5_OLDER
    if 6 <= gap <= 10:
        return AGE_BAND_6_TO_10_OLDER
    if 11 <= gap <= SETTINGS.max_older_years:
        return AGE_BAND_11_TO_15_OLDER
    return None


def iter_dates(start_year: int, end_year: int):
    for year in range(start_year, end_year + 1):
        current = date(year, 1, 1)
        while current.year == year:
            yield current
            current = date.fromordinal(current.toordinal() + 1)


def build_date_pool(
    profile: BirthProfile,
    user_chart: Chart,
) -> list[DateCandidate]:
    """
    전체 연령 범위의 모든 날짜를 계산한다.

    이 단계의 정오 점수는 진행 상태와 날짜 참고값일 뿐이며,
    날짜를 제거하는 필터로 사용하지 않는다. 최종 후보는 다음 단계에서
    모든 날짜의 12시진을 전부 계산해 결정한다.
    """
    start_year, end_year, _, _ = automatic_age_range(
        profile.year,
        SETTINGS.max_older_years,
        SETTINGS.max_younger_years,
    )

    pool: list[DateCandidate] = []
    for index, current in enumerate(
        iter_dates(start_year, end_year),
        1,
    ):
        chart = calculate_partial_chart(
            current.year,
            current.month,
            current.day,
        )
        score, evidence = score_compatibility(
            user_chart,
            chart.year_pillar,
            chart.month_pillar,
            chart.day_pillar,
            None,
            profile.gender,
        )
        pool.append(
            DateCandidate(
                birth_date=current.isoformat(),
                chart=chart,
                score=score,
                evidence=evidence,
            )
        )

        every = SETTINGS.scan_progress_every_dates
        if every > 0 and index % every == 0:
            LOGGER.info(
                "전체 날짜 계산 진행: %s개 날짜 완료",
                index,
            )

    LOGGER.info(
        "전체 날짜 계산 완료: %s~%s년, %s개 날짜",
        start_year,
        end_year,
        len(pool),
    )
    return pool


def select_diverse_dates(
    pool: list[DateCandidate],
    user_birth_year: int,
) -> list[DateCandidate]:
    """
    과거 호환용 함수.

    현재 구조에서는 연령·월·일주 쿼터로 날짜를 제거하지 않는다.
    전체 연령 범위의 모든 날짜를 그대로 12시진 계산 단계로 넘긴다.
    """
    del user_birth_year
    return list(pool)


def age_band_summary(
    candidates: list[DateCandidate],
    user_birth_year: int,
) -> dict[str, int]:
    summary = {band: 0 for band in AGE_BAND_ORDER}
    for item in candidates:
        year = date.fromisoformat(item.birth_date).year
        band = age_band(user_birth_year, year)
        if band is not None:
            summary[band] += 1
    return summary


def _risk_penalty(candidate: Candidate) -> float:
    return sum(
        -item.score
        for item in candidate.evidence
        if item.score < 0
    )


def _representative_sort_key(
    candidate: Candidate,
) -> tuple[float, float, float, float]:
    return (
        candidate.local_score,
        -_risk_penalty(candidate),
        candidate.score.spouse_palace,
        candidate.score.internal_stability,
    )


def expand_times(
    profile: BirthProfile,
    user_chart: Chart,
    selected: list[DateCandidate],
) -> list[Candidate]:
    """
    전체 날짜마다 위치 보정이 적용된 12시진을 모두 계산하고,
    해당 생년월일에서 가장 높은 시주 하나만 대표 후보로 남긴다.
    """
    if not SETTINGS.full_range_time_scan:
        raise RuntimeError(
            "현재 후보 선정 방식은 FULL_RANGE_TIME_SCAN=1이 필요합니다."
        )

    representatives: list[Candidate] = []
    total_combinations = len(selected) * len(DOUBLE_HOURS)

    for date_index, item in enumerate(selected, 1):
        current = date.fromisoformat(item.birth_date)
        time_candidates: list[Candidate] = []

        for label, hour, minute in DOUBLE_HOURS:
            chart, calculation_audit = calculate_chart_with_audit(
                current.year,
                current.month,
                current.day,
                hour,
                minute,
            )
            score, evidence = score_compatibility(
                user_chart,
                chart.year_pillar,
                chart.month_pillar,
                chart.day_pillar,
                chart.hour_pillar,
                profile.gender,
            )
            time_candidates.append(
                Candidate(
                    candidate_id=(
                        f"{current.isoformat()}_"
                        f"{hour:02d}{minute:02d}_{label}"
                    ),
                    birth_date=current.isoformat(),
                    birth_time=f"{hour:02d}:{minute:02d}",
                    time_label=label,
                    chart=chart,
                    stage1_score=item.score.total,
                    local_score=score.total,
                    score=score,
                    evidence=evidence,
                    chart_source="local_location_corrected",
                    local_calculation_audit=calculation_audit,
                )
            )

        time_candidates.sort(
            key=_representative_sort_key,
            reverse=True,
        )
        representative = time_candidates[0]
        top3 = time_candidates[:3]
        representative.time_top3_average = round(
            sum(item.local_score for item in top3) / len(top3),
            2,
        )
        representative.time_score_range = round(
            time_candidates[0].local_score
            - time_candidates[-1].local_score,
            2,
        )
        representative.alternate_times = [
            {
                "birth_time": candidate.birth_time,
                "time_label": candidate.time_label,
                "hour_pillar": candidate.chart.hour_pillar,
                "local_score": round(candidate.local_score, 2),
                "difference_from_best": round(
                    candidate.local_score
                    - representative.local_score,
                    2,
                ),
            }
            for candidate in time_candidates[1:]
        ]
        representatives.append(representative)

        every = SETTINGS.scan_progress_every_dates
        if every > 0 and date_index % every == 0:
            LOGGER.info(
                "전체 12시진 계산 진행: %s/%s 날짜",
                date_index,
                len(selected),
            )

    representatives.sort(
        key=lambda candidate: (
            candidate.local_score,
            candidate.time_top3_average,
            -_risk_penalty(candidate),
            candidate.score.spouse_palace,
        ),
        reverse=True,
    )

    LOGGER.info(
        "전체 후보 계산 완료: %s개 날짜 × 12시진 = %s개 조합, "
        "날짜 대표 후보 %s개, 위치 보정 %+d분",
        len(selected),
        total_combinations,
        len(representatives),
        candidate_location_correction_minutes(),
    )
    return representatives


def select_final_top10(
    candidates: list[Candidate],
    target_count: int,
) -> list[Candidate]:
    if target_count <= 0:
        raise ValueError("target_count는 1 이상이어야 합니다.")
    if len(candidates) < target_count:
        raise RuntimeError(
            f"날짜 대표 후보가 {len(candidates)}개뿐이라 "
            f"TOP {target_count}을 구성할 수 없습니다."
        )

    selected = candidates[:target_count]
    dates = [candidate.birth_date for candidate in selected]
    if len(set(dates)) != len(dates):
        raise RuntimeError(
            "최종 TOP 후보에 같은 생년월일이 중복되어 있습니다."
        )
    return selected


def select_distinct_candidates(
    candidates: list[Candidate],
    target_count: int,
    max_per_birth_date: int = 1,
) -> list[Candidate]:
    if target_count <= 0:
        return []
    if max_per_birth_date <= 0:
        raise ValueError("max_per_birth_date는 1 이상이어야 합니다.")

    selected: list[Candidate] = []
    date_counts: dict[str, int] = {}
    for candidate in candidates:
        count = date_counts.get(candidate.birth_date, 0)
        if count >= max_per_birth_date:
            continue
        selected.append(candidate)
        date_counts[candidate.birth_date] = count + 1
        if len(selected) >= target_count:
            break
    return selected


def local_ranking_diagnostics(
    candidates: list[Candidate],
    top_n: int = 10,
) -> dict[str, object]:
    top = candidates[:top_n]
    day_master_distribution = Counter(
        candidate.chart.day_master
        for candidate in top
    )
    return {
        "selection_scope": "전체 연령 범위의 모든 날짜와 12시진",
        "candidate_date_count": len(candidates),
        "datetime_combination_count": len(candidates) * len(DOUBLE_HOURS),
        "location_correction_minutes": (
            candidate_location_correction_minutes()
        ),
        "top_n": top_n,
        "top_day_master_distribution": dict(day_master_distribution),
        "top_candidates": [
            {
                "rank": rank,
                "candidate_id": candidate.candidate_id,
                "birth_datetime": (
                    f"{candidate.birth_date} {candidate.birth_time}"
                ),
                "local_chart": {
                    "year": candidate.chart.year_pillar,
                    "month": candidate.chart.month_pillar,
                    "day": candidate.chart.day_pillar,
                    "hour": candidate.chart.hour_pillar,
                },
                "calculation_audit": candidate.local_calculation_audit,
                "local_score": candidate.local_score,
                "score_breakdown": {
                    "spouse_palace": candidate.score.spouse_palace,
                    "day_master": candidate.score.day_master,
                    "branch_relations": candidate.score.branch_relations,
                    "element_balance": candidate.score.element_balance,
                    "spouse_star": candidate.score.spouse_star,
                    "zodiac": candidate.score.zodiac,
                    "month_support": candidate.score.month_support,
                    "internal_stability": (
                        candidate.score.internal_stability
                    ),
                },
            }
            for rank, candidate in enumerate(top, 1)
        ],
    }
