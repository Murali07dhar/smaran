"""AES-256-GCM helpers for media encrypted at rest (Claude 1.3).

Public interface (fixed by the shared contract):

    encrypt_bytes(data: bytes) -> tuple[bytes, bytes]   # (ciphertext, nonce)
    decrypt_bytes(ciphertext: bytes, nonce: bytes) -> bytes

* Key: ``settings.MEDIA_KEY_B64`` = base64 of exactly 32 random bytes.
  Generate one with ``python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"``.
* The key is read on every call (never at import) so a missing or invalid key
  fails loudly where it is used, and tests can swap keys.
* ``ciphertext`` includes the 16-byte GCM tag at the end, so any change to the
  ciphertext, the nonce or the key makes ``decrypt_bytes`` raise ``CryptoError``.
* A fresh random 96-bit nonce is generated per call. With random 96-bit nonces
  the safe limit is about 2**32 encryptions per key, far above this product.
* ``derive_subkey`` gives other parts of the media module (URL signing) a key
  that is separated from the encryption key, so the AES key is never reused as
  an HMAC key.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_BYTES = 12
KEY_BYTES = 32


class CryptoError(Exception):
    """Raised when data cannot be decrypted (tampering, wrong key or nonce)."""


class CryptoConfigError(CryptoError):
    """Raised when MEDIA_KEY_B64 is missing or is not a 32-byte base64 key."""


def generate_key_b64() -> str:
    """Return a new random key suitable for MEDIA_KEY_B64."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def _load_key() -> bytes:
    raw = getattr(settings, "MEDIA_KEY_B64", None)
    if not raw:
        raise CryptoConfigError("MEDIA_KEY_B64 is not set")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        try:  # tolerate url-safe base64
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except (binascii.Error, ValueError) as exc:
            raise CryptoConfigError("MEDIA_KEY_B64 is not valid base64") from exc
    if len(key) != KEY_BYTES:
        raise CryptoConfigError(
            f"MEDIA_KEY_B64 must decode to {KEY_BYTES} bytes (AES-256), got {len(key)}"
        )
    return key


def encrypt_bytes(data: bytes) -> tuple[bytes, bytes]:
    """Encrypt ``data``. Returns ``(ciphertext, nonce)``; store both."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_load_key()).encrypt(nonce, bytes(data), None)
    return ciphertext, nonce


def decrypt_bytes(ciphertext: bytes, nonce: bytes) -> bytes:
    """Decrypt and authenticate. Raises ``CryptoError`` on any mismatch."""
    nonce = bytes(nonce)
    if len(nonce) != NONCE_BYTES:
        raise CryptoError("invalid nonce length")
    try:
        return AESGCM(_load_key()).decrypt(nonce, bytes(ciphertext), None)
    except InvalidTag as exc:
        raise CryptoError("authentication failed: data was modified or key is wrong") from exc


def derive_subkey(label: str) -> bytes:
    """Derive a purpose-bound 32-byte key from the media key (HMAC-SHA256 KDF)."""
    return hmac.new(_load_key(), b"smaran/" + label.encode("utf-8"), hashlib.sha256).digest()
