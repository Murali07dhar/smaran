"""Runtime settings, read from environment only (no secrets in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str
    state_db: str
    service_token: str | None
    gemini_api_key: str | None
    gemini_model: str
    gemini_timeout_s: float
    allow_time_override: bool
    mlflow_tracking_uri: str | None


def get_settings() -> Settings:
    return Settings(
        env=os.getenv("AI_ENV", "development"),
        state_db=os.getenv("AI_STATE_DB", "data/ai_state.db"),
        service_token=os.getenv("AI_SERVICE_TOKEN") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_timeout_s=float(os.getenv("GEMINI_TIMEOUT_S", "6")),
        allow_time_override=_flag("AI_ALLOW_TIME_OVERRIDE"),
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI") or None,
    )
