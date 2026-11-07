"""Adaptive difficulty (Personalize), River-based. Output 1..10 plus a plain-language rationale.

Per (patient, game) River state:
* LogisticRegression: P(correct | level, hint use, relative speed) -> gates level-ups
* EWMean of response time: personal speed baseline (slow is never penalised heavily)
* PageHinkley on the error stream: flags a recent decline in accuracy
Rationales never use failure/penalty language (elder UI rule).
"""
from __future__ import annotations

import pickle  # noqa: S403
import statistics
from dataclasses import dataclass
from datetime import datetime

from river import drift, linear_model, optim, stats

from ..clock import ensure_utc
from ..schemas import RecentItem
from ..store import PerfEvent, Store

MIN_WINDOW = 3
GATE_MIN_SEEN = 12  # events needed before the learned model may veto a level-up
UP_SCORE, DOWN_SCORE, DOWN2_SCORE = 0.85, 0.55, 0.30

Event = tuple[bool, int, int]  # (correct, response_ms, hints)


@dataclass
class DecisionResult:
    difficulty: int
    rationale: str


class DifficultyModel:
    def __init__(self) -> None:
        self.lr = linear_model.LogisticRegression(optimizer=optim.SGD(0.1))
        try:
            self.rt_mean = stats.EWMean(fading_factor=0.1)
        except TypeError:  # older River releases call it alpha
            self.rt_mean = stats.EWMean(alpha=0.1)
        self.ph = drift.PageHinkley(min_instances=10, delta=0.01, threshold=3.0, alpha=0.99)
        self.n = 0
        self.last_window: list[Event] = []

    def features(self, level: int, hints: int, rt_ms: int, baseline: float | None) -> dict[str, float]:
        slow = 0.0
        if baseline and baseline > 0 and rt_ms > 0:
            slow = min(rt_ms / baseline, 3.0) / 3.0
        return {"level": level / 10.0, "hint": min(hints, 2) / 2.0, "slow": slow}


def new_events(prev: list[Event], cur: list[Event]) -> list[Event]:
    """Drop the part of `cur` that overlaps the end of `prev` (callers re-send sliding windows)."""
    for k in range(min(len(prev), len(cur)), 0, -1):
        if prev[-k:] == cur[:k]:
            return cur[k:]
    return cur


def _pct(x: float) -> int:
    return int(round(100 * x))


def decide(window: list[Event], current: int, baseline_rt: float | None, drifting: bool,
           p_next: float | None) -> DecisionResult:
    n = len(window)
    if n < MIN_WINDOW:
        return DecisionResult(current, f"There are only {n} recent answers so far, so the level stays at {current} "
                                       "until there is a little more to go on.")
    acc = sum(1 for c, _, _ in window if c) / n
    hint_rate = sum(min(h, 2) for _, _, h in window) / (2.0 * n)
    rts = [rt for _, rt, _ in window if rt > 0]
    speed_ratio = (statistics.median(rts) / baseline_rt) if (rts and baseline_rt) else 1.0
    score = acc - 0.25 * hint_rate - 0.10 * min(max(speed_ratio - 1.3, 0.0), 1.0)
    if drifting and acc < 0.7:
        score -= 0.10

    hint_txt = "few hints" if hint_rate < 0.2 else ("some hints" if hint_rate < 0.5 else "many hints")
    step, kind = 0, "hold"
    if score >= UP_SCORE and (p_next is None or p_next >= 0.7):
        step, kind = 1, "up"
    elif score <= DOWN2_SCORE:
        step, kind = -2, "down2"
    elif score <= DOWN_SCORE:
        step, kind = -1, "down"

    new = max(1, min(10, current + step))
    if kind == "up" and new == current:
        text = f"Recent answers went smoothly ({_pct(acc)}% correct, {hint_txt}); the level is already at its top."
    elif kind == "up":
        text = (f"Recent answers went smoothly ({_pct(acc)}% correct, {hint_txt}), "
                "so the next round is one step more challenging.")
    elif kind in ("down", "down2") and new == current:
        text = f"Recent rounds looked tiring ({_pct(acc)}% correct, {hint_txt}); the level is already at its gentlest."
    elif kind == "down":
        text = (f"Recent rounds looked tiring ({_pct(acc)}% correct, {hint_txt}), "
                "so the next round is one step gentler.")
    elif kind == "down2":
        text = (f"Recent rounds looked tiring ({_pct(acc)}% correct, {hint_txt}), "
                "so the next round is two steps gentler.")
    else:
        text = f"Recent answers are in a comfortable range ({_pct(acc)}% correct, {hint_txt}), so the level stays at {current}."
        if score >= UP_SCORE and p_next is not None and p_next < 0.7:
            text += " The next step up still looks a little too hard."
    if drifting and acc < 0.7:
        text += " Performance has shifted recently, so we are being careful."
    if speed_ratio > 1.5:
        text += " Responses are slower than usual, which is fine because nothing is timed."
    return DecisionResult(new, text)


def _load(store: Store, key: str) -> DifficultyModel:
    blob = store.load_blob(key)
    if blob:
        try:
            m = pickle.loads(blob)  # noqa: S301
            if isinstance(m, DifficultyModel):
                return m
        except Exception:
            pass
    return DifficultyModel()


def next_difficulty(store: Store, patient_id: str, game_id: str, recent: list[RecentItem],
                    current: int, now: datetime) -> DecisionResult:
    key = f"diff:{patient_id}:{game_id}"
    window: list[Event] = [(r.correct, r.response_ms, r.hints) for r in recent]
    with store.lock:
        m = _load(store, key)
        fresh = new_events(m.last_window, window)
        baseline = m.rt_mean.get() if m.n >= 10 else None
        drifting = False
        perf: list[PerfEvent] = []
        for correct, rt, hints in fresh:
            x = m.features(current, hints, rt, m.rt_mean.get() if m.n >= 5 else None)
            m.lr.learn_one(x, correct)
            m.ph.update(0.0 if correct else 1.0)
            drifting = drifting or bool(getattr(m.ph, "drift_detected", False))
            if rt > 0:
                m.rt_mean.update(float(rt))
            m.n += 1
            perf.append(PerfEvent(ts=ensure_utc(now), source="game", correct=correct, response_ms=rt,
                                  hints=hints, difficulty=current, game_id=game_id))
        p_next = None
        if m.n >= GATE_MIN_SEEN and window:
            hr = sum(min(h, 2) for _, _, h in window) / (2.0 * len(window))
            p_next = float(m.lr.predict_proba_one({"level": min(current + 1, 10) / 10.0, "hint": hr,
                                                   "slow": 1.0 / 3.0}).get(True, 0.5))
        result = decide(window, current, baseline, drifting, p_next)
        m.last_window = window
        if perf:
            store.add_perf(patient_id, perf)
        store.save_blob(key, pickle.dumps(m, protocol=4))
        store.commit()
    return result
