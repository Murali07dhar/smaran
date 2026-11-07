import json
from pathlib import Path

import numpy as np
import pytest

from app.core.va_mapping import FER_CLASSES, FER_VA
from app.main import create_app
from ml.synthetic import PatientSpec, simulate_patient

ROOT = Path(__file__).resolve().parents[1]
PATHS = {"/ai/triggers/update", "/ai/difficulty/next", "/ai/severity/estimate", "/ai/emotion/fuse",
         "/ai/content/generate"}


def test_exactly_the_contract_endpoints(client):
    assert set(client.app.openapi()["paths"]) == PATHS
    assert set(json.loads((ROOT / "openapi.json").read_text())["paths"]) == PATHS


def test_response_shapes_match_contract(client):
    t = client.post("/ai/triggers/update", json={"patient_id": "p", "observations": [
        {"cue_id": "c", "cue_type": "photo", "valence_label": "joy", "recalled": True, "with_cue": True,
         "ts": "2026-03-01T09:00:00Z"}]}).json()
    assert set(t) == {"triggers"}
    assert set(t["triggers"][0]) == {"cue_id", "confidence", "valence_label", "last_validated_at", "half_life_days"}
    d = client.post("/ai/difficulty/next", json={"patient_id": "p", "game_id": "g", "recent": [],
                                                 "current_difficulty": 3}).json()
    assert set(d) == {"difficulty", "rationale"}
    s = client.post("/ai/severity/estimate", json={"patient_id": "p", "window_days": 7}).json()
    assert set(s) == {"band", "gds_style_indicator", "drivers", "disclaimer"}
    assert s["band"] in {"stable", "watch", "alert"} and 1 <= s["gds_style_indicator"] <= 7
    e = client.post("/ai/emotion/fuse", json={"face": {"valence": 0.1, "arousal": 0.1, "conf": 0.5}}).json()
    assert set(e) == {"valence", "arousal", "label", "confidence"}
    c = client.post("/ai/content/generate", json={"kind": "game_prompt", "locale": "en", "context": {}}).json()
    assert set(c) == {"text", "source"} and c["source"] in {"gemini", "template"}


def test_service_token_enforced(monkeypatch, make_client):
    monkeypatch.setenv("AI_SERVICE_TOKEN", "s3cret")
    c = make_client()
    body = {"face": {"valence": 0.1, "arousal": 0.1, "conf": 0.5}}
    r = c.post("/ai/emotion/fuse", json=body)
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    assert c.post("/ai/emotion/fuse", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/ai/emotion/fuse", json=body, headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.get("/healthz").status_code == 200


def test_production_requires_token(monkeypatch):
    monkeypatch.setenv("AI_ENV", "production")
    with pytest.raises(RuntimeError):
        create_app(":memory:")


def test_time_override_disabled_by_default(monkeypatch, make_client):
    monkeypatch.setenv("AI_ALLOW_TIME_OVERRIDE", "0")
    c = make_client()
    r = c.post("/ai/severity/estimate", json={"patient_id": "p", "window_days": 7},
               headers={"X-Smaran-Now": "not-a-date"})
    assert r.status_code == 200  # header ignored


def test_healthz_does_not_leak_key(monkeypatch, make_client):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    body = make_client().get("/healthz").text
    assert "super-secret-key" not in body


def test_synthetic_generator_is_deterministic_and_declines():
    a = simulate_patient(PatientSpec("x", "declining", seed=5, days=150))
    b = simulate_patient(PatientSpec("x", "declining", seed=5, days=150))
    assert a == b
    lv = [g["difficulty"] for g in a["game_events"]]
    q = len(lv) // 4
    assert np.mean(lv[:q]) > np.mean(lv[-q:]) + 1


def test_smoke_onnx_contract():
    ort = pytest.importorskip("onnxruntime")
    sess = ort.InferenceSession(str(ROOT / "ml/models/fer_cnn_smoke.onnx"), providers=["CPUExecutionProvider"])
    assert [i.name for i in sess.get_inputs()] == ["input"]
    logits, probs = sess.run(None, {"input": np.random.rand(3, 1, 48, 48).astype(np.float32)})
    assert logits.shape == probs.shape == (3, 7)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5)
    meta = json.loads((ROOT / "ml/models/fer_cnn_smoke.meta.json").read_text())
    assert meta["classes"] == FER_CLASSES and meta["trained"] is False
    assert {k: tuple(v) for k, v in meta["class_valence_arousal"].items()} == FER_VA
