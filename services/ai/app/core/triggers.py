"""Trigger engine (Associate).

confidence = P(theta_with_cue > theta_without_cue) * exp(-lambda * delta_t)

* theta_with_cue    ~ Beta(aw, bw): recall probability when the cue is shown
* theta_without_cue ~ Beta(ao, bo): recall probability for the same item without the cue
  Both start at Beta(1, 1). With no without-cue data this reduces to E[theta_with_cue].
* lambda = ln2 / half_life_days. delta_t = days since the last observation of the cue.
* A River online logistic model (per patient) learns how recall depends on the gap since the
  last validation and adjusts each cue's half-life: surprising recalls after long gaps lengthen
  it, surprising misses shorten it (clamped to 3..180 days).
* Cues whose resolved valence is 'negative' are capped at 0.05 so they are never promoted.
"""
from __future__ import annotations

import hashlib
import math
import pickle  # noqa: S403  (blobs are written only by this service to its own DB)
from datetime import datetime

import numpy as np
from river import linear_model, optim
from scipy.stats import beta as beta_dist

from ..clock import days_between, ensure_utc
from ..schemas import POSITIVE_LABELS, Observation, TriggerOut
from ..store import CueState, PerfEvent, Store

DEFAULT_HALF_LIFE_DAYS = 30.0
MIN_HALF_LIFE_DAYS = 3.0
MAX_HALF_LIFE_DAYS = 180.0
MAX_EVIDENCE = 40.0  # cap on effective trials per Beta (older evidence fades: disease is non-stationary)
NEGATIVE_CAP = 0.05
REVALIDATION_MIN_GAP_DAYS = 1.0
VALENCE_FORGET = 0.9
_GRID = np.linspace(0.0, 1.0, 1001)


def prob_cue_beats_baseline(aw: float, bw: float, ao: float, bo: float) -> float:
    """P(theta_w > theta_o) by trapezoidal integration of pdf_w(x) * cdf_o(x)."""
    y = beta_dist.pdf(_GRID, aw, bw) * beta_dist.cdf(_GRID, ao, bo)
    return float(np.sum((y[1:] + y[:-1]) * np.diff(_GRID)) / 2.0)


def decay_factor(half_life_days: float, dt_days: float) -> float:
    return math.exp(-(math.log(2.0) / half_life_days) * dt_days)


def resolve_label(counts: dict[str, float], last_label: str) -> str:
    if not counts:
        return last_label
    best = max(counts.values())
    top = [k for k, v in counts.items() if v >= best - 1e-9]
    return last_label if last_label in top else top[0]


def confidence_at(state: CueState, now: datetime) -> float:
    raw = prob_cue_beats_baseline(state.aw, state.bw, state.ao, state.bo)
    c = raw * decay_factor(state.half_life_days, days_between(now, state.last_ts))
    if resolve_label(state.valence_counts, state.last_label) == "negative":
        c = min(c, NEGATIVE_CAP)
    return max(0.0, min(1.0, c))


class RevalidationModel:
    """Per-patient River logistic model: P(recall | gap, with_cue, positive, experience)."""

    def __init__(self) -> None:
        self.lr = linear_model.LogisticRegression(optimizer=optim.SGD(0.2))
        self.n = 0

    @staticmethod
    def features(gap_days: float, with_cue: bool, positive: bool, n_obs: int) -> dict[str, float]:
        return {
            "log_gap": math.log1p(gap_days) / 5.0,
            "with_cue": 1.0 if with_cue else 0.0,
            "positive": 1.0 if positive else 0.0,
            "experience": min(n_obs, 20) / 20.0,
        }

    def predict(self, x: dict[str, float]) -> float:
        return float(self.lr.predict_proba_one(x).get(True, 0.5))

    def learn(self, x: dict[str, float], y: bool) -> None:
        self.lr.learn_one(x, y)
        self.n += 1


def _load_model(store: Store, patient_id: str) -> RevalidationModel:
    blob = store.load_blob(f"reval:{patient_id}")
    if blob:
        try:
            m = pickle.loads(blob)  # noqa: S301
            if isinstance(m, RevalidationModel):
                return m
        except Exception:  # corrupted/old blob: start fresh rather than fail the request
            pass
    return RevalidationModel()


def _cap_evidence(a: float, b: float) -> tuple[float, float]:
    total = a + b - 2.0
    if total > MAX_EVIDENCE:
        s = MAX_EVIDENCE / total
        return 1.0 + (a - 1.0) * s, 1.0 + (b - 1.0) * s
    return a, b


def _apply(state: CueState, obs: Observation, model: RevalidationModel, is_new: bool) -> None:
    ts = ensure_utc(obs.ts)
    positive = obs.valence_label in POSITIVE_LABELS

    if not is_new and ts >= state.last_ts:
        gap = days_between(ts, state.last_ts)
        if gap >= REVALIDATION_MIN_GAP_DAYS:
            x = model.features(gap, obs.with_cue, positive, state.n_obs)
            p = model.predict(x)
            surprise = (1.0 if obs.recalled else 0.0) - p
            weight = min(1.0, model.n / 8.0)
            hl = state.half_life_days * math.exp(0.35 * weight * surprise)
            state.half_life_days = max(MIN_HALF_LIFE_DAYS, min(MAX_HALF_LIFE_DAYS, hl))
            model.learn(x, obs.recalled)

    if obs.with_cue:
        if obs.recalled:
            state.aw += 1.0
        else:
            state.bw += 1.0
        state.aw, state.bw = _cap_evidence(state.aw, state.bw)
    else:
        if obs.recalled:
            state.ao += 1.0
        else:
            state.bo += 1.0
        state.ao, state.bo = _cap_evidence(state.ao, state.bo)

    for k in list(state.valence_counts):
        state.valence_counts[k] *= VALENCE_FORGET
    state.valence_counts[obs.valence_label] = state.valence_counts.get(obs.valence_label, 0.0) + 1.0
    state.cue_type = obs.cue_type
    state.last_label = obs.valence_label
    state.n_obs += 1
    state.last_ts = max(state.last_ts, ts)


def _obs_key(patient_id: str, o: Observation) -> str:
    raw = f"{patient_id}|{o.cue_id}|{ensure_utc(o.ts).isoformat()}|{int(o.with_cue)}|{int(o.recalled)}"
    return hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324  (dedupe key, not security)


def to_out(state: CueState, now: datetime) -> TriggerOut:
    return TriggerOut(
        cue_id=state.cue_id,
        confidence=round(confidence_at(state, now), 4),
        valence_label=resolve_label(state.valence_counts, state.last_label),
        last_validated_at=state.last_ts,
        half_life_days=round(state.half_life_days, 2),
    )


def update_triggers(store: Store, patient_id: str, observations: list[Observation], now: datetime) -> list[TriggerOut]:
    """Apply new observations (idempotent) and return ALL cues for the patient, recomputed at `now`."""
    with store.lock:
        states = {c.cue_id: c for c in store.get_cues(patient_id)}
        model = _load_model(store, patient_id)
        perf: list[PerfEvent] = []
        for obs in sorted(observations, key=lambda o: ensure_utc(o.ts)):
            key = _obs_key(patient_id, obs)
            if store.seen(key):
                continue
            store.mark_seen(key)
            st = states.get(obs.cue_id)
            is_new = st is None
            if st is None:
                st = CueState(cue_id=obs.cue_id, cue_type=obs.cue_type, last_ts=ensure_utc(obs.ts),
                              last_label=obs.valence_label, half_life_days=DEFAULT_HALF_LIFE_DAYS)
                states[obs.cue_id] = st
            _apply(st, obs, model, is_new)
            perf.append(PerfEvent(ts=ensure_utc(obs.ts), source="cue", correct=obs.recalled,
                                  with_cue=obs.with_cue, game_id=None))
        for st in states.values():
            store.save_cue(patient_id, st)
        if perf:
            store.add_perf(patient_id, perf)
        store.save_blob(f"reval:{patient_id}", pickle.dumps(model, protocol=4))
        store.commit()
        outs = [to_out(s, now) for s in states.values()]
    return sorted(outs, key=lambda t: (-t.confidence, t.cue_id))
