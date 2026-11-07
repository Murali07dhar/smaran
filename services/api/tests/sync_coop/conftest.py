"""Fixtures for 1.4 (sync + co-op) tests, wired to the REAL core (alembic-migrated DB from tests/conftest.py)."""
import importlib.util
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("COOP_USE_LUA", "1" if importlib.util.find_spec("lupa") else "0")


@pytest.fixture()
def SessionFactory(engine):
    from app.core.db import Base

    yield sessionmaker(engine, expire_on_commit=False)
    with engine.begin() as conn:  # per-test cleanup (children first)
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(t.delete())

@pytest.fixture()
def api(engine, SessionFactory):
    import fakeredis
    from fakeredis import aioredis as fake_aioredis

    from app.core.db import get_session
    from app.modules.coop.deps import get_redis
    from app.modules.coop.router import router as coop_router, ws_router
    from app.modules.sync.router import router as sync_router

    application = FastAPI()
    application.include_router(sync_router, prefix="/api/v1")
    application.include_router(coop_router, prefix="/api/v1")
    application.include_router(ws_router)

    def _session():
        s = SessionFactory()
        try:
            yield s
        finally:
            s.close()

    redis_client = fake_aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    application.dependency_overrides[get_session] = _session
    application.dependency_overrides[get_redis] = lambda: redis_client
    return application


@pytest.fixture()
def client(api):
    # One `with` block = one event loop shared by REST calls and WebSockets (needed for the async Redis client).
    with TestClient(api) as c:
        yield c


@pytest.fixture()
def pipeline_calls(monkeypatch):
    from app.modules.insights import pipeline

    calls: list = []
    monkeypatch.setattr(pipeline, "process_synced_data", lambda session, patient_id, session_ids: calls.append((patient_id, list(session_ids))))
    return calls


@pytest.fixture()
def world(SessionFactory):
    """Two patients; caregiver_a linked to patient_a only; caregiver_x linked to nobody; one admin."""
    from app.models import CaregiverLink, User

    def make_user(s, role, name):
        u = User(id=uuid.uuid4(), role=role, name=name, language="en",
                 created_at=datetime.now(timezone.utc))
        s.add(u)
        return u

    with SessionFactory() as s:
        w = {
            "patient_a": make_user(s, "patient", "Pat A"),
            "patient_b": make_user(s, "patient", "Pat B"),
            "caregiver_a": make_user(s, "caregiver", "Care A"),
            "caregiver_x": make_user(s, "caregiver", "Care X"),
            "admin": make_user(s, "admin", "Admin"),
        }
        s.flush()
        s.add(CaregiverLink(id=uuid.uuid4(), caregiver_id=w["caregiver_a"].id,
                            patient_id=w["patient_a"].id, relation="daughter",
                            created_at=datetime.now(timezone.utc)))
        s.commit()
    return w


def hdr(user):
    from app.core.security import create_tokens

    return {"Authorization": f"Bearer {create_tokens(user)[0]}"}
