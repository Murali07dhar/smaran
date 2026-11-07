"""Lazy model backends. Each returns None / raises ModelUnavailable if the model can't run,
so routes can answer 503 with a `fallback` hint and the client uses browser SpeechSynthesis / Web Speech API.

Real AI4Bharat integration points are marked INTEGRATION. They need GPU or multi-GB downloads (see docs/MODELS.md).
They are intentionally NOT exercised in CI.
"""
from __future__ import annotations

import io
import math
import struct
import wave
from functools import lru_cache

from .config import ASR_LANG, TTS_LANG, settings


class ModelUnavailable(Exception):
    def __init__(self, what: str, reason: str):
        super().__init__(f"{what}: {reason}")
        self.what, self.reason = what, reason


def _models_enabled() -> bool:
    return settings.models_mode != "off"


# ---------------- ASR (IndicConformer) ----------------
@lru_cache(maxsize=1)
def _load_asr():
    if not _models_enabled():
        raise ModelUnavailable("asr", "VOICE_MODELS_MODE=off")
    try:
        # INTEGRATION: AI4Bharat IndicConformer multilingual (HF: ai4bharat/indic-conformer-600m-multilingual).
        # Loaded with trust_remote_code; ~2.4 GB download; runs on CPU slowly, comfortably on GPU.
        from transformers import AutoModel  # type: ignore

        return AutoModel.from_pretrained(
            "ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True, cache_dir=settings.model_dir
        )
    except Exception as e:  # missing deps, no weights, offline, gated model
        raise ModelUnavailable("asr", f"{type(e).__name__}: {e}")


def transcribe(audio_bytes: bytes, locale: str) -> str:
    lang = ASR_LANG.get(locale)
    if not lang:
        raise ModelUnavailable("asr", f"no ASR model for locale '{locale}' (use voice packs / on-screen buttons)")
    model = _load_asr()
    try:
        import torch  # type: ignore
        import torchaudio  # type: ignore

        wav, sr = torchaudio.load(io.BytesIO(audio_bytes))
        wav = torch.mean(wav, dim=0, keepdim=True)
        if sr != 16000:
            wav = torchaudio.transforms.Resample(sr, 16000)(wav)
        return str(model(wav, lang, "ctc")).strip()  # API per model card; verify against your checkpoint
    except ModelUnavailable:
        raise
    except Exception as e:
        raise ModelUnavailable("asr", f"inference failed: {type(e).__name__}: {e}")


# ---------------- Language ID (IndicLID) ----------------
_SCRIPT_RANGES = [
    ("bn", 0x0980, 0x09FF),   # Bengali-Assamese script (as and bn share it)
    ("ne", 0x0900, 0x097F),   # Devanagari (ne, brx, hi...)
    ("mni", 0xABC0, 0xABFF),  # Meetei Mayek
]


def detect_language(text: str) -> dict:
    """Try IndicLID; fall back to a transparent script heuristic that CANNOT separate as/bn or ne/brx."""
    if _models_enabled():
        try:
            # INTEGRATION: IndicLID (ai4bharat/IndicLID) fastText + BERT cascade; ~1.5 GB. Not auto-loaded here.
            raise ModelUnavailable("lid", "IndicLID weights not installed")
        except ModelUnavailable:
            pass
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for code, lo, hi in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if latin and latin >= sum(counts.values()):
        return {"locale": "en", "confidence": 0.5, "method": "script_heuristic", "ambiguous_with": []}
    if not counts:
        return {"locale": "unknown", "confidence": 0.0, "method": "script_heuristic", "ambiguous_with": []}
    top = max(counts, key=counts.get)  # type: ignore[arg-type]
    amb = {"bn": ["as"], "ne": ["brx"]}.get(top, [])
    return {"locale": top, "confidence": 0.4 if amb else 0.7, "method": "script_heuristic", "ambiguous_with": amb}


# ---------------- TTS (Indic TTS) ----------------
@lru_cache(maxsize=1)
def _load_tts():
    if not _models_enabled():
        raise ModelUnavailable("tts", "VOICE_MODELS_MODE=off")
    try:
        # INTEGRATION: AI4Bharat Indic-TTS (FastPitch + HiFi-GAN per language) or indic-parler-tts.
        # Per-language checkpoints are 100s of MB each; Parler variant needs a GPU for usable latency.
        from TTS.utils.synthesizer import Synthesizer  # type: ignore  # noqa: F401

        raise ModelUnavailable("tts", "Indic TTS checkpoints not installed in VOICE_MODEL_DIR")
    except ImportError as e:
        raise ModelUnavailable("tts", f"Coqui TTS not installed: {e}")


def synthesize(text: str, locale: str) -> bytes:
    if locale not in TTS_LANG:
        raise ModelUnavailable("tts", f"no TTS model for locale '{locale}' (use recorded voice packs)")
    _load_tts()
    raise ModelUnavailable("tts", "not implemented without checkpoints")


# ---------------- Canned audio for mock mode / tests ----------------
def beep_wav(ms: int = 300, freq: float = 440.0, rate: int = 16000) -> bytes:
    n = int(rate * ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)))
    return buf.getvalue()
