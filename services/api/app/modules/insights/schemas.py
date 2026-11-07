"""Pydantic v2 response models: EXACT shapes from the ROUTES section of the briefing."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._util import as_utc, enum_value


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: UUID
    kind: str
    severity: str
    message: str
    created_at: datetime
    acknowledged_at: datetime | None = None

    @field_validator("kind", "severity", mode="before")
    @classmethod
    def _unwrap_enum(cls, v):
        return enum_value(v)

    @field_validator("created_at", "acknowledged_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)


class AckIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class TrendDay(BaseModel):
    date: str  # YYYY-MM-DD (UTC day)
    sessions: int
    avg_score: float | None
    avg_response_ms: float | None
    engagement_minutes: float


class TrendsOut(BaseModel):
    days: list[TrendDay]


class CueStats(BaseModel):
    n: int
    accuracy: float | None  # 0..1
    avg_response_ms: float | None


class DomainCue(BaseModel):
    domain: str
    with_cue_accuracy: float | None
    without_cue_accuracy: float | None


class CueComparisonOut(BaseModel):
    with_cue: CueStats
    without_cue: CueStats
    by_domain: list[DomainCue]


class TriggerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cue_id: str
    cue_type: str
    valence_label: str
    confidence: float
    last_validated_at: datetime
    half_life_days: float

    @field_validator("cue_id", mode="before")
    @classmethod
    def _str(cls, v):
        return str(v)

    @field_validator("last_validated_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)


class SeverityOut(BaseModel):
    band: str | None
    gds_style_indicator: int | None
    drivers: list[Any]
    disclaimer: str
    computed_at: datetime | None

    @field_validator("computed_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)
