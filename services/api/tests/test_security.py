import time
import uuid
from datetime import timedelta

import jwt
import pytest

from app.core import security as sec
from app.core.config import settings
from app.core.ids import uuid7
from app.models import User


def _user(role="caregiver") -> User:
    return User(id=uuid7(), role=role, name="X", language="en")


# ---- passwords / PINs ---------------------------------------------------------------
def test_password_roundtrip_and_salt():
    h1, h2 = sec.hash_password("S3cret-pass!"), sec.hash_password("S3cret-pass!")
    assert h1 != h2 and h1.startswith("$2")
    assert sec.verify_password("S3cret-pass!", h1) and sec.verify_password("S3cret-pass!", h2)
    assert not sec.verify_password("s3cret-pass!", h1)


def test_password_edge_cases():
    assert not sec.verify_password("anything", None)
    assert not sec.verify_password("anything", "")
    assert not sec.verify_password("anything", "not-a-bcrypt-hash")
    with pytest.raises(ValueError):
        sec.hash_password("")
    long_a, long_b = "a" * 100 + "X", "a" * 100 + "Y"  # bcrypt alone would truncate at 72 bytes
    assert not sec.verify_password(long_b, sec.hash_password(long_a))
    assert sec.verify_password("पासवर्ड-অসমীয়া", sec.hash_password("पासवर्ड-অসমীয়া"))


def test_pin_rules():
    h = sec.hash_pin("2468")
    assert sec.verify_pin("2468", h) and not sec.verify_pin("2469", h)
    assert not sec.verify_pin("abcd", h) and not sec.verify_pin("", h) and not sec.verify_pin("2468", None)
    for bad in ("123", "123456789", "12a4", "", "12 34"):
        with pytest.raises(ValueError):
            sec.hash_pin(bad)


# ---- tokens ---------------------------------------------------------------------------
def test_create_tokens_claims():
    u = _user()
    access, refresh = sec.create_tokens(u)
    a, r = sec.decode_token(access), sec.decode_token(refresh)
    assert a["type"] == "access" and r["type"] == "refresh"
    assert a["sub"] == r["sub"] == str(u.id) and a["role"] == "caregiver"
    assert a["exp"] - a["iat"] == 15 * 60
    assert r["exp"] - r["iat"] == settings.REFRESH_TOKEN_DAYS * 86400
    assert a["jti"] != r["jti"] and access != refresh


def test_decode_expected_type():
    access, refresh = sec.create_tokens(_user())
    assert sec.decode_token(access, expected_type="access")["type"] == "access"
    with pytest.raises(sec.TokenError):
        sec.decode_token(refresh, expected_type="access")
    with pytest.raises(sec.TokenError):
        sec.decode_token(access, expected_type="refresh")


def test_decode_rejects_bad_tokens():
    uid = uuid.uuid4()
    with pytest.raises(sec.TokenError):
        sec.decode_token("garbage")
    with pytest.raises(sec.TokenError):  # expired
        sec.decode_token(sec.create_token(uid, "access", timedelta(seconds=-5)))
    good = sec.create_token(uid, "access", timedelta(minutes=5))
    head, body, sig = good.split(".")
    with pytest.raises(sec.TokenError):  # tampered signature
        sec.decode_token(f"{head}.{body}.{sig[:-2]}AA")
    forged = jwt.encode({"sub": str(uid), "type": "access", "iss": settings.JWT_ISSUER, "iat": int(time.time()),
                         "exp": int(time.time()) + 60}, "another-secret-another-secret-another!!", algorithm="HS256")
    with pytest.raises(sec.TokenError):  # wrong key
        sec.decode_token(forged)
    none_alg = jwt.encode({"sub": str(uid), "type": "access", "iss": settings.JWT_ISSUER, "iat": 1, "exp": 4102444800},
                          None, algorithm="none")
    with pytest.raises(sec.TokenError):  # alg=none
        sec.decode_token(none_alg)
    wrong_iss = jwt.encode({"sub": str(uid), "type": "access", "iss": "evil", "iat": int(time.time()),
                            "exp": int(time.time()) + 60}, settings.JWT_SECRET, algorithm="HS256")
    with pytest.raises(sec.TokenError):
        sec.decode_token(wrong_iss)
    no_type = jwt.encode({"sub": str(uid), "iss": settings.JWT_ISSUER, "iat": int(time.time()),
                          "exp": int(time.time()) + 60}, settings.JWT_SECRET, algorithm="HS256")
    with pytest.raises(sec.TokenError):  # required claim missing
        sec.decode_token(no_type)


def test_require_roles_validates_arguments():
    with pytest.raises(ValueError):
        sec.require_roles()
    with pytest.raises(ValueError):
        sec.require_roles("caregiver", "superuser")


# ---- ids ------------------------------------------------------------------------------
def test_uuid7_shape_and_order():
    ids = [uuid7() for _ in range(2000)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
