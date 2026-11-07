"""Application settings (12-factor: everything comes from the environment).

Shared contract: `from app.core.config import settings` exposes DATABASE_URL,
REDIS_URL, JWT_SECRET, AI_SERVICE_URL, VOICE_SERVICE_URL, MEDIA_KEY_B64.
"""
from __future__ import annotations

import base64
import binascii
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"change-me", "changeme", "change-me-to-a-long-random-string"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )

    # --- shared contract settings -------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://smaran:smaran@localhost:5432/smaran"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = Field(..., description="HMAC secret for JWTs; >= 32 chars; required.")
    AI_SERVICE_URL: str = "http://localhost:8001"
    VOICE_SERVICE_URL: str = "http://localhost:8002"
    # base64 of exactly 32 random bytes (AES-256-GCM key). Used by app.core.crypto (1.3).
    MEDIA_KEY_B64: str = ""

    # --- core extras ----------------------------------------------------------------
    ENVIRONMENT: str = "development"  # development | test | production
    LOG_LEVEL: str = "INFO"
    SQL_ECHO: bool = False
    # Comma separated. Patient PWA :5173, caregiver dashboard :5174.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 14
    # auth_consent (1.2) tuning; read by that module via getattr(settings, ...) so .env/env vars work
    PATIENT_PIN_TTL_MIN: int = 10
    PATIENT_QR_TTL_MIN: int = 10
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MIN: int = 15
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "smaran"
    BCRYPT_ROUNDS: int = 12
    # media (1.3): ciphertext volume + signed-URL lifetime (0/"" = module default: ./media_data, 600 s)
    MEDIA_DIR: str = ""
    MEDIA_URL_TTL_SECONDS: int = 0
    # Fail startup if a module is missing/broken (CI / integration). Off for parallel dev.
    STRICT_MODULES: bool = False
    # Optional directory holding stub routers (see /mocks/api_stubs) used when a real
    # module is missing. Empty = no stubs.
    MODULE_STUBS_PATH: str = ""

    @field_validator("JWT_SECRET")
    @classmethod
    def _jwt_secret_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @field_validator("MEDIA_KEY_B64")
    @classmethod
    def _media_key_valid(cls, v: str) -> str:
        if not v:
            return v
        try:
            raw = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("MEDIA_KEY_B64 must be valid base64") from exc
        if len(raw) != 32:
            raise ValueError("MEDIA_KEY_B64 must decode to exactly 32 bytes (AES-256)")
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET.lower() in _PLACEHOLDER_SECRETS:
                raise ValueError("JWT_SECRET is a placeholder; set a real secret in production")
            if not self.MEDIA_KEY_B64:
                raise ValueError("MEDIA_KEY_B64 is required in production")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL normalised to the psycopg (v3) driver."""
        url = self.DATABASE_URL
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
