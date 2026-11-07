import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, SeverityIndicator
from app.modules.insights import pipeline, rules
from app.modules.insights.router import CSV_HEADER
from insights_helpers import (
    NOW, add_alert, add_event, add_reminder, add_session, add_trigger, link, make_user, noon,
)  # fmt: skip

P = "/api/v1/patients"


@pytest.fixture()
def world(db):
    cg = make_user(db, "caregiver", "CG")
    cg2 = make_user(db, "caregiver", "CG2")
    admin = make_user(db, "admin", "Admin")
    p = make_user(db, "patient", "P")
    q = make_user(db, "patient", "Q")
    link(db, cg, p)
    link(db, cg2, q)
    return type("W", (), dict(cg=cg, cg2=cg2, admin=admin, p=p, q=q))


# ------------------------------------------------------------------ trends
def test_trends_exact_shape_dense_days_and_values(db, make_client, world):
    s1 = add_session(db, world.p, noon(1), score=80, minutes=10)
    s2 = add_session(db, world.p, noon(1), score=60, minutes=20)
    add_event(db, s1, response_ms=1000)
    add_event(db, s2, response_ms=3000)
    add_session(db, world.p, noon(3), score=50, minutes=5)
    r = make_client(world.cg).get(f"{P}/{world.p.id}/dashboard/trends?days=7")
    assert r.status_code == 200
    days = r.json()["days"]
    assert len(days) == 7
    assert set(days[0]) == {"date", "sessions", "avg_score", "avg_response_ms", "engagement_minutes"}
    by_date = {d["date"]: d for d in days}
    today = datetime.now(timezone.utc).date()
    y = by_date[(today - timedelta(days=1)).isoformat()]
    assert y == {"date": y["date"], "sessions": 2, "avg_score": 70.0, "avg_response_ms": 2000.0, "engagement_minutes": 30.0}
    empty = by_date[today.isoformat()]
    assert empty["sessions"] == 0 and empty["avg_score"] is None and empty["engagement_minutes"] == 0.0
    assert days[-1]["date"] == today.isoformat()


def test_trends_days_param_validated(db, make_client, world):
    assert make_client(world.cg).get(f"{P}/{world.p.id}/dashboard/trends?days=0").status_code == 422
    assert make_client(world.cg).get(f"{P}/{world.p.id}/dashboard/trends?days=366").status_code == 422


# ------------------------------------------------------------------ cue comparison
def test_cue_comparison(db, make_client, world):
    mem = add_session(db, world.p, noon(1), domain="memory")
    att = add_session(db, world.p, noon(1), domain="attention")
    for correct, ms in ((True, 1000), (True, 2000), (False, 3000)):
        add_event(db, mem, correct=correct, with_cue=True, response_ms=ms)
    for correct, ms in ((False, 4000), (True, 2000)):
        add_event(db, mem, correct=correct, with_cue=False, response_ms=ms)
    add_event(db, att, correct=True, with_cue=True, response_ms=1000)
    add_event(db, mem, correct=None, with_cue=True, type="hint_used")  # not an answer: ignored
    body = make_client(world.cg).get(f"{P}/{world.p.id}/dashboard/cue-comparison").json()
    assert set(body) == {"with_cue", "without_cue", "by_domain"}
    assert body["with_cue"] == {"n": 4, "accuracy": 0.75, "avg_response_ms": 1750.0}
    assert body["without_cue"] == {"n": 2, "accuracy": 0.5, "avg_response_ms": 3000.0}
    assert body["by_domain"] == [
        {"domain": "attention", "with_cue_accuracy": 1.0, "without_cue_accuracy": None},
        {"domain": "memory", "with_cue_accuracy": 0.6667, "without_cue_accuracy": 0.5},
    ]


def test_cue_comparison_without_data(db, make_client, world):
    body = make_client(world.cg).get(f"{P}/{world.p.id}/dashboard/cue-comparison").json()
    assert body["with_cue"] == {"n": 0, "accuracy": None, "avg_response_ms": None}
    assert body["by_domain"] == []


# ------------------------------------------------------------------ triggers / severity
def test_triggers_sorted_by_confidence(db, make_client, world):
    add_trigger(db, world.p, "low", confidence=0.3)
    add_trigger(db, world.p, "high", confidence=0.9)
    rows = make_client(world.cg).get(f"{P}/{world.p.id}/dashboard/triggers").json()
    assert [r["cue_id"] for r in rows] == ["high", "low"]
    assert set(rows[0]) == {"cue_id", "cue_type", "valence_label", "confidence", "last_validated_at", "half_life_days"}


def test_severity_empty_and_latest(db, make_client, world):
    c = make_client(world.cg)
    empty = c.get(f"{P}/{world.p.id}/dashboard/severity").json()
    assert empty["band"] is None and empty["disclaimer"] == rules.DISCLAIMER
    db.add(SeverityIndicator(id=pipeline.uuid7(), patient_id=world.p.id, band="stable", gds_style_indicator=2, drivers=[], computed_at=NOW - timedelta(days=2)))
    db.add(SeverityIndicator(id=pipeline.uuid7(), patient_id=world.p.id, band="watch", gds_style_indicator=4, drivers=["x"], computed_at=NOW))
    db.commit()
    body = c.get(f"{P}/{world.p.id}/dashboard/severity").json()
    assert set(body) == {"band", "gds_style_indicator", "drivers", "disclaimer", "computed_at"}
    assert (body["band"], body["gds_style_indicator"], body["drivers"]) == ("watch", 4, ["x"])


# ------------------------------------------------------------------ RBAC
@pytest.mark.parametrize("path", ["dashboard/trends", "dashboard/cue-comparison", "dashboard/triggers", "dashboard/severity", "report.csv"])
def test_patient_routes_forbid_unlinked_caregiver_and_patient_role(db, make_client, world, path):
    url = f"{P}/{world.q.id}/{path}"            # q belongs to cg2
    assert make_client(world.cg).get(url).status_code == 403
    assert make_client(world.cg2).get(url).status_code == 200
    assert make_client(world.admin).get(url).status_code == 200
    assert make_client(world.q).get(url).status_code == 403   # elder-facing role: no dashboards


# ------------------------------------------------------------------ alerts
def test_alert_listing_scopes_and_filters(db, make_client, world):
    open_p = add_alert(db, world.p, "score_drop")
    add_alert(db, world.p, "activity_drop", acked=True)
    add_alert(db, world.q, "score_drop")
    c = make_client(world.cg)
    rows = c.get("/api/v1/alerts").json()
    assert [r["id"] for r in rows] == [str(open_p.id)]
    assert set(rows[0]) == {"id", "patient_id", "kind", "severity", "message", "created_at", "acknowledged_at"}
    assert len(c.get("/api/v1/alerts?status=all").json()) == 2
    assert len(c.get(f"/api/v1/alerts?patient_id={world.p.id}&status=all").json()) == 2
    assert c.get(f"/api/v1/alerts?patient_id={world.q.id}").status_code == 403
    assert len(make_client(world.admin).get("/api/v1/alerts?status=all").json()) == 3
    assert make_client(world.p).get("/api/v1/alerts").status_code == 403
    assert c.get("/api/v1/alerts?status=bogus").status_code == 422


def test_ack_flow(db, engine, make_client, world, changes):
    a = add_alert(db, world.p, "score_drop")
    c = make_client(world.cg)
    r = c.post(f"/api/v1/alerts/{a.id}/ack", json={"note": "called her"})
    assert r.status_code == 200 and r.json()["acknowledged_at"] is not None
    with Session(engine) as s:
        row = s.get(Alert, a.id)
        assert row.acknowledged_by == world.cg.id and row.note == "called her"
    assert len(changes) == 1 and changes[0]["entity"] == pipeline.ENTITY_ALERT
    assert changes[0]["payload"]["acknowledged_at"] is not None
    assert c.get("/api/v1/alerts").json() == []                       # no longer open
    # idempotent: second ack changes nothing and records nothing
    c.post(f"/api/v1/alerts/{a.id}/ack", json={"note": "other"})
    with Session(engine) as s:
        assert s.get(Alert, a.id).note == "called her"
    assert len(changes) == 1


def test_ack_without_body_forbidden_and_missing(db, make_client, world, changes):
    mine = add_alert(db, world.p, "activity_drop")
    theirs = add_alert(db, world.q, "activity_drop")
    c = make_client(world.cg)
    assert c.post(f"/api/v1/alerts/{mine.id}/ack").status_code == 200
    assert c.post(f"/api/v1/alerts/{theirs.id}/ack").status_code == 403
    assert c.post(f"/api/v1/alerts/{pipeline.uuid7()}/ack").status_code == 404
    assert make_client(world.p).post(f"/api/v1/alerts/{mine.id}/ack").status_code == 403


# ------------------------------------------------------------------ CSV
def test_report_csv(db, make_client, world):
    add_session(db, world.p, noon(1), score=80, minutes=10)
    add_reminder(db, world.p, ["missed"], now=datetime.now(timezone.utc))
    r = make_client(world.cg).get(f"{P}/{world.p.id}/report.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == CSV_HEADER
    assert len(rows) == 1 + 90 + 1                                    # header + 90 days + disclaimer
    assert rows[-1][0].startswith("note: ") and "not a diagnosis" in rows[-1][0]
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    row = dict(zip(CSV_HEADER, next(x for x in rows if x[0] == yesterday)))
    assert row["sessions"] == "1" and row["avg_score"] == "80.0" and row["reminders_missed"] == "1"
