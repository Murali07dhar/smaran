"""Fake stand-in for app.modules.insights.ai_client.AIClient (same two methods).

    fake = FakeAIClient()                       # deterministic happy path
    fake = FakeAIClient(fail=True)              # AI service down -> both methods return None
    fake = FakeAIClient(severity_band="watch")  # force a severity band
    fake = FakeAIClient(raise_exc=RuntimeError("boom"))   # unexpected bug in the client

Calls are recorded in .trigger_calls / .severity_calls.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.modules.insights.ai_client import SeverityResponse, TriggerOut


class FakeAIClient:
    def __init__(self, *, fail=False, raise_exc=None, triggers=None, severity=None, severity_band="stable", gds=2):
        self.fail = fail
        self.raise_exc = raise_exc
        self._triggers = triggers
        self._severity = severity
        self.severity_band = severity_band
        self.gds = gds
        self.trigger_calls: list[tuple] = []
        self.severity_calls: list[tuple] = []

    def update_triggers(self, patient_id, observations):
        self.trigger_calls.append((patient_id, observations))
        if self.raise_exc:
            raise self.raise_exc
        if self.fail:
            return None
        if self._triggers is not None:
            return self._triggers
        by_cue: dict[str, list[dict]] = {}
        for o in observations:
            by_cue.setdefault(o["cue_id"], []).append(o)
        out = []
        for cue_id, obs in by_cue.items():
            recalled = sum(1 for o in obs if o["recalled"]) / len(obs)
            out.append(
                TriggerOut(
                    cue_id=cue_id,
                    confidence=round(recalled, 3),
                    valence_label=obs[0]["valence_label"],
                    last_validated_at=datetime.now(timezone.utc),
                    half_life_days=14.0,  # placeholder constant, NOT the real AI model
                )
            )
        return out

    def estimate_severity(self, patient_id, window_days, samples=None):
        self.severity_calls.append((patient_id, window_days))
        if self.raise_exc:
            raise self.raise_exc
        if self.fail:
            return None
        if self._severity is not None:
            return self._severity
        return SeverityResponse(
            band=self.severity_band, gds_style_indicator=self.gds, drivers=["fake driver"], disclaimer="fake"
        )
