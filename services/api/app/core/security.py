"""Authentication helpers + RBAC. Fixed shared interfaces (import paths and signatures):

    get_current_user() -> User                           (FastAPI dependency)
    require_roles(*roles)                                (dependency factory -> User)
    assert_can_access_patient(session, user, patient_id) (raises HTTPException 403)
    hash_password / verify_password / hash_pin / verify_pin
    create_tokens(user) -> (access, refresh)
    decode_token(token) -> claims

Additive helpers (not part of the contract, safe to ignore): create_token, TokenError,
can_access_patient, accessible_patient_ids.

Auth is bearer-token only (no cookies) so the future native app can reuse it unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import re
import uuid
from datetime import timedelta
from functools import lru_cache
from typing import Any, Callable

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_session
from app.core.ids import uuid7
from app.models import ROLES, CaregiverLink, User, utcnow

ACCESS = "access"
REFRESH = "refresh"
PIN_RE = re.compile(r"^\d{4,8}$")

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


class TokenError(Exception):
    """Raised by decode_token() for any invalid, expired or wrong-type token."""


# --------------------------------------------------------------------------------------
# Password / PIN hashing (bcrypt, salted, cost = settings.BCRYPT_ROUNDS)
# --------------------------------------------------------------------------------------
def _prehash(secret: str) -> bytes:
    # bcrypt silently truncates at 72 bytes; SHA-256 + base64 (44 bytes, no NULs) avoids that.
    return base64.b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _hash(secret: str) -> str:
    return bcrypt.hashpw(_prehash(secret), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("ascii")


@lru_cache
def _dummy_hash() -> str:
    return _hash("smaran-timing-equalizer")


def _verify(secret: str, hashed: str | None) -> bool:
    if not hashed:
        bcrypt.checkpw(_prehash(secret), _dummy_hash().encode("ascii"))  # equalise timing
        return False
    try:
        return bcrypt.checkpw(_prehash(secret), hashed.encode("ascii"))
    except ValueError:  # malformed hash
        return False


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    return _hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    return _verify(password or "", password_hash)


def hash_pin(pin: str) -> str:
    """PINs are 4-8 digits. NOTE: a PIN has little entropy; the login route must rate-limit."""
    if not PIN_RE.match(pin or ""):
        raise ValueError("PIN must be 4 to 8 digits")
    return _hash(pin)


def verify_pin(pin: str, pin_hash: str | None) -> bool:
    if not PIN_RE.match(pin or ""):
        _verify("0000", pin_hash)  # keep timing flat for malformed input
        return False
    return _verify(pin, pin_hash)


# --------------------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------------------
def create_token(
    subject: uuid.UUID | str, token_type: str, expires_delta: timedelta, **extra_claims: Any
) -> str:
    """Generic signer. 1.2 can use it for other token types (e.g. token_type='qr')."""
    now = utcnow()
    claims: dict[str, Any] = {
        **extra_claims,
        "iss": settings.JWT_ISSUER,
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid7()),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_tokens(user: User) -> tuple[str, str]:
    """-> (access_token [ACCESS_TOKEN_MINUTES, default 15], refresh_token [REFRESH_TOKEN_DAYS])."""
    access = create_token(user.id, ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_MINUTES), role=user.role)
    refresh = create_token(user.id, REFRESH, timedelta(days=settings.REFRESH_TOKEN_DAYS), role=user.role)
    return access, refresh


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Verify signature, issuer and expiry; returns claims. Raises TokenError otherwise.

    `expected_type` ('access' | 'refresh' | ...) is optional so the shared one-argument call
    `decode_token(token)` keeps working; get_current_user always demands 'access'.
    """
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if expected_type is not None and claims.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return claims


# --------------------------------------------------------------------------------------
# FastAPI dependencies
# --------------------------------------------------------------------------------------
def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the bearer access token to a User row (401 on any problem)."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    try:
        claims = decode_token(credentials.credentials, expected_type=ACCESS)
        user_id = uuid.UUID(claims["sub"])
    except (TokenError, ValueError) as exc:
        raise _unauthorized("Invalid or expired token") from exc
    user = session.get(User, user_id)
    if user is None:
        raise _unauthorized("User no longer exists")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    """Dependency factory: `user: User = Depends(require_roles('caregiver', 'admin'))`."""
    if not roles:
        raise ValueError("require_roles() needs at least one role")
    unknown = set(roles) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown role(s): {sorted(unknown)}")
    allowed = frozenset(roles)

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this action")
        return user

    return _dependency


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        return None


def can_access_patient(session: Session, user: User, patient_id: uuid.UUID | str) -> bool:
    pid = _as_uuid(patient_id)
    if pid is None:
        return False
    if user.role == "admin":
        return True
    if user.role == "patient":
        return user.id == pid
    if user.role in ("caregiver", "health_worker"):
        link = session.scalar(
            select(CaregiverLink.id).where(
                CaregiverLink.caregiver_id == user.id, CaregiverLink.patient_id == pid
            )
        )
        return link is not None
    return False


def assert_can_access_patient(session: Session, user: User, patient_id: uuid.UUID | str) -> None:
    """admin: any patient | patient: only self | caregiver/health_worker: needs a caregiver_links row.

    Raises HTTPException(403) otherwise. (Existence of the patient is the route's concern: 404.)
    """
    if not can_access_patient(session, user, patient_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this patient")


def accessible_patient_ids(session: Session, user: User) -> set[uuid.UUID] | None:
    """Ids a user may see, for list endpoints. None means 'all patients' (admin)."""
    if user.role == "admin":
        return None
    if user.role == "patient":
        return {user.id}
    if user.role in ("caregiver", "health_worker"):
        rows = session.scalars(select(CaregiverLink.patient_id).where(CaregiverLink.caregiver_id == user.id))
        return set(rows)
    return set()
