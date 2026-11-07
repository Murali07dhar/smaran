import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError

from app import models as m
from app.core.db import Base
from tests.conftest import link, make_user

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def test_every_briefing_table_exists_exactly():
    expected = {"users", "patient_profiles", "caregiver_links", "consent_records", "media_assets", "routines",
                "reminders", "reminder_events", "game_sessions", "game_events", "emotion_samples",
                "memory_triggers", "alerts", "severity_indicators", "sync_changes", "sync_ops"}
    assert set(Base.metadata.tables) == expected
    assert {c.__tablename__ for c in m.ALL_MODELS} == expected
    assert [c.__name__ for c in m.ALL_MODELS][:3] == ["User", "PatientProfile", "CaregiverLink"]


EXACT_COLUMNS = {
    "users": "id role name email phone password_hash pin_hash language created_at",
    "patient_profiles": "patient_id age language estimated_stage notes",
    "caregiver_links": "id caregiver_id patient_id relation created_at",
    "consent_records": "id patient_id kind granted granted_by ts",
    "media_assets": "id patient_id uploader_id kind mime size_bytes enc_path nonce tags created_at",
    "routines": "id patient_id title steps created_by server_version updated_at",
    "reminders": "id patient_id category title schedule_rrule locale voice_clip_id escalate_after_misses active server_version updated_at",
    "reminder_events": "id reminder_id patient_id due_at status ts",
    "game_sessions": "id patient_id game_id domain started_at ended_at difficulty score device_id server_ts",
    "game_events": "id session_id patient_id type item_id correct response_ms cue_id with_cue ts",
    "emotion_samples": "id session_id patient_id valence arousal label confidence source caregiver_confirmed ts",
    "memory_triggers": "id patient_id cue_id cue_type valence_label confidence last_validated_at half_life_days updated_at",
    "alerts": "id patient_id kind severity message created_at acknowledged_by acknowledged_at note",
    "severity_indicators": "id patient_id band gds_style_indicator drivers computed_at",
    "sync_changes": "cursor entity entity_id action payload patient_id server_ts",
    "sync_ops": "op_id device_id applied_at",
}


@pytest.mark.parametrize("table,cols", EXACT_COLUMNS.items())
def test_columns_match_briefing_exactly(table, cols):
    assert [c.name for c in Base.metadata.tables[table].columns] == cols.split()


def test_role_check_constraint(session):
    session.add(m.User(role="superuser", name="x", language="en"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_unique_email_phone_and_link(session):
    make_user(session, "caregiver", email="dup@t.test")
    session.add(m.User(role="caregiver", name="d", language="en", email="dup@t.test"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    c, p = make_user(session, "caregiver"), make_user(session, "patient")
    link(session, c, p)
    session.add(m.CaregiverLink(caregiver_id=c.id, patient_id=p.id, relation="son"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_timestamps_are_aware_utc_and_naive_rejected(session):
    u = make_user(session, "caregiver")
    assert u.created_at is None or u.created_at.tzinfo is not None
    session.commit()
    session.refresh(u)
    assert u.created_at.tzinfo is not None and u.created_at.utcoffset() == timedelta(0)
    ist = timezone(timedelta(hours=5, minutes=30))
    p = make_user(session, "patient")
    s = m.GameSession(patient_id=p.id, game_id="g", domain="memory", started_at=datetime(2026, 1, 1, 10, 0, tzinfo=ist),
                      difficulty=3, device_id="d")
    session.add(s)
    session.commit()
    session.refresh(s)
    assert s.started_at == datetime(2026, 1, 1, 4, 30, tzinfo=timezone.utc) and s.started_at.utcoffset() == timedelta(0)
    session.add(m.GameSession(patient_id=p.id, game_id="g", domain="memory", started_at=datetime(2026, 1, 1, 10, 0),
                              difficulty=3, device_id="d"))
    with pytest.raises(StatementError, match="naive datetime"):
        session.flush()


def test_server_version_and_updated_at_bump_on_update(session):
    p, c = make_user(session, "patient"), make_user(session, "caregiver")
    r = m.Reminder(patient_id=p.id, category="medicine", title="Pill", schedule_rrule="FREQ=DAILY;BYHOUR=8",
                   locale="as", escalate_after_misses=2)
    session.add(r)
    session.commit()
    session.refresh(r)
    assert r.server_version == 1 and r.active is True
    first = r.updated_at
    time.sleep(0.01)
    r.title = "Pill (new)"
    session.commit()
    session.refresh(r)
    assert r.server_version == 2 and r.updated_at > first
    r.title = "again"
    session.commit()
    session.refresh(r)
    assert r.server_version == 3
    rt = m.Routine(patient_id=p.id, title="Morning", steps=[{"order": 1, "title": "Wake"}], created_by=c.id)
    session.add(rt)
    session.commit()
    rt.title = "Morning 2"
    session.commit()
    session.refresh(rt)
    assert rt.server_version == 2 and rt.steps == [{"order": 1, "title": "Wake"}]


def test_check_constraints(session):
    p = make_user(session, "patient")
    bad = [
        m.Reminder(patient_id=p.id, category="shopping", title="t", schedule_rrule="x", locale="en", escalate_after_misses=1),
        m.Alert(patient_id=p.id, kind="score_drop", severity="critical", message="m"),
        m.EmotionSample(patient_id=p.id, valence=0, arousal=0, label="rage", confidence=.5, source="face", ts=NOW),
        m.EmotionSample(patient_id=p.id, valence=0, arousal=0, label="joy", confidence=.5, source="magic", ts=NOW),
        m.SeverityIndicator(patient_id=p.id, band="watch", gds_style_indicator=9, drivers=[]),
        m.GameSession(patient_id=p.id, game_id="g", domain="trivia", started_at=NOW, difficulty=3, device_id="d"),
        m.GameSession(patient_id=p.id, game_id="g", domain="memory", started_at=NOW, difficulty=11, device_id="d"),
        m.ConsentRecord(patient_id=p.id, kind="location", granted=True, granted_by=p.id),
        m.SyncChange(entity="reminders", entity_id=uuid.uuid4(), action="merge", payload={}, patient_id=p.id),
    ]
    for obj in bad:
        session.add(obj)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        p = session.get(m.User, p.id) or make_user(session, "patient")


def test_memory_trigger_unique_per_patient_cue(session):
    p = make_user(session, "patient")
    kw = dict(patient_id=p.id, cue_id="c1", cue_type="music", valence_label="joy", confidence=.8,
              last_validated_at=NOW, half_life_days=30.0)
    session.add(m.MemoryTrigger(**kw))
    session.flush()
    session.add(m.MemoryTrigger(**kw))
    with pytest.raises(IntegrityError):
        session.flush()


def test_sync_changes_cursor_is_monotonic_and_json_roundtrips(session):
    p = make_user(session, "patient")
    rows = [m.SyncChange(entity="reminders", entity_id=uuid.uuid4(), action="upsert", payload={"n": i, "nested": {"a": [1, 2]}},
                         patient_id=p.id) for i in range(5)]
    session.add_all(rows)
    session.commit()
    cursors = [r.cursor for r in rows]
    assert all(isinstance(c, int) for c in cursors) and cursors == sorted(cursors) and len(set(cursors)) == 5
    got = session.scalars(select(m.SyncChange).where(m.SyncChange.cursor > cursors[1]).order_by(m.SyncChange.cursor)).all()
    assert [g.payload["n"] for g in got] == [2, 3, 4] and got[0].payload["nested"] == {"a": [1, 2]}


def test_deleting_patient_cascades(session):
    c, p = make_user(session, "caregiver"), make_user(session, "patient")
    link(session, c, p)
    gs = m.GameSession(patient_id=p.id, game_id="g", domain="memory", started_at=NOW, difficulty=3, device_id="d")
    session.add(gs)
    session.flush()
    rem = m.Reminder(patient_id=p.id, category="hydration", title="Water", schedule_rrule="FREQ=DAILY", locale="en", escalate_after_misses=1)
    session.add(rem)
    session.flush()
    session.add_all([
        m.GameEvent(session_id=gs.id, patient_id=p.id, type="answer", item_id="i1", correct=True, response_ms=900, with_cue=False, ts=NOW),
        m.EmotionSample(session_id=gs.id, patient_id=p.id, valence=.5, arousal=.4, label="joy", confidence=.9, source="face", ts=NOW),
        m.ReminderEvent(reminder_id=rem.id, patient_id=p.id, due_at=NOW, status="done"),
        m.Alert(patient_id=p.id, kind="score_drop", severity="info", message="m", acknowledged_by=c.id),
        m.ConsentRecord(patient_id=p.id, kind="camera", granted=True, granted_by=c.id),
        m.SyncChange(entity="alerts", entity_id=uuid.uuid4(), action="delete", payload={}, patient_id=p.id),
    ])
    session.commit()
    session.delete(session.get(m.User, p.id))
    session.commit()
    for model in (m.PatientProfile, m.CaregiverLink, m.GameSession, m.GameEvent, m.EmotionSample, m.Reminder,
                  m.ReminderEvent, m.Alert, m.ConsentRecord, m.SyncChange):
        assert session.scalars(select(model)).first() is None, model.__name__
    assert session.get(m.User, c.id) is not None  # the caregiver survives


def test_alert_ack_user_set_null_when_caregiver_deleted(session):
    c, p = make_user(session, "caregiver"), make_user(session, "patient")
    a = m.Alert(patient_id=p.id, kind="severity", severity="watch", message="m", acknowledged_by=c.id, acknowledged_at=NOW)
    session.add(a)
    session.commit()
    session.delete(c)
    session.commit()
    session.refresh(a)
    assert a.acknowledged_by is None and a.acknowledged_at is not None
