"""Pydantic v2 request/response models for /sync. Shapes follow the SYNC CONTRACT exactly."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- wire shapes (binding) -------------------------------------------------


class SyncOpIn(BaseModel):
    op_id: UUID
    entity: str = Field(min_length=1, max_length=64)
    entity_id: UUID
    action: str = Field(min_length=1, max_length=16)  # validated per-op so one bad op never 422s the batch
    payload: dict[str, Any] = Field(default_factory=dict)
    client_ts: datetime


class PushRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    ops: list[SyncOpIn] = Field(max_length=500)


class RejectedOp(BaseModel):
    op_id: UUID
    reason: str


class PushResponse(BaseModel):
    accepted: list[UUID]
    rejected: list[RejectedOp]
    server_cursor: int


class PullChange(BaseModel):
    cursor: int
    entity: str
    entity_id: UUID
    action: str
    payload: dict[str, Any]
    patient_id: UUID
    server_ts: datetime


class PullResponse(BaseModel):
    changes: list[PullChange]
    server_cursor: int


# ---- per-entity payload validation ----------------------------------------
class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")  # unknown/legacy client fields are dropped, never stored


class GameSessionPayload(_Payload):
    patient_id: UUID
    game_id: str = Field(min_length=1, max_length=128)
    domain: Literal["memory", "attention", "routine", "pattern_object", "executive"]
    started_at: datetime
    ended_at: Optional[datetime] = None
    difficulty: int = Field(ge=1, le=10)
    score: Optional[float] = None
    device_id: Optional[str] = Field(default=None, max_length=64)


class GameEventPayload(_Payload):
    session_id: UUID
    patient_id: UUID
    type: Literal["item_shown", "answer", "hint_used", "cue_shown", "timeout", "reaction"]
    item_id: str = Field(min_length=1, max_length=128)
    correct: Optional[bool] = None
    response_ms: Optional[int] = Field(default=None, ge=0)
    cue_id: Optional[str] = Field(default=None, max_length=128)
    with_cue: bool = False
    ts: datetime


class EmotionSamplePayload(_Payload):
    session_id: Optional[UUID] = None
    patient_id: UUID
    valence: float
    arousal: float
    label: Literal["joy", "comfort", "excitement", "amusement", "familiarity", "neutral", "negative"]
    confidence: float = Field(ge=0, le=1)
    source: Literal["face", "speech", "fused"]
    caregiver_confirmed: Optional[bool] = None
    ts: datetime


class ReminderEventPayload(_Payload):
    reminder_id: UUID
    patient_id: UUID
    due_at: datetime
    status: Literal["done", "later", "missed"]
    ts: datetime


class ReminderPayload(_Payload):
    patient_id: UUID
    category: Literal["medicine", "hydration", "activity", "appointment"]
    title: str = Field(min_length=1, max_length=200)
    schedule_rrule: str = Field(min_length=1, max_length=500)
    locale: str = Field(min_length=2, max_length=8)
    voice_clip_id: Optional[str] = Field(default=None, max_length=128)
    escalate_after_misses: int = Field(ge=0, le=100)
    active: bool = True
    # Version the client believes this record is at after its edit. Required for updates.
    server_version: Optional[int] = Field(default=None, ge=0)


class RoutinePayload(_Payload):
    patient_id: UUID
    title: str = Field(min_length=1, max_length=200)
    steps: list[Any] = Field(default_factory=list)
    created_by: Optional[UUID] = None
    server_version: Optional[int] = Field(default=None, ge=0)
