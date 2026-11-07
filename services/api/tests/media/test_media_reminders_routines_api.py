"""API tests for reminders + routines CRUD (need fastapi, sqlalchemy, httpx)."""
import uuid

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from app.modules.sync import changelog

REMINDER = {
    "category": "medicine",
    "title": "Blood pressure tablet",
    "schedule": "FREQ=DAILY;BYHOUR=8;BYMINUTE=0",
    "locale": "as",
    "escalate_after_misses": 2,
}
ROUTINE = {"title": "Morning", "steps": ["Wake up", {"title": "Brush teeth", "order": 2}]}


def base(world, kind):
    return f"/api/v1/patients/{world['patient'].id}/{kind}"


def other_patient(world):
    from app.models import CaregiverLink, User
    p = User(id=uuid.uuid4(), role="patient", name="P2", language="en")
    with world["Session"]() as s:
        s.add(p)
        s.flush()
        # real RBAC: access needs a caregiver_links row; link the health worker so the 404 (not 403) path is exercised
        s.add(CaregiverLink(id=uuid.uuid4(), caregiver_id=world["hw"].id, patient_id=p.id, relation="chw"))
        s.commit()
    return p


# =========================================================== reminders

def test_reminder_crud_bumps_server_version_and_records_every_change(client_for, world):
    c = client_for(world["cg"])
    r = c.post(base(world, "reminders"), json=REMINDER)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["server_version"] == 1
    assert item["schedule"] == REMINDER["schedule"]          # REMINDER contract field name
    assert item["patient_id"] == str(world["patient"].id) and item["active"] is True
    assert item["voice_clip_id"] is None and item["escalate_after_misses"] == 2

    url = f"{base(world, 'reminders')}/{item['id']}"
    v2 = c.put(url, json={**REMINDER, "title": "BP tablet (after breakfast)"}).json()
    v3 = c.put(url, json={**REMINDER, "active": False}).json()
    assert (v2["server_version"], v3["server_version"]) == (2, 3)
    assert v3["active"] is False and v3["updated_at"] >= v2["updated_at"]

    listed = c.get(base(world, "reminders")).json()
    assert [(x["id"], x["server_version"]) for x in listed] == [(item["id"], 3)]

    assert c.delete(url).status_code == 204
    assert c.get(base(world, "reminders")).json() == []

    actions = [(x["entity"], x["action"]) for x in changelog.CALLS]
    assert actions == [("reminders", "upsert")] * 3 + [("reminders", "delete")]
    assert [x["payload"]["server_version"] for x in changelog.CALLS] == [1, 2, 3, 4]
    assert all(x["patient_id"] == world["patient"].id and str(x["entity_id"]) == item["id"] for x in changelog.CALLS)
    assert changelog.CALLS[0]["payload"]["schedule"] == REMINDER["schedule"]


def test_client_generated_id_is_used_and_duplicates_conflict(client_for, world):
    c = client_for(world["cg"])
    rid = str(uuid.uuid4())
    assert c.post(base(world, "reminders"), json={**REMINDER, "id": rid}).json()["id"] == rid
    assert c.post(base(world, "reminders"), json={**REMINDER, "id": rid}).status_code == 409
    assert len(changelog.CALLS) == 1


def test_server_generates_uuid7_when_no_id(client_for, world):
    rid = client_for(world["cg"]).post(base(world, "reminders"), json=REMINDER).json()["id"]
    assert uuid.UUID(rid).version == 7


def test_schedule_rrule_alias_is_accepted(client_for, world):
    body = {k: v for k, v in REMINDER.items() if k != "schedule"} | {"schedule_rrule": "FREQ=HOURLY;INTERVAL=2"}
    r = client_for(world["cg"]).post(base(world, "reminders"), json=body)
    assert r.status_code == 201 and r.json()["schedule"] == "FREQ=HOURLY;INTERVAL=2"


@pytest.mark.parametrize("schedule", ["not a rule", "", "FREQ=SECONDLY", "FREQ=DAILY;BYHOUR=77", "FREQ=NEVER"])
def test_invalid_rrule_is_422_and_nothing_is_recorded(client_for, world, schedule):
    c = client_for(world["cg"])
    r = c.post(base(world, "reminders"), json={**REMINDER, "schedule": schedule})
    assert r.status_code == 422
    assert c.get(base(world, "reminders")).json() == [] and not changelog.CALLS


def test_invalid_rrule_on_update_leaves_row_untouched(client_for, world):
    c = client_for(world["cg"])
    item = c.post(base(world, "reminders"), json=REMINDER).json()
    url = f"{base(world, 'reminders')}/{item['id']}"
    assert c.put(url, json={**REMINDER, "schedule": "garbage"}).status_code == 422
    assert c.get(base(world, "reminders")).json()[0]["server_version"] == 1
    assert len(changelog.CALLS) == 1


@pytest.mark.parametrize("patch", [{"category": "snacks"}, {"locale": "xx"}, {"title": "  "}, {"title": ""},
                                    {"escalate_after_misses": -1}, {"voice_clip_id": "nope"}])
def test_field_validation(client_for, world, patch):
    assert client_for(world["cg"]).post(base(world, "reminders"), json={**REMINDER, **patch}).status_code == 422


def test_all_contract_locales_accepted(client_for, world):
    c = client_for(world["cg"])
    for loc in ("as", "bn", "ne", "brx", "mni", "en", "lus", "kha", "grt"):
        assert c.post(base(world, "reminders"), json={**REMINDER, "locale": loc}).status_code == 201


def _asset(world, patient, kind):
    from app.models import MediaAsset
    a = MediaAsset(id=uuid.uuid4(), patient_id=patient.id, uploader_id=world["cg"].id, kind=kind,
                   mime="audio/wav" if kind == "audio" else "image/jpeg", size_bytes=1,
                   enc_path="x/y.enc", nonce=b"\x00" * 12, tags=[])
    with world["Session"]() as s:
        s.add(a)
        s.commit()
    return a


def test_voice_clip_must_be_this_patients_audio(client_for, world):
    c = client_for(world["hw"])
    mine = _asset(world, world["patient"], "audio")
    photo = _asset(world, world["patient"], "photo")
    theirs = _asset(world, other_patient(world), "audio")
    ok = c.post(base(world, "reminders"), json={**REMINDER, "voice_clip_id": str(mine.id)})
    assert ok.status_code == 201 and ok.json()["voice_clip_id"] == str(mine.id)
    assert c.post(base(world, "reminders"), json={**REMINDER, "voice_clip_id": str(photo.id)}).status_code == 422
    assert c.post(base(world, "reminders"), json={**REMINDER, "voice_clip_id": str(theirs.id)}).status_code == 422
    # an id that is not a media asset is treated as a voice-pack clip id and accepted
    assert c.post(base(world, "reminders"), json={**REMINDER, "voice_clip_id": str(uuid.uuid4())}).status_code == 201


@pytest.mark.parametrize("kind,payload", [("reminders", REMINDER), ("routines", ROUTINE)])
def test_rbac_matrix(client_for, world, kind, payload):
    owner = client_for(world["cg"])
    item = owner.post(base(world, kind), json=payload).json()
    url = f"{base(world, kind)}/{item['id']}"
    calls_before = len(changelog.CALLS)

    # patient: may read own data, may not write
    p = client_for(world["patient"])
    assert p.get(base(world, kind)).status_code == 200
    assert p.post(base(world, kind), json=payload).status_code == 403
    assert p.put(url, json=payload).status_code == 403
    assert p.delete(url).status_code == 403

    # caregiver not linked to this patient: nothing at all
    x = client_for(world["other_cg"])
    assert x.get(base(world, kind)).status_code == 403
    assert x.post(base(world, kind), json=payload).status_code == 403
    assert x.put(url, json=payload).status_code == 403
    assert x.delete(url).status_code == 403

    assert len(changelog.CALLS) == calls_before          # denied writes never reach the change log
    assert owner.get(base(world, kind)).json()[0]["server_version"] == 1

    # health worker can write
    assert client_for(world["hw"]).put(url, json=payload).json()["server_version"] == 2


@pytest.mark.parametrize("kind,payload", [("reminders", REMINDER), ("routines", ROUTINE)])
def test_items_are_scoped_to_their_patient(client_for, world, kind, payload):
    c = client_for(world["hw"])
    item = c.post(base(world, kind), json=payload).json()
    p2 = other_patient(world)
    wrong = f"/api/v1/patients/{p2.id}/{kind}/{item['id']}"
    assert c.put(wrong, json=payload).status_code == 404
    assert c.delete(wrong).status_code == 404
    assert c.get(f"/api/v1/patients/{p2.id}/{kind}").json() == []
    assert c.put(f"{base(world, kind)}/{uuid.uuid4()}", json=payload).status_code == 404


@pytest.mark.parametrize("kind,payload", [("reminders", REMINDER), ("routines", ROUTINE)])
def test_nothing_is_committed_if_record_change_fails(client_for, world, monkeypatch, kind, payload):
    c = client_for(world["cg"])
    item = c.post(base(world, kind), json=payload).json()
    url = f"{base(world, kind)}/{item['id']}"

    def boom(*a, **k):
        raise RuntimeError("changelog down")
    with monkeypatch.context() as m:
        m.setattr(changelog, "record_change", boom)
        with pytest.raises(RuntimeError):
            c.post(base(world, kind), json=payload)
        with pytest.raises(RuntimeError):
            c.put(url, json={**payload, "title": "changed"})
        with pytest.raises(RuntimeError):
            c.delete(url)

    rows = c.get(base(world, kind)).json()
    assert len(rows) == 1 and rows[0]["server_version"] == 1 and rows[0]["title"] == payload["title"]


# =========================================================== routines

def test_routine_crud_bumps_server_version_and_records_every_change(client_for, world):
    c = client_for(world["cg"])
    r = c.post(base(world, "routines"), json=ROUTINE)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["server_version"] == 1 and item["created_by"] == str(world["cg"].id)
    assert [st["title"] for st in item["steps"]] == [st if isinstance(st, str) else st["title"] for st in ROUTINE["steps"]]
    assert [st["order"] for st in item["steps"]] == list(range(1, len(item["steps"]) + 1))  # D1 canonical shape

    url = f"{base(world, 'routines')}/{item['id']}"
    v2 = c.put(url, json={"title": "Morning v2", "steps": ["Wake up"]}).json()
    assert v2["server_version"] == 2 and v2["title"] == "Morning v2" and v2["created_by"] == item["created_by"]
    assert c.delete(url).status_code == 204
    assert c.get(base(world, "routines")).json() == []

    assert [(x["entity"], x["action"]) for x in changelog.CALLS] == [
        ("routines", "upsert"), ("routines", "upsert"), ("routines", "delete")]
    assert changelog.CALLS[2]["payload"]["server_version"] == 3


@pytest.mark.parametrize("patch", [{"steps": []}, {"steps": "wake"}, {"steps": [1, 2]}, {"steps": [""]},
                                    {"steps": ["x"] * 51}, {"title": ""}, {"title": "   "}])
def test_routine_validation(client_for, world, patch):
    assert client_for(world["cg"]).post(base(world, "routines"), json={**ROUTINE, **patch}).status_code == 422
    assert not changelog.CALLS
