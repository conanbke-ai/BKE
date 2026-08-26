from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class BirthProfile:
    name: str
    gender: Literal["F", "M"]
    calendar_type: Literal["solar", "lunar"]
    is_leap_month: bool
    year: int
    month: int
    day: int
    hour: int
    minute: int
    location: str
    timezone: str
    partner_gender: Literal["F", "M"]
    relationship_mode: Literal["lover", "friend"] = "lover"
    birth_time_known: bool = True


@dataclass
class Chart:
    year_pillar: str
    month_pillar: str
    day_pillar: str
    hour_pillar: str
    day_master: str
    spouse_palace: str
    stems: list[str]
    branches: list[str]
    element_counts: dict[str, int]
    element_percent: dict[str, float]
    element_source: str = "pillar_simple"
    useful_elements: list[str] = field(default_factory=list)
    strength_label: str = ""


@dataclass
class PartialChart:
    year_pillar: str
    month_pillar: str
    day_pillar: str
    day_master: str
    spouse_palace: str
    stems: list[str]
    branches: list[str]
    element_counts: dict[str, int]
    element_percent: dict[str, float]
    element_source: str = "pillar_simple"
    useful_elements: list[str] = field(default_factory=list)
    strength_label: str = ""


@dataclass
class RelationEvidence:
    category: str
    relation: str
    score: float
    evidence: str


@dataclass
class ScoreBreakdown:
    # 각 필드는 해당 기준의 최종 가중 기여도다.
    spouse_palace: float = 0
    day_master: float = 0
    branch_relations: float = 0
    element_balance: float = 0
    spouse_star: float = 0
    zodiac: float = 0
    month_support: float = 0
    internal_stability: float = 0
    base_score: float = 0
    raw_total: float = 0
    total: float = 0
    quality_scores: dict[str, float] = field(default_factory=dict)
    component_weights: dict[str, float] = field(default_factory=dict)
    scoring_mode: str = "lover"
    formula_version: str = ""


@dataclass
class DateCandidate:
    birth_date: str
    chart: PartialChart
    score: ScoreBreakdown
    evidence: list[RelationEvidence]


@dataclass
class Candidate:
    candidate_id: str
    birth_date: str
    birth_time: str
    time_label: str

    # 전체 후보군 예선에서 위치 보정 후 계산한 로컬 원국.
    chart: Chart
    stage1_score: float
    local_score: float
    score: ScoreBreakdown
    evidence: list[RelationEvidence]

    # 최종 TOP 10에 한해 포스텔러에서 확인한 원국.
    forceteller_chart: Chart | None = None
    chart_source: str = "local_location_corrected"
    chart_difference: list[str] = field(default_factory=list)
    local_calculation_audit: dict[str, object] = field(default_factory=dict)

    # 로컬 예선 순위와 포스텔러 재평가 결과를 분리해 보존한다.
    prefilter_rank: int = 0
    prefilter_score: float = 0.0
    final_score_source: str = "local_prefilter"
    forceteller_rescored_at: str = ""

    data_dir: str = ""
    screenshot_path: str = ""
    html_path: str = ""
    text_path: str = ""
    network_path: str = ""
    metadata_path: str = ""
    collection_status: str = "not_requested"
    collection_error: str = ""
    result_url: str = ""
    forceteller_facts_path: str = ""

    # 같은 생년월일의 12시진을 비교한 참고값.
    alternate_times: list[dict[str, object]] = field(default_factory=list)
    time_top3_average: float = 0.0
    time_score_range: float = 0.0
    time_median_score: float = 0.0
    selected_time_score: float = 0.0
    robust_prefilter_score: float = 0.0


@dataclass
class AICandidateReport:
    rank: int
    candidate_id: str
    ai_score: float
    interpretation_certainty: Literal["high", "medium", "limited"]
    certainty_reason: str
    candidate_type: str
    summary: str
    candidate_personality: str
    zodiac_and_sign_reading: str
    emotional_and_affection_style: str
    communication_style: str
    relationship_fit: str
    conflict_pattern: str
    daily_life_compatibility: str
    long_term_outlook: str
    strengths: list[str]
    risks: list[str]
    evidence: list[str]
    reality_checks: list[str]
    comparison_reason: str
    term_explanations: list[str]


@dataclass
class AITop10Report:
    title: str
    methodology_note: str
    overall_cautions: list[str]
    candidates: list[AICandidateReport] = field(default_factory=list)
