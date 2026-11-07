"""Shared helpers for the media module's routers (FastAPI-aware)."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

# Entity names written to sync_changes.entity. They mirror the table names the briefing uses
# ("reminders, routines, media_assets ... received on /sync/pull"). Change here if 1.4 differs.
ENTITY_REMINDERS = "reminders"
ENTITY_ROUTINES = "routines"
ENTITY_MEDIA = "media_assets"

WRITE_ROLES = ("caregiver", "health_worker")


def require_writer(user) -> None:
    """Only caregivers and health workers may create/update/delete (briefing: assignment 1.3)."""
    if getattr(user, "role", None) not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Only caregivers and health workers can make changes")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def nonce_bytes(value) -> bytes:
    """media_assets.nonce is expected to be bytes; tolerate a base64 string if 1.1 chose text."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    import base64

    return base64.b64decode(value)


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")


def new_id(requested: uuid.UUID | None) -> uuid.UUID:
    from .ids import uuid7

    return requested or uuid7()
