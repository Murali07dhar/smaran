from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, MemoryTrigger, SeverityIndicator
from app.modules.insights import pipeline
from fake_ai.client import FakeAIClient
from insights_helpers import (
    NOW, add_alert, add_emotion, add_event, add_reminder, add_session, add_trigger, make_user,
)  # fmt: skip


def alerts_of(db, patient, kind=None):
    q = select(Alert).where(Alert.patient_id == patient.id)
    if kind:
        q = q.where(Alert.kind == kind)
    return list(db.scalars(q))


def run(db, patient, session_ids=(), ai=None):
    res = pipeline._run(db, patient.id, list(session_ids), NOW, ai=ai or FakeAIClient())
    db.commit()
    return res


# ---------------------------------------------------------------- observations / triggers
def test_observations_payload_and_trigger_upsert(db, changes):
    p = make_user(db, "patient", "P")
    s = add_session(db, p, NOW - timedelta(days=1))
    add_event(db, s, correct=True, with_cue=True, cue_id="cue-1")
    add_event(db, s, correct=False, with_cue=False, cue_id="cue-2")
    add_event(db, s, correct=True, with_cue=False, cue_id=None)            # no cue -> synthetic "no_cue:<domain>" baseline (D2)
    add_event(db, s, correct=None, with_cue=True, cue_id="cue-3", type="cue_shown")  # not answered -> skipped
    add_emotion(db, s, "joy")
    fake = FakeAIClient()

    res = run(db, p, [s.id], ai=fake)

    (_, observations), = fake.trigger_calls
    assert {o["cue_id"] for o in observations} == {"cue-1", "cue-2", "no_cue:memory"}
    by_id = {o["cue_id"]: o for o in observations}
    assert by_id["no_cue:memory"]["cue_type"] == "none" and by_id["no_cue:memory"]["valence_label"] == "neutral"
    assert by_id["no_cue:memory"]["with_cue"] is False
    assert by_id["cue-1"]["valence_label"] == "joy"     # fallback: session's dominant emotion
    assert by_id["cue-1"]["cue_type"] == "unknown"
    assert {"recalled", "with_cue", "ts"} <= set(observations[0])
    assert res.triggers_updated == 2
    rows = list(db.scalars(select(MemoryTrigger).where(MemoryTrigger.patient_id == p.id)))
    assert {r.cue_id for r in rows} == {"cue-1", "cue-2"}
    trig_changes = [c for c in changes if c["entity"] == pipeline.ENTITY_TRIGGER]
    assert len(trig_changes) == 2 and all(c["action"] == "upsert" for c in trig_changes)
    assert trig_changes[0]["patient_id"] == p.id


def test_existing_trigger_metadata_is_reused_and_row_updated_in_place(db, changes):
    p = make_user(db, "patient", "P")
    existing = add_trigger(db, p, cue_id="cue-1", cue_type="photo", label="comfort", confidence=0.1)
    s = add_session(db, p, NOW - timedelta(days=1))
    add_event(db, s, correct=True, with_cue=True, cue_id="cue-1")
    fake = FakeAIClient()

    run(db, p, [s.id], ai=fake)

    obs = fake.trigger_calls[0][1][0]
    assert (obs["cue_type"], obs["valence_label"]) == ("photo", "comfort")
    rows = list(db.scalars(select(MemoryTrigger).where(MemoryTrigger.patient_id == p.id)))
    assert len(rows) == 1 and rows[0].id == existing.id and rows[0].confidence == 1.0
    assert rows[0].cue_type == "photo"


# ---------------------------------------------------------------- severity
def test_severity_row_stored_and_watch_band_creates_alert(db, changes):
    p = make_user(db, "patient", "P")
    s = add_session(db, p, NOW - timedelta(days=1))
    res = run(db, p, [s.id], ai=FakeAIClient(severity_band="watch", gds=4))
    assert res.severity_stored
    sev = db.scalars(select(SeverityIndicator).where(SeverityIndicator.patient_id == p.id)).one()
    assert (sev.band, sev.gds_style_indicator) == ("watch", 4)
    (a,) = alerts_of(db, p, "severity")
    assert a.severity == "watch"
    assert any(c["entity"] == pipeline.ENTITY_ALERT and c["entity_id"] == a.id for c in changes)


def test_stable_band_creates_no_severity_alert(db, changes):
    p = make_user(db, "patient", "P")
    s = add_session(db, p, NOW - timedelta(days=1))
    run(db, p, [s.id], ai=FakeAIClient(severity_band="stable"))
    assert alerts_of(db, p, "severity") == []


# ---------------------------------------------------------------- alert rules
def test_score_drop_alert(db, changes):
    p = make_user(db, "patient", "P")
    for d, score in ((10, 90), (9, 90), (2, 50), (1, 50)):
        add_session(db, p, NOW - timedelta(days=d), score=score)
    run(db, p)
    (a,) = alerts_of(db, p, "score_drop")
    assert a.severity == "alert"  # 44% drop
    assert alerts_of(db, p, "activity_drop") == []


def test_no_score_drop_when_scores_are_stable(db, changes):
    p = make_user(db, "patient", "P")
    for d in (10, 9, 2, 1):
        add_session(db, p, NOW - timedelta(days=d), score=80)
    run(db, p)
    assert alerts_of(db, p) == []


def test_activity_drop_alert(db, changes):
    p = make_user(db, "patient", "P")
    add_session(db, p, NOW - timedelta(days=5))
    run(db, p)
    (a,) = alerts_of(db, p, "activity_drop")
    assert a.severity == "watch"


def test_no_activity_alert_for_patient_without_any_session(db, changes):
    p = make_user(db, "patient", "P")
    run(db, p)
    assert alerts_of(db, p) == []


def test_missed_reminders_alert_and_broken_streak(db, changes):
    p = make_user(db, "patient", "P")
    q = make_user(db, "patient", "Q")
    add_session(db, p, NOW - timedelta(days=1))
    add_session(db, q, NOW - timedelta(days=1))
    add_reminder(db, p, ["missed", "missed", "missed", "done"])
    add_reminder(db, q, ["missed", "done", "missed", "missed"])
    run(db, p)
    run(db, q)
    (a,) = alerts_of(db, p, "missed_reminders")
    assert a.severity == "alert" and "Morning tablet" in a.message
    assert alerts_of(db, q, "missed_reminders") == []


# ---------------------------------------------------------------- de-duplication / escalation / ack
def test_no_duplicate_open_alert_then_new_one_after_ack(db, changes):
    p = make_user(db, "patient", "P")
    add_session(db, p, NOW - timedelta(days=5))
    run(db, p)
    run(db, p)
    run(db, p)
    assert len(alerts_of(db, p, "activity_drop")) == 1
    assert len([c for c in changes if c["entity"] == pipeline.ENTITY_ALERT]) == 1

    a = alerts_of(db, p, "activity_drop")[0]
    a.acknowledged_at = NOW
    db.commit()
    run(db, p)
    assert len(alerts_of(db, p, "activity_drop")) == 2


def test_open_alert_is_escalated_in_place_never_downgraded(db, changes):
    p = make_user(db, "patient", "P")
    add_session(db, p, NOW - timedelta(days=1))
    existing = add_alert(db, p, kind="severity", severity="watch")
    run(db, p, ai=FakeAIClient(severity_band="alert", gds=6))
    rows = alerts_of(db, p, "severity")
    assert len(rows) == 1 and rows[0].id == existing.id and rows[0].severity == "alert"
    run(db, p, ai=FakeAIClient(severity_band="watch", gds=4))
    assert alerts_of(db, p, "severity")[0].severity == "alert"


# ---------------------------------------------------------------- AI down
def test_ai_down_skips_ai_output_but_rules_still_run(db, changes):
    p = make_user(db, "patient", "P")
    s = add_session(db, p, NOW - timedelta(days=5))
    add_event(db, s, correct=True, with_cue=True, cue_id="cue-1")
    res = run(db, p, [s.id], ai=FakeAIClient(fail=True))
    assert res.ai_available is False and res.triggers_updated == 0 and not res.severity_stored
    assert list(db.scalars(select(MemoryTrigger))) == []
    assert list(db.scalars(select(SeverityIndicator))) == []
    assert len(alerts_of(db, p, "activity_drop")) == 1


def test_process_synced_data_never_raises_and_rolls_back(db, engine, changes, monkeypatch):
    p = make_user(db, "patient", "P")
    monkeypatch.setattr(pipeline, "get_ai_client", lambda: FakeAIClient(raise_exc=RuntimeError("boom")))
    pipeline.process_synced_data(db, p.id, [])  # must not raise


def test_process_synced_data_happy_path_commits(db, engine, changes, monkeypatch):
    p = make_user(db, "patient", "P")
    monkeypatch.setattr(pipeline, "get_ai_client", lambda: FakeAIClient(severity_band="watch"))
    pipeline.process_synced_data(db, p.id, [])
    with Session(engine) as other:
        assert len(list(other.scalars(select(Alert).where(Alert.kind == "severity")))) == 1


# ---------------------------------------------------------------- periodic scan
def test_scan_runs_rules_for_patients_only(db, changes):
    cg = make_user(db, "caregiver", "CG")
    inactive = make_user(db, "patient", "Inactive")
    newbie = make_user(db, "patient", "Newbie")
    add_session(db, inactive, NOW - timedelta(days=5))
    summary = pipeline.scan_all_patients(db, now=NOW, use_ai=False)
    assert summary == {"patients": 2, "alerts_changed": 1, "errors": 0}
    assert len(alerts_of(db, inactive, "activity_drop")) == 1
    assert alerts_of(db, newbie) == [] and alerts_of(db, cg) == []


def test_scan_stops_calling_ai_after_first_failure(db, changes, monkeypatch):
    for i in range(3):
        make_user(db, "patient", f"P{i}")
    fake = FakeAIClient(fail=True)
    monkeypatch.setattr(pipeline, "get_ai_client", lambda: fake)
    summary = pipeline.scan_all_patients(db, now=NOW)
    assert summary["patients"] == 3 and len(fake.severity_calls) == 1
