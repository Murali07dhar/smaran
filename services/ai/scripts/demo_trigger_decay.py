"""Demonstrates trigger confidence RISING with recall and then DECAYING with time.

Phase 1: one cue is recalled in 12 daily sessions, with periodic misses *without* the cue.
Phase 2: no sessions for 150 days; confidence decays with exp(-lambda * dt).

    python scripts/demo_trigger_decay.py    # writes docs/trigger_demo.csv (+ .png if matplotlib)
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.triggers import update_triggers  # noqa: E402
from app.schemas import Observation  # noqa: E402
from app.store import Store  # noqa: E402

START = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
PID, CUE = "demo-patient", "cue-family-photo"


def obs(day: int, recalled: bool, with_cue: bool) -> Observation:
    return Observation(cue_id=CUE, cue_type="photo", valence_label="joy", recalled=recalled,
                       with_cue=with_cue, ts=START + timedelta(days=day))


def main() -> None:
    store = Store(":memory:")
    rows: list[dict] = []
    for day in range(12):
        batch = [obs(day, True, True)]
        if day % 4 == 3:
            batch.append(obs(day, False, False))  # item not recalled without the cue
        t = update_triggers(store, PID, batch, START + timedelta(days=day))[0]
        rows.append({"day": day, "phase": "sessions", "confidence": t.confidence, "half_life_days": t.half_life_days})
    last = 11
    for gap in (0, 7, 14, 30, 60, 90, 120, 150):
        now = START + timedelta(days=last + gap)
        t = update_triggers(store, PID, [], now)[0]
        rows.append({"day": last + gap, "phase": "decay", "confidence": t.confidence, "half_life_days": t.half_life_days})

    out = Path(__file__).resolve().parents[1] / "docs"
    out.mkdir(exist_ok=True)
    with (out / "trigger_demo.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"{'day':>4} {'phase':<9} {'confidence':>10}  chart")
    for r in rows:
        print(f"{r['day']:>4} {r['phase']:<9} {r['confidence']:>10.3f}  {'#' * int(r['confidence'] * 40)}")

    sess = [r["confidence"] for r in rows if r["phase"] == "sessions"]
    dec = [r["confidence"] for r in rows if r["phase"] == "decay"]
    assert sess[-1] > sess[0], "confidence should rise with repeated recall"
    assert all(a >= b for a, b in zip(dec, dec[1:])), "confidence should only decay without sessions"
    assert dec[-1] < dec[0] * 0.2, "after 150 days confidence should have decayed substantially"
    print("OK: rises with recall, then decays over time")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 3.5))
        for phase, color in (("sessions", "#0F766E"), ("decay", "#B45309")):
            pts = [r for r in rows if r["phase"] == phase]
            ax.plot([p["day"] for p in pts], [p["confidence"] for p in pts], marker="o", color=color, label=phase)
        ax.set_xlabel("day")
        ax.set_ylabel("trigger confidence")
        ax.set_title("SMARAN trigger confidence: rises with recall, decays over time")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / "trigger_demo.png", dpi=130)
    except ImportError:
        print("matplotlib not installed: skipped PNG")


if __name__ == "__main__":
    main()
