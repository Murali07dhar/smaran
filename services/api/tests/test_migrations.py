"""Migration up/down on the test DB (SQLite by default; Postgres when TEST_DATABASE_URL is set)."""
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.core.db import Base, make_engine
from tests.conftest import alembic_config, wipe


@pytest.fixture
def scratch(db_url, engine):
    """Take over the shared DB for one test, then restore it at head."""
    eng = make_engine(db_url)
    yield eng
    wipe(eng)
    command.upgrade(alembic_config(db_url), "head")
    eng.dispose()


def user_tables(eng):
    return {t for t in inspect(eng).get_table_names() if t != "alembic_version"}


def test_upgrade_creates_all_tables_downgrade_removes_them(scratch, db_url):
    cfg = alembic_config(db_url)
    wipe(scratch)
    assert user_tables(scratch) == set()
    command.upgrade(cfg, "head")
    assert user_tables(scratch) == set(Base.metadata.tables)
    command.downgrade(cfg, "base")
    assert user_tables(scratch) == set()
    command.upgrade(cfg, "head")  # re-runnable after a downgrade
    assert user_tables(scratch) == set(Base.metadata.tables)


def test_migration_matches_models_no_drift(scratch, db_url):
    wipe(scratch)
    command.upgrade(alembic_config(db_url), "head")
    with scratch.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], f"models.py and migration have drifted: {diff}"


def test_expected_indexes_and_constraints_exist(scratch, db_url):
    insp = inspect(scratch)
    ix = lambda t: {i["name"] for i in insp.get_indexes(t)}
    assert "ix_game_sessions_patient_started" in ix("game_sessions")
    assert "ix_game_events_patient_ts" in ix("game_events")
    assert "ix_emotion_samples_patient_ts" in ix("emotion_samples")
    assert "ix_reminder_events_patient_due" in ix("reminder_events")
    assert "ix_sync_changes_patient_cursor" in ix("sync_changes")
    uqs = {u["name"] for u in insp.get_unique_constraints("caregiver_links")}
    assert "uq_caregiver_links_caregiver_patient" in uqs
