import os

os.environ["VOICE_MODELS_MODE"] = "off"
os.environ["VOICE_REQUIRE_AUTH"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models import beep_wav, detect_language  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/voice/health").json()["status"] == "ok"


def test_capabilities_lists_pack_only_locales():
    j = client.get("/voice/capabilities").json()
    assert set(j["voice_pack_only_locales"]) == {"lus", "kha", "grt"}


def test_asr_503_with_fallback_when_models_off():
    r = client.post("/voice/asr?locale=as", content=b"\x00\x01", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["fallback"] == "browser_web_speech_api_or_tap_buttons"


def test_asr_pack_only_locale_rejected():
    r = client.post("/voice/asr?locale=lus", content=b"\x00")
    assert r.status_code == 422 and r.json()["fallback"] == "tap_buttons"


def test_asr_empty_and_oversized():
    assert client.post("/voice/asr?locale=en", content=b"").status_code == 400


def test_tts_503_fallback_and_pack_only():
    r = client.post("/voice/tts", json={"text": "hello", "locale": "en"})
    assert r.status_code == 503 and r.json()["fallback"] == "browser_speech_synthesis_or_voice_pack"
    r = client.post("/voice/tts", json={"text": "hello", "locale": "kha"})
    assert r.status_code == 422 and r.json()["fallback"] == "voice_pack"


def test_tts_text_too_long_and_validation_problem_json():
    assert client.post("/voice/tts", json={"text": "x" * 1000, "locale": "en"}).status_code == 413
    r = client.post("/voice/tts", json={"locale": "en"})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")


def test_lid_heuristic_is_honest_about_ambiguity():
    j = client.post("/voice/lid", json={"text": "আপুনি কেনে আছে"}).json()
    assert j["method"] == "script_heuristic" and "as" in j["ambiguous_with"]
    assert detect_language("hello there")["locale"] == "en"
    assert detect_language("ꯍꯌ")["locale"] == "mni"
    assert detect_language("12345")["locale"] == "unknown"


def test_auth_required_when_enabled():
    from app import auth

    object.__setattr__(auth.settings, "require_auth", True)
    try:
        assert client.post("/voice/lid", json={"text": "hi"}).status_code == 401
    finally:
        object.__setattr__(auth.settings, "require_auth", False)


def test_beep_wav_is_valid_riff():
    assert beep_wav()[:4] == b"RIFF"
