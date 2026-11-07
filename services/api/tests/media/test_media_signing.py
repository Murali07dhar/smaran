import time
import uuid

import pytest

from app.modules.media import signing


def test_default_ttl_is_ten_minutes():
    assert signing.url_ttl_seconds() == 600
    now = 1_700_000_000
    _, exp = signing.make_signature(uuid.uuid4(), now=now)
    assert exp == now + 600


def test_ttl_is_configurable_and_clamped(monkeypatch):
    monkeypatch.setenv("MEDIA_URL_TTL_SECONDS", "120")
    assert signing.url_ttl_seconds() == 120
    monkeypatch.setenv("MEDIA_URL_TTL_SECONDS", "1")
    assert signing.url_ttl_seconds() == signing.MIN_TTL_SECONDS
    monkeypatch.setenv("MEDIA_URL_TTL_SECONDS", "999999")
    assert signing.url_ttl_seconds() == signing.MAX_TTL_SECONDS
    monkeypatch.setenv("MEDIA_URL_TTL_SECONDS", "abc")
    assert signing.url_ttl_seconds() == 600


def test_valid_signature_passes():
    mid = uuid.uuid4()
    sig, exp = signing.make_signature(mid)
    signing.verify_signature(mid, sig, exp)


def test_expired_signature_is_rejected():
    mid = uuid.uuid4()
    sig, exp = signing.make_signature(mid, now=time.time() - 3600)
    with pytest.raises(signing.SignatureError) as err:
        signing.verify_signature(mid, sig, exp)
    assert err.value.reason == "expired"


def test_expiry_boundary():
    mid = uuid.uuid4()
    sig, exp = signing.make_signature(mid, now=1000, ttl=600)
    signing.verify_signature(mid, sig, exp, now=exp)  # still valid at the last second
    with pytest.raises(signing.SignatureError):
        signing.verify_signature(mid, sig, exp, now=exp + 1)


def test_forged_signature_is_rejected():
    mid = uuid.uuid4()
    _, exp = signing.make_signature(mid)
    for forged in ("", "AAAA", "x" * 43, "é" * 10):
        with pytest.raises(signing.SignatureError) as err:
            signing.verify_signature(mid, forged, exp)
        assert err.value.reason == "invalid"


def test_extending_expiry_invalidates_signature():
    mid = uuid.uuid4()
    sig, exp = signing.make_signature(mid)
    with pytest.raises(signing.SignatureError) as err:
        signing.verify_signature(mid, sig, exp + 100000)
    assert err.value.reason == "invalid"


def test_signature_is_bound_to_media_id():
    sig, exp = signing.make_signature(uuid.uuid4())
    with pytest.raises(signing.SignatureError):
        signing.verify_signature(uuid.uuid4(), sig, exp)


def test_signature_from_another_key_is_rejected(monkeypatch):
    from app.core import crypto
    from app.core.config import settings

    mid = uuid.uuid4()
    sig, exp = signing.make_signature(mid)
    monkeypatch.setattr(settings, "MEDIA_KEY_B64", crypto.generate_key_b64(), raising=False)
    with pytest.raises(signing.SignatureError):
        signing.verify_signature(mid, sig, exp)
