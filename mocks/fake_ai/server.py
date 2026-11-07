"""Fake services/ai (port 8001) implementing the AI SERVICE contract shapes. Dev/smoke only.
Run: uvicorn mocks.fake_ai.server:app --port 8001   (replaced by the real services/ai)."""
from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="fake-ai")
now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731
CALLS: list[tuple[str, dict]] = []


@app.post("/ai/triggers/update")
def triggers(body: dict):
    CALLS.append(("triggers", body))
    seen = {}
    for o in body.get("observations", []):
        seen.setdefault(o["cue_id"], o)
    return {"triggers": [{"cue_id": k, "confidence": 0.72, "valence_label": v.get("valence_label", "joy"),
                          "last_validated_at": now(), "half_life_days": 21.0} for k, v in seen.items()]}


@app.post("/ai/severity/estimate")
def severity(body: dict):
    CALLS.append(("severity", body))
    return {"band": "watch", "gds_style_indicator": 3, "drivers": ["response time slower than baseline"],
            "disclaimer": "Support tool, not a diagnosis."}


@app.post("/ai/difficulty/next")
def difficulty(body: dict):
    return {"difficulty": body.get("current_difficulty", 3), "rationale": "fake"}


@app.post("/ai/emotion/fuse")
def fuse(body: dict):
    return {"valence": 0.5, "arousal": 0.3, "label": "comfort", "confidence": 0.6}


@app.post("/ai/content/generate")
def content(body: dict):
    return {"text": "It is time for your medicine.", "source": "template"}


@app.get("/calls")
def calls():
    return [{"endpoint": e, "body": b} for e, b in CALLS]
