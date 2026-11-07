"""Media routes (caregiver photos / voice recordings), encrypted at rest.

POST /media                          multipart: patient_id, kind, file, tags      (caregiver, health_worker)
GET  /patients/{id}/media            metadata list                                  (anyone with patient access)
GET  /media/{id}/url                 -> {url, expires_at}  signed, 10 min           (anyone with patient access)
GET  /media/{id}/content?sig=&exp=   decrypt + stream (Range supported)             (signature IS the credential)

The content route has no bearer-token dependency on purpose: <img>/<audio> elements cannot send an
Authorization header. Access control happens when /url is issued; the URL is an unguessable,
HMAC-signed, short-lived capability.
"""
import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import CryptoConfigError, CryptoError, decrypt_bytes, encrypt_bytes
from app.core.db import get_session
from app.core.security import assert_can_access_patient, get_current_user
from app.models import MediaAsset
from app.modules.sync import changelog

from . import signing, storage, validation
from .common import ENTITY_MEDIA, not_found, nonce_bytes, now_utc, require_writer
from .http_range import RangeNotSatisfiable, parse_range
from .ids import uuid7
from .schemas import MediaOut, SignedUrlOut

log = logging.getLogger(__name__)
router = APIRouter(tags=["media"])

CHUNK = 64 * 1024


def _to_out(asset: MediaAsset) -> MediaOut:
    return MediaOut(
        id=asset.id,
        patient_id=asset.patient_id,
        uploader_id=asset.uploader_id,
        kind=asset.kind,
        mime=asset.mime,
        size_bytes=asset.size_bytes,
        tags=asset.tags if asset.tags is not None else [],
        created_at=validation.ensure_utc(asset.created_at),
    )


@router.post("/media", response_model=MediaOut, status_code=201)
def upload_media(
    patient_id: uuid.UUID = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    tags: str | None = Form(None),
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    require_writer(user)
    assert_can_access_patient(session, user, patient_id)

    try:
        kind = validation.validate_kind(kind)
        mime = validation.validate_declared_mime(kind, file.content_type)
        tags_value = validation.parse_tags(tags)
        data = validation.read_limited(file.file, kind)
        validation.check_content(mime, data)
        if kind == "photo":
            data = validation.strip_image_metadata(data)  # removes EXIF GPS; no-op without Pillow
    except validation.MediaValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    media_id = uuid7()
    rel_path = storage.relative_path(patient_id, media_id)
    try:
        ciphertext, nonce = encrypt_bytes(data)
    except CryptoConfigError as exc:
        log.error("media encryption is not configured: %s", exc)
        raise HTTPException(status_code=500, detail="Media encryption is not configured") from exc

    storage.write_ciphertext(rel_path, ciphertext)
    try:
        asset = MediaAsset(
            id=media_id,
            patient_id=patient_id,
            uploader_id=user.id,
            kind=kind,
            mime=mime,
            size_bytes=len(data),  # plaintext size after metadata stripping
            enc_path=rel_path,
            nonce=nonce,
            tags=tags_value,
            created_at=now_utc(),
        )
        session.add(asset)
        out = _to_out(asset)
        # metadata only: never put enc_path or nonce on the wire
        changelog.record_change(
            session, ENTITY_MEDIA, media_id, "upsert", out.model_dump(mode="json"), patient_id
        )
        session.commit()
    except BaseException:
        session.rollback()
        storage.remove_ciphertext(rel_path)  # no orphan ciphertext when the DB write fails
        raise
    return out


@router.get("/patients/{patient_id}/media", response_model=list[MediaOut])
def list_media(
    patient_id: uuid.UUID,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    assert_can_access_patient(session, user, patient_id)
    rows = session.scalars(
        select(MediaAsset)
        .where(MediaAsset.patient_id == patient_id)
        .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
    ).all()
    return [_to_out(row) for row in rows]


@router.get("/media/{media_id}/url", response_model=SignedUrlOut)
def media_url(
    media_id: uuid.UUID,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    asset = session.get(MediaAsset, media_id)
    if asset is None:
        raise not_found("Media")
    assert_can_access_patient(session, user, asset.patient_id)
    sig, exp = signing.make_signature(media_id)
    # Relative on purpose: the API may sit behind a proxy and the native app has its own base URL.
    return SignedUrlOut(
        url=f"/api/v1/media/{media_id}/content?sig={sig}&exp={exp}",
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
    )


def _chunks(data: bytes, start: int, end: int) -> Iterator[bytes]:
    view = memoryview(data)
    for pos in range(start, end + 1, CHUNK):
        yield bytes(view[pos : min(pos + CHUNK, end + 1)])


@router.get("/media/{media_id}/content")
def media_content(
    media_id: uuid.UUID,
    request: Request,
    sig: str,
    exp: int,
    session: Session = Depends(get_session),
):
    # 1. Credential first (constant-time), before touching the DB or disk.
    try:
        signing.verify_signature(media_id, sig, exp)
    except signing.SignatureError as exc:
        raise HTTPException(status_code=403, detail=exc.detail) from exc

    asset = session.get(MediaAsset, media_id)
    if asset is None:
        raise not_found("Media")

    # 2. Decrypt (AES-GCM also authenticates: tampered files fail here instead of being served).
    try:
        plaintext = decrypt_bytes(storage.read_ciphertext(asset.enc_path), nonce_bytes(asset.nonce))
    except FileNotFoundError as exc:
        log.error("media file missing on disk: %s", asset.id)
        raise HTTPException(status_code=404, detail="Media file is missing") from exc
    except CryptoConfigError as exc:
        log.error("media encryption is not configured: %s", exc)
        raise HTTPException(status_code=500, detail="Media encryption is not configured") from exc
    except CryptoError as exc:
        log.error("media integrity check failed: %s", asset.id)
        raise HTTPException(status_code=500, detail="Stored media failed its integrity check") from exc

    size = len(plaintext)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": "inline",
    }
    try:
        byte_range = parse_range(request.headers.get("range"), size)
    except RangeNotSatisfiable:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})

    if byte_range is None:
        start, end, status = 0, size - 1, 200
    else:
        start, end = byte_range
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(_chunks(plaintext, start, end), status_code=status, media_type=asset.mime, headers=headers)
