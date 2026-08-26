from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date

from bazi_engine import (
    DOUBLE_HOURS,
    calculate_chart,
    calculate_chart_with_audit,
    calculate_partial_chart,
    profile_to_solar,
    candidate_location_correction_minutes,
)
from config import SETTINGS
from logging_utils import LOGGER
from models import BirthProfile, Candidate, Chart, DateCandidate
from scoring import score_compatibility




@dataclass(frozen=True)
class AgeSearchPolicy:
    user_age: int
    min_candidate_age: int
    max_candidate_age: int
    max_younger_years: int
    max_older_years: int
    mode: str
    gender: str
    label: str


def _full_age(born: date, today: date) -> int:
    return today.year - born.year - (
        (today.month, today.day) < (born.month, born.day)
    )


def _profile_solar_birth_date(profile: BirthProfile) -> date:
    solar = profile_to_solar(profile)
    return date(solar.getYear(), solar.getMonth(), solar.getDay())


def resolve_age_search_policy(
    profile: BirthProfile,
    today: date | None = None,
) -> AgeSearchPolicy:
    """개인 후보 탐색에 사용할 현실적인 나이 범위를 결정한다.

    - 10대: 10대 안에서만 최대 3세 차이
    - 성인: 20세 미만 제외
    - 친구 모드: 성별 편향 없이 연령대가 높아질수록 대칭 확장
    - 연인 모드: 남성 사용자는 연하 쪽, 여성 사용자는 연상 쪽을
      상대적으로 더 넓게 허용
    """
    today = today or date.today()
    user_age = _full_age(_profile_solar_birth_date(profile), today)

    if not SETTINGS.dynamic_age_range_enabled:
        younger = SETTINGS.max_younger_years
        older = SETTINGS.max_older_years
        minimum = max(20 if user_age >= 20 else 0, user_age - younger)
        maximum = user_age + older
        return AgeSearchPolicy(
            user_age=user_age,
            min_candidate_age=minimum,
            max_candidate_age=maximum,
            max_younger_years=younger,
            max_older_years=older,
            mode=profile.relationship_mode,
            gender=profile.gender,
            label=(
                f"고정 범위: 연하 최대 {younger}세 · "
                f"연상 최대 {older}세"
            ),
        )

    if user_age < 10:
        younger = older = 2
        minimum = max(0, user_age - younger)
        maximum = min(9, user_age + older)
        band = "아동 연령대"
    elif user_age < 20:
        younger = older = 3
        minimum = max(10, user_age - younger)
        maximum = min(19, user_age + older)
        band = "10대"
    elif profile.relationship_mode == "friend":
        if user_age < 30:
            younger = older = 7
            band = "20대 친구"
        elif user_age < 40:
            younger = older = 10
            band = "30대 친구"
        elif user_age < 50:
            younger = older = 12
            band = "40대 친구"
        else:
            younger = older = 15
            band = "50대 이상 친구"
        minimum = max(20, user_age - younger)
        maximum = user_age + older
    else:
        female = profile.gender == "F"
        if user_age < 30:
            younger, older = ((4, 8) if female else (7, 5))
            band = "20대 연인"
        elif user_age < 40:
            younger, older = ((6, 12) if female else (10, 8))
            band = "30대 연인"
        elif user_age < 50:
            younger, older = ((8, 15) if female else (12, 10))
            band = "40대 연인"
        elif user_age < 60:
            younger, older = ((10, 18) if female else (15, 12))
            band = "50대 연인"
        else:
            younger, older = ((12, 20) if female else (18, 15))
            band = "60대 이상 연인"
        minimum = max(20, user_age - younger)
        maximum = user_age + older

    return AgeSearchPolicy(
        user_age=user_age,
        min_candidate_age=minimum,
        max_candidate_age=maximum,
        max_younger_years=younger,
        max_older_years=older,
        mode=profile.relationship_mode,
        gender=profile.gender,
        label=(
            f"{band}: 만 {minimum}~{maximum}세 · "
            f"연하 최대 {younger}세 · 연상 최대 {older}세"
        ),
    )


def candidate_date_allowed(
    profile: BirthProfile,
    candidate_born: date,
    today: date | None = None,
) -> bool:
    today = today or date.today()
    policy = resolve_age_search_policy(profile, today)
    candidate_age = _full_age(candidate_born, today)
    return (
        policy.min_candidate_age
        <= candidate_age
        <= policy.max_candidate_age
    )


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
    today = date.today()
    policy = resolve_age_search_policy(profile, today)
    # 생일 경계까지 정확히 필터링하기 위해 양끝 연도를 1년씩 넓게 훑는다.
    start_year = today.year - policy.max_candidate_age - 1
    end_year = today.year - policy.min_candidate_age + 1

    pool: list[DateCandidate] = []
    scanned = 0
    for current in iter_dates(start_year, end_year):
        if not candidate_date_allowed(profile, current, today):
            continue
        scanned += 1
        index = scanned
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
            profile.relationship_mode,
            candidate_chart=chart,
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
        "전체 날짜 계산 완료: %s~%s년, %s개 날짜 / 나이 정책: %s",
        start_year,
        end_year,
        len(pool),
        policy.label,
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
                profile.relationship_mode,
                candidate_chart=chart,
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
                    prefilter_score=score.total,
                    final_score_source="local_prefilter",
                )
            )

        time_candidates.sort(
            key=_representative_sort_key,
            reverse=True,
        )
        representative = time_candidates[0]
        exact_best_score = representative.local_score
        top3 = time_candidates[:3]
        top3_average = sum(
            candidate.local_score for candidate in top3
        ) / len(top3)
        ordered_scores = sorted(
            candidate.local_score
            for candidate in time_candidates
        )
        middle = len(ordered_scores) // 2
        median_score = (
            ordered_scores[middle]
            if len(ordered_scores) % 2
            else (
                ordered_scores[middle - 1]
                + ordered_scores[middle]
            ) / 2
        )

        # 우연히 한 시주에서만 치솟는 날짜보다 여러 시진에서 안정적으로
        # 높은 날짜를 우선한다. 대표 시주는 최고 시주를 유지하되,
        # 날짜 예선 순위는 최고 65% + 상위 3개 평균 25% + 중앙값 10%다.
        robust_score = (
            exact_best_score * 0.65
            + top3_average * 0.25
            + median_score * 0.10
        )
        representative.selected_time_score = round(
            exact_best_score,
            2,
        )
        representative.time_top3_average = round(
            top3_average,
            2,
        )
        representative.time_median_score = round(
            median_score,
            2,
        )
        representative.robust_prefilter_score = round(
            robust_score,
            2,
        )
        representative.local_score = round(robust_score, 1)
        representative.prefilter_score = representative.local_score
        representative.time_score_range = round(
            exact_best_score
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
                    candidate.local_score - exact_best_score,
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

    for rank, candidate in enumerate(representatives, 1):
        candidate.prefilter_rank = rank
        candidate.prefilter_score = candidate.local_score
        candidate.final_score_source = "local_prefilter"

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



def verified_forceteller_candidates(
    candidates: list[Candidate],
) -> list[Candidate]:
    verified = [
        candidate
        for candidate in candidates
        if candidate.forceteller_chart is not None
        and candidate.final_score_source == "forceteller_rescored"
        and candidate.collection_status
        in {"collected", "skipped_existing", "cached"}
    ]
    verified.sort(
        key=lambda candidate: (
            candidate.local_score,
            -_risk_penalty(candidate),
            candidate.score.spouse_palace,
            candidate.score.internal_stability,
            -candidate.prefilter_rank,
        ),
        reverse=True,
    )
    return verified


def select_verified_final_top10(
    candidates: list[Candidate],
    target_count: int,
) -> list[Candidate]:
    verified = verified_forceteller_candidates(candidates)
    if len(verified) < target_count:
        raise RuntimeError(
            f"포스텔러 원국으로 재평가된 후보가 {len(verified)}명뿐이라 "
            f"TOP {target_count}을 구성할 수 없습니다."
        )
    selected = verified[:target_count]
    dates = [candidate.birth_date for candidate in selected]
    if len(set(dates)) != len(dates):
        raise RuntimeError(
            "포스텔러 재평가 TOP 후보에 같은 생년월일이 중복되어 있습니다."
        )
    return selected


def reorder_with_verified_top10(
    candidates: list[Candidate],
    top10: list[Candidate],
) -> None:
    selected_ids = {candidate.candidate_id for candidate in top10}
    remaining = [
        candidate
        for candidate in candidates
        if candidate.candidate_id not in selected_ids
    ]
    remaining.sort(
        key=lambda candidate: (
            candidate.prefilter_rank if candidate.prefilter_rank > 0 else 10**9,
            -candidate.prefilter_score,
        )
    )
    candidates[:] = list(top10) + remaining


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
    profile: BirthProfile | None = None,
) -> dict[str, object]:
    top = candidates[:top_n]
    day_master_distribution = Counter(
        candidate.chart.day_master
        for candidate in top
    )
    age_policy = (
        asdict(resolve_age_search_policy(profile))
        if profile is not None
        else None
    )
    return {
        "selection_scope": "동적 현실 나이 범위의 모든 날짜와 12시진",
        "age_search_policy": age_policy,
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
                "prefilter_rank": candidate.prefilter_rank,
                "prefilter_score": candidate.prefilter_score,
                "selected_time_score": candidate.selected_time_score,
                "top3_average": candidate.time_top3_average,
                "time_median_score": candidate.time_median_score,
                "robust_prefilter_score": candidate.robust_prefilter_score,
                "effective_score": candidate.local_score,
                "final_score_source": candidate.final_score_source,
                "formula_version": candidate.score.formula_version,
                "quality_scores": candidate.score.quality_scores,
                "component_weights": candidate.score.component_weights,
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
