"""Pure, dependency-free sync rules (no FastAPI / SQLAlchemy imports).

Kept separate so the rules can be unit-tested anywhere and reused by changelog.py
without pulling the web stack into other modules' import graphs.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

# --- entity classification -------------------------------------------------
APPEND_ONLY_ENTITIES = frozenset(
    {"game_sessions", "game_events", "emotion_samples", "reminder_events"}
)
LWW_ENTITIES = frozenset({"reminders", "routines"})
# Entities a device may push. Everything else the server owns (see below).
PUSHABLE_ENTITIES = APPEND_ONLY_ENTITIES | LWW_ENTITIES
# Known to the system but only ever written by the server (REST modules / AI).
SERVER_OWNED_ENTITIES = frozenset({"media_assets", "memory_triggers", "alerts"})
KNOWN_ENTITIES = PUSHABLE_ENTITIES | SERVER_OWNED_ENTITIES

# Entities served by GET /sync/pull.
PULL_ENTITIES = ("reminders", "routines", "media_assets", "memory_triggers", "alerts")

# Fields never sent to devices, per entity (media is encrypted at rest; device gets metadata only).
HIDDEN_PULL_FIELDS = {"media_assets": frozenset({"enc_path", "nonce"})}

VALID_ACTIONS = frozenset({"upsert", "delete"})

# Apply order inside one push so parents land before children even if the
# client queued them out of order (reminders -> sessions -> events).
_APPLY_ORDER = {
    "reminders": 0,
    "routines": 1,
    "game_sessions": 2,
    "reminder_events": 3,
    "game_events": 4,
    "emotion_samples": 5,
}


def apply_priority(entity: str) -> int:
    return _APPLY_ORDER.get(entity, 99)


# --- time helpers ----------------------------------------------------------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Naive datetimes (e.g. read back from SQLite) are treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: datetime) -> str:
    return as_utc(dt).isoformat().replace("+00:00", "Z")


# --- last-write-wins -------------------------------------------------------
def lww_decision(
    stored_version: int,
    stored_updated_at: Optional[datetime],
    incoming_version: int,
    client_ts: Optional[datetime],
) -> tuple[bool, int]:
    """Decide whether an incoming write wins. Returns (apply, new_server_version).

    * incoming version > stored  -> incoming wins, version kept as sent.
    * equal versions (two devices edited the same base) -> later client_ts wins and
      the stored version is bumped by one so versions stay strictly increasing.
    * lower -> stale, rejected.
    """
    if incoming_version > stored_version:
        return True, incoming_version
    if incoming_version == stored_version:
        c, s = as_utc(client_ts), as_utc(stored_updated_at)
        if c is not None and s is not None and c > s:
            return True, stored_version + 1
    return False, stored_version


# --- JSON helpers ----------------------------------------------------------
def _json_default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, datetime):
        return iso_utc(o)
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=str)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def to_jsonable(payload: Any) -> Any:
    """Round-trip through JSON so UUID/datetime/Decimal values become plain JSON."""
    return json.loads(json.dumps(payload, default=_json_default))


def sanitize_pull_payload(entity: str, payload: Any) -> Any:
    hidden = HIDDEN_PULL_FIELDS.get(entity)
    if not hidden or not isinstance(payload, dict):
        return payload
    return {k: v for k, v in payload.items() if k not in hidden}
