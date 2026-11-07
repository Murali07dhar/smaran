"""Push processing: idempotency, append-only vs last-write-wins, RBAC, per-op rejection."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.security import assert_can_access_patient
from app.models import (
    EmotionSample,
    GameEvent,
    GameSession,
    Reminder,
    ReminderEvent,
    Routine,
    SyncChange,
    SyncOp,
)

from . import rules
from .changelog import record_change
from .schemas import (
    EmotionSamplePayload,
    GameEventPayload,
    GameSessionPayload,
    PushRequest,
    ReminderEventPayload,
    ReminderPayload,
    RoutinePayload,
    SyncOpIn,
)

log = logging.getLogger("smaran.sync")

MODELS = {
    "game_sessions": GameSession,
    "game_events": GameEvent,
    "emotion_samples": EmotionSample,
    "reminder_events": ReminderEvent,
    "reminders": Reminder,
    "routines": Routine,
}
PAYLOADS = {
    "game_sessions": GameSessionPayload,
    "game_events": GameEventPayload,
    "emotion_samples": EmotionSamplePayload,
    "reminder_events": ReminderEventPayload,
    "reminders": ReminderPayload,
    "routines": RoutinePayload,
}
_ROW_FIELDS = {
    "reminders": (
        "id", "patient_id", "category", "title", "schedule_rrule", "locale", "voice_clip_id",
        "escalate_after_misses", "active", "server_version", "updated_at",
    ),
    "routines": ("id", "patient_id", "title", "steps", "created_by", "server_version", "updated_at"),
}


class OpRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Effect:
    patient_id: Optional[UUID] = None
    session_ids: set = field(default_factory=set)
    notify_pipeline: bool = False  # True only when NEW append-only rows were inserted


@dataclass
class PushResult:
    accepted: list
    rejected: list
    pipeline_targets: dict  # patient_id -> set(session_ids)


# ---- helpers ---------------------------------------------------------------
def _validate(entity: str, payload: dict):
    try:
        return PAYLOADS[entity].model_validate(payload)
    except ValidationError as exc:
        err = exc.errors()[0]
        loc = ".".join(str(p) for p in err.get("loc", ())) or "payload"
        raise OpRejected(f"invalid_payload:{loc}") from None


def _check_access(session, user, patient_id: UUID, cache: dict) -> None:
    ok = cache.get(patient_id)
    if ok is None:
        try:
            assert_can_access_patient(session, user, patient_id)
            ok = True
        except HTTPException:
            ok = False
        cache[patient_id] = ok
    if not ok:
        raise OpRejected("forbidden_patient")


def _row_payload(entity: str, row) -> dict:
    return {name: getattr(row, name) for name in _ROW_FIELDS[entity]}


# ---- append-only -----------------------------------------------------------
def _apply_append_only(session, user, device_id, op: SyncOpIn, cache) -> Effect:
    if op.action == "delete":
        raise OpRejected("append_only_no_delete")
    model = MODELS[op.entity]
    p = _validate(op.entity, op.payload)
    _check_access(session, user, p.patient_id, cache)

    session_ids: set = set()
    if op.entity == "game_sessions":
        session_ids = {op.entity_id}
    elif op.entity == "game_events":
        parent = session.get(GameSession, p.session_id)
        if parent is None or parent.patient_id != p.patient_id:
            raise OpRejected("unknown_session")
        session_ids = {p.session_id}
    elif op.entity == "emotion_samples" and p.session_id is not None:
        parent = session.get(GameSession, p.session_id)
        if parent is None or parent.patient_id != p.patient_id:
            raise OpRejected("unknown_session")
        session_ids = {p.session_id}
    elif op.entity == "reminder_events":
        parent = session.get(Reminder, p.reminder_id)
        if parent is None or parent.patient_id != p.patient_id:
            raise OpRejected("unknown_reminder")

    existing = session.get(model, op.entity_id)
    if existing is not None:
        if existing.patient_id != p.patient_id:
            raise OpRejected("id_conflict")
        return Effect(patient_id=p.patient_id)  # insert-or-ignore: first write wins

    values = p.model_dump()
    if op.entity == "game_sessions":
        values["device_id"] = values.get("device_id") or device_id
        values["server_ts"] = rules.utcnow()
    session.add(model(id=op.entity_id, **values))
    session.flush()
    return Effect(patient_id=p.patient_id, session_ids=session_ids, notify_pipeline=True)


# ---- last-write-wins -------------------------------------------------------
def _apply_lww(session, user, op: SyncOpIn, cache) -> Effect:
    model = MODELS[op.entity]
    row = session.get(model, op.entity_id)
    now = rules.utcnow()

    if op.action == "delete":
        if row is None:
            return Effect()  # already gone: idempotent no-op
        _check_access(session, user, row.patient_id, cache)
        dv = op.payload.get("server_version")
        if isinstance(dv, int) and dv < row.server_version:
            raise OpRejected("stale_version")
        patient_id = row.patient_id
        has_events = op.entity == "reminders" and (
            session.scalar(
                select(func.count()).select_from(ReminderEvent).where(ReminderEvent.reminder_id == row.id)
            )
            or 0
        ) > 0
        if has_events:
            # reminder_events are append-only history: deactivate instead of orphaning/failing the FK.
            row.active = False
            row.server_version += 1
            row.updated_at = now
            session.flush()
            record_change(session, op.entity, row.id, "upsert", _row_payload(op.entity, row), patient_id)
        else:
            version = row.server_version + 1
            session.delete(row)
            session.flush()
            record_change(
                session, op.entity, op.entity_id, "delete",
                {"id": op.entity_id, "server_version": version}, patient_id,
            )
        return Effect(patient_id=patient_id)

    p = _validate(op.entity, op.payload)
    _check_access(session, user, p.patient_id, cache)
    values = p.model_dump(exclude={"server_version", "patient_id", "created_by"})

    if row is None:
        extra = {}
        if op.entity == "routines":
            extra["created_by"] = p.created_by or user.id
        row = model(
            id=op.entity_id,
            patient_id=p.patient_id,
            server_version=p.server_version if p.server_version else 1,
            updated_at=now,
            **values,
            **extra,
        )
        session.add(row)
    else:
        if row.patient_id != p.patient_id:
            raise OpRejected("patient_mismatch")
        if p.server_version is None:
            raise OpRejected("invalid_payload:server_version")
        apply, new_version = rules.lww_decision(row.server_version, row.updated_at, p.server_version, op.client_ts)
        if not apply:
            raise OpRejected("stale_version")
        for k, v in values.items():
            setattr(row, k, v)
        row.server_version = new_version
        row.updated_at = now
    session.flush()
    record_change(session, op.entity, row.id, "upsert", _row_payload(op.entity, row), row.patient_id)
    return Effect(patient_id=row.patient_id)


def apply_op(session, user, device_id, op: SyncOpIn, cache) -> Effect:
    if op.action not in rules.VALID_ACTIONS:
        raise OpRejected("invalid_action")
    if op.entity not in rules.KNOWN_ENTITIES:
        raise OpRejected("unknown_entity")
    if op.entity not in rules.PUSHABLE_ENTITIES:
        raise OpRejected("entity_not_pushable")
    if op.entity in rules.APPEND_ONLY_ENTITIES:
        return _apply_append_only(session, user, device_id, op, cache)
    return _apply_lww(session, user, op, cache)


# ---- push ------------------------------------------------------------------
def process_push(session, user, body: PushRequest) -> PushResult:
    """Apply ops (does NOT commit). Each op runs in its own SAVEPOINT together with its sync_ops row,
    so a rejected op leaves no trace and can be retried after the client fixes it."""
    op_ids = [o.op_id for o in body.ops]
    done: set = set(session.scalars(select(SyncOp.op_id).where(SyncOp.op_id.in_(op_ids)))) if op_ids else set()
    outcome: dict[UUID, Optional[str]] = {}
    cache: dict = {}
    targets: dict = {}

    ordered = sorted(enumerate(body.ops), key=lambda t: (rules.apply_priority(t[1].entity), t[0]))
    for _idx, op in ordered:
        if op.op_id in done:
            outcome[op.op_id] = None  # replay: already applied -> accepted, nothing re-executed
            continue
        try:
            with session.begin_nested():
                session.add(SyncOp(op_id=op.op_id, device_id=body.device_id, applied_at=rules.utcnow()))
                session.flush()
                effect = apply_op(session, user, body.device_id, op, cache)
        except OpRejected as exc:
            outcome[op.op_id] = exc.reason
            continue
        except IntegrityError:
            # Either a concurrent push applied the same op_id, or a constraint failed.
            if session.get(SyncOp, op.op_id) is not None:
                outcome[op.op_id] = None
                done.add(op.op_id)
            else:
                outcome[op.op_id] = "integrity_error"
            continue
        outcome[op.op_id] = None
        done.add(op.op_id)
        if effect.notify_pipeline and effect.patient_id is not None:
            targets.setdefault(effect.patient_id, set()).update(effect.session_ids)

    accepted, rejected, seen = [], [], set()
    for op in body.ops:
        if op.op_id in seen:
            continue
        seen.add(op.op_id)
        reason = outcome.get(op.op_id)
        (accepted.append(op.op_id) if reason is None else rejected.append({"op_id": op.op_id, "reason": reason}))
    return PushResult(accepted=accepted, rejected=rejected, pipeline_targets=targets)


def current_cursor(session) -> int:
    return int(session.scalar(select(func.coalesce(func.max(SyncChange.cursor), 0))) or 0)


# ---- pull ------------------------------------------------------------------
def accessible_patient_ids(session, user) -> Optional[set]:
    """None = unrestricted (admin). Mirrors assert_can_access_patient: patient -> self,
    caregiver/health_worker -> linked patients via caregiver_links."""
    from app.models import CaregiverLink

    if user.role == "admin":
        return None
    if user.role == "patient":
        return {user.id}
    return set(session.scalars(select(CaregiverLink.patient_id).where(CaregiverLink.caregiver_id == user.id)))
