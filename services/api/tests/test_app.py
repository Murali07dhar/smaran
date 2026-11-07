import textwrap
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.modules as modules_pkg
from app.core.config import Settings, settings
from app.main import MODULES, ModuleLoadError, app, load_modules


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_app_starts_with_real_and_stubbed_modules(client):
    assert client.get("/healthz").json()["status"] == "ok"
    mods = app.state.modules
    assert set(mods) == set(MODULES)
    for name in ("auth_consent", "sync", "coop"):  # merged real modules
        assert mods[name]["status"] == "loaded", mods[name]
    for name in ("media", "insights"):  # merged by Integrator A2
        assert mods[name]["status"] == "loaded", mods[name]


def test_readyz_reports_db_and_modules(client):
    r = client.get("/readyz")
    body = r.json()
    assert r.status_code == 200 and body["database"] == "ok" and body["status"] in ("ok", "degraded")
    assert set(body["modules"]) == set(MODULES)


def test_errors_are_rfc7807(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json() == {"type": "about:blank", "title": "Not Found", "status": 404, "instance": "/api/v1/nope", "detail": "Not Found"}


def test_security_headers_and_cors(client):
    r = client.get("/api/v1/nope", headers={"Origin": "http://localhost:5173"})
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    pre = client.options("/healthz", headers={"Origin": "http://localhost:5174", "Access-Control-Request-Method": "GET"})
    assert pre.headers["access-control-allow-origin"] == "http://localhost:5174"
    bad = client.options("/healthz", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_unhandled_exception_is_problem_json():
    a = FastAPI()
    from app.core.errors import install_exception_handlers
    install_exception_handlers(a)

    @a.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    r = TestClient(a, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500 and r.json()["detail"] == "Internal server error" and "secret" not in r.text


@pytest.fixture
def fake_modules(tmp_path, monkeypatch):
    def write(rel: str, code: str):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(code))

    write("goodmod/__init__.py", "")
    write("goodmod/router.py", """
        from fastapi import APIRouter
        router = APIRouter()
        ws_router = APIRouter()
        @router.get("/ping")
        def ping(): return {"pong": True}
        @ws_router.websocket("/ws/good/{room}")
        async def ws(websocket, room: str): ...
    """)
    write("brokenmod/__init__.py", "")
    write("brokenmod/router.py", "import definitely_not_installed_xyz\n")
    write("norouter/__init__.py", "")
    write("norouter/router.py", "x = 1\n")
    monkeypatch.setattr(modules_pkg, "__path__", [*modules_pkg.__path__, str(tmp_path)])
    import importlib
    importlib.invalidate_caches()
    return tmp_path


def test_duplicate_routes_are_logged(fake_modules, caplog):
    (fake_modules / "dupmod").mkdir()
    (fake_modules / "dupmod" / "__init__.py").write_text("")
    (fake_modules / "dupmod" / "router.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/ping')\ndef p(): ...\n")
    import importlib
    importlib.invalidate_caches()
    load_modules(FastAPI(), ("goodmod", "dupmod"), strict=False)
    assert "duplicate route GET /api/v1/ping" in caplog.text


def test_loader_includes_real_modules_and_survives_broken_ones(fake_modules):
    a = FastAPI()
    report = load_modules(a, ("goodmod", "brokenmod", "norouter", "absentmod"), strict=False)
    assert report["goodmod"]["status"] == "loaded"
    assert report["brokenmod"]["status"] == "failed" and "definitely_not_installed_xyz" in report["brokenmod"]["detail"]
    assert report["norouter"]["status"] == "failed"
    assert report["absentmod"]["status"] == "missing"
    assert "/api/v1/ping" in a.openapi()["paths"]  # http routes are prefixed
    c = TestClient(a)
    assert c.get("/api/v1/ping").json() == {"pong": True}
    assert c.get("/api/v1/ws/good/1").status_code == 404  # ws route is NOT under /api/v1


def test_strict_mode_raises(fake_modules):
    with pytest.raises(ModuleLoadError):
        load_modules(FastAPI(), ("absentmod",), strict=True)
    with pytest.raises(ModuleLoadError):
        load_modules(FastAPI(), ("brokenmod",), strict=True)
    load_modules(FastAPI(), ("goodmod",), strict=True)


def test_stub_fallback(monkeypatch, tmp_path):
    """The stub mechanism still works for a module that has no real router (real stubs were deleted in A2)."""
    (tmp_path / "ghost.py").write_text(
        "from fastapi import APIRouter, HTTPException\n"
        "router = APIRouter()\n"
        "@router.get('/ghost')\n"
        "def g():\n    raise HTTPException(501, 'not implemented')\n"
    )
    monkeypatch.setattr(settings, "MODULE_STUBS_PATH", str(tmp_path))
    a = FastAPI()
    from app.core.errors import install_exception_handlers
    install_exception_handlers(a)
    report = load_modules(a, ("ghost",), strict=False)
    assert report["ghost"]["status"] == "stub"
    r = TestClient(a).get("/api/v1/ghost")
    assert r.status_code == 501 and r.headers["content-type"].startswith("application/problem+json")


def test_settings_validation(monkeypatch):
    base = dict(JWT_SECRET="x" * 40, DATABASE_URL="postgresql+psycopg://u:p@h/db")
    assert Settings(**base).sqlalchemy_url.startswith("postgresql+psycopg://")
    assert Settings(JWT_SECRET="x" * 40, DATABASE_URL="postgres://u:p@h/db").sqlalchemy_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(**base, CORS_ORIGINS="http://a, http://b ,").cors_origins_list == ["http://a", "http://b"]
    with pytest.raises(ValueError):
        Settings(JWT_SECRET="short")
    with pytest.raises(ValueError):
        Settings(**base, MEDIA_KEY_B64="not-base64!!")
    import base64, os
    with pytest.raises(ValueError):
        Settings(**base, MEDIA_KEY_B64=base64.b64encode(b"short").decode())
    assert Settings(**base, MEDIA_KEY_B64=base64.b64encode(os.urandom(32)).decode()).MEDIA_KEY_B64
    with pytest.raises(ValueError):  # production guards
        Settings(JWT_SECRET="change-me-to-a-long-random-string", ENVIRONMENT="production",
                 MEDIA_KEY_B64=base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(ValueError):
        Settings(**base, ENVIRONMENT="production")  # MEDIA_KEY_B64 missing
