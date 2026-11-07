"""Factories for insights tests."""
import uuid
from datetime import datetime, time, timedelta, timezone

from app.models import (
    Alert, CaregiverLink, EmotionSample, GameEvent, GameSession, MemoryTrigger, Reminder, ReminderEvent, User,
)  # fmt: skip

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)  # fixed clock for pipeline/rule tests


def noon(days_ago: int) -> datetime:
    """Noon UTC of (today - days_ago): safe from day-boundary flakiness in route tests."""
    d = datetime.now(UTC).date() - timedelta(days=days_ago)
    return datetime.combine(d, time(12, 0), tzinfo=UTC)


def make_user(db, role="caregiver", name="Test"):
    u = User(id=uuid.uuid4(), role=role, name=name, language="en")
    db.add(u)
    db.commit()
    return u


def link(db, caregiver, patient):
    db.add(CaregiverLink(id=uuid.uuid4(), caregiver_id=caregiver.id, patient_id=patient.id, relation="child"))
    db.commit()


def add_session(db, patient, started, score=70.0, domain="memory", minutes=10):
    s = GameSession(
        id=uuid.uuid4(), patient_id=patient.id, game_id="g1", domain=domain, started_at=started,
        ended_at=(started + timedelta(minutes=minutes)) if minutes is not None else None,
        difficulty=3, score=score, device_id="d1",
    )  # fmt: skip
    db.add(s)
    db.commit()
    return s


def add_event(db, sess, correct=True, with_cue=False, cue_id=None, response_ms=2000, ts=None, type="answer"):
    e = GameEvent(
        id=uuid.uuid4(), session_id=sess.id, patient_id=sess.patient_id, type=type, item_id="i1",
        correct=correct, response_ms=response_ms, cue_id=cue_id, with_cue=with_cue, ts=ts or sess.started_at,
    )  # fmt: skip
    db.add(e)
    db.commit()
    return e


def add_emotion(db, sess, label="joy"):
    db.add(EmotionSample(
        id=uuid.uuid4(), session_id=sess.id, patient_id=sess.patient_id, valence=0.5, arousal=0.5, label=label,
        confidence=0.8, source="fused", ts=sess.started_at,
    ))  # fmt: skip
    db.commit()


def add_reminder(db, patient, statuses_newest_first, category="medicine", escalate=3, title="Morning tablet", now=NOW):
    r = Reminder(
        id=uuid.uuid4(), patient_id=patient.id, category=category, title=title, schedule_rrule="FREQ=DAILY",
        locale="en", escalate_after_misses=escalate, active=True, server_version=1, updated_at=now,
    )  # fmt: skip
    db.add(r)
    db.commit()
    for i, st in enumerate(statuses_newest_first):
        due = now - timedelta(days=i + 1)
        db.add(ReminderEvent(id=uuid.uuid4(), reminder_id=r.id, patient_id=patient.id, due_at=due, status=st, ts=due))
    db.commit()
    return r


def add_trigger(db, patient, cue_id="cue-1", cue_type="photo", label="joy", confidence=0.5):
    t = MemoryTrigger(
        id=uuid.uuid4(), patient_id=patient.id, cue_id=cue_id, cue_type=cue_type, valence_label=label,
        confidence=confidence, last_validated_at=NOW, half_life_days=10.0, updated_at=NOW,
    )  # fmt: skip
    db.add(t)
    db.commit()
    return t


def add_alert(db, patient, kind="score_drop", severity="watch", created=NOW, acked=False):
    a = Alert(
        id=uuid.uuid4(), patient_id=patient.id, kind=kind, severity=severity, message="m", created_at=created,
        acknowledged_at=created if acked else None,
    )  # fmt: skip
    db.add(a)
    db.commit()
    return a
