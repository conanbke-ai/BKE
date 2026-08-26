from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from config import SETTINGS

_LOCK = threading.RLock()
_JOBS: dict[str, "ProgressJob"] = {}
_METRICS_PATH = SETTINGS.data_dir / 'runtime_metrics.json'
_METRIC_NAMESPACE = 'live_v2'
_CACHE_HINTS = ('저장된', '바로 불러', '바로 사용', '캐시')


def _metric_key(key: str) -> str:
    return f'{_METRIC_NAMESPACE}:{key}'


class ProgressCancelled(RuntimeError):
    """Raised cooperatively when the user cancels an active analysis job."""


class TimingMetrics:
    """EWMA timing store used to calibrate estimates to the machine that runs the service."""

    def __init__(self, path: Path = _METRICS_PATH) -> None:
        self.path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                self._data = raw
        except Exception:
            self._data = {}

    def stats(self, key: str) -> dict[str, Any]:
        with _LOCK:
            row = dict(self._data.get(key) or {})
        return {
            'seconds_per_unit': float(row.get('seconds_per_unit') or 0.0),
            'count': int(row.get('count') or 0),
            'error_ratio': float(row.get('error_ratio') or 0.0),
            'updated_at': float(row.get('updated_at') or 0.0),
        }

    def estimate(self, key: str, *, units: float = 1.0, fallback_per_unit: float = 1.0) -> float:
        row = self.stats(key)
        per_unit = row['seconds_per_unit'] or fallback_per_unit
        return max(0.15, per_unit * max(0.01, units))

    def record(self, key: str, elapsed: float, *, units: float = 1.0) -> None:
        if elapsed <= 0:
            return
        units = max(0.01, units)
        sample = elapsed / units
        with _LOCK:
            old = self._data.get(key) or {}
            old_value = float(old.get('seconds_per_unit') or sample)
            old_error = float(old.get('error_ratio') or 0.0)
            count = int(old.get('count') or 0)

            # A single network spike should not replace an otherwise stable history.
            alpha = 0.30 if count >= 5 else 0.42 if count >= 2 else 0.58
            new_value = sample if count == 0 else old_value * (1 - alpha) + sample * alpha

            current_error = 0.0 if count == 0 else abs(sample - old_value) / max(0.2, old_value)
            error_alpha = 0.28 if count >= 3 else 0.45
            new_error = current_error if count <= 1 else old_error * (1 - error_alpha) + current_error * error_alpha

            self._data[key] = {
                'seconds_per_unit': round(new_value, 4),
                'count': count + 1,
                'error_ratio': round(min(2.0, new_error), 4),
                'updated_at': time.time(),
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                # Timing data is an optimization only; it must never break analysis.
                pass


METRICS = TimingMetrics()


@dataclass
class Stage:
    key: str
    label: str
    expected: float
    units: float = 1.0
    metric_key: str | None = None
    fraction: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    last_progress_at: float | None = None
    last_progress_fraction: float = 0.0
    pace_seconds_per_fraction: float | None = None
    pace_samples: int = 0
    eta_anchor_at: float | None = None
    eta_anchor_remaining: float | None = None
    cache_shortcut: bool = False


@dataclass
class ProgressJob:
    id: str
    kind: str
    stages: list[Stage]
    summary: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    status: str = 'waiting'
    message: str = '분석을 준비하고 있어요.'
    error: str = ''
    _total_recorded: bool = False
    record_metrics: bool = True
    cache_shortcut: bool = False

    def expected_total(self) -> float:
        return sum(stage.expected for stage in self.stages)

    @property
    def total_metric_key(self) -> str:
        return _total_metric_key(self.kind, self.summary)

    def ensure_active(self) -> None:
        with _LOCK:
            if self.status == 'cancelled':
                raise ProgressCancelled('사용자가 분석을 중단했습니다.')

    def update(self, stage_key: str, fraction: float, message: str | None = None) -> None:
        now = time.time()
        with _LOCK:
            if self.status == 'cancelled':
                raise ProgressCancelled('사용자가 분석을 중단했습니다.')
            target = next((stage for stage in self.stages if stage.key == stage_key), None)
            if target is None:
                return

            self.status = 'running'
            incoming = min(1.0, max(0.0, float(fraction)))
            previous = target.fraction
            if target.started_at is None:
                target.started_at = now
                target.last_progress_at = now
                target.last_progress_fraction = previous
                target.eta_anchor_at = now
                target.eta_anchor_remaining = max(0.0, target.expected * (1.0 - previous))

            # Fractions must be monotonic. Message-only heartbeats are allowed, but do not
            # reset the ETA countdown because that was the cause of the apparent frozen clock.
            new_fraction = max(previous, incoming)
            if new_fraction > previous + 1e-9:
                base_at = target.last_progress_at or target.started_at or now
                base_fraction = target.last_progress_fraction
                delta_fraction = max(1e-6, new_fraction - base_fraction)
                delta_time = max(0.001, now - base_at)
                sample_pace = delta_time / delta_fraction

                if target.pace_seconds_per_fraction is None:
                    target.pace_seconds_per_fraction = sample_pace
                else:
                    # Network-backed collection is noisy. Smooth progress samples rather than
                    # allowing one slow request to replace the whole estimate.
                    alpha = 0.42 if target.pace_samples < 2 else 0.28
                    target.pace_seconds_per_fraction = (
                        target.pace_seconds_per_fraction * (1.0 - alpha) + sample_pace * alpha
                    )
                target.pace_samples += 1
                target.last_progress_at = now
                target.last_progress_fraction = new_fraction

                planned_remaining = target.expected * (1.0 - new_fraction)
                observed_remaining = (target.pace_seconds_per_fraction or target.expected) * (1.0 - new_fraction)
                observed_weight = min(0.88, 0.48 + target.pace_samples * 0.10)
                anchor_remaining = planned_remaining * (1.0 - observed_weight) + observed_remaining * observed_weight
                target.eta_anchor_at = now
                target.eta_anchor_remaining = max(0.0, anchor_remaining)

            target.fraction = new_fraction
            if message:
                self.message = message
                if any(hint in message for hint in _CACHE_HINTS):
                    target.cache_shortcut = True
                    self.cache_shortcut = True

            if target.fraction >= 1.0 and target.finished_at is None:
                target.finished_at = now
                target.eta_anchor_remaining = 0.0
                elapsed = max(0.001, target.finished_at - (target.started_at or target.finished_at))
                if self.record_metrics and target.metric_key and not target.cache_shortcut:
                    METRICS.record(target.metric_key, elapsed, units=target.units)

    def complete(self, message: str = '리포트 정리가 끝났어요.') -> None:
        with _LOCK:
            if self.status == 'cancelled':
                raise ProgressCancelled('사용자가 분석을 중단했습니다.')
            now = time.time()
            for stage in self.stages:
                if stage.fraction < 1.0:
                    stage.fraction = 1.0
                    if stage.started_at is None:
                        stage.started_at = now
                    if stage.finished_at is None:
                        stage.finished_at = now
            self.status = 'done'
            self.message = message
            if not self._total_recorded:
                elapsed = max(0.05, now - self.created_at)
                if self.record_metrics and not self.cache_shortcut:
                    METRICS.record(self.total_metric_key, elapsed)
                self._total_recorded = True

    def cancel(self, message: str = '분석을 중단했어요.') -> None:
        with _LOCK:
            if self.status in {'done', 'error'}:
                return
            self.status = 'cancelled'
            self.message = message
            self.error = ''

    def fail(self, message: str) -> None:
        with _LOCK:
            if self.status == 'cancelled':
                return
            self.status = 'error'
            self.error = message
            self.message = message

    def _stage_remaining(self, stage: Stage, now: float) -> tuple[float, bool]:
        if stage.fraction >= 1.0:
            return 0.0, False
        if stage.started_at is None:
            return max(0.0, stage.expected * (1.0 - stage.fraction)), False

        # ETA is anchored whenever measurable progress occurs, then counts down continuously
        # between callbacks. This prevents a network request from leaving the displayed time
        # frozen at the same value for tens of seconds.
        anchor_at = stage.eta_anchor_at or stage.started_at
        anchor_remaining = stage.eta_anchor_remaining
        if anchor_remaining is None:
            anchor_remaining = max(0.0, stage.expected * (1.0 - stage.fraction))
        elapsed_since_anchor = max(0.0, now - anchor_at)
        remaining = max(0.0, anchor_remaining - elapsed_since_anchor)

        last_progress = stage.last_progress_at or stage.started_at
        stale_for = max(0.0, now - last_progress)
        # When an external request exceeds the current estimate, showing 0 seconds or holding
        # the last number is misleading. Switch to an explicit recalibration state until the
        # next real progress sample arrives.
        recalculating = remaining <= 0.05 and stage.fraction < 1.0 and stale_for >= 3.0
        return remaining, recalculating

    def _predicted_remaining(self, now: float) -> tuple[float, bool]:
        if self.status in {'done', 'cancelled', 'error'}:
            return 0.0, False

        remaining = 0.0
        recalculating = False
        for stage in self.stages:
            if stage.fraction >= 1.0:
                continue
            stage_remaining, stage_recalculating = self._stage_remaining(stage, now)
            remaining += stage_remaining
            recalculating = recalculating or stage_recalculating
        return max(0.0, remaining), recalculating

    def snapshot(self) -> dict[str, Any]:
        with _LOCK:
            now = time.time()
            total = max(0.1, self.expected_total())
            done_weight = sum(stage.expected * stage.fraction for stage in self.stages)
            terminal = self.status in {'done', 'cancelled', 'error'}
            percent = 100.0 if self.status == 'done' else min(99.0, done_weight / total * 100.0)
            remaining, recalculating = (0.0, False) if terminal else self._predicted_remaining(now)

            total_stats = METRICS.stats(self.total_metric_key)
            sample_count = int(total_stats['count'])
            historical_error = float(total_stats['error_ratio'])

            # Keep an internal uncertainty interval for diagnostics/API compatibility,
            # but the UI intentionally presents the central estimate instead of a distracting wide range.
            if sample_count >= 5:
                margin = min(0.18, max(0.08, historical_error * 1.20))
            elif sample_count >= 2:
                margin = 0.16
            elif sample_count >= 1:
                margin = 0.18
            else:
                # Before clean live measurements exist, do not pretend the fallback formula
                # is second-level precise. The UI renders this as a friendly range.
                margin = 0.22

            active = next((s for s in self.stages if s.started_at and not s.finished_at and s.fraction < 1.0), None)
            if active and active.fraction >= 0.12:
                margin = min(margin, 0.09)
            if active and active.fraction >= 0.35:
                margin = min(margin, 0.07)

            remaining_seconds = 0 if terminal else (None if recalculating else max(1, int(round(remaining))))
            expected_seconds = max(1, int(round(total)))
            low = 0 if terminal else (None if remaining_seconds is None else max(1, int(round(remaining_seconds * (1 - margin)))))
            high = 0 if terminal else (None if remaining_seconds is None else max(low, int(round(remaining_seconds * (1 + margin)))))
            expected_low = max(1, int(round(expected_seconds * (1 - margin))))
            expected_high = max(expected_low, int(round(expected_seconds * (1 + margin))))

            steps: list[dict[str, Any]] = []
            for stage in self.stages:
                if stage.fraction >= 1:
                    stage_status = 'done'
                elif self.status == 'cancelled' and stage.started_at:
                    stage_status = 'cancelled'
                elif stage.started_at and not stage.finished_at:
                    stage_status = 'active'
                else:
                    stage_status = 'pending'
                steps.append({
                    'key': stage.key,
                    'label': stage.label,
                    'status': stage_status,
                    'fraction': round(stage.fraction, 3),
                })

            return {
                'job_id': self.id,
                'kind': self.kind,
                'status': self.status,
                'message': self.message,
                'percent': round(percent, 1),
                'remaining_seconds': {
                    'seconds': remaining_seconds,
                    'min': low,
                    'max': high,
                    'state': 'recalculating' if recalculating else 'counting',
                    'calibrated': sample_count > 0 or bool(active and active.fraction >= 0.05),
                },
                'expected_seconds': {
                    'seconds': expected_seconds,
                    'min': expected_low,
                    'max': expected_high,
                    'calibrated': sample_count > 0,
                    'samples': sample_count,
                    'basis': 'measured' if sample_count > 0 else 'baseline',
                },
                'elapsed_seconds': round(now - self.created_at, 1),
                'active_elapsed_seconds': round(now - active.started_at, 1) if active and active.started_at else 0.0,
                'active_stage_key': active.key if active else '',
                'timing_profile': str(self.summary.get('timing_profile') or 'live'),
                'timing_learning': bool(self.record_metrics),
                'cache_shortcut': bool(self.cache_shortcut),
                'steps': steps,
                'error': self.error,
            }


def _flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'y', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'n', 'off', ''}:
        return False
    return default


def _auto_year_span(summary: dict[str, Any]) -> int:
    """Return the actual number of birth years searched by the current age-range rule."""
    try:
        user_year = int(summary.get('birth_year') or 0)
    except (TypeError, ValueError):
        user_year = 0
    if user_year < 1900:
        # Most users are in the 25-39 bucket; this is only a preview fallback before a birth date is typed.
        return 14

    age = date.today().year - user_year
    if age <= 24:
        older, younger = 5, 3
    elif age <= 39:
        older, younger = 8, 5
    elif age <= 49:
        older, younger = 10, 8
    else:
        older, younger = 12, 10

    start_year = max(1900, user_year - older)
    latest_adult_year = date.today().year - SETTINGS.min_partner_age
    end_year = min(user_year + younger, latest_adult_year)
    if start_year > end_year:
        return 1
    return max(1, end_year - start_year + 1)


def _total_metric_key(kind: str, summary: dict[str, Any]) -> str:
    if kind == 'pair':
        return _metric_key('job_total:pair')
    if kind == 'group':
        members = max(2, int(summary.get('members') or 2))
        return _metric_key(f'job_total:group:m{members}')

    build = 1 if summary.get('build_matches') else 0
    pair = 1 if summary.get('include_pair') else 0
    group_members = max(0, int(summary.get('group_members') or 0))
    auto_years = _auto_year_span(summary) if build else 0
    return _metric_key(f'job_total:initial:b{build}:p{pair}:g{group_members}:a{auto_years}')


def _initial_stages(summary: dict[str, Any]) -> list[Stage]:
    build = _flag(summary.get('build_matches'))
    pair = _flag(summary.get('include_pair'))
    # group_members는 프론트와 API 모두 '본인 포함 총 인원'으로 통일한다.
    group_total_members = max(0, int(summary.get('group_members') or 0))
    group_extra_members = max(0, group_total_members - 1)
    pair_count = group_total_members * (group_total_members - 1) / 2 if group_total_members >= 2 else 0

    stages = [
        Stage('natal', '출생정보와 원국 확인', METRICS.estimate(_metric_key('natal_collect'), fallback_per_unit=5.5), metric_key=_metric_key('natal_collect')),
        Stage('local', '내 사주와 운세 구조 정리', METRICS.estimate(_metric_key('local_report'), fallback_per_unit=1.6), metric_key=_metric_key('local_report')),
    ]
    if build:
        auto_years = _auto_year_span(summary)
        # Local exhaustive search and network-backed candidate verification behave very
        # differently, so they must not share one ETA stage. Keeping them separate is the
        # key to a stable live countdown.
        stages.extend([
            Stage(
                'auto_scan',
                '잘 맞는 사람 후보 전체 탐색',
                METRICS.estimate(_metric_key('auto_scan_per_year'), units=auto_years, fallback_per_unit=2.2),
                units=auto_years,
                metric_key=_metric_key('auto_scan_per_year'),
            ),
            Stage(
                'auto_collect',
                '추천 후보 원국 자료 확인',
                METRICS.estimate(_metric_key('auto_collect_per_candidate'), units=max(2, auto_years * 2 * SETTINGS.auto_shortlist_per_year), fallback_per_unit=4.2),
                units=max(2, auto_years * 2 * SETTINGS.auto_shortlist_per_year),
                metric_key=_metric_key('auto_collect_per_candidate'),
            ),
        ])
    if pair:
        stages.extend([
            Stage('pair_collect', '1:1 상대 원국 확인', METRICS.estimate(_metric_key('pair_target_collect'), fallback_per_unit=4.2), metric_key=_metric_key('pair_target_collect')),
            Stage('pair_score', '1:1 궁합 계산', METRICS.estimate(_metric_key('pair_score'), fallback_per_unit=1.2), metric_key=_metric_key('pair_score')),
        ])
    if group_total_members >= 2:
        stages.extend([
            Stage(
                'group_collect',
                '그룹 구성원 원국 확인',
                METRICS.estimate(_metric_key('group_collect_per_member'), units=group_total_members, fallback_per_unit=4.0),
                units=group_total_members,
                metric_key=_metric_key('group_collect_per_member'),
            ),
            Stage(
                'group_pairwise',
                '그룹 연결 구조 계산',
                METRICS.estimate(_metric_key('group_pair_per_pair'), units=max(1, pair_count), fallback_per_unit=0.045),
                units=max(1, pair_count),
                metric_key=_metric_key('group_pair_per_pair'),
            ),
        ])

    narrative_units = 1.0 + (0.22 if build else 0.0) + (0.16 if pair else 0.0) + min(0.45, group_extra_members * 0.025)
    stages.extend([
        Stage(
            'narrative',
            '해설을 생활 언어로 정리',
            METRICS.estimate(_metric_key('initial_narrative_unit'), units=narrative_units, fallback_per_unit=7.0),
            units=narrative_units,
            metric_key=_metric_key('initial_narrative_unit'),
        ),
        Stage('finalize', '리포트 화면 마무리', METRICS.estimate(_metric_key('finalize'), fallback_per_unit=0.7), metric_key=_metric_key('finalize')),
    ])
    return stages


def _group_stages(summary: dict[str, Any]) -> list[Stage]:
    members = max(2, int(summary.get('members') or 2))
    pairs = members * (members - 1) / 2
    return [
        Stage('collect', '구성원 원국 확인', METRICS.estimate(_metric_key('group_collect_per_member'), units=members, fallback_per_unit=4.0), units=members, metric_key=_metric_key('group_collect_per_member')),
        Stage('pairwise', '모든 1:1 연결 계산', METRICS.estimate(_metric_key('group_pair_per_pair'), units=max(1, pairs), fallback_per_unit=0.045), units=max(1, pairs), metric_key=_metric_key('group_pair_per_pair')),
        Stage('finalize', '그룹 관계표 정리', METRICS.estimate(_metric_key('finalize'), fallback_per_unit=0.7), metric_key=_metric_key('finalize')),
    ]


def _pair_stages(summary: dict[str, Any]) -> list[Stage]:
    return [
        Stage('collect', '두 사람 원국 확인', METRICS.estimate(_metric_key('pair_collect'), fallback_per_unit=4.2), metric_key=_metric_key('pair_collect')),
        Stage('pairwise', '궁합 구조 계산', METRICS.estimate(_metric_key('pair_score'), fallback_per_unit=1.4), metric_key=_metric_key('pair_score')),
        Stage('finalize', '궁합 화면 정리', METRICS.estimate(_metric_key('finalize'), fallback_per_unit=0.7), metric_key=_metric_key('finalize')),
    ]


def _base_stages_for(kind: str, summary: dict[str, Any]) -> list[Stage]:
    if kind == 'group':
        return _group_stages(summary)
    if kind == 'pair':
        return _pair_stages(summary)
    return _initial_stages(summary)


def _stages_for(kind: str, summary: dict[str, Any]) -> list[Stage]:
    stages = _base_stages_for(kind, summary)
    base_total = sum(s.expected for s in stages)
    if base_total <= 0:
        return stages

    # For an identical analysis shape, the most useful estimate is the measured end-to-end time
    # from this machine. Blend it with stage estimates until enough samples accumulate.
    total_stats = METRICS.stats(_total_metric_key(kind, summary))
    count = int(total_stats['count'])
    measured = float(total_stats['seconds_per_unit'])
    if count <= 0 or measured <= 0:
        return stages

    # Keep the conservative baseline as the anchor. Clean live history improves the
    # estimate gradually instead of letting a few unusually fast runs collapse the ETA.
    history_weight = 0.25 if count == 1 else 0.35 if count == 2 else 0.45 if count < 5 else 0.55 if count < 10 else 0.65
    target_total = base_total * (1.0 - history_weight) + measured * history_weight
    scale = min(1.8, max(0.72, target_total / base_total))
    for stage in stages:
        stage.expected = max(0.1, stage.expected * scale)
    return stages


def estimate(kind: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = summary or {}
    normalized = kind if kind in {'initial', 'group', 'pair'} else 'initial'
    temp = ProgressJob('preview', normalized, _stages_for(normalized, summary), summary=dict(summary), record_metrics=False)
    snapshot = temp.snapshot()
    return {'expected_seconds': snapshot['expected_seconds'], 'steps': snapshot['steps']}


def create_job(kind: str, summary: dict[str, Any] | None = None) -> ProgressJob:
    summary = summary or {}
    normalized = kind if kind in {'initial', 'group', 'pair'} else 'initial'
    timing_profile = str(summary.get('timing_profile') or 'live').lower()
    disable_learning = _flag(summary.get('disable_timing_learning'))
    record_metrics = timing_profile == 'live' and not disable_learning
    job = ProgressJob(
        uuid.uuid4().hex,
        normalized,
        _stages_for(normalized, summary),
        summary=dict(summary),
        record_metrics=record_metrics,
    )
    with _LOCK:
        _JOBS[job.id] = job
        cutoff = time.time() - 60 * 60
        for key in [key for key, value in _JOBS.items() if value.created_at < cutoff]:
            _JOBS.pop(key, None)
    return job


def get_job(job_id: str | None) -> ProgressJob | None:
    if not job_id:
        return None
    with _LOCK:
        return _JOBS.get(str(job_id))


def cancel_job(job_id: str | None) -> ProgressJob | None:
    job = get_job(job_id)
    if job:
        job.cancel()
    return job
