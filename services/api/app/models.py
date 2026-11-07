"""SQLAlchemy 2 models: the DATABASE SCHEMA of the shared briefing, column-for-column.

Conventions
- Class names are PascalCase singular (User, PatientProfile, ...); table names are the
  snake_case plurals from the briefing. Column names/types follow the briefing exactly.
- Ids are UUIDs (client-generated UUIDv7 on devices; `uuid7()` default for server-side rows).
- Timestamps are timezone-aware UTC. `UTCDateTime` REJECTS naive datetimes on write and always
  returns aware UTC on read (also on SQLite, which has no tz support).
- Enumerations are stored as short strings + CHECK constraints (no native PG enums: simpler to
  evolve, and every module can compare against plain strings).
- JSON columns are JSONB on PostgreSQL and JSON elsewhere (tests use SQLite).
- "[append-only]" tables (game_sessions, game_events, emotion_samples, reminder_events) are
  append-only BY CONVENTION: the only sanctioned later writes are game_sessions.ended_at/score
  and emotion_samples.caregiver_confirmed.
- `server_version` (routines, reminders) auto-increments on every UPDATE via a column-level
  `onupdate` (and `updated_at` is refreshed). Do not set it by hand unless you mean to override.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7

# --------------------------------------------------------------------------------------
# Shared enumerations (single source of truth for the whole backend)
# --------------------------------------------------------------------------------------
ROLES = ("patient", "caregiver", "health_worker", "admin")
LOCALES = ("as", "bn", "ne", "brx", "mni", "en")  # 'as' first
VOICE_PACK_LOCALES = ("lus", "kha", "grt")  # voice-pack-only locales
CONSENT_KINDS = ("camera", "mic", "data_sharing")
MEDIA_KINDS = ("photo", "audio")
REMINDER_CATEGORIES = ("medicine", "hydration", "activity", "appointment")
REMINDER_EVENT_STATUSES = ("done", "later", "missed")
GAME_DOMAINS = ("memory", "attention", "routine", "pattern_object", "executive")
EMOTION_LABELS = ("joy", "comfort", "excitement", "amusement", "familiarity", "neutral", "negative")
EMOTION_SOURCES = ("face", "speech", "fused")
ALERT_KINDS = ("score_drop", "activity_drop", "missed_reminders", "severity")
ALERT_SEVERITIES = ("info", "watch", "alert")
SYNC_ACTIONS = ("upsert", "delete")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """timestamptz that always round-trips as timezone-aware UTC."""

    impl = DateTime
    cache_ok = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("timezone", True)
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime rejected: SMARAN timestamps must be timezone-aware UTC")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


JsonType = JSON().with_variant(JSONB(), "postgresql")
# BIGSERIAL on PostgreSQL; plain INTEGER PK on SQLite so autoincrement works in tests.
BigIntPk = BigInteger().with_variant(Integer(), "sqlite")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _patient_fk(*, nullable: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable)


# --------------------------------------------------------------------------------------
# Identity & access
# --------------------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    __table_args__ = (CheckConstraint("age >= 0 AND age <= 130", name="age_range"),)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    estimated_stage: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)


class CaregiverLink(Base):
    __tablename__ = "caregiver_links"
    __table_args__ = (
        UniqueConstraint("caregiver_id", "patient_id", name="uq_caregiver_links_caregiver_patient"),
        Index("ix_caregiver_links_patient_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    caregiver_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        CheckConstraint(_in("kind", CONSENT_KINDS), name="kind"),
        Index("ix_consent_records_patient_kind_ts", "patient_id", "kind", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


# --------------------------------------------------------------------------------------
# Media, routines, reminders
# --------------------------------------------------------------------------------------
class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(_in("kind", MEDIA_KINDS), name="kind"),
        Index("ix_media_assets_patient_created", "patient_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    uploader_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enc_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # AES-GCM nonce as raw bytes (12 bytes). ASSUMPTION: briefing leaves the type open.
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tags: Mapped[Any] = mapped_column(JsonType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


class Routine(Base):
    __tablename__ = "routines"
    __table_args__ = (Index("ix_routines_patient_id", "patient_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    steps: Mapped[Any] = mapped_column(JsonType, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    server_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", onupdate=literal_column("server_version") + 1
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(_in("category", REMINDER_CATEGORIES), name="category"),
        CheckConstraint("escalate_after_misses >= 0", name="escalate_nonneg"),
        Index("ix_reminders_patient_active", "patient_id", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule_rrule: Mapped[str] = mapped_column(String(500), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    # ASSUMPTION: string id (voice-pack clip id or a media_assets uuid); no FK.
    voice_clip_id: Mapped[str | None] = mapped_column(String(64))
    escalate_after_misses: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    server_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", onupdate=literal_column("server_version") + 1
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class ReminderEvent(Base):
    """[append-only]"""

    __tablename__ = "reminder_events"
    __table_args__ = (
        CheckConstraint(_in("status", REMINDER_EVENT_STATUSES), name="status"),
        Index("ix_reminder_events_patient_due", "patient_id", "due_at"),
        Index("ix_reminder_events_reminder_due", "reminder_id", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    reminder_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("reminders.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


# --------------------------------------------------------------------------------------
# Games, emotion, memory triggers
# --------------------------------------------------------------------------------------
class GameSession(Base):
    """[append-only] (ended_at/score may be filled once when the session completes)"""

    __tablename__ = "game_sessions"
    __table_args__ = (
        CheckConstraint(_in("domain", GAME_DOMAINS), name="domain"),
        CheckConstraint("difficulty >= 1 AND difficulty <= 10", name="difficulty_range"),
        Index("ix_game_sessions_patient_started", "patient_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    game_id: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    server_ts: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


class GameEvent(Base):
    """[append-only]"""

    __tablename__ = "game_events"
    __table_args__ = (
        Index("ix_game_events_patient_ts", "patient_id", "ts"),
        Index("ix_game_events_session_ts", "session_id", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    # item_shown | answer | hint_used | cue_shown | timeout | reaction (Game SDK); not CHECKed so
    # the SDK can add types without a migration.
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # ASSUMPTION: content/cue ids are strings (content-pack slugs or uuid strings).
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    cue_id: Mapped[str | None] = mapped_column(String(64))
    with_cue: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class EmotionSample(Base):
    """[append-only] (caregiver_confirmed may be set later by a caregiver)"""

    __tablename__ = "emotion_samples"
    __table_args__ = (
        CheckConstraint(_in("label", EMOTION_LABELS), name="label"),
        CheckConstraint(_in("source", EMOTION_SOURCES), name="source"),
        Index("ix_emotion_samples_patient_ts", "patient_id", "ts"),
        Index("ix_emotion_samples_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="SET NULL")
    )
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    valence: Mapped[float] = mapped_column(Float, nullable=False)
    arousal: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    caregiver_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class MemoryTrigger(Base):
    __tablename__ = "memory_triggers"
    __table_args__ = (
        CheckConstraint(_in("valence_label", EMOTION_LABELS), name="valence_label"),
        # ASSUMPTION (see HANDOFF): one trigger row per (patient, cue) so AI updates are upserts.
        UniqueConstraint("patient_id", "cue_id", name="uq_memory_triggers_patient_cue"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    cue_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    valence_label: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    last_validated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    half_life_days: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now()
    )


# --------------------------------------------------------------------------------------
# Insights
# --------------------------------------------------------------------------------------
class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(_in("kind", ALERT_KINDS), name="kind"),
        CheckConstraint(_in("severity", ALERT_SEVERITIES), name="severity"),
        Index("ix_alerts_patient_created", "patient_id", "created_at"),
        Index(
            "ix_alerts_open_patient",
            "patient_id",
            postgresql_where=text("acknowledged_at IS NULL"),
            sqlite_where=text("acknowledged_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    note: Mapped[str | None] = mapped_column(Text)


class SeverityIndicator(Base):
    __tablename__ = "severity_indicators"
    __table_args__ = (
        CheckConstraint("gds_style_indicator >= 1 AND gds_style_indicator <= 7", name="gds_range"),
        Index("ix_severity_indicators_patient_computed", "patient_id", "computed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    # AI service returns 'stable' | 'watch' | 'alert'; intentionally not CHECKed.
    band: Mapped[str] = mapped_column(String(16), nullable=False)
    gds_style_indicator: Mapped[int] = mapped_column(Integer, nullable=False)
    drivers: Mapped[Any] = mapped_column(JsonType, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


# --------------------------------------------------------------------------------------
# Sync
# --------------------------------------------------------------------------------------
class SyncChange(Base):
    """Server change log read by GET /sync/pull. `cursor` is BIGSERIAL."""

    __tablename__ = "sync_changes"
    __table_args__ = (
        CheckConstraint(_in("action", SYNC_ACTIONS), name="action"),
        Index("ix_sync_changes_patient_cursor", "patient_id", "cursor"),
    )

    cursor: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    payload: Mapped[Any] = mapped_column(JsonType, nullable=False, default=dict)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    server_ts: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


class SyncOp(Base):
    """Idempotency ledger for POST /sync/push (op_id is client-generated)."""

    __tablename__ = "sync_ops"
    __table_args__ = (Index("ix_sync_ops_applied_at", "applied_at"),)

    op_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


ALL_MODELS = (
    User,
    PatientProfile,
    CaregiverLink,
    ConsentRecord,
    MediaAsset,
    Routine,
    Reminder,
    ReminderEvent,
    GameSession,
    GameEvent,
    EmotionSample,
    MemoryTrigger,
    Alert,
    SeverityIndicator,
    SyncChange,
    SyncOp,
)
