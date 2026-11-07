"""Encrypted-file storage on the mounted media volume (MEDIA_DIR).

Only ciphertext is ever written. Layout: <MEDIA_DIR>/<patient_id>/<media_id>.enc
media_assets.enc_path stores the path RELATIVE to MEDIA_DIR, so remounting the volume
elsewhere does not break rows.

Pure module (stdlib only).
"""
import os
import tempfile
from pathlib import Path

from app.core.config import settings

DEFAULT_MEDIA_DIR = "./media_data"


def media_root() -> Path:
    raw = getattr(settings, "MEDIA_DIR", None) or os.environ.get("MEDIA_DIR") or DEFAULT_MEDIA_DIR
    return Path(raw).resolve()


def relative_path(patient_id, media_id) -> str:
    return f"{patient_id}/{media_id}.enc"


def _safe_path(rel_path: str) -> Path:
    root = media_root()
    full = (root / rel_path).resolve()
    if root != full and root not in full.parents:
        raise ValueError("path escapes MEDIA_DIR")
    return full


def write_ciphertext(rel_path: str, ciphertext: bytes) -> None:
    """Atomically write ciphertext (temp file + fsync + rename), mode 0600."""
    full = _safe_path(rel_path)
    full.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp_name = tempfile.mkstemp(dir=full.parent, prefix=".tmp-", suffix=".enc")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(ciphertext)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, full)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_ciphertext(rel_path: str) -> bytes:
    return _safe_path(rel_path).read_bytes()


def remove_ciphertext(rel_path: str) -> None:
    try:
        _safe_path(rel_path).unlink()
    except FileNotFoundError:
        pass
