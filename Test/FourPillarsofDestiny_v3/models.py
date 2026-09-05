from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Gender = Literal['F', 'M']
CalendarType = Literal['solar', 'lunar']
Mode = Literal['love', 'friend']


@dataclass
class BirthProfile:
    name: str
    gender: Gender
    calendar_type: CalendarType
    year: int
    month: int
    day: int
    hour: int
    minute: int
    time_known: bool = True
    is_leap_month: bool = False
    # 출생지는 시주 시간 보정과 해외 시간대 확인에 사용합니다.
    # 입력이 없던 과거 데이터는 기존 호환성을 위해 서울 대표 위치로 처리합니다.
    country_code: str = 'KR'
    country: str = '대한민국'
    city: str = ''
    location: str = '서울특별시, 대한민국'
    location_id: str = ''
    partner_gender: Gender = 'M'
    # 계산식은 내부 기본값을 사용하되 향후 고급 설정을 열 수 있도록 명시적으로 보존합니다.
    solar_time_mode: str = 'true_solar'

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    element_percent_local: dict[str, float] = field(default_factory=dict)
    # 원본 출생시각을 덮어쓰지 않고, 시간 보정 근거와 경계 경고를 함께 보존합니다.
    time_correction: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForcetellerFacts:
    profile: BirthProfile
    chart: Chart
    element_percent: dict[str, float]
    ten_gods: dict[str, float] = field(default_factory=dict)
    strength_label: str = ''
    strength_index: float | None = None
    strength_factors: dict[str, bool | None] = field(default_factory=dict)
    useful_elements: list[str] = field(default_factory=list)
    useful_element_detail: str = ''
    hidden_stems: dict[str, list[str]] = field(default_factory=dict)
    special_stars: list[str] = field(default_factory=list)
    special_star_positions: dict[str, list[str]] = field(default_factory=dict)
    daewoon: list[dict[str, Any]] = field(default_factory=list)
    source_quality: int = 0
    source: str = 'local_fallback'
    warnings: list[str] = field(default_factory=list)
    raw_source_path: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    category: str
    title: str
    detail: str
    direction: Literal['positive', 'negative', 'neutral'] = 'neutral'
    weight: float = 0.0


@dataclass
class AxisScore:
    key: str
    label: str
    score: float
    weight: float
    explanation: str
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def contribution(self) -> float:
        return self.score * self.weight


@dataclass
class CompatibilityResult:
    mode: Mode
    total: float
    label: str
    axes: list[AxisScore]
    direction_a_to_b: float
    direction_b_to_a: float
    strengths: list[str]
    risks: list[str]
    technical_notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatchCandidate:
    profile: BirthProfile
    facts: ForcetellerFacts
    result: CompatibilityResult
    rank: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
