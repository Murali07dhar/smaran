from datetime import datetime, timezone

import pytest
from sqlalchemy import case, func, select

import seed as seedmod
from app import models as m
from app.core import security as sec

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


@pytest.fixture
def seeded(session):
    assert seedmod.seed(session, days=30, now=NOW) is True
    return session


def test_seed_populates_everything(seeded):
    s = seeded
    assert count(s, m.User) == 4 and count(s, m.PatientProfile) == 2 and count(s, m.CaregiverLink) == 4
    assert {r for (r,) in s.execute(select(m.User.role))} == {"caregiver", "health_worker", "patient"}
    for model in (m.GameSession, m.GameEvent, m.ReminderEvent, m.MemoryTrigger, m.Alert, m.SeverityIndicator,
                  m.Reminder, m.Routine, m.ConsentRecord, m.SyncChange):
        assert count(s, model) > 0, model.__name__
    for pid in (seedmod.P1, seedmod.P2):
        days = {d.date() for (d,) in s.execute(select(m.GameSession.started_at).where(m.GameSession.patient_id == pid))}
        assert len(days) >= 22, "about 30 days of history expected"
        first = min(d for (d,) in s.execute(select(m.GameSession.started_at).where(m.GameSession.patient_id == pid)))
        assert (NOW - first).days >= 28
    assert s.scalar(select(func.max(m.GameSession.started_at))) <= NOW


def test_seed_is_idempotent_and_reset_works(seeded):
    before = {mod.__name__: count(seeded, mod) for mod in m.ALL_MODELS}
    assert seedmod.seed(seeded, days=30, now=NOW) is False  # no-op
    assert {mod.__name__: count(seeded, mod) for mod in m.ALL_MODELS} == before
    assert seedmod.seed(seeded, days=30, now=NOW, do_reset=True) is True
    after = {mod.__name__: count(seeded, mod) for mod in m.ALL_MODELS}
    assert after == before


def test_seed_story_and_consistency(seeded):
    s = seeded
    # Tomba declines, with open alerts and a watch band; Bimala stable
    def avg(pid, since, until):
        return s.scalar(select(func.avg(m.GameSession.score)).where(
            m.GameSession.patient_id == pid, m.GameSession.started_at >= since, m.GameSession.started_at < until))
    from datetime import timedelta
    assert avg(seedmod.P2, NOW - timedelta(days=10), NOW + timedelta(days=1)) < avg(seedmod.P2, NOW - timedelta(days=30), NOW - timedelta(days=20))
    open_t = s.scalars(select(m.Alert).where(m.Alert.patient_id == seedmod.P2, m.Alert.acknowledged_at.is_(None))).all()
    assert len(open_t) >= 3 and {a.severity for a in open_t} >= {"watch", "alert"}
    latest = lambda pid: s.scalars(select(m.SeverityIndicator).where(m.SeverityIndicator.patient_id == pid)
                                   .order_by(m.SeverityIndicator.computed_at.desc())).first()
    assert latest(seedmod.P1).band == "stable" and latest(seedmod.P2).band == "watch"
    # cues help (core idea of the product): accuracy with cue > without, over all answers
    acc = lambda wc: s.scalar(select(func.avg(case((m.GameEvent.correct.is_(True), 1.0), else_=0.0)))
                              .where(m.GameEvent.type == "answer", m.GameEvent.with_cue == wc))
    assert acc(True) > acc(False)
    # every cue_id used in events has a memory_trigger for that patient
    triggers = {(t.patient_id, t.cue_id) for t in s.scalars(select(m.MemoryTrigger))}
    used = {(e.patient_id, e.cue_id) for e in s.scalars(select(m.GameEvent).where(m.GameEvent.cue_id.is_not(None)))}
    assert used <= triggers
    # consent: emotion samples exist only for the patient who granted camera consent
    cam = {c.patient_id: c.granted for c in s.scalars(select(m.ConsentRecord).where(m.ConsentRecord.kind == "camera"))}
    assert cam == {seedmod.P1: True, seedmod.P2: False}
    assert {e.patient_id for e in s.scalars(select(m.EmotionSample))} == {seedmod.P1}
    # score alerts carry the not-a-diagnosis disclaimer
    assert all("not a diagnosis" in a.message for a in s.scalars(select(m.Alert).where(m.Alert.kind.in_(["score_drop", "severity"]))))


def test_seed_users_can_authenticate_and_access_patients(seeded):
    s = seeded
    cg = s.scalar(select(m.User).where(m.User.email == "caregiver@smaran.demo"))
    hw = s.scalar(select(m.User).where(m.User.email == "healthworker@smaran.demo"))
    assert sec.verify_password(seedmod.DEMO_PASSWORD, cg.password_hash)
    for who in (cg, hw):
        assert sec.accessible_patient_ids(s, who) == {seedmod.P1, seedmod.P2}
    p1 = s.get(m.User, seedmod.P1)
    assert sec.verify_pin("2468", p1.pin_hash) and p1.password_hash is None


def test_seed_sync_changes_cover_pullable_entities(seeded):
    ents = {e for (e,) in seeded.execute(select(m.SyncChange.entity).distinct())}
    assert ents == {"reminders", "routines", "memory_triggers", "alerts"}
    ch = seeded.scalars(select(m.SyncChange).where(m.SyncChange.entity == "reminders")).first()
    assert ch.payload["id"] == str(ch.entity_id) and ch.payload["schedule_rrule"]


def test_seed_refuses_production(monkeypatch, capsys):
    monkeypatch.setattr(seedmod.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("sys.argv", ["seed.py"])
    assert seedmod.main() == 2


def test_seeded_patients_are_listable_by_the_caregiver():
    """Regression: seed stores estimated_stage as text ('mild'); GET /patients must serialise it."""
    from app.modules.auth_consent.schemas import PatientListItem
    item = PatientListItem(id="00000000-0000-0000-0000-000000000001", name="x", age=70, language="as",
                           estimated_stage="mild", last_active_at=None, open_alerts=0, severity_band=None)
    assert item.estimated_stage == "mild"
