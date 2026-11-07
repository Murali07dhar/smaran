"""Evaluate the trigger and severity engines on SYNTHETIC patients and log to MLflow.

This only shows the engines behave sensibly on simulated data. It says NOTHING about real
clinical accuracy.

    python -m ml.evaluate_synthetic --patients 18 --days 150
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from sklearn.metrics import roc_auc_score

from app.core import severity
from app.core.triggers import confidence_at, update_triggers
from app.schemas import Observation, PerfSample
from app.store import Store
from ml.synthetic import DECLINE_PER_MONTH, PatientSpec, simulate_patient, to_samples
from ml.tracking import tracked_run


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def trigger_auc(spec: PatientSpec) -> tuple[list[float], list[int]]:
    """Confidence just BEFORE each with-cue trial vs whether that trial was recalled."""
    sim = simulate_patient(spec)
    store = Store(":memory:")
    scores, labels = [], []
    seen: set[str] = set()
    for o in sorted(sim["observations"], key=lambda r: r["ts"]):
        ob = Observation(**o)
        if ob.with_cue and ob.cue_id in seen:
            st = next(s for s in store.get_cues(spec.patient_id) if s.cue_id == ob.cue_id)
            scores.append(confidence_at(st, ob.ts))
            labels.append(int(ob.recalled))
        update_triggers(store, spec.patient_id, [ob], ob.ts)
        seen.add(ob.cue_id)
    return scores, labels


def severity_band(spec: PatientSpec) -> str:
    sim = simulate_patient(spec)
    store = Store(":memory:")
    now = spec.start + timedelta(days=spec.days)
    samples = [PerfSample(**s) for s in to_samples(sim)]
    return severity.estimate(store, spec.patient_id, 30, now, samples).band


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patients", type=int, default=18)
    ap.add_argument("--days", type=int, default=150)
    a = ap.parse_args()
    stages = list(DECLINE_PER_MONTH)
    all_s: list[float] = []
    all_y: list[int] = []
    bands: dict[str, dict[str, int]] = {s: {"stable": 0, "watch": 0, "alert": 0} for s in stages}
    for i in range(a.patients):
        spec = PatientSpec(patient_id=f"eval-{i:03d}", stage=stages[i % 3], seed=100 + i, days=a.days)
        s, y = trigger_auc(spec)
        all_s += s
        all_y += y
        bands[spec.stage][severity_band(spec)] += 1
    auc = roc_auc_score(all_y, all_s) if len(set(all_y)) > 1 else float("nan")
    print(f"trigger confidence AUC for next with-cue recall: {auc:.3f} (n={len(all_y)})")
    for stage, c in bands.items():
        print(f"severity bands for {stage:<13}: {c}")
    with tracked_run("smaran-ai", "synthetic-eval", {"patients": a.patients, "days": a.days}) as run:
        run.log_metrics({"trigger_auc": float(auc)})
        for stage, c in bands.items():
            run.log_metrics({f"{stage}_{k}": float(v) for k, v in c.items()})


if __name__ == "__main__":
    main()
