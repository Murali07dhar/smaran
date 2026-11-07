"""Bearer JWT verification (tokens issued by services/api). RBAC: any authenticated role may use voice;
admin-only routes are not needed here. Auth can be disabled ONLY via VOICE_REQUIRE_AUTH=false (local dev/CI)."""
from __future__ import annotations

import jwt  # PyJWT
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

_bearer = HTTPBearer(auto_error=False)
ROLES = {"patient", "caregiver", "health_worker", "admin"}


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if not settings.require_auth:
        return {"sub": "dev", "role": "admin"}
    if cred is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    key = settings.jwt_public_key or settings.jwt_secret
    if not key:
        raise HTTPException(status_code=500, detail="Server auth not configured")
    try:
        claims = jwt.decode(cred.credentials, key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if claims.get("role") not in ROLES:
        raise HTTPException(status_code=403, detail="Role not permitted")
    return claims
