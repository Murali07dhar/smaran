"""Co-op relay check with the same frame shape packages/games + patient-web send ({type, seq:0, payload}).
Usage: python scripts/smoke_coop_ws.py [API_BASE_URL]"""
import asyncio, json, sys, uuid
import httpx, websockets

ROOT = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


async def main() -> None:
    c = httpx.Client(base_url=ROOT + "/api/v1", timeout=20)
    t = c.post("/auth/login", json={"email": "caregiver@smaran.demo", "password": "Smaran-Demo-123"}).json()["access_token"]
    cg = {"Authorization": f"Bearer {t}"}
    pid = c.get("/patients", headers=cg).json()[0]["id"]
    room = c.post("/coop/rooms", headers=cg, json={"patient_id": pid, "game_id": "memory_pairs"}).json()
    fam = c.post("/coop/rooms/join", headers=cg, json={"join_code": room["join_code"], "role": "family"}).json()
    pin = c.post(f"/patients/{pid}/pin", headers=cg).json()["pin"]
    pt = {"Authorization": "Bearer " + c.post("/auth/patient-pin-login", json={"pin": pin}).json()["access_token"]}
    wsroot = ROOT.replace("http", "ws")
    async with websockets.connect(f"{wsroot}/ws/coop/{fam['room_id']}?token={fam['ws_token']}") as a:
        # second participant: same caregiver joins again as patient role (token is per join)
        pj = c.post("/coop/rooms/join", headers=pt, json={"join_code": room["join_code"], "role": "patient"}).json()
        async with websockets.connect(f"{wsroot}/ws/coop/{pj['room_id']}?token={pj['ws_token']}") as b:
            await b.send(json.dumps({"type": "join", "seq": 0, "payload": {}}))
            await b.send(json.dumps({"type": "state_patch", "seq": 0, "payload": {"flipped": [1]}}))
            seen = []
            try:
                while len(seen) < 6:
                    seen.append(json.loads(await asyncio.wait_for(a.recv(), 3)))
            except asyncio.TimeoutError:
                pass
            print("family received:", [(m["type"], m["seq"]) for m in seen])
            assert any(m["type"] == "state_patch" and m["payload"] == {"flipped": [1]} for m in seen), "state_patch not relayed"
            seqs = [m["seq"] for m in seen]
            assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq must be strictly increasing (server authoritative)"
    try:
        async with websockets.connect(f"{wsroot}/ws/coop/{fam['room_id']}?token=bad") as x:
            await x.recv()
        raise SystemExit("bad token accepted")
    except Exception as e:  # noqa: BLE001
        print("bad token rejected:", type(e).__name__)
    print("COOP WS OK")


asyncio.run(main())
