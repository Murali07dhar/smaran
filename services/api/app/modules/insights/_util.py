"""Small helpers shared inside the insights module."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Coerce to tz-aware UTC. SQLite (used in tests) returns naive datetimes; Postgres returns aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7 (Python 3.11/3.12 stdlib has none). Used for server-created rows."""
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    rand_a = (rand >> 62) & 0xFFF
    rand_b = rand & ((1 << 62) - 1)
    value = (ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def enum_value(v):
    """Return .value for Enum members, otherwise the value itself (real models may use Enums)."""
    return getattr(v, "value", v)
