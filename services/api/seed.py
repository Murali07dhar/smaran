"""Seed realistic DEMO data so the dashboard looks real. DEV ONLY.

    python seed.py            # seed (no-op if already seeded)
    python seed.py --reset    # delete the demo users (cascades) and re-seed
    python seed.py --days 30  # history length

Creates: 1 caregiver, 1 health worker, 2 patients (+ profiles, links, consents), and for each patient
30 days of game_sessions / game_events / reminder_events, plus memory_triggers, alerts, severity
indicators, reminders, routines, a few emotion_samples (only where camera consent is granted) and the
matching sync_changes rows so a fresh device can /sync/pull everything.

Story: Bimala (as, mild) trends gently up; cues help. Tomba (mni, moderate) trends down over the last
~10 days -> score_drop / missed_reminders alerts and a 'watch' severity band.
Ids are deterministic (uuid5) so re-running is idempotent; timestamps are relative to "now".
Seeded game ids, cue ids, routine step shape and severity `drivers` shape are PLACEHOLDERS owned by
workstreams 4/1.3/2 - replace when those land.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password, hash_pin
from app.models import (
    Alert,
    CaregiverLink,
    ConsentRecord,
    EmotionSample,
    GameEvent,
    GameSession,
    MemoryTrigger,
    PatientProfile,
    Reminder,
    ReminderEvent,
    Routine,
    SeverityIndicator,
    SyncChange,
    User,
)

NS = uuid.UUID("5a3a5a4e-2600-4000-8000-000000000000")
IST = timedelta(hours=5, minutes=30)
DEMO_PASSWORD = os.environ.get("SEED_PASSWORD", "Smaran-Demo-123")


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


CAREGIVER_ID, HEALTH_WORKER_ID = uid("user:caregiver"), uid("user:health_worker")
P1, P2 = uid("user:patient:bimala"), uid("user:patient:tomba")
SEEDED_USER_IDS = (P1, P2, CAREGIVER_ID, HEALTH_WORKER_ID)  # patients first (cascade), then staff

GAMES = [
    ("photo_pairs", "memory"),
    ("tap_target", "attention"),
    ("daily_steps", "routine"),
    ("odd_one_out", "pattern_object"),
    ("sequence_builder", "executive"),
]

# patient key -> config
PATIENTS = {
    "bimala": dict(
        id=P1, name="Bimala Das", age=74, lang="as", stage="mild", pin="2468",
        notes="Retired schoolteacher from Jorhat. Loves Bihu songs and tea-garden photos.",
        acc_start=0.60, acc_end=0.73, diff_start=3, diff_end=5, rt_drift=-250,
        done=(0.88, 0.08, 0.04), camera=True, mic=True, relation="daughter",
        cues=[
            ("cue_bihu_dhol", "music", "joy", 0.86, 45),
            ("cue_tea_garden_photo", "photo", "familiarity", 0.81, 60),
            ("cue_mother_lullaby", "voice", "comfort", 0.74, 30),
            ("cue_wedding_photo", "photo", "joy", 0.69, 40),
            ("cue_temple_bell", "sound", "comfort", 0.58, 21),
        ],
    ),
    "tomba": dict(
        id=P2, name="Tomba Singh", age=79, lang="mni", stage="moderate", pin="1357",
        notes="Farmer from Bishnupur, Manipur. Responds to pena music and Loktak lake photos.",
        acc_start=0.68, acc_end=0.40, diff_start=5, diff_end=3, rt_drift=900,
        done=(0.80, 0.12, 0.08), camera=False, mic=False, relation="son",
        cues=[
            ("cue_pena_music", "music", "amusement", 0.77, 40),
            ("cue_loktak_photo", "photo", "familiarity", 0.72, 50),
            ("cue_ima_voice", "voice", "comfort", 0.63, 25),
            ("cue_festival_drum", "sound", "excitement", 0.51, 20),
            ("cue_paddy_field_photo", "photo", "familiarity", 0.44, 18),
        ],
    ),
}

EMOTION_CENTERS = {  # label -> (valence, arousal)
    "joy": (0.8, 0.6), "comfort": (0.6, 0.2), "familiarity": (0.5, 0.3), "amusement": (0.7, 0.5),
    "excitement": (0.7, 0.85), "neutral": (0.0, 0.2), "negative": (-0.6, 0.6),
}
DISCLAIMER = " (Support indicator only - not a diagnosis.)"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def payload_of(obj) -> dict:
    out = {}
    for attr in inspect(obj).mapper.column_attrs:
        v = getattr(obj, attr.key)
        if isinstance(v, bytes):
            continue
        out[attr.key] = v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, uuid.UUID) else v
    return out


def seed_users(s: Session) -> None:
    s.add_all([
        User(id=CAREGIVER_ID, role="caregiver", name="Anita Devi", email="caregiver@smaran.demo",
             phone="+919000000001", password_hash=hash_password(DEMO_PASSWORD), language="as"),
        User(id=HEALTH_WORKER_ID, role="health_worker", name="Rupam Bora (ASHA)", email="healthworker@smaran.demo",
             phone="+919000000002", password_hash=hash_password(DEMO_PASSWORD), language="en"),
    ])
    for cfg in PATIENTS.values():
        s.add(User(id=cfg["id"], role="patient", name=cfg["name"], pin_hash=hash_pin(cfg["pin"]), language=cfg["lang"]))
    s.flush()
    for cfg in PATIENTS.values():
        s.add(PatientProfile(patient_id=cfg["id"], age=cfg["age"], language=cfg["lang"],
                             estimated_stage=cfg["stage"], notes=cfg["notes"]))
        s.add(CaregiverLink(id=uid(f"link:cg:{cfg['id']}"), caregiver_id=CAREGIVER_ID, patient_id=cfg["id"],
                            relation=cfg["relation"]))
        s.add(CaregiverLink(id=uid(f"link:hw:{cfg['id']}"), caregiver_id=HEALTH_WORKER_ID, patient_id=cfg["id"],
                            relation="health_worker"))
    s.flush()


def seed_consents(s: Session, now: datetime) -> None:
    for cfg in PATIENTS.values():
        for kind, granted in (("data_sharing", True), ("camera", cfg["camera"]), ("mic", cfg["mic"])):
            s.add(ConsentRecord(id=uid(f"consent:{cfg['id']}:{kind}"), patient_id=cfg["id"], kind=kind,
                                granted=granted, granted_by=CAREGIVER_ID, ts=now - timedelta(days=31)))


def seed_reminders_and_routines(s: Session, now: datetime) -> dict:
    reminders: dict = {}
    templates = [
        ("medicine", "Morning medicine", "FREQ=DAILY;BYHOUR=8;BYMINUTE=0", (8,), 2),
        ("medicine", "Evening medicine", "FREQ=DAILY;BYHOUR=20;BYMINUTE=0", (20,), 2),
        ("hydration", "Drink a glass of water", "FREQ=DAILY;BYHOUR=10,13,16,19;BYMINUTE=0", (10, 13, 16, 19), 3),
        ("activity", "Evening walk", "FREQ=DAILY;BYHOUR=17;BYMINUTE=30", (17,), 3),
        ("appointment", "Clinic visit", "FREQ=MONTHLY;BYMONTHDAY=15;BYHOUR=11;BYMINUTE=0", (), 1),
    ]
    routines = {
        "bimala": [("Morning routine", ["Wake up and sit on the bed", "Wash face", "Brush teeth", "Get dressed", "Have tea", "Take morning medicine"]),
                   ("Bedtime routine", ["Wash hands and face", "Change into night clothes", "Take evening medicine", "Switch off the light"])],
        "tomba": [("Morning routine", ["Wake up", "Wash face", "Brush teeth", "Get dressed", "Eat breakfast"]),
                  ("Evening routine", ["Light the lamp", "Evening walk", "Have dinner", "Take evening medicine", "Go to bed"])],
    }
    for key, cfg in PATIENTS.items():
        for i, (cat, title, rrule, hours, esc) in enumerate(templates):
            r = Reminder(id=uid(f"reminder:{key}:{i}"), patient_id=cfg["id"], category=cat, title=title,
                         schedule_rrule=rrule, locale=cfg["lang"], voice_clip_id=None,
                         escalate_after_misses=esc, active=True, updated_at=now - timedelta(days=31))
            s.add(r)
            reminders[(key, i)] = (r, hours)
        for j, (title, steps) in enumerate(routines[key]):
            s.add(Routine(id=uid(f"routine:{key}:{j}"), patient_id=cfg["id"], title=title,
                          steps=[{"order": n + 1, "title": t} for n, t in enumerate(steps)],
                          created_by=CAREGIVER_ID, updated_at=now - timedelta(days=31)))
    s.flush()
    return reminders


def seed_reminder_events(s: Session, now: datetime, days: int, reminders: dict, rng: random.Random) -> None:
    today = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for (key, _i), (rem, hours) in reminders.items():
        cfg = PATIENTS[key]
        for d in range(days - 1, -1, -1):
            for h in hours:
                due = today - timedelta(days=d) + timedelta(hours=h) - IST  # local hour -> UTC
                if due > now:
                    continue
                done_p, later_p, _ = cfg["done"]
                if key == "tomba" and d < 10:  # decline: more misses in the last 10 days
                    done_p, later_p = 0.45, 0.20
                x = rng.random()
                if x < done_p:
                    status, ts = "done", due + timedelta(minutes=rng.randint(1, 15))
                elif x < done_p + later_p:
                    status, ts = "later", due + timedelta(minutes=5)
                else:
                    status, ts = "missed", due + timedelta(minutes=60)
                s.add(ReminderEvent(id=uid(f"revent:{rem.id}:{d}:{h}"), reminder_id=rem.id, patient_id=cfg["id"],
                                    due_at=due, status=status, ts=min(ts, now)))


def seed_games(s: Session, now: datetime, days: int, rng: random.Random) -> None:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for key, cfg in PATIENTS.items():
        cue_ids = [c[0] for c in cfg["cues"]]
        for d in range(days - 1, -1, -1):
            progress = (days - 1 - d) / max(days - 1, 1)  # 0 oldest .. 1 today
            slots = [4.5 + rng.uniform(-0.5, 0.5), 10.5 + rng.uniform(-0.7, 0.7)]  # UTC hours (~10:00 / 16:00 IST)
            if key == "tomba" and d < 7:  # activity drop: fewer sessions lately
                slots = slots[:1] if rng.random() < 0.6 else []
            elif rng.random() < 0.1:
                slots = slots[:1]
            for si, hour in enumerate(slots):
                start = today - timedelta(days=d) + timedelta(hours=hour)
                if start > now:
                    continue
                game_id, domain = GAMES[rng.randrange(len(GAMES))]
                difficulty = int(round(cfg["diff_start"] + (cfg["diff_end"] - cfg["diff_start"]) * progress))
                base = cfg["acc_start"] + (cfg["acc_end"] - cfg["acc_start"]) * progress
                sid = uid(f"session:{key}:{d}:{si}")
                n_items, t, correct_n = 8, start, 0
                events: list[GameEvent] = []
                sample_ts = None
                for k in range(n_items):
                    with_cue = rng.random() < 0.5
                    cue = rng.choice(cue_ids) if with_cue else None
                    item = f"{game_id}_item_{k + 1}"
                    if with_cue:
                        events.append(GameEvent(id=uid(f"ev:{sid}:{k}:c"), session_id=sid, patient_id=cfg["id"], type="cue_shown",
                                                item_id=item, correct=None, response_ms=None, cue_id=cue, with_cue=True, ts=t))
                        t += timedelta(seconds=2)
                        sample_ts = sample_ts or t
                    events.append(GameEvent(id=uid(f"ev:{sid}:{k}:s"), session_id=sid, patient_id=cfg["id"], type="item_shown",
                                            item_id=item, correct=None, response_ms=None, cue_id=cue, with_cue=with_cue, ts=t))
                    p = clamp(base + (0.15 if with_cue else 0.0) - 0.03 * (difficulty - 4), 0.05, 0.97)
                    ok = rng.random() < p
                    rt = int(max(700, rng.gauss(3800 - (500 if with_cue else 0) + cfg["rt_drift"] * progress, 900)))
                    t += timedelta(milliseconds=rt)
                    if rng.random() < 0.08:  # occasional hint, shown without penalty language
                        events.append(GameEvent(id=uid(f"ev:{sid}:{k}:h"), session_id=sid, patient_id=cfg["id"], type="hint_used",
                                                item_id=item, correct=None, response_ms=None, cue_id=cue, with_cue=with_cue, ts=t))
                    events.append(GameEvent(id=uid(f"ev:{sid}:{k}:a"), session_id=sid, patient_id=cfg["id"], type="answer",
                                            item_id=item, correct=ok, response_ms=rt, cue_id=cue, with_cue=with_cue, ts=t))
                    correct_n += ok
                    t += timedelta(seconds=rng.randint(2, 5))
                s.add(GameSession(id=sid, patient_id=cfg["id"], game_id=game_id, domain=domain, started_at=start,
                                  ended_at=t, difficulty=difficulty, score=round(100 * correct_n / n_items, 1),
                                  device_id=f"demo-tablet-{key}", server_ts=min(t + timedelta(minutes=2), now)))
                s.flush()  # sessions must exist before events (FK)
                s.add_all(events)
                if cfg["camera"] and sample_ts is not None:  # emotion capture only with camera consent
                    label = rng.choices(list(EMOTION_CENTERS), weights=[35, 20, 20, 10, 5, 8, 2])[0]
                    v, a = EMOTION_CENTERS[label]
                    s.add(EmotionSample(id=uid(f"emo:{sid}"), session_id=sid, patient_id=cfg["id"],
                                        valence=round(clamp(v + rng.gauss(0, 0.1), -1, 1), 2),
                                        arousal=round(clamp(a + rng.gauss(0, 0.1), 0, 1), 2), label=label,
                                        confidence=round(rng.uniform(0.6, 0.95), 2),
                                        source=rng.choice(["face", "fused"]),
                                        caregiver_confirmed=True if rng.random() < 0.15 else None, ts=sample_ts))


def seed_triggers(s: Session, now: datetime) -> list:
    rows = []
    for key, cfg in PATIENTS.items():
        for n, (cue_id, cue_type, label, conf, half_life) in enumerate(cfg["cues"]):
            age_days = n * 2 + (4 if key == "tomba" else 1)
            row = MemoryTrigger(id=uid(f"trigger:{key}:{cue_id}"), patient_id=cfg["id"], cue_id=cue_id, cue_type=cue_type,
                                valence_label=label, confidence=conf, last_validated_at=now - timedelta(days=age_days),
                                half_life_days=float(half_life), updated_at=now - timedelta(days=age_days))
            s.add(row)
            rows.append(row)
    return rows


def seed_alerts_and_severity(s: Session, now: datetime) -> list:
    def A(name, pid, kind, sev, msg, days_ago, ack_by=None, note=None):
        created = now - timedelta(days=days_ago)
        return Alert(id=uid(f"alert:{name}"), patient_id=pid, kind=kind, severity=sev, message=msg, created_at=created,
                     acknowledged_by=ack_by, acknowledged_at=(created + timedelta(hours=5)) if ack_by else None, note=note)

    alerts = [
        A("b1", P1, "severity", "info", "Weekly check: engagement and scores look steady." + DISCLAIMER, 12, CAREGIVER_ID, "Thank you - noted."),
        A("t1", P2, "activity_drop", "info", "Fewer play sessions than usual this week.", 5, HEALTH_WORKER_ID,
          "Spoke to family: Tomba had a cold. Will re-check next visit."),
        A("t2", P2, "score_drop", "watch", "Average game score is about 15% below the previous two weeks. A gentle check-in may help." + DISCLAIMER, 7),
        A("t3", P2, "missed_reminders", "watch", "Several medicine and water reminders were missed over the last 3 days.", 3),
        A("t4", P2, "score_drop", "alert", "Scores have stayed lower for 5 days, mostly on memory games. Consider a visit or call." + DISCLAIMER, 2),
    ]
    s.add_all(alerts)
    sev = {
        P1: [("stable", 2)] * 4,
        P2: [("stable", 3), ("stable", 3), ("watch", 4), ("watch", 4)],
    }
    for pid, series in sev.items():
        for i, (band, gds) in enumerate(series):
            weeks_ago = len(series) - 1 - i
            drivers = [
                {"feature": "game_score_trend", "direction": "down" if pid == P2 and i >= 2 else "flat", "detail": "14-day vs previous 14-day average"},
                {"feature": "reminder_adherence", "direction": "down" if pid == P2 and i >= 2 else "flat", "detail": "share of reminders marked done"},
                {"feature": "engagement", "direction": "down" if pid == P2 and i >= 2 else "flat", "detail": "sessions per day"},
            ]
            s.add(SeverityIndicator(id=uid(f"sev:{pid}:{i}"), patient_id=pid, band=band, gds_style_indicator=gds,
                                    drivers=drivers, computed_at=now - timedelta(days=7 * weeks_ago, minutes=1)))
    return alerts


def seed_sync_changes(s: Session, now: datetime, objs: list) -> None:
    s.flush()
    for o in sorted(objs, key=lambda o: str(o.id)):
        s.add(SyncChange(entity=o.__tablename__, entity_id=o.id, action="upsert", payload=payload_of(o),
                         patient_id=o.patient_id, server_ts=now))


def reset(s: Session) -> None:
    for uid_ in SEEDED_USER_IDS:  # patients first so staff FKs (consent.granted_by...) are released
        s.execute(delete(User).where(User.id == uid_))
    s.flush()


def seed(session: Session, *, days: int = 30, do_reset: bool = False, now: datetime | None = None) -> bool:
    """Returns True if data was written, False if the demo data already existed."""
    now = now or datetime.now(timezone.utc)
    if do_reset:
        reset(session)
    elif session.scalar(select(User.id).where(User.id == CAREGIVER_ID)):
        return False
    rng = random.Random(26003)
    seed_users(session)
    seed_consents(session, now)
    reminders = seed_reminders_and_routines(session, now)
    seed_reminder_events(session, now, days, reminders, rng)
    seed_games(session, now, days, rng)
    triggers = seed_triggers(session, now)
    alerts = seed_alerts_and_severity(session, now)
    session.flush()
    synced = [r for r, _ in reminders.values()] + triggers + alerts
    synced += list(session.scalars(select(Routine)).all())
    seed_sync_changes(session, now, synced)
    session.commit()
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete demo users (cascade) and re-seed")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--force", action="store_true", help="allow running when ENVIRONMENT=production")
    args = ap.parse_args()
    if settings.ENVIRONMENT == "production" and not args.force:
        print("Refusing to seed demo data in production (use --force if you really mean it).", file=sys.stderr)
        return 2
    with SessionLocal() as session:
        wrote = seed(session, days=args.days, do_reset=args.reset)
    if not wrote:
        print("Demo data already present. Use --reset to rebuild.")
        return 0
    print("Seeded demo data.\n"
          f"  caregiver     caregiver@smaran.demo    / {DEMO_PASSWORD}\n"
          f"  health worker healthworker@smaran.demo / {DEMO_PASSWORD}\n"
          f"  patients Bimala Das, Tomba Singh (ids: {P1}, {P2}). Patient PINs are 6 digits, expire in 10 min: issue one from the dashboard (POST /patients/{{id}}/pin).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
