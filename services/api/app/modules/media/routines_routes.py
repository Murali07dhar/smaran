"""Routines CRUD: /patients/{id}/routines (list, POST, PUT /{item_id}, DELETE /{item_id}).

Same rules as reminders: caregivers / health workers write, server_version bumps on every write,
record_change in the same transaction.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import assert_can_access_patient, get_current_user
from app.models import Routine
from app.modules.sync import changelog

from . import validation
from .common import ENTITY_ROUTINES, new_id, not_found, now_utc, require_writer
from .schemas import RoutineIn, RoutineOut

router = APIRouter(tags=["routines"])


def _to_out(row: Routine) -> RoutineOut:
    return RoutineOut(
        id=row.id,
        patient_id=row.patient_id,
        title=row.title,
        steps=validation.normalize_steps(row.steps),
        created_by=row.created_by,
        server_version=row.server_version,
        updated_at=validation.ensure_utc(row.updated_at),
    )


def _lock(session: Session, patient_id: uuid.UUID, item_id: uuid.UUID) -> Routine:
    row = session.scalar(
        select(Routine).where(Routine.id == item_id, Routine.patient_id == patient_id).with_for_update()
    )
    if row is None:
        raise not_found("Routine")
    return row


@router.get("/patients/{patient_id}/routines", response_model=list[RoutineOut])
def list_routines(
    patient_id: uuid.UUID,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    assert_can_access_patient(session, user, patient_id)
    rows = session.scalars(
        select(Routine).where(Routine.patient_id == patient_id).order_by(Routine.updated_at.desc(), Routine.id)
    ).all()
    return [_to_out(r) for r in rows]


@router.post("/patients/{patient_id}/routines", response_model=RoutineOut, status_code=201)
def create_routine(
    patient_id: uuid.UUID,
    body: RoutineIn,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    require_writer(user)
    assert_can_access_patient(session, user, patient_id)
    item_id = new_id(body.id)
    if session.get(Routine, item_id) is not None:
        raise HTTPException(status_code=409, detail="A routine with this id already exists")

    row = Routine(
        id=item_id,
        patient_id=patient_id,
        title=body.title,
        steps=body.steps,
        created_by=user.id,
        server_version=1,
        updated_at=now_utc(),
    )
    session.add(row)
    out = _to_out(row)
    try:
        changelog.record_change(session, ENTITY_ROUTINES, item_id, "upsert", out.model_dump(mode="json"), patient_id)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return out


@router.put("/patients/{patient_id}/routines/{item_id}", response_model=RoutineOut)
def update_routine(
    patient_id: uuid.UUID,
    item_id: uuid.UUID,
    body: RoutineIn,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    require_writer(user)
    assert_can_access_patient(session, user, patient_id)
    try:
        row = _lock(session, patient_id, item_id)
        row.title = body.title
        row.steps = body.steps
        row.server_version = (row.server_version or 0) + 1
        row.updated_at = now_utc()
        out = _to_out(row)
        changelog.record_change(session, ENTITY_ROUTINES, item_id, "upsert", out.model_dump(mode="json"), patient_id)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return out


@router.delete("/patients/{patient_id}/routines/{item_id}", status_code=204)
def delete_routine(
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
        changelog.record_change(session, ENTITY_ROUTINES, item_id, "delete", tombstone, patient_id)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return Response(status_code=204)
