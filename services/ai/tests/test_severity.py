from datetime import timedelta

from app.core.severity import DISCLAIMER, indicator_from_percentile
from ml.synthetic import PatientSpec, simulate_patient, to_samples
from tests.conftest import at


def estimate(client, pid, samples=None, now="2026-05-31T08:00:00Z", window=30):
    body = {"patient_id": pid, "window_days": window}
    if samples is not None:
        body["samples"] = samples
    r = client.post("/ai/severity/estimate", json=body, headers=at(now))
    assert r.status_code == 200, r.text
    return r.json()


def synth(stage, seed=3, days=150):
    spec = PatientSpec(patient_id=f"s-{stage}", stage=stage, seed=seed, days=days)
    now = (spec.start + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return to_samples(simulate_patient(spec)), now


def test_no_data_is_stable_with_disclaimer(client):
    r = estimate(client, "nobody")
    assert r["band"] == "stable" and r["gds_style_indicator"] == 1
    assert r["drivers"][0].startswith("insufficient_data")
    assert r["disclaimer"] == DISCLAIMER


def test_stable_patient_stays_stable(client):
    samples, now = synth("stable")
    r = estimate(client, "ps", samples, now)
    assert r["band"] == "stable"
    assert any(d.startswith("trend:") for d in r["drivers"])


def test_declining_patient_is_flagged(client):
    samples, now = synth("declining")
    r = estimate(client, "pd", samples, now)
    assert r["band"] in ("watch", "alert")
    trend = next(d for d in r["drivers"] if d.startswith("trend:"))
    assert "-" in trend  # composite fell vs the patient's own baseline
    assert any(d.startswith("band:") and "because" in d for d in r["drivers"])


def test_disclaimer_always_present(client):
    samples, now = synth("mild_decline")
    assert estimate(client, "pm", samples, now)["disclaimer"] == DISCLAIMER


def test_samples_are_idempotent(client):
    samples, now = synth("stable")
    a = estimate(client, "pi", samples, now)
    b = estimate(client, "pi", samples, now)
    assert a["drivers"][0] == b["drivers"][0]


def test_indicator_table_boundaries():
    assert indicator_from_percentile(80) == 1
    assert indicator_from_percentile(75) == 1
    assert indicator_from_percentile(45) == 3
    assert indicator_from_percentile(29.9) == 5
    assert indicator_from_percentile(9.9) == 7
    assert indicator_from_percentile(0) == 7


def test_window_validation(client):
    r = client.post("/ai/severity/estimate", json={"patient_id": "p", "window_days": 0})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_game_events_from_difficulty_feed_severity(client):
    good = {"correct": True, "response_ms": 2000, "hints": 0}
    for _ in range(3):
        client.post("/ai/difficulty/next", json={"patient_id": "pf", "game_id": "g",
                                                 "recent": [good] * 4 + [{**good, "correct": False}] * 2 + [good] * 3,
                                                 "current_difficulty": 5})
    r = client.post("/ai/severity/estimate", json={"patient_id": "pf", "window_days": 30}).json()
    assert r["drivers"][0].startswith("data: ") or r["drivers"][0].startswith("insufficient")
