"""HTTP client for services/ai (contract: AI SERVICE section of the briefing).

Every method returns None on ANY failure (timeout, connection error, non-2xx, bad JSON,
schema mismatch) so callers can degrade gracefully. Timeout is 3 s per phase (httpx.Timeout).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

log = logging.getLogger(__name__)

AI_TIMEOUT_SECONDS = 3.0


class TriggerOut(BaseModel):
    cue_id: str
    confidence: float
    valence_label: str
    last_validated_at: datetime
    half_life_days: float = Field(gt=0)


class SeverityResponse(BaseModel):
    band: Literal["stable", "watch", "alert"]
    gds_style_indicator: int = Field(ge=1, le=7)
    drivers: list[Any] = Field(default_factory=list)
    disclaimer: str = ""


class AIClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = AI_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.AI_SERVICE_URL).rstrip("/")
        self.timeout = httpx.Timeout(timeout)
        self.transport = transport  # tests inject httpx.MockTransport

    def _post(self, path: str, payload: dict[str, Any]) -> Any | None:
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                resp = client.post(f"{self.base_url}{path}", json=payload)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            log.warning("AI service call %s failed: %s", path, exc.__class__.__name__)
            return None

    def update_triggers(self, patient_id: Any, observations: list[dict[str, Any]]) -> list[TriggerOut] | None:
        """POST /ai/triggers/update. None = AI unavailable; [] = AI answered with nothing."""
        data = self._post(
            "/ai/triggers/update", {"patient_id": str(patient_id), "observations": observations}
        )
        if not isinstance(data, dict) or not isinstance(data.get("triggers"), list):
            if data is not None:
                log.warning("AI /triggers/update returned an unexpected shape")
            return None
        out: list[TriggerOut] = []
        for item in data["triggers"]:  # validate per item: one bad item must not drop the rest
            try:
                out.append(TriggerOut.model_validate(item))
            except ValidationError:
                log.warning("Dropping invalid trigger item from AI response")
        return out

    def estimate_severity(
        self, patient_id: Any, window_days: int, samples: list[dict[str, Any]] | None = None
    ) -> SeverityResponse | None:
        """POST /ai/severity/estimate. D5: ``samples`` (optional, services/ai CCR-AI-1, idempotent on the AI side)
        carries the performance events the AI Store needs; the API database stays private to services/api."""
        body: dict[str, Any] = {"patient_id": str(patient_id), "window_days": window_days}
        if samples:
            body["samples"] = samples
        data = self._post("/ai/severity/estimate", body)
        if data is None:
            return None
        try:
            return SeverityResponse.model_validate(data)
        except ValidationError:
            log.warning("AI /severity/estimate returned an invalid payload")
            return None


def get_ai_client() -> AIClient:
    """Indirection so tests can monkeypatch the client used by the pipeline."""
    return AIClient()
