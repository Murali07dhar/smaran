"""SMARAN API entrypoint (ONE shared FastAPI app, split by module).

    uvicorn app.main:app --port 8000

Each module in app/modules/<name>/router.py exposes `router` (APIRouter); it is included with
prefix /api/v1. A module MAY also expose `ws_router` for routes that must live OUTSIDE /api/v1
(the co-op WebSocket /ws/coop/{room_id}); it is included with no prefix.

A missing module never crashes startup (see `load_modules`); set STRICT_MODULES=1 in CI/integration
to make any missing or broken module fatal.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.errors import install_exception_handlers
from app.core.redis import redis_ping
from app.models import utcnow

API_PREFIX = "/api/v1"
VERSION = "0.1.0"
# (name, owner). Order only affects OpenAPI ordering.
MODULES: tuple[str, ...] = ("auth_consent", "media", "sync", "coop", "insights")

log = logging.getLogger("smaran.api")


class ModuleLoadError(RuntimeError):
    pass


def _import_stub(name: str):
    """Load mocks/api_stubs/<name>.py from MODULE_STUBS_PATH (dev only)."""
    if not settings.MODULE_STUBS_PATH:
        return None
    path = Path(settings.MODULE_STUBS_PATH) / f"{name}.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"smaran_stub_{name}", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = module  # type: ignore[union-attr]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def load_modules(app: FastAPI, names: tuple[str, ...] = MODULES, *, strict: bool | None = None) -> dict[str, dict[str, Any]]:
    """Include every module router; tolerate missing/broken modules. Returns a status map."""
    strict = settings.STRICT_MODULES if strict is None else strict
    report: dict[str, dict[str, Any]] = {}
    owners: dict[tuple[str, str], str] = {}
    for name in names:
        target = f"app.modules.{name}.router"
        module, state, detail = None, "loaded", None
        try:
            module = importlib.import_module(target)
        except ModuleNotFoundError as exc:
            if exc.name and (exc.name == target or target.startswith(exc.name + ".")) and exc.name.startswith("app.modules"):
                state, detail = "missing", f"{target} not found"
                log.warning("module %s is not installed yet; skipping", name)
            else:  # the module exists but one of ITS imports is broken
                state, detail = "failed", f"{type(exc).__name__}: {exc}"
                log.exception("module %s failed to import", name)
        except Exception as exc:  # noqa: BLE001 - one broken module must not take the API down
            state, detail = "failed", f"{type(exc).__name__}: {exc}"
            log.exception("module %s failed to import", name)

        if module is None:
            if strict:
                raise ModuleLoadError(f"module '{name}' unavailable ({state}): {detail}")
            try:
                module = _import_stub(name)
            except Exception as exc:  # noqa: BLE001
                log.exception("stub for %s failed", name)
                detail = f"{detail}; stub failed: {exc}"
            if module is not None:
                state = "stub"

        router = getattr(module, "router", None) if module is not None else None
        if module is not None and not isinstance(router, APIRouter):
            state, detail = "failed", f"{target} has no APIRouter named 'router'"
            router = None
            if strict:
                raise ModuleLoadError(detail)
        if router is not None:
            app.include_router(router, prefix=API_PREFIX)
            for key in _route_keys(router, API_PREFIX):
                if key in owners and owners[key] != name:
                    log.warning("duplicate route %s %s: modules '%s' and '%s' overlap", *key, owners[key], name)
                owners.setdefault(key, name)
            ws_router = getattr(module, "ws_router", None)
            if isinstance(ws_router, APIRouter):
                app.include_router(ws_router)  # unprefixed, e.g. /ws/coop/{room_id}
        report[name] = {"status": state, **({"detail": detail} if detail else {})}
    return report


def _route_keys(router: APIRouter, prefix: str) -> list[tuple[str, str]]:
    """(METHOD, full path) for every HTTP route of a module router (independent of FastAPI internals)."""
    keys = []
    for route in router.routes:
        if isinstance(route, APIRoute):
            keys += [(m, prefix + route.path) for m in sorted(route.methods or ())]
    return keys


core_router = APIRouter(tags=["core"])


@core_router.get("/healthz", summary="Liveness probe")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "smaran-api", "version": VERSION, "time": utcnow().isoformat()}


@core_router.get("/readyz", summary="Readiness probe (DB required, Redis reported)")
def readyz(request: Request, response: Response) -> dict[str, Any]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # noqa: BLE001
        db = "down"
    redis_ok = redis_ping()
    if db != "ok":
        response.status_code = 503
    status = "ok" if db == "ok" and redis_ok else ("unavailable" if db != "ok" else "degraded")
    return {
        "status": status,
        "database": db,
        "redis": "ok" if redis_ok else "down",
        "modules": getattr(request.app.state, "modules", {}),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    yield
    engine.dispose()


def create_app() -> FastAPI:
    is_prod = settings.ENVIRONMENT == "production"
    app = FastAPI(
        title="SMARAN API",
        version=VERSION,
        description="SMARAN - Understanding Memory Through Emotion. Support tool, not a diagnosis.",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,  # bearer tokens only; no cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.url.path.startswith(API_PREFIX):  # health data: never cache by default
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    install_exception_handlers(app)
    app.include_router(core_router)
    app.state.modules = load_modules(app)
    return app


app = create_app()
