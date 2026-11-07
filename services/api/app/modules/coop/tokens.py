"""Short-lived WebSocket tokens: a JWT carrying room_id and role, signed with settings.JWT_SECRET.

`typ=coop_ws` makes it unusable as an API access token (and vice-versa)."""
from __future__ import annotations

import time
from typing import Any

import jwt

WS_TOKEN_TTL_SECONDS = 300
_ALG = "HS256"
_TYP = "coop_ws"

# WebSocket close codes (4xxx = application-defined)
CLOSE_BAD_TOKEN = 4401
CLOSE_WRONG_ROOM = 4403
CLOSE_NO_ROOM = 4404
CLOSE_ROOM_EXPIRED = 4408


class TokenError(Exception):
    def __init__(self, message: str, close_code: int = CLOSE_BAD_TOKEN):
        super().__init__(message)
        self.close_code = close_code


def mint_ws_token(secret: str, *, room_id: str, role: str, user_id: str, patient_id: str,
                  ttl: int = WS_TOKEN_TTL_SECONDS) -> str:
    now = int(time.time())
    claims = {"typ": _TYP, "sub": user_id, "room_id": room_id, "role": role,
              "patient_id": patient_id, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, secret, algorithm=_ALG)


def verify_ws_token(secret: str, token: str, room_id: str) -> dict[str, Any]:
    if not token:
        raise TokenError("missing token")
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALG], options={"require": ["exp"]})
    except jwt.PyJWTError as exc:
        raise TokenError(f"invalid token: {exc.__class__.__name__}") from None
    if claims.get("typ") != _TYP or claims.get("role") not in ("patient", "family"):
        raise TokenError("not a co-op token")
    if claims.get("room_id") != room_id:
        raise TokenError("token is for a different room", CLOSE_WRONG_ROOM)
    return claims
