"""Post-sync insights pipeline.

Public contract (fixed by the briefing):
    process_synced_data(session, patient_id, session_ids: list[UUID]) -> None

Behaviour:
  1. Build cue observations from the newly synced game events, call services/ai
     (/ai/triggers/update, /ai/severity/estimate; 3 s timeout, graceful fallback).
  2. Upsert memory_triggers (+ record_change) and append a severity_indicators row.
  3. Evaluate the four alert rules (score_drop, activity_drop, missed_reminders, severity),
     never creating a second OPEN alert of the same kind per patient (+ record_change).

It COMMITS its own work and NEVER raises: the synced data was already committed by the sync
module, so an insights failure must not turn a successful /sync/push into a 500.
`scan_all_patients` runs the same rules periodically, because activity_drop cannot fire from a
sync (a sync means the patient just played).
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    EmotionSample,
    GameEvent,
    GameSession,
    MediaAsset,
    MemoryTrigger,
    Reminder,
    ReminderEvent,
    SeverityIndicator,
    User,
)
from app.modules.sync.changelog import record_change

from . import rules
from ._util import as_utc, utcnow, uuid7
from .ai_client import SeverityResponse, TriggerOut, get_ai_client

log = logging.getLogger(__name__)

# `entity` names passed to record_change = the table names used in the sync contract's pull list.
# ASSUMPTION to confirm with Claude 1.4 (one-line change here if they differ).
ENTITY_ALERT = "alerts"
ENTITY_TRIGGER = "memory_triggers"

MAX_OBSERVATIONS = 2000
SAMPLE_CAP = 5000
BASELINE_SAMPLES = 30


@dataclass
class AlertChange:
    alert: Alert
    action: str  # 'created' | 'escalated'


@dataclass
class PipelineResult:
    ai_available: bool = True
    triggers_updated: int = 0
    severity_stored: bool = False
    alert_changes: list[AlertChange] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# payload helpers (JSON-safe dicts for the sync change log)
# --------------------------------------------------------------------------------------
def _iso(dt: datetime | None) -> str | None:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


def alert_payload(a: Alert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "patient_id": str(a.patient_id),
        "kind": str(getattr(a.kind, "value", a.kind)),
        "severity": str(getattr(a.severity, "value", a.severity)),
        "message": a.message,
        "created_at": _iso(a.created_at),
        "acknowledged_by": str(a.acknowledged_by) if a.acknowledged_by else None,
        "acknowledged_at": _iso(a.acknowledged_at),
        "note": a.note,
    }


def trigger_payload(t: MemoryTrigger) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "patient_id": str(t.patient_id),
        "cue_id": str(t.cue_id),
        "cue_type": t.cue_type,
        "valence_label": t.valence_label,
        "confidence": t.confidence,
        "last_validated_at": _iso(t.last_validated_at),
        "half_life_days": t.half_life_days,
        "updated_at": _iso(t.updated_at),
    }


# --------------------------------------------------------------------------------------
# public entry points
# --------------------------------------------------------------------------------------
def process_synced_data(session: Session, patient_id: UUID, session_ids: list[UUID]) -> None:
    try:
        _run(session, patient_id, list(session_ids), now=utcnow())
        session.commit()
    except Exception:  # noqa: BLE001 - must never break the sync endpoint
        session.rollback()
        log.exception("insights pipeline failed for patient %s", patient_id)


def scan_all_patients(session: Session, now: datetime | None = None, use_ai: bool = True) -> dict[str, int]:
    """Periodic pass over every patient (cron/loop via `python -m app.modules.insights.scan`).
    Circuit breaker: after the first AI failure the AI is not called again in this pass."""
    now = now or utcnow()
    ai = get_ai_client() if use_ai else None
    ai_ok = use_ai
    summary = {"patients": 0, "alerts_changed": 0, "errors": 0}
    patient_ids = list(session.scalars(select(User.id).where(User.role == "patient")))
    for pid in patient_ids:
        try:
            res = _run(session, pid, [], now=now, ai=ai, skip_ai=not ai_ok)
            session.commit()
            summary["patients"] += 1
            summary["alerts_changed"] += len(res.alert_changes)
            if ai_ok and not res.ai_available:
                ai_ok = False
        except Exception:  # noqa: BLE001
            session.rollback()
            summary["errors"] += 1
            log.exception("insights scan failed for patient %s", pid)
    return summary


def _run(
    session: Session,
    patient_id: UUID,
    session_ids: Sequence[UUID],
    now: datetime,
    ai=None,
    skip_ai: bool = False,
) -> PipelineResult:
    result = PipelineResult()
    severity: SeverityResponse | None = None

    if not skip_ai:
        ai = ai or get_ai_client()
        observations, cue_types = _build_observations(session, patient_id, session_ids)
        if observations:
            triggers = ai.update_triggers(patient_id, observations)
            if triggers is None:
                result.ai_available = False
            else:
                result.triggers_updated = _upsert_triggers(session, patient_id, triggers, cue_types, now)
        severity = ai.estimate_severity(
            patient_id, rules.SEVERITY_WINDOW_DAYS, _perf_samples(session, patient_id, now)
        )
        if severity is None:
            result.ai_available = False
        else:
            _store_severity(session, patient_id, severity, now)
            result.severity_stored = True
    else:
        result.ai_available = False

    result.alert_changes = evaluate_alerts(session, patient_id, now, severity=severity)
    return result


# --------------------------------------------------------------------------------------
# step 1: observations for /ai/triggers/update
# --------------------------------------------------------------------------------------
def _build_observations(
    session: Session, patient_id: UUID, session_ids: Sequence[UUID]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """One observation per answered event (correct set).

    With-cue trials carry their real cue_id. D2 / CCR-2: services/ai requires a non-empty cue_id, so
    without-cue trials get the synthetic stand-in ``no_cue:<domain>`` (cue_type ``none``, valence ``neutral``).
    Cue metadata comes from the caregiver's media asset when cue_id is a media id (kind -> cue_type,
    emotion-label tag -> valence); otherwise from known triggers, then the session's dominant emotion.
    """
    if not session_ids:
        return [], {}
    events = session.scalars(
        select(GameEvent)
        .where(
            GameEvent.patient_id == patient_id,
            GameEvent.session_id.in_(list(session_ids)),
            GameEvent.correct.is_not(None),
        )
        .order_by(GameEvent.ts)
        .limit(MAX_OBSERVATIONS)
    ).all()
    if not events:
        return [], {}

    domains = {
        sid: dom
        for sid, dom in session.execute(
            select(GameSession.id, GameSession.domain).where(GameSession.id.in_(list(session_ids)))
        )
    }
    cue_ids = sorted({str(e.cue_id) for e in events if e.cue_id is not None})
    known = {
        str(t.cue_id): t
        for t in session.scalars(
            select(MemoryTrigger).where(MemoryTrigger.patient_id == patient_id, MemoryTrigger.cue_id.in_(cue_ids))
        )
    } if cue_ids else {}
    media = _media_cues(session, patient_id, cue_ids)
    dominant = _dominant_valence_by_session(session, patient_id, session_ids)

    observations: list[dict[str, Any]] = []
    cue_types: dict[str, str] = {}
    for e in events:
        if e.cue_id is None:
            cid = f"no_cue:{domains.get(e.session_id, 'memory')}"
            cue_type, valence = "none", "neutral"
        else:
            cid = str(e.cue_id)
            if cid in known:
                cue_type, valence = known[cid].cue_type, known[cid].valence_label
            elif cid in media:
                cue_type, valence = media[cid][0], media[cid][1] or dominant.get(e.session_id, "familiarity")
            else:
                cue_type, valence = "unknown", dominant.get(e.session_id, "neutral")
        cue_types.setdefault(cid, cue_type)
        observations.append(
            {
                "cue_id": cid,
                "cue_type": cue_type,
                "valence_label": valence,
                "recalled": bool(e.correct),
                "with_cue": bool(e.with_cue) if e.cue_id is not None else False,
                "ts": _iso(e.ts),
            }
        )
    return observations, cue_types


def _perf_samples(session: Session, patient_id: UUID, now: datetime) -> list[dict[str, Any]]:
    """D5: answered game events (window + the patient's first BASELINE_SAMPLES) as services/ai PerfSamples.

    The AI keeps its own Store and de-duplicates samples by content hash, so re-sending is idempotent.
    """
    start = now - timedelta(days=rules.SEVERITY_WINDOW_DAYS)
    base = (
        select(GameEvent, GameSession.difficulty, GameSession.game_id)
        .join(GameSession, GameSession.id == GameEvent.session_id)
        .where(GameEvent.patient_id == patient_id, GameEvent.correct.is_not(None))
    )
    recent = session.execute(base.where(GameEvent.ts >= start).order_by(GameEvent.ts.desc()).limit(SAMPLE_CAP)).all()
    earliest = session.execute(base.order_by(GameEvent.ts.asc()).limit(BASELINE_SAMPLES)).all()
    rows = {r[0].id: r for r in [*earliest, *recent]}
    hints: Counter = Counter(
        (sid, item)
        for sid, item in session.execute(
            select(GameEvent.session_id, GameEvent.item_id).where(
                GameEvent.patient_id == patient_id, GameEvent.type == "hint_used"
            )
        )
    )
    out: list[dict[str, Any]] = []
    for ev, difficulty, game_id in sorted(rows.values(), key=lambda r: r[0].ts):
        out.append(
            {
                "ts": _iso(ev.ts),
                "source": "cue" if ev.cue_id is not None else "game",
                "correct": bool(ev.correct),
                "response_ms": ev.response_ms,
                "hints": min(hints.get((ev.session_id, ev.item_id), 0), 50),
                "difficulty": max(1, min(10, int(difficulty))) if difficulty else None,
                "with_cue": bool(ev.with_cue),
                "game_id": str(game_id)[:64],
            }
        )
    return out[:SAMPLE_CAP]


def _media_cues(session: Session, patient_id: UUID, cue_ids: Sequence[str]) -> dict[str, tuple[str, str | None]]:
    """cue_id (== media_assets.id) -> (cue_type, valence tag or None). Non-UUID ids are ignored."""
    ids: list[UUID] = []
    for c in cue_ids:
        try:
            ids.append(UUID(c))
        except ValueError:
            continue
    if not ids:
        return {}
    out: dict[str, tuple[str, str | None]] = {}
    for m in session.scalars(select(MediaAsset).where(MediaAsset.patient_id == patient_id, MediaAsset.id.in_(ids))):
        tags = m.tags if isinstance(m.tags, list) else []
        valence = next((t for t in tags if isinstance(t, str) and t in rules.EMOTION_LABELS), None)
        out[str(m.id)] = (m.kind, valence)
    return out


def _dominant_valence_by_session(
    session: Session, patient_id: UUID, session_ids: Sequence[UUID]
) -> dict[Any, str]:
    rows = session.execute(
        select(EmotionSample.session_id, EmotionSample.label, func.count())
        .where(
            EmotionSample.patient_id == patient_id,
            EmotionSample.session_id.in_(list(session_ids)),
            EmotionSample.label.in_(sorted(rules.POSITIVE_LABELS)),
        )
        .group_by(EmotionSample.session_id, EmotionSample.label)
    ).all()
    per_session: dict[Any, Counter] = defaultdict(Counter)
    for sid, label, n in rows:
        per_session[sid][label] += n
    out: dict[Any, str] = {}
    for sid, counter in per_session.items():
        # most common; ties broken alphabetically for determinism
        out[sid] = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return out


# --------------------------------------------------------------------------------------
# step 2: persist AI output
# --------------------------------------------------------------------------------------
def _upsert_triggers(
    session: Session,
    patient_id: UUID,
    triggers: list[TriggerOut],
    cue_types: dict[str, str],
    now: datetime,
) -> int:
    count = 0
    for t in triggers:
        if t.cue_id.startswith("no_cue:"):
            continue  # D2: synthetic baseline arm, never stored or synced as a memory trigger
        label = t.valence_label if t.valence_label in rules.EMOTION_LABELS else "neutral"
        confidence = min(max(float(t.confidence), 0.0), 1.0)
        row = session.scalars(
            select(MemoryTrigger).where(MemoryTrigger.patient_id == patient_id, MemoryTrigger.cue_id == t.cue_id).limit(1)
        ).first()
        if row is None:
            row = MemoryTrigger(
                id=uuid7(),
                patient_id=patient_id,
                cue_id=t.cue_id,
                cue_type=cue_types.get(t.cue_id, "unknown"),
                valence_label=label,
                confidence=confidence,
                last_validated_at=as_utc(t.last_validated_at),
                half_life_days=t.half_life_days,
                updated_at=now,
            )
            session.add(row)
        else:
            row.valence_label = label
            row.confidence = confidence
            row.last_validated_at = as_utc(t.last_validated_at)
            row.half_life_days = t.half_life_days
            row.updated_at = now
        session.flush()
        record_change(session, ENTITY_TRIGGER, row.id, "upsert", trigger_payload(row), patient_id)
        count += 1
    return count


def _store_severity(session: Session, patient_id: UUID, sev: SeverityResponse, now: datetime) -> None:
    """Append-only history; the dashboard reads the latest row by computed_at."""
    session.add(
        SeverityIndicator(
            id=uuid7(),
            patient_id=patient_id,
            band=sev.band,
            gds_style_indicator=sev.gds_style_indicator,
            drivers=sev.drivers,
            computed_at=now,
        )
    )
    session.flush()


# --------------------------------------------------------------------------------------
# step 3: alert rules (DB queries here, decisions in rules.py)
# --------------------------------------------------------------------------------------
def evaluate_alerts(
    session: Session, patient_id: UUID, now: datetime, severity: SeverityResponse | None = None
) -> list[AlertChange]:
    decisions: list[rules.AlertDecision] = []

    # score_drop: one conditional-aggregate query over a 14-day window
    recent_start = now - timedelta(days=rules.SCORE_WINDOW_DAYS)
    prev_start = now - timedelta(days=2 * rules.SCORE_WINDOW_DAYS)
    recent = case((GameSession.started_at >= recent_start, GameSession.score))
    prev = case((GameSession.started_at < recent_start, GameSession.score))
    r_avg, r_n, p_avg, p_n = session.execute(
        select(func.avg(recent), func.count(recent), func.avg(prev), func.count(prev)).where(
            GameSession.patient_id == patient_id,
            GameSession.score.is_not(None),
            GameSession.started_at >= prev_start,
            GameSession.started_at <= now,
        )
    ).one()
    d = rules.evaluate_score_drop(r_avg, p_avg, r_n or 0, p_n or 0)
    if d:
        decisions.append(d)

    # activity_drop
    last = session.scalar(
        select(func.max(GameSession.started_at)).where(
            GameSession.patient_id == patient_id, GameSession.started_at <= now
        )
    )
    d = rules.evaluate_activity_drop(as_utc(last), now)
    if d:
        decisions.append(d)

    # missed_reminders
    d = rules.evaluate_missed_reminders(_reminder_histories(session, patient_id, now))
    if d:
        decisions.append(d)

    # severity (only when the AI answered this run)
    if severity is not None:
        d = rules.evaluate_severity_band(severity.band, severity.gds_style_indicator)
        if d:
            decisions.append(d)

    changes: list[AlertChange] = []
    for decision in decisions:
        change = _apply_decision(session, patient_id, decision, now)
        if change:
            changes.append(change)
    return changes


def _reminder_histories(session: Session, patient_id: UUID, now: datetime) -> list[rules.ReminderHistory]:
    reminders = session.scalars(
        select(Reminder).where(
            Reminder.patient_id == patient_id,
            Reminder.active.is_(True),
            Reminder.escalate_after_misses >= 1,
        )
    ).all()
    if not reminders:
        return []
    since = now - timedelta(days=rules.MISSED_LOOKBACK_DAYS)
    rows = session.execute(
        select(ReminderEvent.reminder_id, ReminderEvent.status)
        .where(
            ReminderEvent.patient_id == patient_id,
            ReminderEvent.due_at >= since,
            ReminderEvent.due_at <= now,
        )
        .order_by(ReminderEvent.reminder_id, ReminderEvent.due_at.desc())
    ).all()
    by_reminder: dict[Any, list[str]] = defaultdict(list)
    for rid, status in rows:
        by_reminder[rid].append(str(getattr(status, "value", status)))
    return [
        rules.ReminderHistory(
            reminder_id=r.id,
            title=r.title,
            category=str(getattr(r.category, "value", r.category)),
            escalate_after_misses=r.escalate_after_misses,
            statuses_newest_first=tuple(by_reminder.get(r.id, ())),
        )
        for r in reminders
    ]


def _apply_decision(
    session: Session, patient_id: UUID, decision: rules.AlertDecision, now: datetime
) -> AlertChange | None:
    """De-duplication: at most one OPEN (unacknowledged) alert per (patient, kind).
    If one exists and the new decision is MORE severe, escalate it in place; otherwise do nothing."""
    existing = session.scalars(
        select(Alert)
        .where(Alert.patient_id == patient_id, Alert.kind == decision.kind, Alert.acknowledged_at.is_(None))
        .order_by(Alert.created_at.desc())
        .limit(1)
    ).first()
    if existing is not None:
        if rules.should_escalate(str(getattr(existing.severity, "value", existing.severity)), decision.severity):
            existing.severity = decision.severity
            existing.message = decision.message
            session.flush()
            record_change(session, ENTITY_ALERT, existing.id, "upsert", alert_payload(existing), patient_id)
            return AlertChange(existing, "escalated")
        return None
    alert = Alert(
        id=uuid7(),
        patient_id=patient_id,
        kind=decision.kind,
        severity=decision.severity,
        message=decision.message,
        created_at=now,
    )
    session.add(alert)
    session.flush()
    record_change(session, ENTITY_ALERT, alert.id, "upsert", alert_payload(alert), patient_id)
    return AlertChange(alert, "created")
