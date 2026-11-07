from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fakeredis
from sqlalchemy.orm import Session

from app.core.db import Base, get_session
from app.core.security import create_tokens, hash_password
from app.models import CaregiverLink, PatientProfile, User
from app.modules.auth_consent import router
from app.modules.auth_consent.redis_client import get_redis


@pytest.fixture(scope="function")
def db_session(engine):
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:  # per-test cleanup (children first)
            for t in reversed(Base.metadata.sorted_tables):
                conn.execute(t.delete())


@pytest.fixture(scope="function")
def fake_redis():
    return fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)


@pytest.fixture(scope="function")
def app(db_session, fake_redis):
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")

    def _get_session_override():
        yield db_session

    application.dependency_overrides[get_session] = _get_session_override
    application.dependency_overrides[get_redis] = lambda: fake_redis
    return application


@pytest.fixture(scope="function")
def client(app):
    return TestClient(app)


@pytest.fixture
def make_caregiver(db_session):
    def _make(name="Priya Caregiver", email="priya@example.com", password="correct-horse-1"):
        user = User(
            role="caregiver",
            name=name,
            email=email,
            password_hash=hash_password(password),
            language="en",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user, password

    return _make


@pytest.fixture
def make_health_worker(db_session):
    def _make(name="Dr. Health Worker", email="hw@example.com", password="correct-horse-2"):
        user = User(
            role="health_worker",
            name=name,
            email=email,
            password_hash=hash_password(password),
            language="en",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user, password

    return _make


@pytest.fixture
def make_patient(db_session):
    def _make(name="Grandma Devi", age=72, language="as", caregiver=None):
        patient = User(role="patient", name=name, language=language)
        db_session.add(patient)
        db_session.flush()
        profile = PatientProfile(patient_id=patient.id, age=age, language=language)
        db_session.add(profile)
        if caregiver is not None:
            db_session.add(
                CaregiverLink(caregiver_id=caregiver.id, patient_id=patient.id, relation="primary")
            )
        db_session.commit()
        db_session.refresh(patient)
        return patient

    return _make


@pytest.fixture
def auth_headers(fake_redis):
    def _headers(user):
        access, refresh = create_tokens(user)
        return {"Authorization": f"Bearer {access}"}, refresh

    return _headers
