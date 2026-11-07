"""Mock of services/api: posts sample payloads to every AI endpoint (stdlib only).

    python scripts/mock_client.py [--base http://localhost:8001] [--token SECRET]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

PATIENT = "0192f0a0-0000-7000-8000-000000000001"


def post(base: str, path: str, body: dict, token: str | None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--token")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    ts = lambda d: (now - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731

    obs = [{"cue_id": "cue-ganga-photo", "cue_type": "photo", "valence_label": "joy", "recalled": r, "with_cue": w, "ts": ts(d)}
           for d, r, w in [(6, True, True), (5, True, True), (4, False, False), (2, True, True), (1, True, True)]]
    obs.append({"cue_id": "cue-bihu-song", "cue_type": "music", "valence_label": "familiarity", "recalled": True,
                "with_cue": True, "ts": ts(1)})
    calls = [
        ("/ai/triggers/update", {"patient_id": PATIENT, "observations": obs}),
        ("/ai/difficulty/next", {"patient_id": PATIENT, "game_id": "memory_match", "current_difficulty": 4,
                                 "recent": [{"correct": True, "response_ms": 2400, "hints": 0}] * 5
                                 + [{"correct": False, "response_ms": 5200, "hints": 1}]}),
        ("/ai/severity/estimate", {"patient_id": PATIENT, "window_days": 30}),
        ("/ai/emotion/fuse", {"face": {"valence": 0.7, "arousal": 0.4, "conf": 0.8},
                              "speech": {"valence": 0.5, "arousal": 0.3, "conf": 0.6},
                              "baseline": {"valence_mean": 0.05, "valence_std": 0.2, "arousal_mean": 0.0,
                                           "arousal_std": 0.2, "n": 12}}),
        ("/ai/content/generate", {"kind": "reminder_phrase", "locale": "as",
                                  "context": {"patient_name": "Ratna", "category": "hydration", "time": "10:30"}}),
        ("/ai/content/generate", {"kind": "game_prompt", "locale": "en", "context": {"domain": "memory", "cue_type": "photo"}}),
    ]
    failed = 0
    for path, body in calls:
        status, data = post(a.base, path, body, a.token)
        ok = status == 200
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {status} {path}\n     {json.dumps(data, ensure_ascii=False)[:300]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
