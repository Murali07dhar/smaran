import pytest

from app.core import content

CTX = {"patient_name": "Ratna", "category": "medicine", "title": "BP tablet", "time": "08:00"}


def gen(client, kind="reminder_phrase", locale="en", context=None):
    r = client.post("/ai/content/generate", json={"kind": kind, "locale": locale, "context": context or {}})
    assert r.status_code == 200, r.text
    return r.json()


def test_template_when_no_key(client):
    r = gen(client, context=CTX)
    assert r["source"] == "template"
    assert "Ratna" in r["text"] and "BP tablet" in r["text"] and "{" not in r["text"]


def test_deterministic(client):
    assert gen(client, context=CTX) == gen(client, context=CTX)


@pytest.mark.parametrize("locale", ["as", "bn", "ne", "brx", "mni", "lus", "kha", "grt", "en"])
def test_all_locales_return_text(client, locale):
    for kind, ctx in (("reminder_phrase", CTX), ("game_prompt", {"domain": "routine"})):
        r = gen(client, kind, locale, ctx)
        assert r["text"] and r["source"] == "template" and "{" not in r["text"]


def test_no_name_is_handled(client):
    text = gen(client, context={"category": "hydration"})["text"]
    assert "{" not in text and text[0].isupper()


def test_unknown_category_and_domain_fall_back(client):
    assert gen(client, context={"category": "zzz"})["text"]
    assert gen(client, "game_prompt", "en", {"domain": "zzz"})["text"]


def test_invalid_kind_422(client):
    r = client.post("/ai/content/generate", json={"kind": "poem", "locale": "en", "context": {}})
    assert r.status_code == 422


def test_braces_in_context_cannot_inject(client):
    text = gen(client, context={"patient_name": "{title}{name}", "title": "}{name}", "category": "medicine"})["text"]
    assert "{" not in text and "}" not in text


def test_context_is_truncated():
    assert len(content.clean_context({"title": "x" * 500})["title"]) == 60


def test_gemini_success_and_privacy(make_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    seen = {}

    def fake(settings, system, user_json):
        seen["user"], seen["system"] = user_json, system
        return "{name}, it is time for {title}. Take your time."

    monkeypatch.setattr(content, "_call_gemini", fake)
    r = gen(make_client(), context=CTX)
    assert r["source"] == "gemini"
    assert r["text"] == "Ratna, it is time for BP tablet. Take your time."
    assert "Ratna" not in seen["user"] and "BP tablet" not in seen["user"] and "08:00" not in seen["user"]
    assert "morning" in seen["user"] and "English" in seen["system"]


@pytest.mark.parametrize("bad", [
    "{name}, take 500 mg of {title} now.", "{name}, this will cure you: {title}.",
    "{name}, hurry up with {title}!", "{name}, remember something.", "x" * 400, "",
    "{name}, this is for your dementia. {title}",
])
def test_unsafe_gemini_output_falls_back(make_client, monkeypatch, bad):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(content, "_call_gemini", lambda *a, **k: bad)
    assert gen(make_client(), context=CTX)["source"] == "template"


def test_gemini_failure_falls_back(make_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(content, "_call_gemini", lambda *a, **k: None)
    assert gen(make_client(), context=CTX)["source"] == "template"


def test_unsupported_locale_never_calls_gemini(make_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def boom(*a, **k):
        raise AssertionError("must not be called for brx")

    monkeypatch.setattr(content, "_call_gemini", boom)
    assert gen(make_client(), locale="brx", context=CTX)["source"] == "template"


def test_game_prompt_payload_is_coarse():
    p = content.llm_payload("game_prompt", content.clean_context({"domain": "memory", "cue_type": "photo", "difficulty": 9}))
    assert p == {"kind": "game_prompt", "domain": "memory", "cue_type": "photo", "level": "stretch"}
