"""Pydantic v2 request/response models for media, reminders and routines.

JSON is snake_case. Reminder JSON follows the REMINDER contract (field ``schedule``) plus
server_version; the DB column is ``schedule_rrule`` (input also accepts that name).
"""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from . import validation

Category = Literal["medicine", "hydration", "activity", "appointment"]
Locale = Literal["as", "bn", "ne", "brx", "mni", "en", "lus", "kha", "grt"]


# ---------------------------------------------------------------- media

class MediaOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    uploader_id: uuid.UUID
    kind: Literal["photo", "audio"]
    mime: str
    size_bytes: int
    tags: Any
    created_at: datetime


class SignedUrlOut(BaseModel):
    url: str
    expires_at: datetime


# ---------------------------------------------------------------- reminders

class ReminderIn(BaseModel):
    """Body for POST and PUT. ``id`` is honoured on POST only (client-generated UUIDv7).
    Unknown fields (patient_id, server_version, updated_at...) are ignored so a client can
    send back the object it received; the URL path is the authority for patient_id."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: uuid.UUID | None = None
    category: Category
    title: str = Field(min_length=1, max_length=200)
    schedule: str = Field(validation_alias=AliasChoices("schedule", "schedule_rrule"))
    locale: Locale
    voice_clip_id: uuid.UUID | None = None
    escalate_after_misses: int = Field(default=3, ge=0, le=20)  # 0 = never escalate
    active: bool = True

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("schedule")
    @classmethod
    def _schedule(cls, value: str) -> str:
        return validation.validate_rrule(value)


class ReminderOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    category: Category
    title: str
    schedule: str
    locale: str
    voice_clip_id: uuid.UUID | None
    escalate_after_misses: int
    active: bool
    server_version: int
    updated_at: datetime


# ---------------------------------------------------------------- routines

class RoutineIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    steps: list[Any]

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("steps")
    @classmethod
    def _steps(cls, value: list) -> list:
        return validation.validate_steps(value)


class RoutineOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    title: str
    steps: list[Any]
    created_by: uuid.UUID
    server_version: int
    updated_at: datetime
