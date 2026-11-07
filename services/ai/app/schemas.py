"""Request/response schemas: EXACTLY the AI SERVICE contract.

Optional additive fields (labelled CCR in HANDOFF.md): SeverityRequest.samples.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EmotionLabel = Literal["joy", "comfort", "excitement", "amusement", "familiarity", "neutral", "negative"]
Locale = Literal["as", "bn", "ne", "brx", "mni", "en", "lus", "kha", "grt"]
POSITIVE_LABELS = frozenset({"joy", "comfort", "excitement", "amusement", "familiarity"})

_ID = Field(min_length=1, max_length=64)


# ---------------------------------------------------------------- triggers
class Observation(BaseModel):
    cue_id: str = _ID
    cue_type: str = Field(min_length=1, max_length=32)
    valence_label: EmotionLabel
    recalled: bool
    with_cue: bool
    ts: datetime


class TriggersUpdateRequest(BaseModel):
    patient_id: str = _ID
    observations: list[Observation] = Field(default_factory=list, max_length=2000)


class TriggerOut(BaseModel):
    cue_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    valence_label: EmotionLabel
    last_validated_at: datetime
    half_life_days: float = Field(gt=0)


class TriggersUpdateResponse(BaseModel):
    triggers: list[TriggerOut]


# -------------------------------------------------------------- difficulty
class RecentItem(BaseModel):
    correct: bool
    response_ms: int = Field(ge=0, le=10 * 60 * 1000)
    hints: int = Field(default=0, ge=0, le=50)


class DifficultyRequest(BaseModel):
    patient_id: str = _ID
    game_id: str = _ID
    recent: list[RecentItem] = Field(default_factory=list, max_length=200)
    current_difficulty: int = Field(ge=1, le=10)


class DifficultyResponse(BaseModel):
    difficulty: int = Field(ge=1, le=10)
    rationale: str


# ---------------------------------------------------------------- severity
class PerfSample(BaseModel):
    """Optional explicit performance sample (CCR-AI-1)."""

    ts: datetime
    source: Literal["game", "cue"] = "game"
    correct: bool
    response_ms: int | None = Field(default=None, ge=0)
    hints: int = Field(default=0, ge=0, le=50)
    difficulty: int | None = Field(default=None, ge=1, le=10)
    with_cue: bool | None = None
    game_id: str | None = Field(default=None, max_length=64)


class SeverityRequest(BaseModel):
    patient_id: str = _ID
    window_days: int = Field(default=30, ge=1, le=365)
    samples: list[PerfSample] | None = Field(default=None, max_length=5000)


class SeverityResponse(BaseModel):
    band: Literal["stable", "watch", "alert"]
    gds_style_indicator: int = Field(ge=1, le=7)
    drivers: list[str]
    disclaimer: str


# ------------------------------------------------------------------ emotion
class ModalityReading(BaseModel):
    valence: float = Field(ge=-1.0, le=1.0)
    arousal: float = Field(ge=-1.0, le=1.0)
    conf: float = Field(ge=0.0, le=1.0)


class Baseline(BaseModel):
    """Per-patient calibration from the first N sessions (z-scoring)."""

    model_config = ConfigDict(extra="allow")

    valence_mean: float = Field(default=0.0, ge=-1.0, le=1.0)
    valence_std: float = Field(default=0.5, ge=0.0, le=2.0)
    arousal_mean: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal_std: float = Field(default=0.5, ge=0.0, le=2.0)
    n: int = Field(default=0, ge=0)


class FuseRequest(BaseModel):
    face: ModalityReading | None = None
    speech: ModalityReading | None = None
    baseline: Baseline | None = None

    @model_validator(mode="after")
    def _need_one_modality(self) -> "FuseRequest":
        if self.face is None and self.speech is None:
            raise ValueError("at least one of 'face' or 'speech' is required")
        return self


class FuseResponse(BaseModel):
    valence: float
    arousal: float
    label: EmotionLabel
    confidence: float = Field(ge=0.0, le=1.0)


# ------------------------------------------------------------------ content
class ContentRequest(BaseModel):
    kind: Literal["reminder_phrase", "game_prompt"]
    locale: Locale
    context: dict[str, Any] = Field(default_factory=dict)


class ContentResponse(BaseModel):
    text: str
    source: Literal["gemini", "template"]
