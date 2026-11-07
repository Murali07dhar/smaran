import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.setenv("AI_ALLOW_TIME_OVERRIDE", "1")
    for k in ("GEMINI_API_KEY", "AI_SERVICE_TOKEN", "AI_ENV"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def make_client():
    clients = []

    def _make() -> TestClient:
        c = TestClient(create_app(":memory:"))
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.close()


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def at(ts: str) -> dict:
    """Header that pins the server clock (needs AI_ALLOW_TIME_OVERRIDE=1)."""
    return {"X-Smaran-Now": ts}
