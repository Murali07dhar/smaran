"""Co-op rooms (REST) and relay (WebSocket).

REST  (mounted under /api/v1):  POST /coop/rooms ; POST /coop/rooms/join
WS:   /ws/coop/{room_id}?token=<ws_token>&last_seq=<n>
      `router` carries it at /api/v1/ws/coop/{room_id}; `ws_router` carries it at /ws/coop/{room_id}
      (the path written in the briefing). Include whichever the Integrator publishes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.config import settings
from app.core.db import get_session
from app.core.security import assert_can_access_patient, get_current_user

from . import store as store_mod
from .deps import get_redis
from .protocol import ProtocolError, normalize_join_code, validate_client_message
from .store import RoomStore, channel
from .tokens import CLOSE_NO_ROOM, CLOSE_ROOM_EXPIRED, TokenError, mint_ws_token, verify_ws_token

log = logging.getLogger("smaran.coop")

router = APIRouter(tags=["coop"])
ws_router = APIRouter(tags=["coop"])

_idle_tasks: set[asyncio.Task] = set()  # strong refs so pending close timers aren't garbage collected


# ---- REST ------------------------------------------------------------------
class RoomCreate(BaseModel):
    patient_id: UUID
    game_id: str = Field(min_length=1, max_length=128)


class RoomCreated(BaseModel):
    room_id: str
    join_code: str
    expires_at: datetime


class JoinRequest(BaseModel):
    join_code: str = Field(min_length=1, max_length=32)
    role: Literal["patient", "family"]


class JoinResponse(BaseModel):
    room_id: str
    ws_token: str


@router.post("/coop/rooms", response_model=RoomCreated, status_code=201)
async def create_room(
    body: RoomCreate,
    session=Depends(get_session),
    user=Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    await run_in_threadpool(assert_can_access_patient, session, user, body.patient_id)
    try:
        room = await RoomStore(redis).create_room(str(body.patient_id), body.game_id, str(user.id))
    except RuntimeError:
        raise HTTPException(status_code=503, detail="could not allocate join code, retry")
    return RoomCreated(**room)


@router.post("/coop/rooms/join", response_model=JoinResponse)
async def join_room(
    body: JoinRequest,
    session=Depends(get_session),
    user=Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    store = RoomStore(redis)
    code = normalize_join_code(body.join_code)
    room_id = await store.room_id_for_code(code) if code else None
    room = await store.get_room(room_id) if room_id else None
    if room is None:
        raise HTTPException(status_code=404, detail="room not found or expired")

    patient_id = room["patient_id"]
    await run_in_threadpool(assert_can_access_patient, session, user, UUID(patient_id))
    # A caller may only claim the role their account actually has.
    if body.role == "patient" and user.role not in ("patient", "admin"):
        raise HTTPException(status_code=403, detail="role 'patient' requires a patient account")
    if body.role == "family" and user.role == "patient":
        raise HTTPException(status_code=403, detail="role 'family' requires a caregiver account")

    token = mint_ws_token(
        settings.JWT_SECRET, room_id=room_id, role=body.role, user_id=str(user.id), patient_id=patient_id
    )
    return JoinResponse(room_id=room_id, ws_token=token)


# ---- WebSocket -------------------------------------------------------------
async def _close_when_idle(store: RoomStore, room_id: str) -> None:
    await asyncio.sleep(store_mod.EMPTY_ROOM_SECONDS)
    try:
        if await store.close_if_idle(room_id):
            log.info("closed idle co-op room %s", room_id)
    except Exception:  # noqa: BLE001
        log.exception("idle close failed for room %s", room_id)


async def _close_at_expiry(websocket: WebSocket, expires_at: datetime) -> None:
    delay = (expires_at - datetime.now(timezone.utc)).total_seconds()
    await asyncio.sleep(max(0.0, delay))
    await websocket.close(code=CLOSE_ROOM_EXPIRED)


async def coop_ws(
    websocket: WebSocket,
    room_id: str,
    token: str = Query(default=""),
    last_seq: int = Query(default=0, ge=0),
    redis: Redis = Depends(get_redis),
):
    # 1) authenticate BEFORE accepting the upgrade
    try:
        claims = verify_ws_token(settings.JWT_SECRET, token, room_id)
    except TokenError as exc:
        await websocket.close(code=exc.close_code)
        return
    role = claims["role"]

    store = RoomStore(redis)
    room = await store.get_room(room_id)
    if room is None:
        await websocket.close(code=CLOSE_NO_ROOM)
        return
    await websocket.accept()

    conn_id = uuid.uuid4().hex
    send_lock = asyncio.Lock()
    state = {"last_sent": last_seq}

    async def send(obj: dict) -> None:
        async with send_lock:
            await websocket.send_text(json.dumps(obj, separators=(",", ":")))

    async def deliver(msg: dict) -> None:
        if msg["seq"] <= state["last_sent"]:  # de-dupe between replay and live stream
            return
        state["last_sent"] = msg["seq"]
        await send(msg)

    async def catch_up() -> None:
        msgs, truncated = await store.backlog_since(room_id, state["last_sent"])
        if truncated:
            await send({"type": "resync", "seq": 0,
                        "payload": {"reason": "backlog_truncated", "oldest_available_seq": msgs[0]["seq"]}})
        for m in msgs:
            await deliver(m)

    pubsub = redis.pubsub()
    tasks: list[asyncio.Task] = []
    member_added = False
    try:
        await pubsub.subscribe(channel(room_id))  # subscribe first so nothing is missed during replay
        await store.add_member(room_id, conn_id)
        member_added = True
        await store.publish(room_id, "join", {"role": role}, role)
        await catch_up()  # replays everything after last_seq, including our own join

        async def forward() -> None:
            try:
                while True:
                    item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if item is None:
                        continue
                    msg = json.loads(item["data"])
                    if msg["seq"] <= state["last_sent"]:
                        continue
                    if msg["seq"] > state["last_sent"] + 1:  # gap: refill in order from the backlog
                        await catch_up()
                    await deliver(msg)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.debug("forwarder for %s stopped", conn_id, exc_info=True)

        expires_at = datetime.fromisoformat(room["expires_at"])
        tasks.append(asyncio.create_task(forward()))
        tasks.append(asyncio.create_task(_close_at_expiry(websocket, expires_at)))

        while True:
            event = await websocket.receive()
            if event["type"] == "websocket.disconnect":
                break
            raw = event.get("text") if event.get("text") is not None else event.get("bytes")
            if raw is None:
                continue
            try:
                mtype, payload = validate_client_message(raw)
            except ProtocolError as exc:
                await send({"type": "error", "seq": 0, "payload": {"code": exc.code, "message": exc.message}})
                continue
            await store.publish(room_id, mtype, payload, role)
    except RuntimeError:
        pass  # receive() after the socket was closed (e.g. room expiry)
    finally:
        for t in tasks:
            t.cancel()

        async def _cleanup() -> None:
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                if member_added:
                    remaining = await store.remove_member(room_id, conn_id)
                    await store.publish(room_id, "leave", {"role": role}, role)
                    if remaining == 0:
                        await store.mark_empty(room_id)
                        task = asyncio.create_task(_close_when_idle(store, room_id))
                        _idle_tasks.add(task)
                        task.add_done_callback(_idle_tasks.discard)
                await pubsub.unsubscribe(channel(room_id))
                closer = getattr(pubsub, "aclose", None) or pubsub.close
                await closer()
            except Exception:  # noqa: BLE001
                log.exception("co-op cleanup failed for room %s", room_id)

        # Shielded: a cancelled handler (server shutdown, test client teardown) must still publish `leave`
        # and arm the idle-close timer, otherwise an emptied room would never be closed.
        cleanup_task = asyncio.ensure_future(_cleanup())
        _idle_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(_idle_tasks.discard)
        await asyncio.shield(cleanup_task)


router.add_api_websocket_route("/ws/coop/{room_id}", coop_ws)
ws_router.add_api_websocket_route("/ws/coop/{room_id}", coop_ws)
