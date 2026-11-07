"""Server change log writer. Imported by every module that mutates synced entities.

    from app.modules.sync.changelog import record_change
    record_change(session, "reminders", reminder.id, "upsert", payload_dict, patient_id)

The function only `session.add()`s a SyncChange row; the caller's transaction commits it,
so the change and the entity write are atomic. The BIGSERIAL cursor is assigned on flush.
"""
from __future__ import annotations

import uuid

from app.models import SyncChange

from .rules import VALID_ACTIONS, to_jsonable, utcnow


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def record_change(session, entity, entity_id, action, payload: dict, patient_id) -> None:
    if not isinstance(entity, str) or not entity:
        raise ValueError("entity must be a non-empty string")
    if action not in VALID_ACTIONS:
        raise ValueError(f"action must be one of {sorted(VALID_ACTIONS)}, got {action!r}")
    if entity == "reminders" and isinstance(payload, dict) and "schedule_rrule" in payload:
        # Wire shape is `schedule` (REMINDER contract); the DB column name must never leak to devices.
        payload = {**payload, "schedule": payload.get("schedule", payload["schedule_rrule"])}
        payload.pop("schedule_rrule")
    session.add(
        SyncChange(
            entity=entity,
            entity_id=_as_uuid(entity_id),
            action=action,
            payload=to_jsonable(payload if payload is not None else {}),
            patient_id=_as_uuid(patient_id),
            server_ts=utcnow(),
        )
    )
