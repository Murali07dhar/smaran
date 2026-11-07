"""Golden-path smoke against RUNNING api + REAL services/ai (+ voice via the same proxy rule as the web apps).
Usage: python scripts/smoke_golden.py [API_BASE_URL] [AI_URL] [VOICE_URL]
Payloads are built exactly as apps/patient-web builds them (core/games/sessionLogic.ts, reminderState.ts):
  caregiver login -> patient -> photo (cue) -> medicine reminder -> routine (D1) -> PIN login ->
  sync push (sessions/events WITH and WITHOUT cue across days, reminder acks) -> pull -> insights ->
  triggers (real AI, no no_cue:* leak) -> cue-comparison -> trends -> severity (real AI, disclaimer) -> alert."""
from __future__ import annotations

import io
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

ROOT = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
AI = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8001").rstrip("/")
VOICE = (sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8002").rstrip("/")
BASE = ROOT + "/api/v1"
now = lambda **kw: (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()  # noqa: E731
u7 = lambda: str(uuid.uuid4())  # noqa: E731  (server only checks UUID form)
results: list[tuple[bool, str]] = []


def ok(cond, msg):
    results.append((bool(cond), msg))
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        print("\n".join(f"  {'ok ' if r else 'BAD'} {m}" for r, m in results[-3:]))
        sys.exit(1)


def png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (240, 160, 60)).save(buf, "JPEG")
    return buf.getvalue()


def main() -> None:
    ok(httpx.get(AI + "/healthz", timeout=10).json()["service"] == "smaran-ai", "real services/ai is up (not the fake)")
    c = httpx.Client(base_url=BASE, timeout=30)
    email = f"golden-{uuid.uuid4().hex[:8]}@example.com"
    ok(c.post("/auth/register", json={"name": "Golden CG", "email": email, "password": "Golden-Pass-123", "role": "caregiver", "language": "en"}).status_code == 201, "caregiver registers")
    r = c.post("/auth/login", json={"email": email, "password": "Golden-Pass-123"})
    cg = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = c.post("/patients", json={"name": "Bimala", "age": 76, "language": "as"}, headers=cg)
    pid = r.json()["id"]
    ok(r.status_code == 201, "caregiver adds patient")

    r = c.post("/media", headers=cg, data={"patient_id": pid, "kind": "photo", "tags": '["joy","label:Wedding"]'}, files={"file": ("w.jpg", png(), "image/jpeg")})
    ok(r.status_code == 201, "caregiver uploads photo (cue)")
    mid = r.json()["id"]
    r = c.post(f"/patients/{pid}/reminders", headers=cg, json={"category": "medicine", "title": "Morning tablet", "schedule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "locale": "as", "escalate_after_misses": 2})
    ok(r.status_code == 201 and "schedule" in r.json() and "schedule_rrule" not in r.json(), "medicine reminder (wire field is `schedule`)")
    rid = r.json()["id"]
    r = c.post(f"/patients/{pid}/routines", headers=cg, json={"title": "Morning", "steps": ["Wake up", {"title": "Brush teeth"}]})
    ok(r.status_code == 201 and r.json()["steps"] == [{"order": 1, "title": "Wake up"}, {"order": 2, "title": "Brush teeth"}], "D1 routine steps normalised")

    r = c.post(f"/patients/{pid}/pin", headers=cg)
    r = c.post("/auth/patient-pin-login", json={"pin": r.json()["pin"]})
    ok(r.status_code == 200 and r.json()["user"]["role"] == "patient" and r.json()["user"]["name"] == "Bimala", "patient PIN login (display name from user.name)")
    pt = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ---- offline play replayed: 6 sessions over 6 days, 4 answers with cue (media id) + 3 without, + a hint
    ops: list[dict] = []
    op = lambda ent, eid, p, ts=None: ops.append({"op_id": u7(), "entity": ent, "entity_id": eid, "action": "upsert", "payload": p, "client_ts": ts or now()})  # noqa: E731
    sids = []
    for d in range(6):
        sid = u7(); sids.append(sid)
        t0 = datetime.now(timezone.utc) - timedelta(days=5 - d, hours=1)
        op("game_sessions", sid, {"id": sid, "patient_id": pid, "game_id": "memory_pairs", "domain": "memory", "started_at": t0.isoformat(), "ended_at": (t0 + timedelta(minutes=8)).isoformat(), "difficulty": 3, "score": 70.0 - d, "device_id": "pt-dev"})
        for i in range(7):
            with_cue = i < 4
            eid = u7()
            op("game_events", eid, {"id": eid, "session_id": sid, "patient_id": pid, "type": "answer", "item_id": f"obj_{i}", "correct": (i % 2 == 0) if with_cue else (i == 5), "response_ms": 900 + 40 * i, "cue_id": mid if with_cue else None, "with_cue": with_cue, "ts": (t0 + timedelta(minutes=i)).isoformat()})
        hid = u7()
        op("game_events", hid, {"id": hid, "session_id": sid, "patient_id": pid, "type": "hint_used", "item_id": "obj_6", "correct": None, "response_ms": None, "cue_id": None, "with_cue": False, "ts": (t0 + timedelta(minutes=7)).isoformat()})
    for i in range(2):  # ack-less misses (reminder alert)
        eid = u7()
        op("reminder_events", eid, {"id": eid, "reminder_id": rid, "patient_id": pid, "due_at": now(hours=30 - 24 * i), "status": "missed", "ts": now(hours=29 - 24 * i)})
    r = c.post("/sync/push", headers=pt, json={"device_id": "pt-dev", "ops": ops})
    j = r.json()
    ok(r.status_code == 200 and len(j["accepted"]) == len(ops) and not j["rejected"], f"push {len(ops)} client-shaped ops accepted {j.get('rejected', '')[:3]}")
    r2 = c.post("/sync/push", headers=pt, json={"device_id": "pt-dev", "ops": ops})
    ok(len(r2.json()["accepted"]) == len(ops), "offline replay idempotent (all re-accepted, no dupes)")
    tr = c.get(f"/patients/{pid}/dashboard/trends?days=30", headers=cg).json()
    ok(sum(x["sessions"] for x in tr["days"]) == 6, "trends: 6 sessions, none duplicated by replay")

    # ---- pull
    cursor, seen = 0, []
    while True:
        j = c.get(f"/sync/pull?since={cursor}", headers=pt).json()
        if not j["changes"]:
            break
        seen += j["changes"]; cursor = j["server_cursor"]
    ents = {x["entity"] for x in seen}
    ok({"reminders", "routines", "media_assets"} <= ents, f"pull entities {sorted(ents)} match sync-core PULL_ENTITIES")
    ok(all(x["entity"] in {"reminders", "routines", "media_assets", "memory_triggers", "alerts"} for x in seen), "no unexpected entity names on pull")

    # ---- insights from REAL AI
    trig = c.get(f"/patients/{pid}/dashboard/triggers", headers=cg).json()
    ok(trig and any(t["cue_id"] == mid for t in trig), "real AI updated trigger for the caregiver photo cue")
    ok(not any(t["cue_id"].startswith("no_cue:") for t in trig), "D2: no synthetic no_cue:* trigger leaks to dashboard")
    t = next(t for t in trig if t["cue_id"] == mid)
    ok(0 <= t["confidence"] <= 1 and t["valence_label"] == "joy" and t["cue_type"] == "photo", f"trigger enriched from media tags (joy/photo) conf={t['confidence']:.2f}")
    cc = c.get(f"/patients/{pid}/dashboard/cue-comparison", headers=cg).json()
    ok(cc["with_cue"]["n"] == 24 and cc["without_cue"]["n"] == 18, f"cue comparison n with/without = {cc['with_cue']['n']}/{cc['without_cue']['n']}")
    sev = c.get(f"/patients/{pid}/dashboard/severity", headers=cg).json()
    ok(sev["disclaimer"] and sev["band"] in {"stable", "watch", "alert"} and 1 <= sev["gds_style_indicator"] <= 7, "severity from real AI + disclaimer")
    ok(any("data:" in d for d in sev["drivers"]) and not any("insufficient" in d for d in sev["drivers"]), f"D5: AI had real data ({sev['drivers'][0]})")
    al = c.get(f"/alerts?patient_id={pid}&status=open", headers=cg).json()
    ok(any(a["kind"] == "missed_reminders" for a in al), "alert raised for missed reminders")
    ok(any(x["entity"] == "alerts" for x in c.get("/sync/pull?since=0", headers=pt).json()["changes"]), "alert change reaches devices via pull")
    ok(any(x["entity"] == "memory_triggers" for x in c.get("/sync/pull?since=0", headers=pt).json()["changes"]), "memory_triggers reach the patient device via pull")

    # ---- voice via same relative-path rule the apps use (D4): direct to :8002 /voice/*
    ok(httpx.get(VOICE + "/voice/health", timeout=10).json()["status"] == "ok", "services/voice health")
    r = c.post("/coop/rooms", headers=cg, json={"patient_id": pid, "game_id": "memory_pairs"})
    ok(r.status_code == 201, "co-op room created for a real game id")
    jr = c.post("/coop/rooms/join", headers=pt, json={"join_code": r.json()["join_code"], "role": "patient"})
    ok(jr.status_code == 200 and jr.json()["ws_token"], "patient joins co-op (ws_token)")
    print("GOLDEN SMOKE OK")


if __name__ == "__main__":
    main()
