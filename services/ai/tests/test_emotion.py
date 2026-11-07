import pytest

from app.core.deepface_fallback import face_reading_from_probs
from app.core.emotion import PROTOTYPES, calibrate, label_for
from app.core.va_mapping import FER_VA, probs_to_va


def fuse(client, **body):
    r = client.post("/ai/emotion/fuse", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def reading(v, a, c):
    return {"valence": v, "arousal": a, "conf": c}


def test_face_only_joy_has_penalised_confidence(client):
    r = fuse(client, face=reading(0.85, 0.5, 0.9))
    assert r["label"] == "joy"
    assert r["confidence"] < 0.9 * 0.85 + 1e-6


def test_negative_and_neutral(client):
    assert fuse(client, face=reading(-0.8, 0.3, 0.9))["label"] == "negative"
    assert fuse(client, face=reading(0.0, 0.0, 0.9))["label"] == "neutral"


def test_agreement_beats_disagreement(client):
    agree = fuse(client, face=reading(0.8, 0.4, 0.9), speech=reading(0.7, 0.4, 0.9))
    clash = fuse(client, face=reading(0.8, 0.4, 0.9), speech=reading(-0.7, 0.4, 0.9))
    assert agree["confidence"] > clash["confidence"]


def test_higher_confidence_modality_dominates(client):
    r = fuse(client, face=reading(0.8, 0.4, 0.95), speech=reading(-0.8, 0.4, 0.05))
    assert r["valence"] > 0.4


def test_zero_confidence_is_neutral_zero(client):
    r = fuse(client, face=reading(0.9, 0.5, 0.0), speech=reading(0.9, 0.5, 0.0))
    assert r == {"valence": 0.0, "arousal": 0.0, "label": "neutral", "confidence": 0.0}


def test_requires_one_modality(client):
    r = client.post("/ai/emotion/fuse", json={"baseline": {"n": 3}})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_out_of_range_rejected(client):
    assert client.post("/ai/emotion/fuse", json={"face": reading(1.5, 0, 0.5)}).status_code == 422


def test_calibration_identity_without_baseline():
    for x in (-0.9, -0.2, 0.0, 0.3, 0.8):
        assert calibrate(x, 0.0, 0.5, 0) == pytest.approx(x)


def test_baseline_recentres_flat_affect_patient(client):
    base = {"valence_mean": 0.3, "valence_std": 0.15, "arousal_mean": 0.0, "arousal_std": 0.15, "n": 50}
    assert fuse(client, face=reading(0.3, 0.0, 0.9))["label"] != "neutral"
    assert fuse(client, face=reading(0.3, 0.0, 0.9), baseline=base)["label"] == "neutral"


def test_baseline_is_shrunk_when_n_small():
    assert abs(calibrate(0.3, 0.3, 0.15, 1) - 0.3) < abs(calibrate(0.3, 0.3, 0.15, 100) - 0.3) + 0.3


@pytest.mark.parametrize("name,v,a", PROTOTYPES)
def test_each_prototype_maps_to_its_label(name, v, a):
    assert label_for(v, a)[0] == name


def test_output_ranges(client):
    r = fuse(client, face=reading(1.0, 1.0, 1.0), speech=reading(-1.0, -1.0, 1.0))
    assert -1 <= r["valence"] <= 1 and -1 <= r["arousal"] <= 1 and 0 <= r["confidence"] <= 1


def test_va_mapping_and_deepface_adapter_agree():
    v, a, c = probs_to_va({"happy": 1.0}, FER_VA)
    assert (v, a, c) == (0.8, 0.45, 1.0)
    face = face_reading_from_probs({"happy": 100.0, "sad": 0.0})
    assert face["valence"] == 0.8 and face["conf"] == 1.0
