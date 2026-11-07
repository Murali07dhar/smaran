"""Test wiring for the insights module.

Runs against the core_stub + in-memory SQLite by default. After integration (stub deleted) point
TEST_DATABASE_URL at a Postgres test database to run against the real models.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
for p in (REPO / "services" / "api", REPO / "mocks" / "core_stub", REPO / "mocks"):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite://")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("AI_SERVICE_URL", "http://ai.test")
os.environ.setdefault("VOICE_SERVICE_URL", "http://voice.test")
os.environ.setdefault("MEDIA_KEY_B64", "")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401  (registers tables on Base)
from app.core.db import Base, get_session  # noqa: E402
from app.core.security import get_current_user  # noqa: E402
from app.modules.insights import pipeline, router as router_module  # noqa: E402


@pytest.fixture()
def engine():
    url = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite://")
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    eng = create_engine(url, **kwargs)
    Base.metadata.create_all(eng)
    yield eng
    if url.startswith("sqlite"):
        Base.metadata.drop_all(eng)
    else:  # shared Postgres test DB (schema owned by tests/conftest.py): empty tables, never drop them
        from sqlalchemy import text
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        with eng.begin() as c:
            c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture()
def changes(monkeypatch):
    """Replace record_change in both modules with a recorder (no sync_changes table needed)."""
    recorded = []

    def fake(session, entity, entity_id, action, payload, patient_id):
        recorded.append({"entity": entity, "entity_id": entity_id, "action": action, "payload": payload, "patient_id": patient_id})

    monkeypatch.setattr(pipeline, "record_change", fake)
    monkeypatch.setattr(router_module, "record_change", fake)
    return recorded


@pytest.fixture()
def make_client(engine):
    def _make(user):
        app = FastAPI()
        app.include_router(router_module.router, prefix="/api/v1")

        def _session():
            with Session(engine, expire_on_commit=False) as s:
                yield s

        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    return _make
