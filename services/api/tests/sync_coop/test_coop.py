import asyncio
import time
import uuid

import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from tests.sync_coop.conftest import hdr

from app.core.config import settings
SECRET = settings.JWT_SECRET


def create_room(client, caregiver, patient, game_id="memory_match"):
    r = client.post("/api/v1/coop/rooms", json={"patient_id": str(patient.id), "game_id": game_id},
                    headers=hdr(caregiver))
    assert r.status_code == 201, r.text
    return r.json()


def join(client, user, code, role):
    return client.post("/api/v1/coop/rooms/join", json={"join_code": code, "role": role}, headers=hdr(user))


def ws_url(room_id, token, last_seq=None):
    url = f"/api/v1/ws/coop/{room_id}?token={token}"
    return url + (f"&last_seq={last_seq}" if last_seq is not None else "")


@pytest.fixture()
def room(client, world):
    info = create_room(client, world["caregiver_a"], world["patient_a"])
    fam = join(client, world["caregiver_a"], info["join_code"], "family").json()
    pat = join(client, world["patient_a"], info["join_code"], "patient").json()
    return {"room_id": info["room_id"], "family_token": fam["ws_token"], "patient_token": pat["ws_token"], **info}


def recv_until(ws, predicate, limit=50):
    frames = []
    for _ in range(limit):
        f = ws.receive_json()
        frames.append(f)
        if predicate(f):
            return frames
    raise AssertionError(f"predicate never matched; got {frames}")


# ------------------------------------------------------------- join code flow
def test_create_room_and_join_flow(client, world):
    from datetime import datetime, timezone

    info = create_room(client, world["caregiver_a"], world["patient_a"])
    assert len(info["join_code"]) == 6 and not set(info["join_code"]) & set("ILO01")
    exp = datetime.fromisoformat(info["expires_at"].replace("Z", "+00:00"))
    secs = (exp - datetime.now(timezone.utc)).total_seconds()
    assert 2 * 3600 - 60 < secs <= 2 * 3600 + 1

    r = join(client, world["caregiver_a"], info["join_code"].lower(), "family")  # case-insensitive
    assert r.status_code == 200 and r.json()["room_id"] == info["room_id"]
    claims = jwt.decode(r.json()["ws_token"], SECRET, algorithms=["HS256"])
    assert claims["room_id"] == info["room_id"] and claims["role"] == "family"
    assert 0 < claims["exp"] - time.time() <= 300

    p = join(client, world["patient_a"], info["join_code"], "patient")
    assert p.status_code == 200 and jwt.decode(p.json()["ws_token"], SECRET, algorithms=["HS256"])["role"] == "patient"


def test_create_room_requires_access_to_patient(client, world):
    r = client.post("/api/v1/coop/rooms", json={"patient_id": str(world["patient_a"].id), "game_id": "g"},
                    headers=hdr(world["caregiver_x"]))
    assert r.status_code == 403
    assert client.post("/api/v1/coop/rooms", json={"patient_id": str(world["patient_a"].id), "game_id": "g"}).status_code == 401


def test_join_rejections(client, world):
    info = create_room(client, world["caregiver_a"], world["patient_a"])
    assert join(client, world["caregiver_a"], "ZZZZZZ", "family").status_code == 404      # unknown code
    assert join(client, world["caregiver_a"], "AB0IL1", "family").status_code == 404      # invalid shape
    assert join(client, world["caregiver_x"], info["join_code"], "family").status_code == 403  # no access to patient
    assert join(client, world["patient_b"], info["join_code"], "patient").status_code == 403   # other patient
    assert join(client, world["caregiver_a"], info["join_code"], "patient").status_code == 403  # role spoofing
    assert join(client, world["patient_a"], info["join_code"], "family").status_code == 403
    assert client.post("/api/v1/coop/rooms/join", json={"join_code": info["join_code"], "role": "wizard"},
                       headers=hdr(world["caregiver_a"])).status_code == 422


def test_join_codes_are_unique_across_rooms(client, world):
    codes = {create_room(client, world["caregiver_a"], world["patient_a"])["join_code"] for _ in range(20)}
    assert len(codes) == 20


# ------------------------------------------------------------- bad tokens
def _expect_rejected(client, room_id, token):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ws_url(room_id, token)):
            pass


def test_ws_rejects_bad_tokens(client, world, room):
    rid = room["room_id"]
    _expect_rejected(client, rid, "")
    _expect_rejected(client, rid, "garbage")
    now = int(time.time())
    good = {"typ": "coop_ws", "sub": "u", "room_id": rid, "role": "family", "exp": now + 60}
    _expect_rejected(client, rid, jwt.encode({**good, "exp": now - 10}, SECRET, algorithm="HS256"))          # expired
    _expect_rejected(client, rid, jwt.encode(good, "wrong-secret-wrong-secret-wrong-secret", algorithm="HS256"))  # bad signature
    _expect_rejected(client, rid, jwt.encode({**good, "room_id": str(uuid.uuid4())}, SECRET, algorithm="HS256"))  # other room
    _expect_rejected(client, rid, jwt.encode({**good, "typ": "access"}, SECRET, algorithm="HS256"))          # API token reuse
    _expect_rejected(client, rid, jwt.encode({**good, "role": "admin"}, SECRET, algorithm="HS256"))          # unknown role


def test_ws_rejects_token_for_nonexistent_room(client):
    rid = str(uuid.uuid4())
    token = jwt.encode({"typ": "coop_ws", "sub": "u", "room_id": rid, "role": "family",
                        "exp": int(time.time()) + 60}, SECRET, algorithm="HS256")
    _expect_rejected(client, rid, token)


# ------------------------------------------------------------- ordering
def test_two_clients_see_the_same_server_assigned_order(client, room):
    rid = room["room_id"]
    with client.websocket_connect(ws_url(rid, room["family_token"])) as fam, \
         client.websocket_connect(ws_url(rid, room["patient_token"])) as pat:
        for i in range(3):  # interleaved senders; client-supplied seq must be ignored
            fam.send_json({"type": "state_patch", "seq": 999, "payload": {"from": "family", "n": i}})
            pat.send_json({"type": "state_patch", "seq": 0, "payload": {"from": "patient", "n": i}})
        # frames: join(family)=1, join(patient)=2, then 6 patches => 8 per client
        fam_frames = [fam.receive_json() for _ in range(8)]
        pat_frames = [pat.receive_json() for _ in range(8)]

    assert [f["seq"] for f in fam_frames] == list(range(1, 9))
    assert [f["seq"] for f in pat_frames] == list(range(1, 9))
    assert fam_frames == pat_frames  # identical order and content for both clients
    assert [f["type"] for f in fam_frames[:2]] == ["join", "join"]
    # each sender's own messages keep their relative order
    for who in ("family", "patient"):
        ns = [f["payload"]["n"] for f in fam_frames if f["type"] == "state_patch" and f["payload"]["from"] == who]
        assert ns == [0, 1, 2]
    assert {f["sender_role"] for f in fam_frames} == {"family", "patient"}


def test_invalid_client_messages_get_error_frames_and_dont_consume_seq(client, room):
    with client.websocket_connect(ws_url(room["room_id"], room["family_token"])) as ws:
        assert ws.receive_json()["type"] == "join"
        ws.send_text("not json")
        assert ws.receive_json()["payload"]["code"] == "invalid_json"
        ws.send_json({"type": "join", "payload": {}})  # clients may not forge join/leave
        assert ws.receive_json()["payload"]["code"] == "unsupported_type"
        ws.send_json({"type": "hint", "payload": {"cell": 4}})
        f = ws.receive_json()
        assert f["type"] == "hint" and f["seq"] == 2 and f["payload"] == {"cell": 4}


# ------------------------------------------------------------- reconnect replay
def test_reconnect_replays_missed_messages_in_order(client, room):
    rid = room["room_id"]
    with client.websocket_connect(ws_url(rid, room["family_token"])) as fam:
        with client.websocket_connect(ws_url(rid, room["patient_token"])) as pat:
            frames = [pat.receive_json(), pat.receive_json()]          # seq 1 join(fam), seq 2 join(pat)
            assert [f["seq"] for f in frames] == [1, 2]
            last_seen = frames[-1]["seq"]
        # patient dropped; family keeps playing
        recv_until(fam, lambda f: f["type"] == "leave")                 # seq 3 (also syncs the test)
        fam.send_json({"type": "state_patch", "payload": {"step": 1}})
        fam.send_json({"type": "encourage", "payload": {"text": "well done"}})
        recv_until(fam, lambda f: f["type"] == "encourage")             # seq 4, 5 persisted

        with client.websocket_connect(ws_url(rid, room["patient_token"], last_seq=last_seen)) as pat2:
            replay = [pat2.receive_json() for _ in range(4)]            # 3 leave, 4, 5, 6 own join
        assert [f["seq"] for f in replay] == [3, 4, 5, 6]
        assert [f["type"] for f in replay] == ["leave", "state_patch", "encourage", "join"]
        assert replay[1]["payload"] == {"step": 1}


def test_reconnect_with_current_seq_gets_no_duplicates(client, room):
    rid = room["room_id"]
    with client.websocket_connect(ws_url(rid, room["family_token"])) as fam:
        fam.receive_json()  # seq 1
        fam.send_json({"type": "hint", "payload": {}})
        assert fam.receive_json()["seq"] == 2
    with client.websocket_connect(ws_url(rid, room["family_token"], last_seq=2)) as fam2:
        f = fam2.receive_json()
        assert f["seq"] > 2  # only new frames (leave + own join), nothing at or below last_seq


def test_backlog_is_bounded_and_truncation_is_signalled(client, room, monkeypatch):
    from app.modules.coop import store

    monkeypatch.setattr(store, "BACKLOG_SIZE", 3)
    rid = room["room_id"]
    with client.websocket_connect(ws_url(rid, room["family_token"])) as fam:
        fam.receive_json()
        for i in range(6):
            fam.send_json({"type": "state_patch", "payload": {"i": i}})
        recv_until(fam, lambda f: f["type"] == "state_patch" and f["payload"]["i"] == 5)
        with client.websocket_connect(ws_url(rid, room["patient_token"], last_seq=0)) as pat:
            first = pat.receive_json()
            assert first["type"] == "resync" and first["payload"]["reason"] == "backlog_truncated"
            nxt = pat.receive_json()
            assert nxt["seq"] == first["payload"]["oldest_available_seq"]


# ------------------------------------------------------------- empty room closing
def test_empty_room_is_closed_after_timeout(client, world, room, monkeypatch):
    from app.modules.coop import store

    monkeypatch.setattr(store, "EMPTY_ROOM_SECONDS", 0.3)
    with client.websocket_connect(ws_url(room["room_id"], room["family_token"])) as fam:
        fam.receive_json()
    time.sleep(0.8)  # the portal's event loop keeps running; the idle timer fires there
    assert join(client, world["caregiver_a"], room["join_code"], "family").status_code == 404
    _expect_rejected(client, room["room_id"], room["family_token"])


def test_room_with_a_connected_client_is_not_closed(client, world, room, monkeypatch):
    from app.modules.coop import store

    monkeypatch.setattr(store, "EMPTY_ROOM_SECONDS", 0.3)
    with client.websocket_connect(ws_url(room["room_id"], room["family_token"])) as fam:
        fam.receive_json()
        with client.websocket_connect(ws_url(room["room_id"], room["patient_token"])) as pat:
            pat.receive_json()
        time.sleep(0.8)  # patient left, family still present -> room must survive
        assert join(client, world["caregiver_a"], room["join_code"], "family").status_code == 200


def test_rejoining_before_timeout_keeps_room_alive(client, world, room, monkeypatch):
    from app.modules.coop import store

    monkeypatch.setattr(store, "EMPTY_ROOM_SECONDS", 0.6)
    with client.websocket_connect(ws_url(room["room_id"], room["family_token"])) as fam:
        fam.receive_json()
    with client.websocket_connect(ws_url(room["room_id"], room["family_token"])) as fam2:
        fam2.receive_json()
        time.sleep(1.0)  # original idle timer fires while someone is connected: must be a no-op
        assert join(client, world["caregiver_a"], room["join_code"], "family").status_code == 200
