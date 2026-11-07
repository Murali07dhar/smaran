"""
Redis access for auth_consent.

Redis is NOT part of the fixed shared-interface contract (only
settings.REDIS_URL is), so this is a local, module-owned dependency. It is
used for three things, none of which need a new DB column or table:

1. Login rate limiting (per IP + identifier), 5 tries -> 15 min lock.
2. Refresh-token allow-list / revocation (rotate-on-use).
3. Ephemeral patient PIN + QR-token storage (see qr.py) — a PIN is a
   short-lived, single-use login code, so it belongs in Redis with a TTL
   rather than a permanent DB column. We still also write the pin's hash to
   users.pin_hash (which the schema already has) for auditability, but the
   source of truth for "is this PIN still valid" is the Redis TTL.
   This is called out as a CONTRACT NOTE in HANDOFF.md, not a schema change
   — no table/column was added.

`redis` (redis-py) is imported lazily inside get_redis() so that the module
has zero hard import-time dependency on the `redis` package — tests
override this dependency with FakeRedis and never touch the real client.
"""
from __future__ import annotations

from app.core.config import settings

_client = None


def _real_client():
    global _client
    if _client is None:
        import redis  # local import: only required outside tests

        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _client


def get_redis():
    """FastAPI dependency. Overridden in tests with a FakeRedis instance."""
    return _real_client()
