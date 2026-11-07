import math
from datetime import datetime, timedelta, timezone

from app.core.triggers import MAX_HALF_LIFE_DAYS, MIN_HALF_LIFE_DAYS, decay_factor, prob_cue_beats_baseline
from tests.conftest import at

START = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


def iso(day: float) -> str:
    return (START + timedelta(days=day)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ob(day, recalled=True, with_cue=True, cue="c1", label="joy", ctype="photo"):
    return {"cue_id": cue, "cue_type": ctype, "valence_label": label, "recalled": recalled,
            "with_cue": with_cue, "ts": iso(day)}


def post(client, pid, observations, now_day):
    r = client.post("/ai/triggers/update", json={"patient_id": pid, "observations": observations},
                    headers=at(iso(now_day)))
    assert r.status_code == 200, r.text
    return {t["cue_id"]: t for t in r.json()["triggers"]}


def test_beta_math_basics():
    assert math.isclose(prob_cue_beats_baseline(1, 1, 1, 1), 0.5, abs_tol=1e-3)
    assert math.isclose(prob_cue_beats_baseline(11, 1, 1, 1), 11 / 12, abs_tol=1e-3)
    assert math.isclose(decay_factor(30, 30), 0.5, abs_tol=1e-9)


def test_confidence_rises_with_recall(client):
    seen = []
    for day in range(8):
        seen.append(post(client, "p1", [ob(day)], day)["c1"]["confidence"])
    assert all(b >= a for a, b in zip(seen, seen[1:]))
    assert seen[-1] > seen[0] + 0.15


def test_confidence_decays_without_sessions(client):
    first = post(client, "p1", [ob(d) for d in range(6)], 5)["c1"]
    hl = first["half_life_days"]
    c0 = first["confidence"]
    c30 = post(client, "p1", [], 5 + 30)["c1"]["confidence"]
    c120 = post(client, "p1", [], 5 + 120)["c1"]["confidence"]
    assert c120 < c30 < c0
    assert math.isclose(c30 / c0, 2 ** (-30 / hl), rel_tol=0.02)


def test_recall_without_cue_lowers_confidence(client):
    a = post(client, "pa", [ob(d) for d in range(5)], 5)["c1"]["confidence"]
    both = [ob(d) for d in range(5)] + [ob(d, recalled=True, with_cue=False) for d in range(5)]
    b = post(client, "pb", both, 5)["c1"]["confidence"]
    assert b < a


def test_miss_without_cue_raises_confidence(client):
    base = [ob(d) for d in range(5)]
    a = post(client, "pa", base, 5)["c1"]["confidence"]
    b = post(client, "pb", base + [ob(d, recalled=False, with_cue=False) for d in range(4)], 5)["c1"]["confidence"]
    assert b > a


def test_idempotent_replay(client):
    batch = [ob(d) for d in range(4)]
    first = post(client, "p1", batch, 4)
    second = post(client, "p1", batch, 4)
    assert first == second


def test_negative_valence_never_promoted(client):
    t = post(client, "p1", [ob(d, label="negative") for d in range(8)], 8)["c1"]
    assert t["valence_label"] == "negative"
    assert t["confidence"] <= 0.05


def test_returns_all_cues_sorted(client):
    res = post(client, "p1", [ob(0, cue="a"), ob(1, cue="a"), ob(0, cue="b", recalled=False)], 1)
    assert set(res) == {"a", "b"}
    out = client.post("/ai/triggers/update", json={"patient_id": "p1", "observations": []},
                      headers=at(iso(1))).json()["triggers"]
    assert [t["cue_id"] for t in out] == ["a", "b"]


def test_half_life_adapts_and_is_clamped(client):
    obs = [ob(d * 5) for d in range(14)]
    t = post(client, "p1", obs, 70)["c1"]
    assert t["half_life_days"] > 30
    assert MIN_HALF_LIFE_DAYS <= t["half_life_days"] <= MAX_HALF_LIFE_DAYS


def test_patients_are_isolated(client):
    post(client, "p1", [ob(0), ob(1)], 1)
    assert post(client, "p2", [], 1) == {}


def test_validation_errors_are_problem_json(client):
    r = client.post("/ai/triggers/update", json={"patient_id": "p1", "observations": [{"cue_id": "x"}]})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 422 and body["errors"]
