"""
Patient PIN + QR-token login.

CONTRACT NOTE (see HANDOFF.md "Contract deviations"): the fixed schema has
users.pin_hash but no expiry column, and no qr_token table at all. Rather
than invent a column, both the PIN and the QR token are ephemeral,
Redis-backed, with the hashed PIN also written to users.pin_hash for
auditability. Source of truth for validity is the Redis TTL, not the DB row.

- PIN: 6 digits, caregiver/health_worker generated, single ACTIVE pin per
  patient (generating a new one invalidates the previous one), expires
  after PATIENT_PIN_TTL_MIN minutes. Not single-use — valid for repeated
  login attempts until it expires or is regenerated, so a patient who
  mistypes can retry without a caregiver re-issuing it.
- QR token: a short-lived signed JWT (HS256, same JWT_SECRET) encoding
  {patient_id, purpose:"qr_login", jti}, verified statelessly by signature
  + exp, then marked used in Redis (single-use) so a captured/replayed QR
  image can't be reused after the first successful login.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import TokenError, create_token, decode_token

PIN_TTL_MIN = getattr(settings, "PATIENT_PIN_TTL_MIN", 10)
QR_TTL_MIN = getattr(settings, "PATIENT_QR_TTL_MIN", 10)

_PIN_ACTIVE_KEY = "pin_active:{patient_id}"
_PIN_LOGIN_KEY = "pin_login:{pin}"
_QR_USED_KEY = "qr_used:{jti}"


def generate_pin(redis, patient_id: str) -> tuple[str, datetime]:
    """Issue a new 6-digit PIN for patient_id, invalidating any prior one."""
    old_pin = redis.get(_PIN_ACTIVE_KEY.format(patient_id=patient_id))
    if old_pin:
        old_pin_str = old_pin.decode() if isinstance(old_pin, bytes) else old_pin
        redis.delete(_PIN_LOGIN_KEY.format(pin=old_pin_str))

    pin = f"{secrets.randbelow(1_000_000):06d}"
    ttl_seconds = PIN_TTL_MIN * 60
    redis.setex(_PIN_ACTIVE_KEY.format(patient_id=patient_id), ttl_seconds, pin)
    redis.setex(_PIN_LOGIN_KEY.format(pin=pin), ttl_seconds, str(patient_id))

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    return pin, expires_at


def lookup_patient_by_pin(redis, pin: str) -> str | None:
    raw = redis.get(_PIN_LOGIN_KEY.format(pin=pin))
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


def generate_qr_token(patient_id: str) -> tuple[str, datetime]:
    """Signed with the core's create_token (type='qr'): never accepted as an access/refresh token."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=QR_TTL_MIN)
    token = create_token(patient_id, "qr", timedelta(minutes=QR_TTL_MIN), purpose="qr_login")
    return token, expires_at


def _qr_401(title: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"type": "about:blank", "title": title, "status": 401},
    )


def verify_and_consume_qr(redis, token: str) -> str:
    try:
        claims = decode_token(token, "qr")
    except TokenError as exc:
        raise _qr_401("qr_token_expired" if "expired" in str(exc).lower() else "qr_token_invalid") from exc
    if claims.get("purpose") != "qr_login":
        raise _qr_401("qr_token_invalid")

    used_key = _QR_USED_KEY.format(jti=claims["jti"])
    if redis.exists(used_key):
        raise _qr_401("qr_token_already_used")
    remaining = max(1, int(claims["exp"]) - int(datetime.now(timezone.utc).timestamp()))
    redis.setex(used_key, remaining, "1")
    return claims["sub"]
