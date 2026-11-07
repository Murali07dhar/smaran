"""
Refresh-token rotation + revocation, layered on top of
app.core.security.create_tokens/decode_token (owned by 1.1 — not
reimplemented here, only orchestrated).

Scheme: every issued refresh token's jti is written to Redis as "active"
with a TTL matching its own expiry (an allow-list, which is operationally
equivalent to a revocation list: a jti not present is treated as revoked/
unknown). /auth/refresh consumes (deletes) the presented jti and issues a
new pair, so a stolen-then-used-once refresh token stops working for
whoever holds the other copy — classic rotate-on-use. On logout (not a
route in this contract, but exposed as a plain helper for 1.1/Integrator
to call if a logout route is added later) a jti can be revoked directly.
"""
from __future__ import annotations

from app.core.security import decode_token

_ACTIVE_KEY = "refresh_active:{jti}"


def mark_active(redis, jti: str, ttl_seconds: int) -> None:
    redis.setex(_ACTIVE_KEY.format(jti=jti), max(1, ttl_seconds), "1")


def is_active(redis, jti: str) -> bool:
    return bool(redis.exists(_ACTIVE_KEY.format(jti=jti)))


def revoke(redis, jti: str) -> None:
    redis.delete(_ACTIVE_KEY.format(jti=jti))


def claims_for_new_refresh(token: str) -> dict:
    """Decode + basic-validate a presented refresh token's claims."""
    claims = decode_token(token)
    return claims
