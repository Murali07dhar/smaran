#!/usr/bin/env python
"""Fill the database with fake (clearly synthetic) data for the insights module.

    # against the core_stub + SQLite (no Docker needed):
    PYTHONPATH=services/api DATABASE_URL=sqlite+pysqlite:///./fake.db \
        python mocks/fake_data/fill_fake_data.py --create-tables

    # inside the real stack (real app.models on PYTHONPATH, tables created by Alembic):
    make seed-fake

Creates 1 caregiver (login: fake.caregiver@smaran.test / fake-password-1) and 4 patients:
  Asha  stable       steady scores, cues help, reminders done
  Bimal declining    scores fall ~35% week over week            -> score_drop
  Chandra inactive   last session 5 days ago                     -> activity_drop
  Dolly  missed meds  3 medicine reminders missed in a row       -> missed_reminders
Re-running is safe: if the fake caregiver already exists, nothing is created.
Everything is deterministic (seeded RNG). All names/values are fictional.
"""
from __future__ import annotations

import argparse
import os
import random
import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    CaregiverLink, EmotionSample, GameEvent, GameSession, MemoryTrigger, Reminder, ReminderEvent, User,
)  # fmt: skip

try:
    from app.core.security import hash_password
except Exception:  # noqa: BLE001
    hash_password = None

UTC = timezone.utc
CAREGIVER_EMAIL = "fake.caregiver@smaran.test"
CUES = [("cue-tea-cup", "photo", "comfort"), ("cue-bihu-song", "audio", "joy"), ("cue-old-bicycle", "photo", "familiarity")]
DOMAINS = ["memory", "attention", "routine", "pattern_object", "executive"]


def at(days_ago: int, hour: int = 10, minute: int = 0, now: datetime | None = None) -> datetime:
    base = (now or datetime.now(UTC)) - timedelta(days=days_ago)
    return datetime.combine(base.date(), time(hour, minute), tzinfo=UTC)


def add_sessions(db: Session, rng: random.Random, patient: User, day_scores: dict[int, float]) -> None:
    for days_ago, base_score in day_scores.items():
        started = at(days_ago, 10, rng.randint(0, 30))
        domain = rng.choice(DOMAINS)
        s = GameSession(
            id=uuid.uuid4(), patient_id=patient.id, game_id=f"game-{domain}", domain=domain, started_at=started,
            ended_at=started + timedelta(minutes=rng.randint(6, 14)), difficulty=rng.randint(2, 5),
            score=round(max(0.0, min(100.0, base_score + rng.uniform(-3, 3))), 1), device_id="fake-tablet",
        )  # fmt: skip
        db.add(s)
        db.flush()
        for i in range(8):
            cue_id, _, label = CUES[i % len(CUES)]
            with_cue = i % 2 == 0
            p_correct = (0.80 if with_cue else 0.55) * (base_score / 80.0)
            db.add(GameEvent(
                id=uuid.uuid4(), session_id=s.id, patient_id=patient.id, type="answer", item_id=f"item-{i}",
                correct=rng.random() < p_correct, response_ms=rng.randint(1500, 7000) + (0 if with_cue else 1200),
                cue_id=cue_id if with_cue else None, with_cue=with_cue, ts=started + timedelta(seconds=40 * (i + 1)),
            ))  # fmt: skip
        db.add(EmotionSample(
            id=uuid.uuid4(), session_id=s.id, patient_id=patient.id, valence=0.6, arousal=0.4, label="comfort",
            confidence=0.7, source="fused", caregiver_confirmed=None, ts=started + timedelta(minutes=3),
        ))  # fmt: skip


def add_reminder(db: Session, patient: User, title: str, category: str, statuses_newest_first: list[str]) -> None:
    r = Reminder(
        id=uuid.uuid4(), patient_id=patient.id, category=category, title=title,
        schedule_rrule="FREQ=DAILY;BYHOUR=8;BYMINUTE=0", locale="en", escalate_after_misses=3, active=True,
        server_version=1, updated_at=datetime.now(UTC),
    )  # fmt: skip
    db.add(r)
    db.flush()
    for i, status in enumerate(statuses_newest_first):
        due = at(i + 1, 8, 0)  # +1 so events are never in the future
        db.add(ReminderEvent(id=uuid.uuid4(), reminder_id=r.id, patient_id=patient.id, due_at=due, status=status, ts=due))


def fill(db: Session) -> None:
    if db.scalars(select(User).where(User.email == CAREGIVER_EMAIL)).first():
        print("Fake data already present; nothing to do.")
        return
    rng = random.Random(26003)
    caregiver = User(
        id=uuid.uuid4(), role="caregiver", name="Fake Caregiver", email=CAREGIVER_EMAIL, language="en",
        password_hash=hash_password("fake-password-1") if hash_password else None,
    )  # fmt: skip
    db.add(caregiver)

    steady = {d: 78.0 for d in range(0, 14, 2)}
    declining = {**{d: 52.0 for d in range(0, 7, 2)}, **{d: 82.0 for d in range(8, 14, 2)}}
    inactive = {d: 70.0 for d in range(5, 19, 2)}
    plans = [
        ("Asha (fake)", 74, "as", steady, ("Morning tablet", "medicine", ["done"] * 5)),
        ("Bimal (fake)", 79, "bn", declining, ("Drink water", "hydration", ["done", "later", "done"])),
        ("Chandra (fake)", 81, "ne", inactive, ("Evening walk", "activity", ["done", "done"])),
        ("Dolly (fake)", 77, "as", {d: 68.0 for d in range(0, 14, 2)}, ("Morning tablet", "medicine", ["missed"] * 3 + ["done"])),
    ]  # fmt: skip
    for name, age, lang, scores, (rtitle, rcat, rstatuses) in plans:
        patient = User(id=uuid.uuid4(), role="patient", name=name, language=lang)
        db.add(patient)
        db.flush()
        db.add(CaregiverLink(id=uuid.uuid4(), caregiver_id=caregiver.id, patient_id=patient.id, relation="child"))
        add_sessions(db, rng, patient, scores)
        add_reminder(db, patient, rtitle, rcat, rstatuses)
        for cue_id, cue_type, label in CUES[:2]:
            db.add(MemoryTrigger(
                id=uuid.uuid4(), patient_id=patient.id, cue_id=cue_id, cue_type=cue_type, valence_label=label,
                confidence=round(rng.uniform(0.5, 0.9), 2), last_validated_at=at(1), half_life_days=14.0,
                updated_at=at(1),
            ))  # fmt: skip
    db.commit()
    print(f"Created caregiver {CAREGIVER_EMAIL} and {len(plans)} fake patients.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--create-tables", action="store_true", help="create tables first (stub/SQLite only)")
    parser.add_argument("--run-pipeline", action="store_true", help="then run the insights scan (rules only, no AI)")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("set --database-url or DATABASE_URL")
    kwargs = {"connect_args": {"check_same_thread": False}} if args.database_url.startswith("sqlite") else {}
    engine = create_engine(args.database_url, **kwargs)
    if args.create_tables:
        from app.core.db import Base

        Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        fill(db)
        if args.run_pipeline:
            from app.modules.insights.pipeline import scan_all_patients

            print("scan:", scan_all_patients(db, use_ai=False))


if __name__ == "__main__":
    main()
