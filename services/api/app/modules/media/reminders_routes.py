"""Reminders CRUD: /patients/{id}/reminders (list, POST, PUT /{item_id}, DELETE /{item_id}).

Rules: read = anyone with access to the patient; write = caregiver / health_worker with access.
Every write bumps server_version (starts at 1) and calls changelog.record_change in the same
transaction, so a device can never miss a change that was committed. Rows are locked with
SELECT ... FOR UPDATE while editing so concurrent PUTs cannot produce the same version twice.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import assert_can_access_patient, get_current_user
from app.models import MediaAsset, Reminder
from app.modules.sync import changelog

from . import validation
from .common import ENTITY_REMINDERS, new_id, not_found, now_utc, require_writer
from .schemas import ReminderIn, ReminderOut

router = APIRouter(tags=["reminders"])


def _to_out(row: Reminder) -> ReminderOut:
    return ReminderOut(
        id=row.id,
        patient_id=row.patient_id,
        category=row.category,
        title=row.title,
        schedule=row.schedule_rrule,
        locale=row.locale,
        voice_clip_id=row.voice_clip_id,
        escalate_after_misses=row.escalate_after_misses,
        active=row.active,
        server_version=row.server_version,
        updated_at=validation.ensure_utc(row.updated_at),
    )


def _check_voice_clip(session: Session, patient_id: uuid.UUID, clip_id: uuid.UUID | None) -> None:
    """voice_clip_id may point at a caregiver recording in media_assets (must be this patient's audio).
    Ids that match no media asset are assumed to be voice-pack clips owned by services/voice and are accepted."""
    if clip_id is None:
        return
    asset = session.get(MediaAsset, clip_id)
    if asset is not None and (asset.patient_id != patient_id or asset.kind != "audio"):
        raise HTTPException(status_code=422, detail="voice_clip_id must be an audio recording of this patient")


def _lock(session: Session, patient_id: uuid.UUID, item_id: uuid.UUID) -> Reminder:
    row = session.scalar(
        select(Reminder).where(Reminder.id == item_id, Reminder.patient_id == patient_id).with_for_update()
    )
    if row is None:
        raise not_found("Reminder")
    return row


@router.get("/patients/{patient_id}/reminders", response_model=list[ReminderOut])
def list_reminders(
    patient_id: uuid.UUID,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    assert_can_access_patient(session, user, patient_id)
    rows = session.scalars(
        select(Reminder).where(Reminder.patient_id == patient_id).order_by(Reminder.updated_at.desc(), Reminder.id)
    ).all()
    return [_to_out(r) for r in rows]


@router.post("/patients/{patient_id}/reminders", response_model=ReminderOut, status_code=201)
def create_reminder(
    patient_id: uuid.UUID,
    body: ReminderIn,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    require_writer(user)
    assert_can_access_patient(session, user, patient_id)
    _check_voice_clip(session, patient_id, body.voice_clip_id)
    item_id = new_id(body.id)
    if session.get(Reminder, item_id) is not None:
        raise HTTPException(status_code=409, detail="A reminder with this id already exists")

    row = Reminder(
        id=item_id,
        patient_id=patient_id,
        category=body.category,
        title=body.title,
        schedule_rrule=body.schedule,
        locale=body.locale,
        voice_clip_id=str(body.voice_clip_id) if body.voice_clip_id else None,
        escalate_after_misses=body.escalate_after_misses,
        active=body.active,
        server_version=1,
        updated_at=now_utc(),
    )
    session.add(row)
    out = _to_out(row)
    try:
        changelog.record_change(session, ENTITY_REMINDERS, item_id, "upsert", out.model_dump(mode="json"), patient_id)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return out


@router.put("/patients/{patient_id}/reminders/{item_id}", response_model=ReminderOut)
def update_reminder(
    patient_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReminderIn,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    require_writer(user)
    assert_can_access_patient(session, user, patient_id)
    _check_voice_clip(session, patient_id, body.voice_clip_id)
    try:
        row = _lock(session, patient_id, item_id)
        row.category = body.category
        row.title = body.title
        row.schedule_rrule = body.schedule
        row.locale = body.locale
        row.voice_clip_id = str(body.voice_clip_id) if body.voice_clip_id else None
        row.escalate_after_misses = body.escalate_after_misses
        row.active = body.active
        row.server_version = (row.server_version or 0) + 1
        row.updated_at = now_utc()
        out = _to_out(row)
        changelog.record_change(session, ENTITY_REMINDERS, item_id, "upsert", out.model_dump(mode="json"), patient_id)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return out


@router.delete("/patients/{patient_id}/reminders/{item_id}", status_code=204)
def delete_reminder(
    patient_id: uuid.UUID,
    item_id: uuid.UUID,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    require_writer(user)
    assert_can_access_patient(session, user, patient_id)
    try:
        row = _lock(session, patient_id, item_id)
        tombstone = {
            "id": str(item_id),
            "patient_id": str(patient_id),
            "server_version": (row.server_version or 0) + 1,
        }
        session.delete(row)
        changelog.record_change(session, ENTITY_REMINDERS, item_id, "delete", tombstone, patient_id)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return Response(status_code=204)
