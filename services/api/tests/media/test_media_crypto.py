import base64
import os

import pytest

from app.core import crypto
from app.core.config import settings


def test_round_trip_and_ciphertext_hides_plaintext():
    data = b"grandma's photo " * 1000
    ct, nonce = crypto.encrypt_bytes(data)
    assert len(nonce) == 12
    assert data[:32] not in ct
    assert len(ct) == len(data) + 16  # GCM tag
    assert crypto.decrypt_bytes(ct, nonce) == data


def test_empty_payload_round_trip():
    ct, nonce = crypto.encrypt_bytes(b"")
    assert crypto.decrypt_bytes(ct, nonce) == b""


def test_nonces_are_unique():
    nonces = {crypto.encrypt_bytes(b"x")[1] for _ in range(200)}
    assert len(nonces) == 200


@pytest.mark.parametrize("position", [0, 5, -1])
def test_tampered_ciphertext_is_rejected(position):
    ct, nonce = crypto.encrypt_bytes(b"medicine photo bytes")
    broken = bytearray(ct)
    broken[position] ^= 0x01
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_bytes(bytes(broken), nonce)


def test_truncated_ciphertext_is_rejected():
    ct, nonce = crypto.encrypt_bytes(b"abcdef")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_bytes(ct[:-1], nonce)


def test_wrong_nonce_is_rejected():
    ct, nonce = crypto.encrypt_bytes(b"abcdef")
    other = bytes([nonce[0] ^ 1]) + nonce[1:]
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_bytes(ct, other)
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_bytes(ct, nonce[:-1])


def test_wrong_key_cannot_decrypt(monkeypatch):
    ct, nonce = crypto.encrypt_bytes(b"secret")
    monkeypatch.setattr(settings, "MEDIA_KEY_B64", crypto.generate_key_b64(), raising=False)
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_bytes(ct, nonce)


@pytest.mark.parametrize("bad", ["", "not base64 !!", base64.b64encode(b"short").decode(), base64.b64encode(os.urandom(16)).decode()])
def test_bad_key_configuration_fails_loudly(monkeypatch, bad):
    monkeypatch.setattr(settings, "MEDIA_KEY_B64", bad, raising=False)
    with pytest.raises(crypto.CryptoConfigError):
        crypto.encrypt_bytes(b"x")


def test_derived_subkeys_are_separated_from_each_other():
    assert crypto.derive_subkey("a") != crypto.derive_subkey("b")
    assert len(crypto.derive_subkey("a")) == 32
