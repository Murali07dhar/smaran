"""Pure co-op protocol helpers (no web/Redis imports)."""
from __future__ import annotations

import json
import re
import secrets
from typing import Any

# 31 symbols: no I, L, O, 0, 1 (ambiguous when read aloud or on a small screen).
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 6
_CODE_RE = re.compile(rf"^[{JOIN_CODE_ALPHABET}]{{{JOIN_CODE_LENGTH}}}$")

ROLES = ("patient", "family")
CLIENT_MESSAGE_TYPES = frozenset({"state_patch", "hint", "encourage"})
SERVER_MESSAGE_TYPES = frozenset({"join", "leave"})
MAX_MESSAGE_BYTES = 16 * 1024


class ProtocolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def generate_join_code(rng=secrets) -> str:
    return "".join(rng.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def normalize_join_code(raw: str) -> str | None:
    """Upper-case and strip spaces/hyphens; None if the result cannot be a valid code."""
    code = re.sub(r"[\s-]", "", raw or "").upper()
    return code if _CODE_RE.match(code) else None


def validate_client_message(raw: str | bytes) -> tuple[str, dict[str, Any]]:
    """Parse a client frame -> (type, payload). The client's own `seq` is ignored: the server assigns it."""
    size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if size > MAX_MESSAGE_BYTES:
        raise ProtocolError("message_too_large", f"max {MAX_MESSAGE_BYTES} bytes")
    try:
        msg = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ProtocolError("invalid_json", "message must be JSON") from None
    if not isinstance(msg, dict):
        raise ProtocolError("invalid_message", "message must be a JSON object")
    mtype = msg.get("type")
    if mtype not in CLIENT_MESSAGE_TYPES:
        raise ProtocolError("unsupported_type", f"type must be one of {sorted(CLIENT_MESSAGE_TYPES)}")
    payload = msg.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_payload", "payload must be a JSON object")
    return mtype, payload
