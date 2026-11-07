"""Short-lived signed URLs for media content.

signature = base64url( HMAC-SHA256( key, "<media_id>.<exp>" ) ), exp = unix seconds.
The HMAC key is derived from MEDIA_KEY_B64 with a purpose label (key separation), so no
extra secret has to be provisioned. Rotating MEDIA_KEY_B64 invalidates outstanding URLs
(they live 10 minutes by default), which is acceptable.

Pure module: no FastAPI / SQLAlchemy imports.
"""
import base64
import hashlib
import hmac
import os
import time
import uuid

from app.core.config import settings
from app.core.crypto import derive_subkey

DEFAULT_TTL_SECONDS = 600  # 10 minutes
MIN_TTL_SECONDS = 30
MAX_TTL_SECONDS = 3600


class SignatureError(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason  # 'invalid' | 'expired'
        self.detail = detail


def url_ttl_seconds() -> int:
    raw = getattr(settings, "MEDIA_URL_TTL_SECONDS", None) or os.environ.get("MEDIA_URL_TTL_SECONDS")
    try:
        ttl = int(raw) if raw else DEFAULT_TTL_SECONDS
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL_SECONDS
    return max(MIN_TTL_SECONDS, min(MAX_TTL_SECONDS, ttl))


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def compute_signature(media_id: uuid.UUID | str, exp: int) -> str:
    message = f"{media_id}.{int(exp)}".encode("ascii")
    digest = hmac.new(derive_subkey("media-url-signing/v1"), message, hashlib.sha256).digest()
    return _b64url(digest)


def make_signature(media_id: uuid.UUID | str, now: float | None = None, ttl: int | None = None) -> tuple[str, int]:
    """Return (sig, exp) for a URL valid for ``ttl`` seconds (default 10 minutes)."""
    issued = time.time() if now is None else now
    exp = int(issued) + (url_ttl_seconds() if ttl is None else ttl)
    return compute_signature(media_id, exp), exp


def verify_signature(media_id: uuid.UUID | str, sig: str, exp: int, now: float | None = None) -> None:
    """Raise SignatureError unless ``sig`` is genuine for (media_id, exp) and not expired.

    The signature is checked first, in constant time, so a forged or tampered ``exp``
    is reported as invalid rather than leaking anything about the asset.
    """
    expected = compute_signature(media_id, exp)
    if not hmac.compare_digest(str(sig).encode("utf-8"), expected.encode("ascii")):
        raise SignatureError("invalid", "Invalid signature")
    current = time.time() if now is None else now
    if int(exp) < current:
        raise SignatureError("expired", "Link expired")
