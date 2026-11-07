"""Redis client helpers (sync for request handlers, asyncio for WebSockets/pub-sub)."""
from __future__ import annotations

from functools import lru_cache

import redis
import redis.asyncio as aredis

from app.core.config import settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@lru_cache
def get_async_redis() -> aredis.Redis:
    return aredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def redis_ping() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False
