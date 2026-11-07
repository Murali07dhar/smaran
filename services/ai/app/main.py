"""FastAPI app factory for the SMARAN AI service (:8001)."""
from __future__ import annotations

import dataclasses

from fastapi import FastAPI

from . import __version__
from .api import router
from .config import get_settings
from .problem import install_problem_handlers
from .store import Store


def create_app(state_db: str | None = None) -> FastAPI:
    settings = get_settings()
    if state_db is not None:
        settings = dataclasses.replace(settings, state_db=state_db)
    if settings.env == "production" and not settings.service_token:
        raise RuntimeError("AI_SERVICE_TOKEN is required when AI_ENV=production")

    app = FastAPI(title="SMARAN AI Engine", version=__version__,
                  description="Detect -> Associate -> Personalize. Support tool, never a diagnosis.")
    app.state.settings = settings
    app.state.store = Store(settings.state_db)
    install_problem_handlers(app)
    app.include_router(router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok", "service": "smaran-ai", "version": __version__,
                "gemini_configured": bool(settings.gemini_api_key)}

    @app.on_event("shutdown")
    def _close() -> None:
        app.state.store.close()

    return app
