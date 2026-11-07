"""Emotion fusion (Detect): face + speech -> one valence-arousal point -> emotion label.

* Per-patient calibration: z-score against the patient's own baseline (first N sessions),
  shrunk toward a population prior (mean 0, sd 0.5) when n is small. With no baseline the
  calibration is the identity.
* Confidence-weighted fusion (face 0.6, speech 0.4 base weights).
* Label = nearest prototype on the valence-arousal plane (transparent, heuristic).
* Confidence is lowered when only one modality is present, when modalities disagree, and
  when the point sits between two labels. Callers should treat low confidence as unconfirmed;
  a caregiver can always confirm or override.
"""
from __future__ import annotations

import math

from ..schemas import Baseline, ModalityReading

BASE_WEIGHTS = {"face": 0.6, "speech": 0.4}
PRIOR_STD = 0.5
STD_FLOOR = 0.15
SHRINK_N0 = 5
SINGLE_MODALITY_PENALTY = 0.85

PROTOTYPES: list[tuple[str, float, float]] = [
    ("joy", 0.85, 0.50),
    ("excitement", 0.60, 0.80),
    ("amusement", 0.60, 0.25),
    ("familiarity", 0.30, -0.05),
    ("comfort", 0.50, -0.55),
    ("neutral", 0.00, 0.00),
    ("negative", -0.65, 0.50),
    ("negative", -0.65, -0.40),
    ("negative", -0.40, 0.05),
]


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def calibrate(x: float, mean: float, std: float, n: int) -> float:
    w = n / (n + SHRINK_N0) if n > 0 else 0.0
    m = w * mean
    s = max(w * std + (1.0 - w) * PRIOR_STD, STD_FLOOR)
    return _clip(0.5 * (x - m) / s)


def label_for(valence: float, arousal: float) -> tuple[str, float]:
    """Nearest prototype label and a margin factor in [0.7, 1.0]."""
    best: dict[str, float] = {}
    for name, pv, pa in PROTOTYPES:
        d = math.hypot(valence - pv, arousal - pa)
        if name not in best or d < best[name]:
            best[name] = d
    ranked = sorted(best.items(), key=lambda kv: kv[1])
    margin = (ranked[1][1] - ranked[0][1]) if len(ranked) > 1 else 1.0
    return ranked[0][0], 0.7 + 0.3 * min(1.0, margin / 0.3)


def fuse(face: ModalityReading | None, speech: ModalityReading | None,
         baseline: Baseline | None) -> dict:
    readings = {k: r for k, r in (("face", face), ("speech", speech)) if r is not None}
    if not readings:
        raise ValueError("at least one modality is required")
    b = baseline or Baseline()
    cal: dict[str, tuple[float, float]] = {
        k: (calibrate(r.valence, b.valence_mean, b.valence_std, b.n),
            calibrate(r.arousal, b.arousal_mean, b.arousal_std, b.n))
        for k, r in readings.items()
    }
    weights = {k: BASE_WEIGHTS[k] * readings[k].conf for k in readings}
    wsum = sum(weights.values())
    if wsum <= 0.0:
        return {"valence": 0.0, "arousal": 0.0, "label": "neutral", "confidence": 0.0}

    valence = sum(weights[k] * cal[k][0] for k in readings) / wsum
    arousal = sum(weights[k] * cal[k][1] for k in readings) / wsum
    label, margin_factor = label_for(valence, arousal)

    base_total = sum(BASE_WEIGHTS[k] for k in readings)
    conf = sum(BASE_WEIGHTS[k] * readings[k].conf for k in readings) / base_total
    if len(readings) == 1:
        conf *= SINGLE_MODALITY_PENALTY
    else:
        disagreement = math.hypot(cal["face"][0] - cal["speech"][0], cal["face"][1] - cal["speech"][1]) / (2 * math.sqrt(2))
        conf *= 1.0 - 0.5 * min(1.0, disagreement)
    conf = _clip(conf * margin_factor, 0.0, 1.0)
    return {"valence": round(valence, 4), "arousal": round(arousal, 4), "label": label,
            "confidence": round(conf, 4)}
