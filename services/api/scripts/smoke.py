"""FULL backend smoke test against a RUNNING API (+ fake AI on AI_SERVICE_URL).
Usage: python scripts/smoke.py [BASE_URL]        (default http://localhost:8000)
Env:   SMOKE_MEDIA_DIR=<MEDIA_DIR>  (optional: also proves ciphertext on disk is unreadable)
Flow: caregiver register/login -> patient -> upload photo -> reminder -> PIN login -> sync push
      (session, events, missed reminder_events) -> pull (reminder + media metadata) -> insights/dashboard
      shapes -> alert + ack -> signed URL / Range / forged sig -> co-op room join."""
from __future__ import annotations

import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
BASE = ROOT + "/api/v1"
now = lambda **kw: (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()  # noqa: E731
ok = lambda cond, msg: (print(("PASS " if cond else "FAIL ") + msg), cond or sys.exit(1))  # noqa: E731


def jpeg() -> bytes:
    from PIL import Image
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (26.0, 10.0, 30.0), "E", (91.0, 45.0, 0.0)
    buf = io.BytesIO()
    Image.new("RGB", (48, 32), (200, 120, 40)).save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=20)
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/auth/register", json={"name": "Smoke Caregiver", "email": email, "password": "Smoke-Pass-123", "role": "caregiver", "language": "en"})
    ok(r.status_code == 201, f"register caregiver ({r.status_code})")
    r = c.post("/auth/login", json={"email": email, "password": "Smoke-Pass-123"})
    ok(r.status_code == 200 and r.json()["token_type"] == "bearer", "caregiver login")
    cg = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = c.post("/patients", json={"name": "Smoke Patient", "age": 74, "language": "as"}, headers=cg)
    ok(r.status_code == 201, "create patient")
    pid = r.json()["id"]

    # --- media upload (EXIF GPS must be stripped, content encrypted at rest)
    raw = jpeg()
    r = c.post("/media", headers=cg, data={"patient_id": pid, "kind": "photo", "tags": '["family"]'}, files={"file": ("p.jpg", raw, "image/jpeg")})
    ok(r.status_code == 201 and "enc_path" not in r.json() and "nonce" not in r.json(), "upload photo (no enc_path/nonce leaked)")
    mid = r.json()["id"]
    media_dir = os.environ.get("SMOKE_MEDIA_DIR")
    if media_dir:
        blobs = [p for p in Path(media_dir).rglob("*") if p.is_file()]
        ok(blobs and all(b"JFIF" not in p.read_bytes()[:64] and b"\xff\xd8" != p.read_bytes()[:2] for p in blobs), "ciphertext on disk is not a readable JPEG")
    r = c.get(f"/media/{mid}/url", headers=cg)
    ok(r.status_code == 200 and r.json()["url"].startswith("/api/v1/media/"), "signed URL issued")
    url = r.json()["url"]
    anon = httpx.Client(base_url=ROOT, timeout=20)
    r = anon.get(url)
    ok(r.status_code == 200 and r.content[:2] == b"\xff\xd8" and b"GPS" not in r.content and r.headers["cache-control"].startswith("private"), "content decrypts via signed URL (no bearer), no GPS EXIF")
    r = anon.get(url, headers={"Range": "bytes=0-9"})
    ok(r.status_code == 206 and len(r.content) == 10, "Range request -> 206")
    ok(anon.get(url.replace("sig=", "sig=00")).status_code == 403, "forged signature -> 403")
    ok(anon.get(f"/api/v1/media/{mid}/content?sig=x&exp=1").status_code == 403, "expired/forged -> 403")

    # --- reminder via 1.3
    r = c.post(f"/patients/{pid}/reminders", headers=cg, json={"category": "medicine", "title": "Morning tablet", "schedule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "locale": "as", "escalate_after_misses": 2})
    ok(r.status_code == 201 and r.json()["server_version"] == 1, "create reminder")
    rid = r.json()["id"]
    ok(c.post(f"/patients/{pid}/reminders", headers=cg, json={"category": "medicine", "title": "x", "schedule": "FREQ=SECONDLY", "locale": "as"}).status_code == 422, "bad RRULE rejected")

    # --- patient PIN login
    r = c.post(f"/patients/{pid}/pin", headers=cg)
    ok(r.status_code in (200, 201) and len(r.json()["pin"]) == 6, "issue PIN")
    r = c.post("/auth/patient-pin-login", json={"pin": r.json()["pin"]})
    ok(r.status_code == 200 and r.json()["user"]["role"] == "patient", "patient PIN login")
    pt = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ok(c.post("/media", headers=pt, data={"patient_id": pid, "kind": "photo"}, files={"file": ("p.jpg", raw, "image/jpeg")}).status_code == 403, "patient cannot upload (RBAC)")

    # --- sync push: session + events + 2 missed reminder events
    sid = str(uuid.uuid4())
    op = lambda ent, eid, p: {"op_id": str(uuid.uuid4()), "entity": ent, "entity_id": eid, "action": "upsert", "payload": p, "client_ts": now()}  # noqa: E731
    sess = op("game_sessions", sid, {"patient_id": pid, "game_id": "memory_match", "domain": "memory", "started_at": now(hours=1), "ended_at": now(minutes=50), "difficulty": 3, "score": 61.0})
    evs = [op("game_events", str(uuid.uuid4()), {"session_id": sid, "patient_id": pid, "type": "answer", "item_id": f"photo-{i}", "correct": i % 2 == 0, "response_ms": 900 + i, "with_cue": i < 3, "cue_id": "cue-song-1", "ts": now(minutes=55 - i)}) for i in range(4)]
    rem = [op("reminder_events", str(uuid.uuid4()), {"reminder_id": rid, "patient_id": pid, "due_at": now(hours=30 - 24 * i), "status": "missed", "ts": now(hours=29 - 24 * i)}) for i in range(2)]
    r = c.post("/sync/push", headers=pt, json={"device_id": "pt-dev", "ops": evs + rem + [sess]})
    j = r.json()
    ok(r.status_code == 200 and len(j["accepted"]) == 7 and not j["rejected"], f"patient pushes session/events/reminder_events {j.get('rejected')}")
    ok(len(c.post("/sync/push", headers=pt, json={"device_id": "pt-dev", "ops": [sess]}).json()["accepted"]) == 1, "replay idempotent")

    # --- pull as patient: reminder + media metadata arrive
    cursor, seen = 0, []
    while True:
        j = c.get(f"/sync/pull?since={cursor}", headers=pt).json()
        if not j["changes"]:
            break
        seen += j["changes"]
        cursor = j["server_cursor"]
    ents = {(x["entity"], x["entity_id"]) for x in seen}
    ok(("reminders", rid) in ents, "pull delivers reminder")
    ok(("media_assets", mid) in ents, "pull delivers media metadata")
    ok(not any("enc_path" in str(x["payload"]) or "nonce" in str(x["payload"]) for x in seen if x["entity"] == "media_assets"), "media sync payload has no enc_path/nonce")

    # --- insights + dashboard exact shapes
    d = c.get(f"/patients/{pid}/dashboard/trends?days=30", headers=cg).json()
    ok(len(d["days"]) == 30 and set(d["days"][0]) == {"date", "sessions", "avg_score", "avg_response_ms", "engagement_minutes"} and sum(x["sessions"] for x in d["days"]) == 1, "trends shape + 1 session")
    d = c.get(f"/patients/{pid}/dashboard/cue-comparison", headers=cg).json()
    ok(set(d) == {"with_cue", "without_cue", "by_domain"} and set(d["with_cue"]) == {"n", "accuracy", "avg_response_ms"} and d["with_cue"]["n"] == 3 and d["without_cue"]["n"] == 1, "cue-comparison shape")
    d = c.get(f"/patients/{pid}/dashboard/triggers", headers=cg).json()
    ok(d and set(d[0]) >= {"cue_id", "cue_type", "valence_label", "confidence", "last_validated_at", "half_life_days"} and d[0]["cue_id"] == "cue-song-1", "triggers shape (fake AI updated memory_triggers)")
    d = c.get(f"/patients/{pid}/dashboard/severity", headers=cg).json()
    ok(set(d) >= {"band", "gds_style_indicator", "drivers", "disclaimer", "computed_at"} and d["disclaimer"], "severity shape + disclaimer")
    r = c.get(f"/patients/{pid}/report.csv", headers=cg)
    ok(r.status_code == 200 and "text/csv" in r.headers["content-type"], "report.csv")
    ok(c.get(f"/patients/{pid}/dashboard/trends", headers=pt).status_code == 403, "patient role blocked from dashboard (RBAC)")

    # --- alert appears, no duplicate, ack
    al = c.get(f"/alerts?patient_id={pid}&status=open", headers=cg).json()
    mr = [a for a in al if a["kind"] == "missed_reminders"]
    ok(len(mr) == 1 and set(mr[0]) >= {"id", "patient_id", "kind", "severity", "message", "created_at", "acknowledged_at"}, "missed_reminders alert appears (exactly one)")
    r = c.post(f"/alerts/{mr[0]['id']}/ack", headers=cg, json={"note": "called her"})
    ok(r.status_code == 200, "acknowledge alert")
    ok(not [a for a in c.get(f"/alerts?patient_id={pid}&status=open", headers=cg).json() if a["id"] == mr[0]["id"]], "acked alert leaves open list")
    ok(any(x["entity"] == "alerts" for x in c.get("/sync/pull?since=0", headers=pt).json()["changes"]), "alert change reaches devices via pull")
    pl = c.get("/patients", headers=cg).json()
    ok(pl and "severity_band" in pl[0] and "open_alerts" in pl[0], "GET /patients carries alert/severity summary")

    # --- co-op
    r = c.post("/coop/rooms", headers=cg, json={"patient_id": pid, "game_id": "memory_match"})
    ok(r.status_code == 201 and len(r.json()["join_code"]) == 6, "co-op room")
    r = c.post("/coop/rooms/join", headers=cg, json={"join_code": r.json()["join_code"], "role": "family"})
    ok(r.status_code == 200 and r.json()["ws_token"], "co-op join")
    print("SMOKE OK")


if __name__ == "__main__":
    main()
