"""
Pydantic v2 request/response models for auth_consent.
Shapes follow the ROUTES contract exactly; fields added beyond the literal
contract text (e.g. notes on patient detail) are called out in HANDOFF.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Role = Literal["patient", "caregiver", "health_worker", "admin"]
ConsentKind = Literal["camera", "mic", "data_sharing"]


# --------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str

    @model_validator(mode="after")
    def _one_identifier(self) -> "LoginRequest":
        if not self.email and not self.phone:
            raise ValueError("email or phone is required")
        return self

    @property
    def identifier(self) -> str:
        return (self.email or self.phone or "").lower()


class RefreshRequest(BaseModel):
    refresh_token: str


class PatientPinLoginRequest(BaseModel):
    pin: Optional[str] = Field(default=None, min_length=6, max_length=6)
    qr_token: Optional[str] = None

    @model_validator(mode="after")
    def _one_of(self) -> "PatientPinLoginRequest":
        if not self.pin and not self.qr_token:
            raise ValueError("pin or qr_token is required")
        if self.pin and self.qr_token:
            raise ValueError("provide only one of pin or qr_token")
        return self


class RegisterRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str = Field(min_length=8)
    role: Literal["caregiver", "health_worker"]
    language: str = "en"

    @model_validator(mode="after")
    def _one_identifier(self) -> "RegisterRequest":
        if not self.email and not self.phone:
            raise ValueError("email or phone is required")
        return self


class UserOut(BaseModel):
    id: UUID
    role: Role
    name: str
    language: str

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# ---------------------------------------------------------------- patients
class PatientCreateRequest(BaseModel):
    name: str
    age: int = Field(ge=0, le=130)
    language: str


class PatientListItem(BaseModel):
    id: UUID
    name: str
    age: int
    language: str
    estimated_stage: Optional[str] = None
    last_active_at: Optional[datetime] = None
    open_alerts: int
    severity_band: Optional[str] = None


class PatientDetail(PatientListItem):
    # Not in the literal ROUTES line for GET /patients but present in the
    # fixed schema (patient_profiles.notes); included here since it is
    # caregiver-authored context useful on the single-patient view. See
    # HANDOFF.md "Contract deviations" — additive only, nothing removed.
    notes: Optional[str] = None


class PinIssueOut(BaseModel):
    pin: str
    qr_token: str
    expires_at: datetime


class CaregiverLinkCreate(BaseModel):
    caregiver_id: UUID
    patient_id: UUID
    relation: str


class CaregiverLinkOut(BaseModel):
    id: UUID
    caregiver_id: UUID
    patient_id: UUID
    relation: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- consents
class ConsentCreate(BaseModel):
    kind: ConsentKind
    granted: bool


class ConsentRecordOut(BaseModel):
    id: UUID
    patient_id: UUID
    kind: ConsentKind
    granted: bool
    granted_by: UUID
    ts: datetime

    model_config = {"from_attributes": True}


class ConsentsOut(BaseModel):
    latest: dict[str, ConsentRecordOut]
    history: list[ConsentRecordOut]


# ------------------------------------------------------------- RFC 7807
class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None
