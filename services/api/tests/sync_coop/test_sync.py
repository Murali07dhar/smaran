import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from tests.sync_coop.conftest import hdr

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)


def iso(dt=NOW):
    return dt.isoformat().replace("+00:00", "Z")


def op(entity, entity_id, payload, action="upsert", op_id=None, ts=NOW):
    return {"op_id": str(op_id or uuid.uuid4()), "entity": entity, "entity_id": str(entity_id),
            "action": action, "payload": payload, "client_ts": iso(ts)}


def session_payload(patient, score=10.0):
    return {"patient_id": str(patient.id), "game_id": "memory_match", "domain": "memory",
            "started_at": iso(), "difficulty": 3, "score": score}


def event_payload(patient, session_id, **kw):
    p = {"session_id": str(session_id), "patient_id": str(patient.id), "type": "answer",
         "item_id": "photo-1", "correct": True, "response_ms": 900, "with_cue": True, "ts": iso()}
    p.update(kw)
    return p


def reminder_payload(patient, version=None, title="Take tablet"):
    p = {"patient_id": str(patient.id), "category": "medicine", "title": title,
         "schedule_rrule": "FREQ=DAILY;BYHOUR=9", "locale": "as", "escalate_after_misses": 2}
    if version is not None:
        p["server_version"] = version
    return p


def push(client, user, ops, device="dev-1"):
    return client.post("/api/v1/sync/push", json={"device_id": device, "ops": ops}, headers=hdr(user))


def count(SessionFactory, model):
    with SessionFactory() as s:
        return s.scalar(select(func.count()).select_from(model))


# ---------------------------------------------------------------- changelog
def test_record_change_signature_and_json_safety(SessionFactory, world):
    from app.models import SyncChange
    from app.modules.sync.changelog import record_change

    rid = uuid.uuid4()
    with SessionFactory() as s:
        record_change(s, "reminders", rid, "upsert",
                      {"id": rid, "at": NOW, "n": 1}, world["patient_a"].id)
        s.commit()
    with SessionFactory() as s:
        row = s.scalar(select(SyncChange))
        assert row.entity == "reminders" and row.entity_id == rid and row.action == "upsert"
        assert row.payload == {"id": str(rid), "at": "2026-10-01T10:00:00Z", "n": 1}
        assert row.cursor >= 1

    with SessionFactory() as s, pytest.raises(ValueError):
        record_change(s, "reminders", rid, "explode", {}, world["patient_a"].id)


# ---------------------------------------------------------------- push: idempotency
def test_replay_is_idempotent(client, SessionFactory, world, pipeline_calls):
    from app.models import GameSession, SyncOp

    sid = uuid.uuid4()
    body = [op("game_sessions", sid, session_payload(world["patient_a"]))]
    r1 = push(client, world["patient_a"], body)
    assert r1.status_code == 200 and r1.json()["accepted"] == [body[0]["op_id"]]
    r2 = push(client, world["patient_a"], body)  # exact replay
    assert r2.json()["accepted"] == [body[0]["op_id"]] and r2.json()["rejected"] == []
    assert count(SessionFactory, GameSession) == 1
    assert count(SessionFactory, SyncOp) == 1
    assert len(pipeline_calls) == 1  # replay does not re-trigger the pipeline


def test_duplicate_op_id_inside_one_batch(client, SessionFactory, world):
    from app.models import GameSession

    o = op("game_sessions", uuid.uuid4(), session_payload(world["patient_a"]))
    r = push(client, world["patient_a"], [o, o])
    assert r.json()["accepted"] == [o["op_id"]]
    assert count(SessionFactory, GameSession) == 1


# ---------------------------------------------------------------- push: append-only
def test_append_only_is_insert_or_ignore(client, SessionFactory, world):
    from app.models import GameSession

    sid = uuid.uuid4()
    push(client, world["patient_a"], [op("game_sessions", sid, session_payload(world["patient_a"], 10.0))])
    r = push(client, world["patient_a"], [op("game_sessions", sid, session_payload(world["patient_a"], 99.0))])
    assert len(r.json()["accepted"]) == 1  # new op_id, same row: accepted but ignored
    with SessionFactory() as s:
        assert s.get(GameSession, sid).score == 10.0


def test_append_only_rejects_delete(client, world):
    sid = uuid.uuid4()
    push(client, world["patient_a"], [op("game_sessions", sid, session_payload(world["patient_a"]))])
    o = op("game_sessions", sid, {}, action="delete")
    r = push(client, world["patient_a"], [o]).json()
    assert r["accepted"] == [] and r["rejected"] == [{"op_id": o["op_id"], "reason": "append_only_no_delete"}]


def test_events_before_their_session_in_same_batch_are_accepted(client, SessionFactory, world):
    from app.models import GameEvent

    sid = uuid.uuid4()
    ev = op("game_events", uuid.uuid4(), event_payload(world["patient_a"], sid))
    ss = op("game_sessions", sid, session_payload(world["patient_a"]))
    r = push(client, world["patient_a"], [ev, ss]).json()  # child queued first
    assert sorted(r["accepted"]) == sorted([ev["op_id"], ss["op_id"]]) and r["rejected"] == []
    assert count(SessionFactory, GameEvent) == 1


def test_event_for_unknown_session_rejected(client, world):
    o = op("game_events", uuid.uuid4(), event_payload(world["patient_a"], uuid.uuid4()))
    r = push(client, world["patient_a"], [o]).json()
    assert r["rejected"][0]["reason"] == "unknown_session"


# ---------------------------------------------------------------- push: partial rejection + RBAC
def test_partial_rejection(client, SessionFactory, world):
    from app.models import GameSession

    good = op("game_sessions", uuid.uuid4(), session_payload(world["patient_a"]))
    unknown = op("telepathy", uuid.uuid4(), {})
    not_pushable = op("alerts", uuid.uuid4(), {})
    forbidden = op("game_sessions", uuid.uuid4(), session_payload(world["patient_b"]))
    invalid = op("game_sessions", uuid.uuid4(), {**session_payload(world["patient_a"]), "difficulty": 99})
    bad_action = op("reminders", uuid.uuid4(), reminder_payload(world["patient_a"]), action="merge")

    r = push(client, world["caregiver_a"], [good, unknown, not_pushable, forbidden, invalid, bad_action]).json()
    assert r["accepted"] == [good["op_id"]]
    reasons = {x["op_id"]: x["reason"] for x in r["rejected"]}
    assert reasons[unknown["op_id"]] == "unknown_entity"
    assert reasons[not_pushable["op_id"]] == "entity_not_pushable"
    assert reasons[forbidden["op_id"]] == "forbidden_patient"
    assert reasons[invalid["op_id"]].startswith("invalid_payload:difficulty")
    assert reasons[bad_action["op_id"]] == "invalid_action"
    assert count(SessionFactory, GameSession) == 1  # only the good op persisted


def test_rejected_ops_are_not_recorded_so_they_can_be_retried(client, SessionFactory, world):
    from app.models import SyncOp

    o = op("game_sessions", uuid.uuid4(), session_payload(world["patient_b"]))
    assert push(client, world["caregiver_x"], [o]).json()["rejected"]
    assert count(SessionFactory, SyncOp) == 0
    assert push(client, world["admin"], [o]).json()["accepted"] == [o["op_id"]]  # now permitted


def test_patient_cannot_push_for_another_patient(client, world):
    o = op("game_sessions", uuid.uuid4(), session_payload(world["patient_b"]))
    r = push(client, world["patient_a"], [o]).json()
    assert r["rejected"][0]["reason"] == "forbidden_patient"


def test_unauthenticated_push_is_401(client):
    assert client.post("/api/v1/sync/push", json={"device_id": "d", "ops": []}).status_code == 401


# ---------------------------------------------------------------- push: last-write-wins
def test_lww_versions_and_changelog(client, SessionFactory, world):
    from app.models import Reminder, SyncChange

    rid = uuid.uuid4()
    p = world["patient_a"]
    assert push(client, world["caregiver_a"], [op("reminders", rid, reminder_payload(p, title="v1"))]).json()["accepted"]
    newer = op("reminders", rid, reminder_payload(p, version=2, title="v2"))
    assert push(client, world["caregiver_a"], [newer]).json()["accepted"] == [newer["op_id"]]
    stale = op("reminders", rid, reminder_payload(p, version=1, title="old"))
    r = push(client, world["caregiver_a"], [stale]).json()
    assert r["rejected"] == [{"op_id": stale["op_id"], "reason": "stale_version"}]
    missing_version = op("reminders", rid, reminder_payload(p, title="no version"))
    assert push(client, world["caregiver_a"], [missing_version]).json()["rejected"][0]["reason"] == \
        "invalid_payload:server_version"

    with SessionFactory() as s:
        row = s.get(Reminder, rid)
        assert row.title == "v2" and row.server_version == 2
        changes = list(s.scalars(select(SyncChange).where(SyncChange.entity == "reminders").order_by(SyncChange.cursor)))
        assert [c.payload["title"] for c in changes] == ["v1", "v2"]


def test_lww_cannot_move_a_record_to_another_patient(client, world):
    rid = uuid.uuid4()
    push(client, world["admin"], [op("reminders", rid, reminder_payload(world["patient_a"]))])
    o = op("reminders", rid, reminder_payload(world["patient_b"], version=5))
    assert push(client, world["admin"], [o]).json()["rejected"][0]["reason"] == "patient_mismatch"


def test_delete_reminder_records_delete_change(client, SessionFactory, world):
    from app.models import Reminder, SyncChange

    rid = uuid.uuid4()
    push(client, world["caregiver_a"], [op("reminders", rid, reminder_payload(world["patient_a"]))])
    d = op("reminders", rid, {}, action="delete")
    assert push(client, world["caregiver_a"], [d]).json()["accepted"] == [d["op_id"]]
    with SessionFactory() as s:
        assert s.get(Reminder, rid) is None
        last = s.scalar(select(SyncChange).order_by(SyncChange.cursor.desc()))
        assert last.action == "delete" and last.entity_id == rid


def test_delete_reminder_with_history_deactivates_instead(client, SessionFactory, world):
    from app.models import Reminder

    rid, p = uuid.uuid4(), world["patient_a"]
    push(client, p, [op("reminders", rid, reminder_payload(p))])
    ev = op("reminder_events", uuid.uuid4(), {"reminder_id": str(rid), "patient_id": str(p.id),
                                              "due_at": iso(), "status": "done", "ts": iso()})
    assert push(client, p, [ev]).json()["accepted"]
    assert push(client, p, [op("reminders", rid, {}, action="delete")]).json()["rejected"] == []
    with SessionFactory() as s:
        row = s.get(Reminder, rid)
        assert row is not None and row.active is False


def test_equal_version_tie_resolved_by_client_ts(client, SessionFactory, world):
    from app.models import Reminder

    rid, p = uuid.uuid4(), world["patient_a"]
    push(client, p, [op("reminders", rid, reminder_payload(p, title="first"))])  # version 1
    later = op("reminders", rid, reminder_payload(p, version=1, title="later"), ts=datetime.now(timezone.utc) + timedelta(minutes=1))
    assert push(client, p, [later]).json()["accepted"] == [later["op_id"]]
    with SessionFactory() as s:
        row = s.get(Reminder, rid)
        assert row.title == "later" and row.server_version == 2


# ---------------------------------------------------------------- pipeline
def test_pipeline_receives_new_session_ids(client, world, pipeline_calls):
    sid = uuid.uuid4()
    p = world["patient_a"]
    push(client, p, [op("game_sessions", sid, session_payload(p)),
                     op("game_events", uuid.uuid4(), event_payload(p, sid))])
    assert pipeline_calls == [(p.id, [sid])]


def test_pipeline_failure_does_not_break_push(client, SessionFactory, world, monkeypatch):
    from app.models import GameSession
    from app.modules.insights import pipeline

    def boom(*_a, **_k):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(pipeline, "process_synced_data", boom)
    o = op("game_sessions", uuid.uuid4(), session_payload(world["patient_a"]))
    r = push(client, world["patient_a"], [o])
    assert r.status_code == 200 and r.json()["accepted"] == [o["op_id"]]
    assert count(SessionFactory, GameSession) == 1


def test_missing_pipeline_module_is_a_noop(client, SessionFactory, world, monkeypatch):
    import sys

    from app.models import GameSession

    monkeypatch.setitem(sys.modules, "app.modules.insights.pipeline", None)  # makes the import raise
    o = op("game_sessions", uuid.uuid4(), session_payload(world["patient_a"]))
    assert push(client, world["patient_a"], [o]).json()["accepted"] == [o["op_id"]]
    assert count(SessionFactory, GameSession) == 1


# ---------------------------------------------------------------- pull
def seed_changes(SessionFactory, patient, n, entity="reminders"):
    from app.modules.sync.changelog import record_change

    ids = []
    with SessionFactory() as s:
        for i in range(n):
            eid = uuid.uuid4()
            ids.append(eid)
            record_change(s, entity, eid, "upsert", {"id": eid, "title": f"r{i}"}, patient.id)
        s.commit()
    return ids


def pull(client, user, since=0, limit=200):
    return client.get(f"/api/v1/sync/pull?since={since}&limit={limit}", headers=hdr(user))


def test_pull_cursor_paging(client, SessionFactory, world):
    ids = seed_changes(SessionFactory, world["patient_a"], 5)
    got, since = [], 0
    for _ in range(10):
        body = pull(client, world["caregiver_a"], since, limit=2).json()
        if not body["changes"]:
            break
        assert len(body["changes"]) <= 2
        assert body["server_cursor"] == body["changes"][-1]["cursor"]
        got += [uuid.UUID(c["entity_id"]) for c in body["changes"]]
        since = body["server_cursor"]
    assert got == ids  # complete, ordered, no duplicates
    end = pull(client, world["caregiver_a"], since).json()
    assert end == {"changes": [], "server_cursor": since}


def test_pull_rbac(client, SessionFactory, world):
    a_ids = seed_changes(SessionFactory, world["patient_a"], 2)
    b_ids = seed_changes(SessionFactory, world["patient_b"], 3)

    def seen(user):
        return {uuid.UUID(c["entity_id"]) for c in pull(client, user).json()["changes"]}

    assert seen(world["caregiver_a"]) == set(a_ids)
    assert seen(world["patient_a"]) == set(a_ids)
    assert seen(world["patient_b"]) == set(b_ids)
    assert seen(world["caregiver_x"]) == set()
    assert seen(world["admin"]) == set(a_ids) | set(b_ids)
    assert client.get("/api/v1/sync/pull").status_code == 401


def test_pull_only_serves_sync_entities_and_hides_media_secrets(client, SessionFactory, world):
    from app.modules.sync.changelog import record_change

    p = world["patient_a"]
    mid = uuid.uuid4()
    with SessionFactory() as s:
        record_change(s, "media_assets", mid, "upsert",
                      {"id": mid, "kind": "photo", "mime": "image/jpeg", "enc_path": "/secret", "nonce": "abc"}, p.id)
        record_change(s, "game_sessions", uuid.uuid4(), "upsert", {"x": 1}, p.id)  # not a pulled entity
        s.commit()
    changes = pull(client, world["caregiver_a"]).json()["changes"]
    assert [c["entity"] for c in changes] == ["media_assets"]
    assert "enc_path" not in changes[0]["payload"] and "nonce" not in changes[0]["payload"]
    assert changes[0]["payload"]["mime"] == "image/jpeg"


def test_pull_limit_is_bounded(client, world):
    assert pull(client, world["admin"], limit=0).status_code == 422
    assert pull(client, world["admin"], limit=501).status_code == 422


def test_push_then_pull_roundtrip(client, world):
    rid, p = uuid.uuid4(), world["patient_a"]
    push(client, world["caregiver_a"], [op("reminders", rid, reminder_payload(p))])
    body = pull(client, p).json()  # the patient's device receives the caregiver's reminder
    assert [c["entity_id"] for c in body["changes"]] == [str(rid)]
    assert body["changes"][0]["payload"]["title"] == "Take tablet"


def test_reminder_payload_never_leaks_db_column_name(world, SessionFactory):
    import uuid
    from sqlalchemy import select
    from app.models import SyncChange
    from app.modules.sync.changelog import record_change

    rid = uuid.uuid4()
    with SessionFactory() as s:
        record_change(s, "reminders", rid, "upsert", {"id": str(rid), "schedule_rrule": "FREQ=DAILY"}, world["patient_a"].id)
        s.commit()
        row = s.scalars(select(SyncChange).where(SyncChange.entity_id == rid)).one()
        assert row.payload["schedule"] == "FREQ=DAILY" and "schedule_rrule" not in row.payload
