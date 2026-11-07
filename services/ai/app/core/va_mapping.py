"""Class -> (valence, arousal) tables, shared by the server, DeepFace fallback and the on-device
FER model (the same table is exported in ml/models/*.meta.json so the PWA mirrors it exactly).

Coordinates are heuristic circumplex positions, NOT learned from elderly or NER data.
"""
from __future__ import annotations

FER_CLASSES = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]  # FER-2013 order
FER_VA: dict[str, tuple[float, float]] = {
    "angry": (-0.65, 0.70),
    "disgust": (-0.60, 0.35),
    "fear": (-0.65, 0.75),
    "happy": (0.80, 0.45),
    "sad": (-0.70, -0.45),
    "surprise": (0.15, 0.80),
    "neutral": (0.00, 0.00),
}

RAVDESS_CLASSES = ["neutral", "calm", "happy", "sad", "angry", "fearful", "disgust", "surprised"]
RAVDESS_VA: dict[str, tuple[float, float]] = {
    "neutral": (0.00, 0.00),
    "calm": (0.30, -0.60),
    "happy": (0.80, 0.45),
    "sad": (-0.70, -0.45),
    "angry": (-0.65, 0.70),
    "fearful": (-0.65, 0.75),
    "disgust": (-0.60, 0.35),
    "surprised": (0.15, 0.80),
}


def probs_to_va(probs: dict[str, float], table: dict[str, tuple[float, float]]) -> tuple[float, float, float]:
    """Probability-weighted valence/arousal and confidence = max class probability."""
    total = sum(max(p, 0.0) for p in probs.values()) or 1.0
    v = sum(max(p, 0.0) * table[k][0] for k, p in probs.items() if k in table) / total
    a = sum(max(p, 0.0) * table[k][1] for k, p in probs.items() if k in table) / total
    conf = max(probs.values(), default=0.0) / total
    return max(-1.0, min(1.0, v)), max(-1.0, min(1.0, a)), max(0.0, min(1.0, conf))
