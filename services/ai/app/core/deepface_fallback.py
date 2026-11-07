"""DeepFace server-side fallback for devices that cannot run the on-device ONNX model.

NOT exposed as an HTTP route: the AI SERVICE contract has no image endpoint, and images must
not be sent to the server without a ConsentRecord. See CONTRACT CHANGE REQUEST CCR-AI-2 in
HANDOFF.md (POST /ai/emotion/analyze). The module is ready to be mounted once approved.

deepface/tensorflow are imported lazily so the service runs without them.
"""
from __future__ import annotations

from .va_mapping import FER_VA, probs_to_va

_DEEPFACE_TO_FER = {"angry": "angry", "disgust": "disgust", "fear": "fear", "happy": "happy",
                    "sad": "sad", "surprise": "surprise", "neutral": "neutral"}


def is_available() -> bool:
    try:
        import deepface  # noqa: F401
    except ImportError:
        return False
    return True


def probs_from_deepface(emotion: dict[str, float]) -> dict[str, float]:
    """DeepFace returns percentages per class; normalise to probabilities in FER naming."""
    probs = {_DEEPFACE_TO_FER[k]: float(v) / 100.0 for k, v in emotion.items() if k in _DEEPFACE_TO_FER}
    total = sum(probs.values()) or 1.0
    return {k: v / total for k, v in probs.items()}


def face_reading_from_probs(emotion: dict[str, float]) -> dict[str, float]:
    v, a, conf = probs_to_va(probs_from_deepface(emotion), FER_VA)
    return {"valence": round(v, 4), "arousal": round(a, 4), "conf": round(conf, 4)}


def analyze_image(image_bgr) -> dict[str, float]:  # noqa: ANN001
    """image_bgr: numpy HxWx3 uint8 array. Returns a `face` reading for /ai/emotion/fuse."""
    from deepface import DeepFace  # type: ignore

    res = DeepFace.analyze(image_bgr, actions=["emotion"], enforce_detection=False, silent=True)
    first = res[0] if isinstance(res, list) else res
    return face_reading_from_probs(first["emotion"])
