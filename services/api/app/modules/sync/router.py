"""POST /sync/push and GET /sync/pull. Mounted by main.py under /api/v1."""
from __future__ import annotations

import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.db import get_session
from app.core.security import get_current_user
from app.models import SyncChange

from . import rules, service
from .schemas import PullChange, PullResponse, PushRequest, PushResponse, RejectedOp

log = logging.getLogger("smaran.sync")
router = APIRouter(prefix="/sync", tags=["sync"])


def process_synced_data(session, patient_id, session_ids) -> None:
    """Late-bound call into Claude 1.5's pipeline. No-op if the module is unavailable.
    Imported at call time to avoid a circular import (pipeline -> changelog -> sync)."""
    try:
        from app.modules.insights.pipeline import process_synced_data as impl
    except Exception:  # noqa: BLE001
        log.warning("insights pipeline unavailable; skipping process_synced_data")
        return
    impl(session, patient_id, session_ids)


@router.post("/push", response_model=PushResponse)
def push(body: PushRequest, session=Depends(get_session), user=Depends(get_current_user)):
    result = service.process_push(session, user, body)
    session.commit()

    # Pipeline runs AFTER the commit and can never fail the push.
    for patient_id, session_ids in result.pipeline_targets.items():
        try:
            process_synced_data(session, patient_id, sorted(session_ids, key=str))
            session.commit()  # persist anything the pipeline wrote (harmless if nothing pending)
        except Exception:  # noqa: BLE001
            log.exception("process_synced_data failed for patient %s", patient_id)
            session.rollback()

    return PushResponse(
        accepted=result.accepted,
        rejected=[RejectedOp(**r) for r in result.rejected],
        server_cursor=service.current_cursor(session),
    )


@router.get("/pull", response_model=PullResponse)
def pull(
    since: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    session=Depends(get_session),
    user=Depends(get_current_user),
):
    stmt = select(SyncChange).where(SyncChange.cursor > since, SyncChange.entity.in_(rules.PULL_ENTITIES))

    ids = service.accessible_patient_ids(session, user)
    if ids is not None:
        if not ids:
            return PullResponse(changes=[], server_cursor=since)
        stmt = stmt.where(SyncChange.patient_id.in_(ids))

    holdback = float(os.getenv("SYNC_PULL_HOLDBACK_SECONDS", "0") or 0)
    if holdback > 0:  # lets in-flight transactions with lower cursors commit before we serve past them
        stmt = stmt.where(SyncChange.server_ts <= rules.utcnow() - timedelta(seconds=holdback))

    rows = list(session.scalars(stmt.order_by(SyncChange.cursor).limit(limit)))
    changes = [
        PullChange(
            cursor=r.cursor,
            entity=r.entity,
            entity_id=r.entity_id,
            action=r.action,
            payload=rules.sanitize_pull_payload(r.entity, r.payload),
            patient_id=r.patient_id,
            server_ts=rules.as_utc(r.server_ts),
        )
        for r in rows
    ]
    return PullResponse(changes=changes, server_cursor=rows[-1].cursor if rows else since)
