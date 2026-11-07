"""Redis-backed room state for the co-op relay.

Keys (all expire with the room):
  coop:room:{id}          hash   patient_id, game_id, created_by, join_code, created_at, expires_at, [empty_since]
  coop:code:{CODE}        string -> room_id
  coop:room:{id}:seq      string server-authoritative sequence counter (INCR)
  coop:room:{id}:msgs     list   last BACKLOG_SIZE messages (JSON) for reconnect replay
  coop:room:{id}:members  set    live connection ids (used for "room is empty" across workers)
  channel coop:room:{id}  pub/sub fan-out

Sequence assignment, backlog append and PUBLISH happen atomically in one Lua script so every
subscriber sees messages in seq order even with several API workers. If scripting is disabled
(COOP_USE_LUA=0, e.g. a test Redis without Lua) a per-room asyncio.Lock gives the same guarantee
for a single process only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .protocol import generate_join_code

log = logging.getLogger("smaran.coop")

ROOM_TTL_SECONDS = 2 * 60 * 60
EMPTY_ROOM_SECONDS = 300  # module attribute on purpose: tests shorten it
KEY_GRACE_SECONDS = 600
BACKLOG_SIZE = int(os.getenv("COOP_BACKLOG_SIZE", "200"))

_LUA_PUBLISH = """
local seq = redis.call('INCR', KEYS[1])
local msg = '{"seq":' .. seq .. ',"type":' .. ARGV[1] .. ',"payload":' .. ARGV[2] ..
            ',"sender_role":' .. ARGV[3] .. ',"ts":' .. ARGV[4] .. '}'
redis.call('RPUSH', KEYS[2], msg)
redis.call('LTRIM', KEYS[2], -tonumber(ARGV[5]), -1)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[6]))
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[6]))
redis.call('PUBLISH', KEYS[3], msg)
return msg
"""

_locks: dict[str, asyncio.Lock] = {}


def k_room(room_id: str) -> str: return f"coop:room:{room_id}"
def k_code(code: str) -> str: return f"coop:code:{code}"
def k_seq(room_id: str) -> str: return f"coop:room:{room_id}:seq"
def k_msgs(room_id: str) -> str: return f"coop:room:{room_id}:msgs"
def k_members(room_id: str) -> str: return f"coop:room:{room_id}:members"
def channel(room_id: str) -> str: return f"coop:room:{room_id}"


def _use_lua() -> bool:
    return os.getenv("COOP_USE_LUA", "1") != "0"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RoomStore:
    def __init__(self, redis):
        self.r = redis
        self._script = None

    # ---- lifecycle ---------------------------------------------------------
    async def create_room(self, patient_id: str, game_id: str, created_by: str) -> dict[str, Any]:
        room_id = str(uuid.uuid4())
        created = _now()
        expires = created + timedelta(seconds=ROOM_TTL_SECONDS)
        ttl = ROOM_TTL_SECONDS + KEY_GRACE_SECONDS
        await self.r.hset(k_room(room_id), mapping={
            "patient_id": patient_id, "game_id": game_id, "created_by": created_by,
            "created_at": created.isoformat(), "expires_at": expires.isoformat(),
        })
        await self.r.expire(k_room(room_id), ttl)
        for _ in range(10):
            code = generate_join_code()
            if await self.r.set(k_code(code), room_id, nx=True, ex=ROOM_TTL_SECONDS):
                await self.r.hset(k_room(room_id), "join_code", code)
                return {"room_id": room_id, "join_code": code, "expires_at": expires}
        await self.r.delete(k_room(room_id))
        raise RuntimeError("could not allocate a unique join code")

    async def room_id_for_code(self, code: str) -> str | None:
        return await self.r.get(k_code(code))

    async def get_room(self, room_id: str) -> dict[str, str] | None:
        """Return room metadata, or None if it does not exist / expired / was empty too long."""
        meta = await self.r.hgetall(k_room(room_id))
        if not meta or "expires_at" not in meta:
            return None
        if _now() >= datetime.fromisoformat(meta["expires_at"]):
            await self.delete_room(room_id, meta)
            return None
        empty_since = meta.get("empty_since")
        if empty_since and await self.r.scard(k_members(room_id)) == 0:
            if time.time() - float(empty_since) >= EMPTY_ROOM_SECONDS - 0.05:
                await self.delete_room(room_id, meta)
                return None
        return meta

    async def delete_room(self, room_id: str, meta: dict | None = None) -> None:
        meta = meta or await self.r.hgetall(k_room(room_id))
        keys = [k_room(room_id), k_seq(room_id), k_msgs(room_id), k_members(room_id)]
        if meta.get("join_code"):
            keys.append(k_code(meta["join_code"]))
        await self.r.delete(*keys)
        _locks.pop(room_id, None)

    # ---- presence ----------------------------------------------------------
    async def add_member(self, room_id: str, conn_id: str) -> None:
        pipe = self.r.pipeline(transaction=True)
        pipe.sadd(k_members(room_id), conn_id)
        pipe.expire(k_members(room_id), ROOM_TTL_SECONDS + KEY_GRACE_SECONDS)
        pipe.hdel(k_room(room_id), "empty_since")
        await pipe.execute()

    async def remove_member(self, room_id: str, conn_id: str) -> int:
        await self.r.srem(k_members(room_id), conn_id)
        return int(await self.r.scard(k_members(room_id)))

    async def mark_empty(self, room_id: str) -> None:
        if await self.r.exists(k_room(room_id)):
            await self.r.hset(k_room(room_id), "empty_since", repr(time.time()))

    async def close_if_idle(self, room_id: str) -> bool:
        meta = await self.r.hgetall(k_room(room_id))
        if not meta or not meta.get("empty_since"):
            return False
        if await self.r.scard(k_members(room_id)) > 0:
            return False
        if time.time() - float(meta["empty_since"]) < EMPTY_ROOM_SECONDS - 0.05:
            return False
        await self.delete_room(room_id, meta)
        return True

    # ---- messages ----------------------------------------------------------
    async def publish(self, room_id: str, mtype: str, payload: dict, sender_role: str) -> dict[str, Any]:
        ts = _now().isoformat().replace("+00:00", "Z")
        ttl = ROOM_TTL_SECONDS + KEY_GRACE_SECONDS
        if _use_lua():
            if self._script is None:
                self._script = self.r.register_script(_LUA_PUBLISH)
            args = [json.dumps(mtype), json.dumps(payload, separators=(",", ":")),
                    json.dumps(sender_role), json.dumps(ts), BACKLOG_SIZE, ttl]
            raw = await self._script(keys=[k_seq(room_id), k_msgs(room_id), channel(room_id)], args=args)
            return json.loads(raw)
        lock = _locks.setdefault(room_id, asyncio.Lock())
        async with lock:
            seq = await self.r.incr(k_seq(room_id))
            msg = {"seq": int(seq), "type": mtype, "payload": payload, "sender_role": sender_role, "ts": ts}
            raw = json.dumps(msg, separators=(",", ":"))
            pipe = self.r.pipeline(transaction=True)
            pipe.rpush(k_msgs(room_id), raw)
            pipe.ltrim(k_msgs(room_id), -BACKLOG_SIZE, -1)
            pipe.expire(k_seq(room_id), ttl)
            pipe.expire(k_msgs(room_id), ttl)
            pipe.publish(channel(room_id), raw)
            await pipe.execute()
        return msg

    async def backlog_since(self, room_id: str, since: int) -> tuple[list[dict], bool]:
        """Messages with seq > since, in order. `truncated` = some requested messages already
        fell out of the backlog window (client should do a full state refresh)."""
        raw = await self.r.lrange(k_msgs(room_id), 0, -1)
        msgs = [m for m in (json.loads(x) for x in raw) if m["seq"] > since]
        truncated = bool(msgs) and msgs[0]["seq"] > since + 1
        return msgs, truncated
