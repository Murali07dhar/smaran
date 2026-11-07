"""
Claude 1.2 — Auth, Patients, Consent.

Routes (mounted by main.py under /api/v1, per the shared contract):
    POST /auth/register
    POST /auth/login
    POST /auth/refresh
    POST /auth/patient-pin-login
    GET  /me
    POST /patients
    GET  /patients
    GET  /patients/{id}
    POST /patients/{id}/pin
    POST /caregiver-links
    GET  /patients/{id}/consents
    POST /patients/{id}/consents

Only imports app.core.db / app.core.security / app.models per the shared
interface contract — nothing here reimplements password/pin hashing,
JWT encode/decode, role checks or patient-access checks; those come from
app.core.security exactly as specified. Redis usage (rate limiting, refresh
rotation, PIN/QR ephemeral storage) is module-local — see redis_client.py,
rate_limit.py, qr.py, tokens.py for why, and HANDOFF.md for the contract
notes this implies.
"""
from __future__ import annotations

from uuid import UUID

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import (
    assert_can_access_patient,
    create_tokens,
    decode_token,
    get_current_user,
    hash_password,
    hash_pin,
    require_roles,
    verify_password,
    verify_pin,
)
from app.models import (
    Alert,
    CaregiverLink,
    ConsentRecord,
    GameSession,
    PatientProfile,
    SeverityIndicator,
    User,
)

from . import qr, rate_limit, tokens
from .redis_client import get_redis
from .schemas import (
    CaregiverLinkCreate,
    CaregiverLinkOut,
    ConsentCreate,
    ConsentRecordOut,
    ConsentsOut,
    LoginRequest,
    MeOut,
    PatientCreateRequest,
    PatientDetail,
    PatientListItem,
    PatientPinLoginRequest,
    PinIssueOut,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(tags=["auth_consent"])


# --------------------------------------------------------------- utilities
def _problem(status_code: int, title: str, detail: Optional[str] = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _issue_tokens_and_track(session: Session, redis, user: User) -> TokenResponse:
    access, refresh = create_tokens(user)
    refresh_claims = decode_token(refresh)
    ttl = max(1, refresh_claims["exp"] - int(datetime.now(timezone.utc).timestamp()))
    tokens.mark_active(redis, refresh_claims["jti"], ttl)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


def _enrich_patient(session: Session, patient: User, profile: PatientProfile) -> dict:
    last_active_at = session.query(func.max(GameSession.started_at)).filter(
        GameSession.patient_id == patient.id
    ).scalar()
    open_alerts = (
        session.query(func.count(Alert.id))
        .filter(Alert.patient_id == patient.id, Alert.acknowledged_at.is_(None))
        .scalar()
        or 0
    )
    latest_severity = (
        session.query(SeverityIndicator)
        .filter(SeverityIndicator.patient_id == patient.id)
        .order_by(SeverityIndicator.computed_at.desc())
        .first()
    )
    return {
        "id": patient.id,
        "name": patient.name,
        "age": profile.age,
        "language": profile.language,
        "estimated_stage": profile.estimated_stage,
        "last_active_at": last_active_at,
        "open_alerts": int(open_alerts),
        "severity_band": latest_severity.band if latest_severity else None,
        "notes": profile.notes,
    }


def _get_patient_or_404(session: Session, patient_id: UUID) -> tuple[User, PatientProfile]:
    patient = session.get(User, patient_id)
    profile = session.get(PatientProfile, patient_id)
    if patient is None or profile is None or patient.role != "patient":
        raise _problem(status.HTTP_404_NOT_FOUND, "patient_not_found")
    return patient, profile


# -------------------------------------------------------------------- auth
@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    session: Session = Depends(get_session),
    redis=Depends(get_redis),
) -> TokenResponse:
    if body.email and session.query(User).filter(User.email == body.email).first():
        raise _problem(status.HTTP_409_CONFLICT, "email_already_registered")
    if body.phone and session.query(User).filter(User.phone == body.phone).first():
        raise _problem(status.HTTP_409_CONFLICT, "phone_already_registered")

    user = User(
        role=body.role,
        name=body.name,
        email=body.email,
        phone=body.phone,
        password_hash=hash_password(body.password),
        language=body.language,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _issue_tokens_and_track(session, redis, user)


@router.post("/auth/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
    redis=Depends(get_redis),
) -> TokenResponse:
    ip = rate_limit.client_ip(request)
    identifier = body.identifier
    rate_limit.assert_not_locked(redis, ip, identifier)

    query = session.query(User)
    user = (
        query.filter(User.email == body.email).first()
        if body.email
        else query.filter(User.phone == body.phone).first()
    )

    if user is None or user.role == "patient" or not verify_password(body.password, user.password_hash):
        rate_limit.record_failure(redis, ip, identifier)
        raise _problem(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")

    rate_limit.clear_failures(redis, ip, identifier)
    return _issue_tokens_and_track(session, redis, user)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest,
    session: Session = Depends(get_session),
    redis=Depends(get_redis),
) -> TokenResponse:
    claims = decode_token(body.refresh_token)
    if claims.get("type") != "refresh":
        raise _problem(status.HTTP_401_UNAUTHORIZED, "not_a_refresh_token")
    if not tokens.is_active(redis, claims["jti"]):
        raise _problem(status.HTTP_401_UNAUTHORIZED, "refresh_token_revoked")

    user = session.get(User, UUID(claims["sub"]))
    if user is None:
        raise _problem(status.HTTP_401_UNAUTHORIZED, "user_not_found")

    tokens.revoke(redis, claims["jti"])
    return _issue_tokens_and_track(session, redis, user)


@router.post("/auth/patient-pin-login", response_model=TokenResponse)
def patient_pin_login(
    body: PatientPinLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
    redis=Depends(get_redis),
) -> TokenResponse:
    ip = rate_limit.client_ip(request)
    identifier = body.pin or "qr"
    rate_limit.assert_not_locked(redis, ip, identifier)

    if body.qr_token:
        try:
            patient_id = qr.verify_and_consume_qr(redis, body.qr_token)
        except HTTPException:
            rate_limit.record_failure(redis, ip, identifier)
            raise
    else:
        patient_id = qr.lookup_patient_by_pin(redis, body.pin)
        if patient_id is None:
            rate_limit.record_failure(redis, ip, identifier)
            raise _problem(status.HTTP_401_UNAUTHORIZED, "invalid_or_expired_pin")

    user = session.get(User, UUID(str(patient_id)))
    if user is None or user.role != "patient":
        rate_limit.record_failure(redis, ip, identifier)
        raise _problem(status.HTTP_401_UNAUTHORIZED, "invalid_or_expired_pin")

    if body.pin and not verify_pin(body.pin, user.pin_hash):
        # Defense in depth: Redis said this pin maps to this patient, but
        # the persisted hash (written at issue time) must also match.
        rate_limit.record_failure(redis, ip, identifier)
        raise _problem(status.HTTP_401_UNAUTHORIZED, "invalid_or_expired_pin")

    rate_limit.clear_failures(redis, ip, identifier)
    return _issue_tokens_and_track(session, redis, user)


@router.get("/me", response_model=MeOut)
def me(current_user: User = Depends(get_current_user)) -> MeOut:
    return MeOut.model_validate(current_user)


# ---------------------------------------------------------------- patients
@router.post("/patients", response_model=PatientDetail, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: PatientCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles("caregiver", "health_worker", "admin")),
) -> PatientDetail:
    patient = User(role="patient", name=body.name, language=body.language)
    session.add(patient)
    session.flush()  # assign patient.id before using it as an FK

    profile = PatientProfile(patient_id=patient.id, age=body.age, language=body.language)
    session.add(profile)

    if current_user.role == "caregiver":
        # Not in the literal POST /patients request body — the caregiver
        # who creates a patient is auto-linked so they immediately see the
        # patient in GET /patients ("caregivers see only linked patients").
        # relation defaults to "primary"; see HANDOFF.md "Contract notes".
        session.add(
            CaregiverLink(caregiver_id=current_user.id, patient_id=patient.id, relation="primary")
        )

    session.commit()
    session.refresh(patient)
    session.refresh(profile)
    return PatientDetail(**_enrich_patient(session, patient, profile))


@router.get("/patients", response_model=list[PatientListItem])
def list_patients(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles("caregiver", "health_worker", "admin")),
) -> list[PatientListItem]:
    if current_user.role == "caregiver":
        patient_ids = [
            row.patient_id
            for row in session.query(CaregiverLink.patient_id)
            .filter(CaregiverLink.caregiver_id == current_user.id)
            .all()
        ]
        patients = session.query(User).filter(User.id.in_(patient_ids)).all() if patient_ids else []
    else:
        patients = session.query(User).filter(User.role == "patient").all()

    out: list[PatientListItem] = []
    for patient in patients:
        profile = session.get(PatientProfile, patient.id)
        if profile is None:
            continue
        out.append(PatientListItem(**_enrich_patient(session, patient, profile)))
    return out


@router.get("/patients/{patient_id}", response_model=PatientDetail)
def get_patient(
    patient_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PatientDetail:
    assert_can_access_patient(session, current_user, patient_id)
    patient, profile = _get_patient_or_404(session, patient_id)
    return PatientDetail(**_enrich_patient(session, patient, profile))


@router.post("/patients/{patient_id}/pin", response_model=PinIssueOut)
def issue_patient_pin(
    patient_id: UUID,
    session: Session = Depends(get_session),
    redis=Depends(get_redis),
    current_user: User = Depends(require_roles("caregiver", "health_worker", "admin")),
) -> PinIssueOut:
    assert_can_access_patient(session, current_user, patient_id)
    patient, _ = _get_patient_or_404(session, patient_id)

    pin, pin_expires_at = qr.generate_pin(redis, patient_id)
    qr_token, qr_expires_at = qr.generate_qr_token(patient_id)

    patient.pin_hash = hash_pin(pin)
    session.add(patient)
    session.commit()

    return PinIssueOut(pin=pin, qr_token=qr_token, expires_at=min(pin_expires_at, qr_expires_at))


# ----------------------------------------------------------- caregiver links
@router.post("/caregiver-links", response_model=CaregiverLinkOut, status_code=status.HTTP_201_CREATED)
def create_caregiver_link(
    body: CaregiverLinkCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CaregiverLinkOut:
    if current_user.role == "patient":
        raise _problem(status.HTTP_403_FORBIDDEN, "forbidden")
    # The requester must already be able to see this patient (existing
    # caregiver on the case, or health_worker/admin) to add another
    # caregiver to it.
    assert_can_access_patient(session, current_user, body.patient_id)
    _get_patient_or_404(session, body.patient_id)

    target = session.get(User, body.caregiver_id)
    if target is None or target.role != "caregiver":
        raise _problem(status.HTTP_404_NOT_FOUND, "caregiver_not_found")

    existing = (
        session.query(CaregiverLink)
        .filter_by(caregiver_id=body.caregiver_id, patient_id=body.patient_id)
        .first()
    )
    if existing is not None:
        raise _problem(status.HTTP_409_CONFLICT, "link_already_exists")

    link = CaregiverLink(
        caregiver_id=body.caregiver_id, patient_id=body.patient_id, relation=body.relation
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return CaregiverLinkOut.model_validate(link)


# ---------------------------------------------------------------- consents
@router.get("/patients/{patient_id}/consents", response_model=ConsentsOut)
def get_consents(
    patient_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ConsentsOut:
    assert_can_access_patient(session, current_user, patient_id)
    _get_patient_or_404(session, patient_id)

    history = (
        session.query(ConsentRecord)
        .filter(ConsentRecord.patient_id == patient_id)
        .order_by(ConsentRecord.ts.desc())
        .all()
    )
    latest: dict[str, ConsentRecordOut] = {}
    for record in history:
        if record.kind not in latest:
            latest[record.kind] = ConsentRecordOut.model_validate(record)

    return ConsentsOut(
        latest=latest,
        history=[ConsentRecordOut.model_validate(r) for r in history],
    )


@router.post("/patients/{patient_id}/consents", response_model=ConsentRecordOut, status_code=status.HTTP_201_CREATED)
def post_consent(
    patient_id: UUID,
    body: ConsentCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ConsentRecordOut:
    assert_can_access_patient(session, current_user, patient_id)
    _get_patient_or_404(session, patient_id)

    record = ConsentRecord(
        patient_id=patient_id,
        kind=body.kind,
        granted=body.granted,
        granted_by=current_user.id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return ConsentRecordOut.model_validate(record)
