"""Test wiring for the media module.

Runs against mocks/core_stub (stand-ins for 1.1 / 1.4 code) until the Integrator deletes the stub;
the sys.path insert is skipped automatically once mocks/core_stub no longer exists.
"""
import base64
import os
import sys
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
API_ROOT = HERE.parents[2]                       # services/api
STUB = HERE.parents[4] / "mocks" / "core_stub"   # mocks/core_stub
for p in (API_ROOT, STUB):
    if p.exists() and str(p) not in sys.path:
        sys.path.append(str(p))


@pytest.fixture(autouse=True)
def media_env(tmp_path, monkeypatch):
    """Fresh random key + temp MEDIA_DIR for every test (no secrets in the repo)."""
    from app.core.config import settings

    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(settings, "MEDIA_KEY_B64", key, raising=False)
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.delenv("MEDIA_URL_TTL_SECONDS", raising=False)
    return {"key": key, "dir": tmp_path / "media"}


# ----- API fixtures (need fastapi + sqlalchemy; pure-logic tests do not use these) -----

@pytest.fixture()
def world():
    """In-memory DB with: one patient, one linked caregiver, one unlinked caregiver, a health worker."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core import db
    from app.models import CaregiverLink, User

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def mk(role, name):
        return User(id=uuid.uuid4(), role=role, name=name, language="en")

    patient, cg, other_cg, hw = mk("patient", "Pa"), mk("caregiver", "Cg"), mk("caregiver", "Other"), mk("health_worker", "Hw")
    with Session() as s:
        s.add_all([patient, cg, other_cg, hw])
        s.flush()
        s.add(CaregiverLink(id=uuid.uuid4(), caregiver_id=cg.id, patient_id=patient.id, relation="son"))
        s.add(CaregiverLink(id=uuid.uuid4(), caregiver_id=hw.id, patient_id=patient.id, relation="chw"))
        s.commit()
    return {"Session": Session, "patient": patient, "cg": cg, "other_cg": other_cg, "hw": hw}


def _install_recorder(changelog):
    """Wrap the REAL record_change: keep its DB write, also append each call to changelog.CALLS."""
    if getattr(changelog, "_recorder_installed", False):
        return
    real = changelog.record_change
    changelog.CALLS = []
    changelog.reset = changelog.CALLS.clear

    def recording(session, entity, entity_id, action, payload, patient_id):
        real(session, entity, entity_id, action, payload, patient_id)
        changelog.CALLS.append({"entity": entity, "entity_id": entity_id, "action": action,
                                "payload": payload, "patient_id": patient_id})

    changelog.record_change = recording
    changelog._recorder_installed = True


@pytest.fixture()
def client_for(world):
    """client_for(user) -> TestClient authenticated as that user."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.security import get_current_user
    from app.modules.media.router import router
    from app.modules.sync import changelog

    _install_recorder(changelog)
    changelog.reset()

    def make(user):
        app = FastAPI()  # one app per client so several users can act in the same test
        app.include_router(router, prefix="/api/v1")

        def _session():
            with world["Session"]() as s:
                yield s

        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    return make


# ----- sample files -----

def _jpeg(with_gps=False):
    import io
    from PIL import Image

    img = Image.new("RGB", (32, 24), (10, 120, 110))
    kw = {}
    if with_gps:
        exif = Image.Exif()
        exif[0x0112] = 6
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2], gps[3], gps[4] = "N", (26.0, 10.0, 30.0), "E", (91.0, 45.0, 0.0)
        kw["exif"] = exif
    out = io.BytesIO()
    img.save(out, "JPEG", **kw)
    return out.getvalue()


@pytest.fixture()
def jpeg_bytes():
    return _jpeg


@pytest.fixture()
def wav_bytes():
    # 44-byte RIFF/WAVE header + a little silence: enough for magic-byte sniffing
    return b"RIFF" + (36 + 200).to_bytes(4, "little") + b"WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00" \
        + (8000).to_bytes(4, "little") + (16000).to_bytes(4, "little") + b"\x02\x00\x10\x00data" \
        + (200).to_bytes(4, "little") + b"\x00" * 200
