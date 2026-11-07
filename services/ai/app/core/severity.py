"""Transparent, rule-based GDS-style indicator (1..7) and stable/watch/alert band.

SUPPORT SIGNAL, NOT A DIAGNOSIS. Norms are synthetic placeholders (app/data/reference_norms.json).

Pipeline:
1. Metrics over the window: accuracy, hint use, cue recall (with cue), average difficulty level.
   Difficulty level is included because the adaptive engine keeps accuracy near a target, which
   would otherwise mask decline.
2. Each metric -> percentile vs reference norms (normal CDF). Composite = mean percentile (0..100).
3. Composite -> indicator via a fixed table. Higher indicator = lower relative performance.
4. Band from absolute indicator plus change vs the patient's OWN first sessions.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ..clock import ensure_utc
from ..schemas import PerfSample, SeverityResponse
from ..store import PerfEvent, Store

DISCLAIMER = (
    "SMARAN provides a support signal for caregivers and health workers. It is not a medical "
    "diagnosis. Please consult a qualified clinician for any health concerns."
)
NORMS = json.loads((Path(__file__).resolve().parent.parent / "data" / "reference_norms.json").read_text())

MIN_EVENTS = 10
BASELINE_N = 30
BASELINE_MIN = 15
# (minimum composite percentile, indicator)
INDICATOR_TABLE = [(75, 1), (60, 2), (45, 3), (30, 4), (20, 5), (10, 6), (0, 7)]
WATCH_INDICATOR, ALERT_INDICATOR = 4, 5
WATCH_DROP_PP, ALERT_DROP_PP = 12.0, 25.0
SLOW_RATIO_WATCH = 1.6


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _pct(value: float, key: str, invert: bool = False) -> float:
    n = NORMS[key]
    p = _phi((value - n["mean"]) / n["sd"])
    return 100.0 * (1.0 - p if invert else p)


def indicator_from_percentile(p: float) -> int:
    for floor, ind in INDICATOR_TABLE:
        if p >= floor:
            return ind
    return 7


@dataclass
class Metrics:
    n_events: int = 0
    n_game: int = 0
    n_cue: int = 0
    accuracy: float | None = None
    hint_rate: float | None = None
    cue_recall: float | None = None
    level: float | None = None
    median_rt: float | None = None
    parts: dict[str, float] = field(default_factory=dict)  # metric -> percentile
    composite: float | None = None


def compute_metrics(events: list[PerfEvent]) -> Metrics:
    game = [e for e in events if e.source == "game"]
    cue = [e for e in events if e.source == "cue" and e.with_cue is not False]
    m = Metrics(n_events=len(events), n_game=len(game), n_cue=len(cue))
    if len(game) >= 3:
        m.accuracy = sum(e.correct for e in game) / len(game)
        m.hint_rate = sum(min(e.hints, 2) for e in game) / (2.0 * len(game))
        m.parts["accuracy"] = _pct(m.accuracy, "accuracy")
        m.parts["hint_use"] = _pct(m.hint_rate, "hint_rate", invert=True)
        lv = [e.difficulty for e in game if e.difficulty is not None]
        if len(lv) >= 3:
            m.level = sum(lv) / len(lv)
            m.parts["level"] = _pct(m.level, "level")
        rts = [e.response_ms for e in game if e.response_ms]
        if rts:
            m.median_rt = float(statistics.median(rts))
    if len(cue) >= 5:
        m.cue_recall = sum(e.correct for e in cue) / len(cue)
        m.parts["cue_recall"] = _pct(m.cue_recall, "cue_recall")
    if m.parts:
        m.composite = sum(m.parts.values()) / len(m.parts)
    return m


def ingest_samples(store: Store, patient_id: str, samples: list[PerfSample]) -> None:
    fresh: list[PerfEvent] = []
    with store.lock:
        for s in samples:
            raw = (f"{patient_id}|{ensure_utc(s.ts).isoformat()}|{s.source}|{int(s.correct)}|"
                   f"{s.response_ms}|{s.hints}|{s.difficulty}|{s.with_cue}|{s.game_id}")
            key = "perf:" + hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324
            if store.seen(key):
                continue
            store.mark_seen(key)
            fresh.append(PerfEvent(ts=ensure_utc(s.ts), source=s.source, correct=s.correct,
                                   response_ms=s.response_ms, hints=s.hints, difficulty=s.difficulty,
                                   with_cue=s.with_cue, game_id=s.game_id))
        if fresh:
            store.add_perf(patient_id, fresh)
        store.commit()


def estimate(store: Store, patient_id: str, window_days: int, now: datetime,
             samples: list[PerfSample] | None = None) -> SeverityResponse:
    if samples:
        ingest_samples(store, patient_id, samples)
    now = ensure_utc(now)
    start = now - timedelta(days=window_days)
    recent = compute_metrics(store.perf_between(patient_id, start, now))
    drivers: list[str] = [f"data: {recent.n_events} recorded events in the last {window_days} days"]

    if recent.n_events < MIN_EVENTS or recent.composite is None:
        drivers.insert(0, f"insufficient_data: at least {MIN_EVENTS} events are needed before an indicator is "
                          "meaningful, so no concern is being raised")
        return SeverityResponse(band="stable", gds_style_indicator=1, drivers=drivers, disclaimer=DISCLAIMER)

    base_events = store.perf_earliest(patient_id, BASELINE_N)
    baseline: Metrics | None = None
    if len(base_events) >= BASELINE_MIN and max(e.ts for e in base_events) < start:
        baseline = compute_metrics(base_events)
        if baseline.composite is None:
            baseline = None

    comp = recent.composite
    indicator = indicator_from_percentile(comp)

    if recent.accuracy is not None:
        drivers.append(f"accuracy: {recent.accuracy:.0%} over {recent.n_game} answers "
                       f"(percentile {recent.parts['accuracy']:.0f} vs reference)")
        drivers.append(f"hint_use: {recent.hint_rate:.0%} of the maximum "
                       f"(percentile {recent.parts['hint_use']:.0f} vs reference)")
    if recent.level is not None:
        drivers.append(f"level: average difficulty {recent.level:.1f} of 10 "
                       f"(percentile {recent.parts['level']:.0f} vs reference)")
    if recent.cue_recall is not None:
        drivers.append(f"cue_recall: {recent.cue_recall:.0%} with a cue over {recent.n_cue} trials "
                       f"(percentile {recent.parts['cue_recall']:.0f} vs reference)")
    drivers.append(f"composite: percentile {comp:.0f} -> indicator {indicator} "
                   "(75+:1, 60+:2, 45+:3, 30+:4, 20+:5, 10+:6, below 10:7)")

    delta = None
    rt_ratio = None
    if baseline is not None:
        delta = comp - baseline.composite
        drivers.append(f"trend: composite changed {delta:+.0f} points vs the patient's own first sessions")
        if recent.median_rt and baseline.median_rt:
            rt_ratio = recent.median_rt / baseline.median_rt
            if rt_ratio >= 1.2:
                drivers.append(f"speed: responses are {rt_ratio:.1f}x slower than the patient's own baseline")
    else:
        drivers.append("trend: not available yet (needs earlier baseline sessions before this window)")

    band, why = "stable", None
    if indicator >= ALERT_INDICATOR:
        band, why = "alert", f"indicator {indicator} is at or above {ALERT_INDICATOR}"
    elif delta is not None and delta <= -ALERT_DROP_PP:
        band, why = "alert", f"composite fell {abs(delta):.0f} points (limit {ALERT_DROP_PP:.0f})"
    elif indicator >= WATCH_INDICATOR:
        band, why = "watch", f"indicator {indicator} is at or above {WATCH_INDICATOR}"
    elif delta is not None and delta <= -WATCH_DROP_PP:
        band, why = "watch", f"composite fell {abs(delta):.0f} points (limit {WATCH_DROP_PP:.0f})"
    elif rt_ratio is not None and rt_ratio >= SLOW_RATIO_WATCH:
        band, why = "watch", f"responses are {rt_ratio:.1f}x slower than baseline (limit {SLOW_RATIO_WATCH})"
    drivers.append(f"band: {band}" + (f" because {why}" if why else " (no rule triggered)"))
    return SeverityResponse(band=band, gds_style_indicator=indicator, drivers=drivers, disclaimer=DISCLAIMER)
