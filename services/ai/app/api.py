"""The five AI SERVICE contract endpoints (mounted under /ai). Thin wrappers over app.core."""
from __future__ import annotations

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from .clock import parse_iso, utcnow
from .config import Settings
from .core import content, difficulty, emotion, severity, triggers
from .schemas import (
    ContentRequest,
    ContentResponse,
    DifficultyRequest,
    DifficultyResponse,
    FuseRequest,
    FuseResponse,
    SeverityRequest,
    SeverityResponse,
    TriggersUpdateRequest,
    TriggersUpdateResponse,
)
from .store import Store


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_now(request: Request, settings: Settings = Depends(get_settings_dep)) -> datetime:
    """Server clock. X-Smaran-Now is honoured ONLY when AI_ALLOW_TIME_OVERRIDE=1 (tests/demos)."""
    if settings.allow_time_override:
        hdr = request.headers.get("x-smaran-now")
        if hdr:
            try:
                return parse_iso(hdr)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid X-Smaran-Now header") from exc
    return utcnow()


def require_service_token(request: Request, settings: Settings = Depends(get_settings_dep)) -> None:
    """Service-to-service auth: services/api must send 'Authorization: Bearer <AI_SERVICE_TOKEN>'."""
    if not settings.service_token:
        return
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), settings.service_token.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid service token",
                            headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/ai", dependencies=[Depends(require_service_token)])


@router.post("/triggers/update", response_model=TriggersUpdateResponse)
def triggers_update(body: TriggersUpdateRequest, store: Store = Depends(get_store),
                    now: datetime = Depends(get_now)) -> TriggersUpdateResponse:
    return TriggersUpdateResponse(
        triggers=triggers.update_triggers(store, body.patient_id, body.observations, now))


@router.post("/difficulty/next", response_model=DifficultyResponse)
def difficulty_next(body: DifficultyRequest, store: Store = Depends(get_store),
                    now: datetime = Depends(get_now)) -> DifficultyResponse:
    r = difficulty.next_difficulty(store, body.patient_id, body.game_id, body.recent,
                                   body.current_difficulty, now)
    return DifficultyResponse(difficulty=r.difficulty, rationale=r.rationale)


@router.post("/severity/estimate", response_model=SeverityResponse)
def severity_estimate(body: SeverityRequest, store: Store = Depends(get_store),
                      now: datetime = Depends(get_now)) -> SeverityResponse:
    return severity.estimate(store, body.patient_id, body.window_days, now, body.samples)


@router.post("/emotion/fuse", response_model=FuseResponse)
def emotion_fuse(body: FuseRequest) -> FuseResponse:
    return FuseResponse(**emotion.fuse(body.face, body.speech, body.baseline))


@router.post("/content/generate", response_model=ContentResponse)
def content_generate(body: ContentRequest, settings: Settings = Depends(get_settings_dep)) -> ContentResponse:
    text, source = content.generate(settings, body.kind, body.locale, body.context)
    return ContentResponse(text=text, source=source)
