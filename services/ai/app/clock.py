"""UTC time helpers. All timestamps in SMARAN are ISO-8601 UTC."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def parse_iso(value: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def iso(ts: datetime) -> str:
    """Fixed-width UTC string so lexical order == chronological order."""
    return ensure_utc(ts).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def days_between(later: datetime, earlier: datetime) -> float:
    """Non-negative elapsed days (clock skew never yields negative decay time)."""
    return max(0.0, (ensure_utc(later) - ensure_utc(earlier)).total_seconds() / 86400.0)
