import json

import httpx

from app.modules.insights.ai_client import AIClient

TRIGGER_OK = {
    "triggers": [
        {"cue_id": "c1", "confidence": 0.8, "valence_label": "joy", "last_validated_at": "2026-10-21T10:00:00Z", "half_life_days": 12.5}
    ]
}


def client(handler):
    return AIClient(base_url="http://ai.test", transport=httpx.MockTransport(handler))


def test_update_triggers_success_and_request_shape():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=TRIGGER_OK)

    out = client(handler).update_triggers("p1", [{"cue_id": "c1"}])
    assert seen["url"] == "http://ai.test/ai/triggers/update"
    assert seen["body"] == {"patient_id": "p1", "observations": [{"cue_id": "c1"}]}
    assert out and out[0].cue_id == "c1" and out[0].half_life_days == 12.5


def test_timeout_returns_none():
    def handler(request):
        raise httpx.ConnectTimeout("slow", request=request)

    assert client(handler).update_triggers("p1", [{}]) is None
    assert client(handler).estimate_severity("p1", 14) is None


def test_http_500_and_bad_json_return_none():
    assert client(lambda r: httpx.Response(500)).update_triggers("p1", [{}]) is None
    assert client(lambda r: httpx.Response(200, content=b"not json")).estimate_severity("p1", 14) is None


def test_invalid_trigger_item_is_dropped_but_others_kept():
    payload = {"triggers": [TRIGGER_OK["triggers"][0], {"cue_id": "bad"}]}
    out = client(lambda r: httpx.Response(200, json=payload)).update_triggers("p1", [{}])
    assert [t.cue_id for t in out] == ["c1"]


def test_unexpected_shape_returns_none():
    assert client(lambda r: httpx.Response(200, json={"nope": 1})).update_triggers("p1", [{}]) is None


def test_severity_valid_and_invalid():
    ok = {"band": "watch", "gds_style_indicator": 4, "drivers": ["a"], "disclaimer": "d"}
    sev = client(lambda r: httpx.Response(200, json=ok)).estimate_severity("p1", 14)
    assert sev.band == "watch" and sev.gds_style_indicator == 4
    bad = {**ok, "band": "catastrophic"}
    assert client(lambda r: httpx.Response(200, json=bad)).estimate_severity("p1", 14) is None
    bad2 = {**ok, "gds_style_indicator": 9}
    assert client(lambda r: httpx.Response(200, json=bad2)).estimate_severity("p1", 14) is None
