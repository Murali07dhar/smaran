"""
Login rate limiting: 5 tries per (ip, identifier) then a 15 minute lock,
backed by Redis counters. No DB writes involved.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import settings

MAX_ATTEMPTS = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
LOCKOUT_SECONDS = getattr(settings, "LOGIN_LOCKOUT_MIN", 15) * 60
ATTEMPT_WINDOW_SECONDS = LOCKOUT_SECONDS  # attempts counter shares the lock window


def _attempts_key(ip: str, identifier: str) -> str:
    return f"login_attempts:{ip}:{identifier}"


def _lock_key(ip: str, identifier: str) -> str:
    return f"login_lock:{ip}:{identifier}"


def assert_not_locked(redis, ip: str, identifier: str) -> None:
    if redis.exists(_lock_key(ip, identifier)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "about:blank",
                "title": "too_many_attempts",
                "status": 429,
                "detail": "Too many failed login attempts. Try again later.",
            },
        )


def record_failure(redis, ip: str, identifier: str) -> None:
    key = _attempts_key(ip, identifier)
    attempts = redis.incr(key)
    if attempts == 1:
        redis.expire(key, ATTEMPT_WINDOW_SECONDS)
    if attempts >= MAX_ATTEMPTS:
        redis.setex(_lock_key(ip, identifier), LOCKOUT_SECONDS, "1")


def clear_failures(redis, ip: str, identifier: str) -> None:
    redis.delete(_attempts_key(ip, identifier))
    redis.delete(_lock_key(ip, identifier))


def client_ip(request) -> str:
    # Respect a trusted proxy header if present (typical behind nginx/ALB);
    # falls back to the direct client address.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
