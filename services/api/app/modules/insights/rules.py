"""Pure alert rules + constants. NO database, NO framework imports: easy to unit-test and,
because it is plain Python, reusable if the rules are ever mirrored on-device.

Thresholds marked [spec] come from the briefing; the rest are my documented assumptions
(see HANDOFF.md, "Assumptions").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DISCLAIMER = (
    "SMARAN is a support tool, not a diagnosis. Scores and severity indicators are estimates "
    "to help caregivers and health workers notice changes; please consult a qualified "
    "healthcare professional for any medical decision."
)

EMOTION_LABELS = frozenset(
    {"joy", "comfort", "excitement", "amusement", "familiarity", "neutral", "negative"}
)
POSITIVE_LABELS = frozenset({"joy", "comfort", "excitement", "amusement", "familiarity"})

SEVERITY_RANK = {"info": 0, "watch": 1, "alert": 2}

# --- score_drop -------------------------------------------------------------------------
SCORE_WINDOW_DAYS = 7                 # [spec]
SCORE_DROP_THRESHOLD = 0.20           # [spec] "down more than 20%"
SCORE_DROP_ALERT_THRESHOLD = 0.40     # assumption: >= 40% drop escalates watch -> alert
MIN_SCORED_SESSIONS = 1               # assumption: per window; raise after pilot to cut noise
# --- activity_drop ----------------------------------------------------------------------
ACTIVITY_DROP_DAYS = 3                # [spec]
ACTIVITY_DROP_ALERT_DAYS = 7          # assumption
# --- missed_reminders -------------------------------------------------------------------
MISSED_LOOKBACK_DAYS = 14             # assumption: only recent reminder events are considered
# --- severity ---------------------------------------------------------------------------
SEVERITY_WINDOW_DAYS = 14             # assumption: window_days sent to /ai/severity/estimate

_EPS = 1e-9


@dataclass(frozen=True)
class AlertDecision:
    kind: str
    severity: str
    message: str


@dataclass(frozen=True)
class ReminderHistory:
    """Recent outcomes of ONE reminder, newest first (statuses: done | later | missed)."""

    reminder_id: object
    title: str
    category: str
    escalate_after_misses: int
    statuses_newest_first: tuple[str, ...]


def severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get(severity, -1)


def should_escalate(existing_severity: str, new_severity: str) -> bool:
    return severity_rank(new_severity) > severity_rank(existing_severity)


def evaluate_score_drop(
    recent_avg: float | None, prev_avg: float | None, recent_n: int, prev_n: int
) -> AlertDecision | None:
    """7-day average score down MORE than 20% vs the previous 7 days."""
    if recent_avg is None or prev_avg is None:
        return None
    if recent_n < MIN_SCORED_SESSIONS or prev_n < MIN_SCORED_SESSIONS:
        return None
    if prev_avg <= 0:
        return None
    drop = (prev_avg - recent_avg) / prev_avg
    if drop <= SCORE_DROP_THRESHOLD + _EPS:
        return None
    severity = "alert" if drop >= SCORE_DROP_ALERT_THRESHOLD - _EPS else "watch"
    pct = round(drop * 100)
    return AlertDecision(
        kind="score_drop",
        severity=severity,
        message=(
            f"Average game score over the last {SCORE_WINDOW_DAYS} days is about {pct}% lower than "
            f"in the {SCORE_WINDOW_DAYS} days before. A gentle check-in may help. "
            "(Support indicator only, not a diagnosis.)"
        ),
    )


def evaluate_activity_drop(last_session_at: datetime | None, now: datetime) -> AlertDecision | None:
    """No sessions for 3 days. A patient with no sessions ever is not flagged (nothing to compare)."""
    if last_session_at is None:
        return None
    elapsed = now - last_session_at
    if elapsed < timedelta(days=ACTIVITY_DROP_DAYS):
        return None
    days = int(elapsed.total_seconds() // 86400)
    severity = "alert" if days >= ACTIVITY_DROP_ALERT_DAYS else "watch"
    return AlertDecision(
        kind="activity_drop",
        severity=severity,
        message=f"No games have been played for {days} days. A friendly nudge or visit might help.",
    )


def missed_streak(statuses_newest_first: tuple[str, ...] | list[str]) -> int:
    n = 0
    for s in statuses_newest_first:
        if s != "missed":
            break
        n += 1
    return n


def evaluate_missed_reminders(histories: list[ReminderHistory]) -> AlertDecision | None:
    """A reminder escalates when its most recent `escalate_after_misses` outcomes are ALL 'missed'
    (a 'done' or 'later' response breaks the streak). One alert per patient for all reminders."""
    hits: list[tuple[ReminderHistory, int]] = []
    for h in histories:
        if h.escalate_after_misses is None or h.escalate_after_misses < 1:
            continue
        streak = missed_streak(h.statuses_newest_first)
        if streak >= h.escalate_after_misses:
            hits.append((h, streak))
    if not hits:
        return None
    severity = "alert" if any(h.category == "medicine" for h, _ in hits) else "watch"
    first, streak = hits[0]
    if len(hits) == 1:
        message = f'Reminder "{first.title}" was missed {streak} times in a row.'
    else:
        message = (
            f'{len(hits)} reminders were missed several times in a row, including "{first.title}" '
            f"({streak} times)."
        )
    return AlertDecision(kind="missed_reminders", severity=severity, message=message)


def evaluate_severity_band(band: str, gds_style_indicator: int | None) -> AlertDecision | None:
    if band not in ("watch", "alert"):
        return None
    suffix = f" (support indicator {gds_style_indicator}/7)" if gds_style_indicator else ""
    return AlertDecision(
        kind="severity",
        severity=band,
        message=(
            f"The overall support indicator is in the '{band}' range{suffix}. Consider reviewing "
            "with a health worker or clinician. (Not a diagnosis.)"
        ),
    )
