"""Test fixtures.

Default DB: a throw-away SQLite file (fast, no services needed).
Real target: export TEST_DATABASE_URL=postgresql+psycopg://user:pw@host/db  (DB is WIPED).
The schema is always created with `alembic upgrade head`, so every run exercises the migration.
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="smaran-tests-"))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_TMP / 'test.db'}"
os.environ.update(
    JWT_SECRET="test-secret-test-secret-test-secret-0123456789",
    DATABASE_URL=TEST_DB_URL,
    ENVIRONMENT="test",
    BCRYPT_ROUNDS="4",
    MODULE_STUBS_PATH="",
    STRICT_MODULES="0",
)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import Base, make_engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import CaregiverLink, PatientProfile, User  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def wipe(engine) -> None:
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        else:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            for t in list(Base.metadata.tables) + ["alembic_version"]:
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{t}"')
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest.fixture(scope="session")
def db_url() -> str:
    return TEST_DB_URL


@pytest.fixture(scope="session")
def engine(db_url):
    eng = make_engine(db_url)
    wipe(eng)
    command.upgrade(alembic_config(db_url), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    s = Session(engine, expire_on_commit=False)
    yield s
    s.rollback()
    s.close()
    with engine.begin() as conn:  # per-test cleanup (cascades clear children)
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(t.delete())


def make_user(session: Session, role: str, name: str | None = None, **kw) -> User:
    user = User(role=role, name=name or role.title(), language=kw.pop("language", "en"),
                email=kw.pop("email", f"{role}-{os.urandom(3).hex()}@t.test"),
                password_hash=kw.pop("password_hash", hash_password("pw-12345678")), **kw)
    session.add(user)
    session.flush()
    if role == "patient":
        session.add(PatientProfile(patient_id=user.id, age=70, language=user.language))
    return user


def link(session: Session, caregiver: User, patient: User, relation: str = "daughter") -> None:
    session.add(CaregiverLink(caregiver_id=caregiver.id, patient_id=patient.id, relation=relation))
    session.flush()
