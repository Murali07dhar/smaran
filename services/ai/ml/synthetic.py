"""Synthetic data generator. NO real patient data exists; everything here is simulated.

Stages: 'stable' (ability ~constant), 'mild_decline', 'declining' (clear drop over months).
Adaptive difficulty keeps accuracy near ~75%, so ability shows up in level, hints and speed.

CLI: python -m ml.synthetic --patients 12 --days 120 --out data/synthetic
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

POSITIVE = ["joy", "comfort", "excitement", "amusement", "familiarity"]
CUE_TYPES = ["photo", "audio", "music", "place", "object", "phrase"]
DECLINE_PER_MONTH = {"stable": 0.004, "mild_decline": 0.03, "declining": 0.10}


@dataclass
class PatientSpec:
    patient_id: str
    stage: str = "stable"
    seed: int = 0
    days: int = 120
    start: datetime = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    n_cues: int = 6
    ability0: float = 0.75


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def simulate_patient(spec: PatientSpec) -> dict[str, list[dict]]:
    """Returns {'observations': [...], 'game_events': [...]} with ISO timestamps."""
    rng = random.Random(spec.seed)
    slope = DECLINE_PER_MONTH[spec.stage]
    cues = []
    for i in range(spec.n_cues):
        label = "negative" if i == spec.n_cues - 1 else rng.choice(POSITIVE)
        cues.append({"cue_id": f"{spec.patient_id}-cue{i}", "cue_type": rng.choice(CUE_TYPES), "valence_label": label,
                     "p_with": rng.uniform(0.55, 0.95), "p_without": rng.uniform(0.25, 0.55)})
    obs: list[dict] = []
    games: list[dict] = []
    for day in range(spec.days):
        if rng.random() > 0.8:
            continue
        ts = spec.start + timedelta(days=day, minutes=rng.randint(0, 240))
        months = day / 30.0
        ability = max(0.05, min(1.0, spec.ability0 - slope * months + rng.gauss(0, 0.02)))
        level = max(1, min(10, round(1 + 9 * ability + rng.gauss(0, 0.6))))
        hint_p = max(0.02, min(0.8, 0.45 - 0.4 * ability))
        base_rt = 6000 - 4000 * ability
        for k in range(8):
            correct = rng.random() < 0.75
            hints = 1 if rng.random() < hint_p else 0
            rt = int(max(300, rng.lognormvariate(math.log(base_rt), 0.25)))
            games.append({"ts": _iso(ts + timedelta(seconds=40 * k)), "game_id": "memory_match", "correct": correct,
                          "response_ms": rt, "hints": hints, "difficulty": level})
        for cue in rng.sample(cues, 3):
            with_cue = rng.random() < 0.6
            p = (cue["p_with"] if with_cue else cue["p_without"]) * (1.0 - 0.6 * slope * months)
            obs.append({"cue_id": cue["cue_id"], "cue_type": cue["cue_type"], "valence_label": cue["valence_label"],
                        "recalled": rng.random() < max(0.02, p), "with_cue": with_cue,
                        "ts": _iso(ts + timedelta(minutes=10))})
    return {"observations": obs, "game_events": games}


def to_samples(sim: dict[str, list[dict]]) -> list[dict]:
    """Convert a simulation to PerfSample dicts for POST /ai/severity/estimate (CCR-AI-1)."""
    out = [{"ts": g["ts"], "source": "game", "correct": g["correct"], "response_ms": g["response_ms"],
            "hints": g["hints"], "difficulty": g["difficulty"], "game_id": g["game_id"]} for g in sim["game_events"]]
    return out


def _write(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patients", type=int, default=12)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stages = list(DECLINE_PER_MONTH)
    pats, obs, games = [], [], []
    for i in range(a.patients):
        spec = PatientSpec(patient_id=f"syn-{i:03d}", stage=stages[i % 3], seed=a.seed + i, days=a.days)
        sim = simulate_patient(spec)
        pats.append({"patient_id": spec.patient_id, "stage": spec.stage})
        obs += [{"patient_id": spec.patient_id, **o} for o in sim["observations"]]
        games += [{"patient_id": spec.patient_id, **g} for g in sim["game_events"]]
    _write(out / "patients.csv", pats)
    _write(out / "observations.csv", obs)
    _write(out / "game_events.csv", games)
    print(f"wrote {len(pats)} patients, {len(obs)} cue observations, {len(games)} game events to {out}")


if __name__ == "__main__":
    main()
