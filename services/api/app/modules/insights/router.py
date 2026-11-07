"""Insights routes (all under /api/v1; main.py adds the prefix). Shapes are binding (ROUTES, 1.5).

RBAC: every route needs a staff role (caregiver | health_worker | admin); the elder-facing
patient role never sees alerts, severity or scores. Patient-scoped routes then call
assert_can_access_patient. Day buckets are UTC days.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Date, case, cast, extract, func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import assert_can_access_patient, get_current_user
from app.models import Alert, CaregiverLink, GameEvent, GameSession, MemoryTrigger, ReminderEvent, SeverityIndicator, User
from app.modules.sync.changelog import record_change

from . import rules
from ._util import enum_value, utcnow
from .pipeline import ENTITY_ALERT, alert_payload
from .schemas import (
    AckIn,
    AlertOut,
    CueComparisonOut,
    CueStats,
    DomainCue,
    SeverityOut,
    TrendDay,
    TrendsOut,
    TriggerRow,
)

router = APIRouter(tags=["insights"])

STAFF_ROLES = {"caregiver", "health_worker", "admin"}
REPORT_DAYS = 90
MAX_ALERTS = 500


def staff_user(user: User = Depends(get_current_user)) -> User:
    if str(enum_value(user.role)) not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Insights are available to caregivers and health workers only")
    return user


# --------------------------------------------------------------------------------------
# SQL helpers (dialect-aware so tests run on SQLite and production on PostgreSQL 16)
# --------------------------------------------------------------------------------------
def _dialect(session: Session) -> str:
    return session.get_bind().dialect.name


def _day_expr(col, dialect: str):
    if dialect == "postgresql":
        return cast(func.timezone("UTC", col), Date)
    return func.date(col)


def _minutes_between(start_col, end_col, dialect: str):
    if dialect == "postgresql":
        raw = extract("epoch", end_col - start_col) / 60.0
    else:
        raw = (func.julianday(end_col) - func.julianday(start_col)) * 1440.0
    return case((end_col >= start_col, raw), else_=0.0)  # NULL end_at -> NULL -> ignored by SUM


def _round(v: Any, nd: int) -> float | None:
    return None if v is None else round(float(v), nd)


def _window(days: int) -> tuple[date, datetime, datetime]:
    today = utcnow().date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, tzinfo=timezone.utc)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return first, start, end


def _trend_days(session: Session, patient_id: UUID, days: int) -> list[TrendDay]:
    """Dense list: one entry per UTC day (zeros / nulls on days without activity)."""
    dialect = _dialect(session)
    first, start, end = _window(days)

    sday = _day_expr(GameSession.started_at, dialect).label("day")
    srows = session.execute(
        select(
            sday,
            func.count(GameSession.id),
            func.avg(GameSession.score),
            func.coalesce(func.sum(_minutes_between(GameSession.started_at, GameSession.ended_at, dialect)), 0.0),
        )
        .where(GameSession.patient_id == patient_id, GameSession.started_at >= start, GameSession.started_at < end)
        .group_by(sday)
    ).all()
    sessions = {str(r[0]): r for r in srows}

    eday = _day_expr(GameEvent.ts, dialect).label("day")
    erows = session.execute(
        select(eday, func.avg(GameEvent.response_ms))
        .where(
            GameEvent.patient_id == patient_id,
            GameEvent.ts >= start,
            GameEvent.ts < end,
            GameEvent.response_ms.is_not(None),
        )
        .group_by(eday)
    ).all()
    resp = {str(r[0]): r[1] for r in erows}

    out: list[TrendDay] = []
    for i in range(days):
        key = (first + timedelta(days=i)).isoformat()
        s = sessions.get(key)
        out.append(
            TrendDay(
                date=key,
                sessions=int(s[1]) if s else 0,
                avg_score=_round(s[2], 2) if s else None,
                avg_response_ms=_round(resp.get(key), 1),
                engagement_minutes=_round(s[3], 1) if s else 0.0,
            )
        )
    return out


def _accessible_patients_subquery(user: User):
    """None = unrestricted (admin). Assumes health_worker access is also stored in caregiver_links."""
    role = str(enum_value(user.role))
    if role == "admin":
        return None
    return select(CaregiverLink.patient_id).where(CaregiverLink.caregiver_id == user.id)


# --------------------------------------------------------------------------------------
# alerts
# --------------------------------------------------------------------------------------
@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    patient_id: UUID | None = None,
    status: Literal["open", "all"] = "open",
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> list[AlertOut]:
    q = select(Alert)
    if patient_id is not None:
        assert_can_access_patient(session, user, patient_id)
        q = q.where(Alert.patient_id == patient_id)
    else:
        sub = _accessible_patients_subquery(user)
        if sub is not None:
            q = q.where(Alert.patient_id.in_(sub))
    if status == "open":
        q = q.where(Alert.acknowledged_at.is_(None))
    rows = session.scalars(q.order_by(Alert.created_at.desc()).limit(MAX_ALERTS)).all()
    return [AlertOut.model_validate(a) for a in rows]


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
def ack_alert(
    alert_id: UUID,
    body: AckIn | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> AlertOut:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    assert_can_access_patient(session, user, alert.patient_id)
    if alert.acknowledged_at is None:  # idempotent: a second ack changes nothing
        alert.acknowledged_by = user.id
        alert.acknowledged_at = utcnow()
        alert.note = body.note if body else None
        session.flush()
        record_change(session, ENTITY_ALERT, alert.id, "upsert", alert_payload(alert), alert.patient_id)
        session.commit()
    return AlertOut.model_validate(alert)


# --------------------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------------------
@router.get("/patients/{patient_id}/dashboard/trends", response_model=TrendsOut)
def trends(
    patient_id: UUID,
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> TrendsOut:
    assert_can_access_patient(session, user, patient_id)
    return TrendsOut(days=_trend_days(session, patient_id, days))


@router.get("/patients/{patient_id}/dashboard/cue-comparison", response_model=CueComparisonOut)
def cue_comparison(
    patient_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> CueComparisonOut:
    """Answered items (correct IS NOT NULL), all time. accuracy is a 0..1 fraction."""
    assert_can_access_patient(session, user, patient_id)
    correct_num = case((GameEvent.correct.is_(True), 1.0), else_=0.0)
    rows = session.execute(
        select(
            GameSession.domain,
            GameEvent.with_cue,
            func.count(GameEvent.id),
            func.avg(correct_num),
            func.avg(GameEvent.response_ms),
            func.count(GameEvent.response_ms),
        )
        .select_from(GameEvent)
        .join(GameSession, GameSession.id == GameEvent.session_id)
        .where(GameEvent.patient_id == patient_id, GameEvent.correct.is_not(None))
        .group_by(GameSession.domain, GameEvent.with_cue)
    ).all()

    tot = {True: [0, 0.0, 0.0, 0], False: [0, 0.0, 0.0, 0]}  # n, correct_sum, resp_sum, resp_n
    domains: dict[str, dict[bool, float | None]] = {}
    for domain, with_cue, n, acc, avg_resp, resp_n in rows:
        key = bool(with_cue)
        t = tot[key]
        t[0] += n
        t[1] += float(acc or 0.0) * n
        if avg_resp is not None:
            t[2] += float(avg_resp) * resp_n
            t[3] += resp_n
        domains.setdefault(domain, {True: None, False: None})[key] = _round(acc, 4)

    def stats(key: bool) -> CueStats:
        n, c, r, rn = tot[key]
        return CueStats(n=n, accuracy=_round(c / n, 4) if n else None, avg_response_ms=_round(r / rn, 1) if rn else None)

    return CueComparisonOut(
        with_cue=stats(True),
        without_cue=stats(False),
        by_domain=[
            DomainCue(domain=d, with_cue_accuracy=v[True], without_cue_accuracy=v[False])
            for d, v in sorted(domains.items())
        ],
    )


@router.get("/patients/{patient_id}/dashboard/triggers", response_model=list[TriggerRow])
def triggers(
    patient_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> list[TriggerRow]:
    assert_can_access_patient(session, user, patient_id)
    rows = session.scalars(
        select(MemoryTrigger).where(MemoryTrigger.patient_id == patient_id).order_by(MemoryTrigger.confidence.desc())
    ).all()
    return [TriggerRow.model_validate(t) for t in rows]


@router.get("/patients/{patient_id}/dashboard/severity", response_model=SeverityOut)
def severity(
    patient_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> SeverityOut:
    """Latest stored indicator. With no data yet: 200 with nulls (an honest 'not enough data')."""
    assert_can_access_patient(session, user, patient_id)
    row = session.scalars(
        select(SeverityIndicator)
        .where(SeverityIndicator.patient_id == patient_id)
        .order_by(SeverityIndicator.computed_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return SeverityOut(band=None, gds_style_indicator=None, drivers=[], disclaimer=rules.DISCLAIMER, computed_at=None)
    return SeverityOut(
        band=str(enum_value(row.band)),
        gds_style_indicator=row.gds_style_indicator,
        drivers=list(row.drivers or []),
        disclaimer=rules.DISCLAIMER,
        computed_at=row.computed_at,
    )


# --------------------------------------------------------------------------------------
# CSV report
# --------------------------------------------------------------------------------------
CSV_HEADER = [
    "date", "sessions", "avg_score", "avg_response_ms", "engagement_minutes",
    "with_cue_answers", "with_cue_accuracy", "without_cue_answers", "without_cue_accuracy",
    "reminders_done", "reminders_later", "reminders_missed",
]  # fmt: skip


@router.get("/patients/{patient_id}/report.csv")
def report_csv(
    patient_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(staff_user),
) -> Response:
    """Daily table for the last 90 UTC days. The last row carries the support-tool disclaimer."""
    assert_can_access_patient(session, user, patient_id)
    dialect = _dialect(session)
    _, start, end = _window(REPORT_DAYS)
    days = _trend_days(session, patient_id, REPORT_DAYS)

    eday = _day_expr(GameEvent.ts, dialect).label("day")
    correct_num = case((GameEvent.correct.is_(True), 1.0), else_=0.0)
    cue: dict[tuple[str, bool], tuple[int, float | None]] = {}
    for day, with_cue, n, acc in session.execute(
        select(eday, GameEvent.with_cue, func.count(GameEvent.id), func.avg(correct_num))
        .where(
            GameEvent.patient_id == patient_id,
            GameEvent.correct.is_not(None),
            GameEvent.ts >= start,
            GameEvent.ts < end,
        )
        .group_by(eday, GameEvent.with_cue)
    ).all():
        cue[(str(day), bool(with_cue))] = (int(n), _round(acc, 4))

    rday = _day_expr(ReminderEvent.due_at, dialect).label("day")
    rem: dict[tuple[str, str], int] = {}
    for day, status, n in session.execute(
        select(rday, ReminderEvent.status, func.count(ReminderEvent.id))
        .where(ReminderEvent.patient_id == patient_id, ReminderEvent.due_at >= start, ReminderEvent.due_at < end)
        .group_by(rday, ReminderEvent.status)
    ).all():
        rem[(str(day), str(enum_value(status)))] = int(n)

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_HEADER)

    def cell(v):
        return "" if v is None else v

    for d in days:
        wc = cue.get((d.date, True), (0, None))
        woc = cue.get((d.date, False), (0, None))
        w.writerow([
            d.date, d.sessions, cell(d.avg_score), cell(d.avg_response_ms), d.engagement_minutes,
            wc[0], cell(wc[1]), woc[0], cell(woc[1]),
            rem.get((d.date, "done"), 0), rem.get((d.date, "later"), 0), rem.get((d.date, "missed"), 0),
        ])  # fmt: skip
    w.writerow(["note: " + rules.DISCLAIMER])

    filename = f"smaran_report_{patient_id}_{utcnow().date().isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
