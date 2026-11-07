# INTEGRATION_STATE (A1 + A2)

**A2 status: DONE.** 1.3 + 1.5 merged; 350 tests green (SQLite + PostgreSQL 16); smoke 34/34; ROUTES check OK; contracts regenerated. See `INTEGRATION_HANDOFF.md` for conflicts, decisions, commands, gaps.
**Next:** Integrator B (services/ai, voice, frontends); run `docker compose config` + image builds where Docker exists; set `STRICT_MODULES=1` in CI.

---- A1 state below (historical) ----
# INTEGRATION_STATE (Integrator A1: backend part 1 of 2)

**Status: DONE.** 1.1 core + 1.4 sync/co-op + 1.2 auth_consent merged into `services/api`. 179 tests green on SQLite and on PostgreSQL 16 (Python 3.11.17, real Redis 7 for the smoke run). 1.3 / 1.5 still stubbed.

## What is merged
| From | In |
|---|---|
| 1.1 | `app/{main,models}.py`, `app/core/*`, `alembic/`, `seed.py`, `scripts/`, `tests/` (106), `packages/contracts` (regenerated), `mocks/api_stubs` (media, insights only) |
| 1.4 | `app/modules/sync/*`, `app/modules/coop/*`, tests in `tests/sync_coop/` |
| 1.2 | `app/modules/auth_consent/*`, tests in `tests/auth_consent/` |
| deleted | all three `mocks/core_stub` dirs; `api_stubs/{auth_consent,sync,coop,sync_changelog_stub,insights_pipeline_stub}.py` |

## Conflicts and resolutions
1. **Co-op WS path (1.4 CCR-1 = 1.1 CCR-1).** Both agreed on `router` + `ws_router`. Loader includes both, so WS answers at `/ws/coop/{room_id}` (contract) and `/api/v1/ws/coop/{room_id}` (alias). Kept both; clients use `/ws/coop`.
2. **PIN login (1.1 CCR-2).** Not needed: 1.2 resolves PIN -> patient via a Redis key, so `{pin}` alone works. QR token path kept.
3. **1.2 ids were `str`, real models use `UUID`.** Schemas/path params/`session.get` switched to `UUID` (wire format unchanged, still strings in JSON).
4. **Duplicate JWT code.** 1.2 `qr.py` signed its own JWT. Now uses core `create_token(..., "qr")` / `decode_token(..., "qr")`. QR tokens can't be used as bearer; access tokens can't be used as QR (new test).
5. **1.2 tuning env vars ignored** (`getattr(settings, ...)` on fields core lacked). Added `PATIENT_PIN_TTL_MIN, PATIENT_QR_TTL_MIN, LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MIN` to `Settings` (additive). `.env.example` merged.
6. **1.4 stub auth (`X-Test-User`)** replaced by real Bearer tokens in tests; its fake pipeline replaced by a monkeypatched recorder.
7. **Co-op flake (1.4, never executed before).** Handler cleanup could be cancelled mid-way (no `leave`, no idle timer). Cleanup now runs shielded. 0 failures in 20+ loops, was ~20-30%.
8. **1.1 `test_app`** assumed every module missing. Updated: auth_consent/sync/coop must be `loaded`; media/insights `stub|missing`.
9. **1.1 `accessible_patient_ids` (1.4 CCR-3):** exists in core; 1.4 still has its own copy in `sync/service.py` (same semantics). Left as is.

## CONTRACT DECISIONS
- No schema, route-shape or shared-signature change. Only additions: 4 `Settings` fields (above).
- 1.1 CCR (`UNIQUE(patient_id, cue_id)`, `VARCHAR` cue/item ids, `server_version` auto-increment) accepted as implemented.
- Refresh-token revocation = Redis allow-list with rotate-on-use (1.2). No logout route (not in contract); `tokens.revoke()` available.
- Login rate limit: 5 failures / 15 min lock (Redis). Consents append-only, latest-per-kind + history.

## Verification
- `assert_can_access_patient` on every patient-scoped 1.2 route (get patient, pin, consents GET/POST, caregiver-links); sync pull/push scoped by `accessible_patient_ids` / per-op check; co-op create/join check access.
- No duplicate hashing; only `coop/tokens.py` (typ=`coop_ws`, same `JWT_SECRET`, unusable as API token) signs its own short-lived JWT, by design.
- Sync: idempotent by `op_id`, append-only insert-or-ignore, push survives `process_synced_data` raising or being absent: all tested.
- Routes: OpenAPI of the merged app lists exactly the contract paths for auth_consent, sync, coop (14 paths in `packages/contracts/openapi.json`).
- Co-op ordering on real Redis (Lua path), two clients sending 15 msgs each concurrently: monotonic seq, identical order on both, per-sender order kept.
- `scripts/smoke.py` passes against uvicorn + PostgreSQL 16 + Redis 7: register -> login -> patient -> PIN -> PIN login -> push (reminder, session, events) -> replay -> pull -> consents -> co-op room/join.

## Stubs still in place (for A2)
- `app/core/crypto.py`: raises `NotImplementedError` (1.3 replaces).
- `app/modules/insights/pipeline.py`: no-op `process_synced_data` (1.5 replaces). No `insights/router.py` yet.
- Media / reminders / routines / insights routes: 501 problem+json from `mocks/api_stubs/{media,insights}.py`, enabled only with `MODULE_STUBS_PATH=<abs>/mocks/api_stubs`.

## Known gaps (unchanged, now owned by A2 / infra)
- No rate limit on `/coop/rooms/join` or WS message rate. WS token is in the query string: mask `token=` in access logs.
- Postgres cursor visibility gap on `/sync/pull` (mitigation `SYNC_PULL_HOLDBACK_SECONDS`; 1.4 reads it via `os.getenv`, so set it in the real environment, not just `.env`).
- Refresh reuse invalidates only the reused token, not the family.
- `lupa` is dev-only (fakeredis Lua); production Redis runs the Lua script natively (verified on Redis 7).
- Tests ran with `bcrypt` rounds 4 (test env). Python 3.11 + fastapi 0.162 / starlette 1.10 / sqlalchemy 2.1 here; `requirements.txt` still uses ranges (pin in CI).
- No audit-log table (1.1 gap), no TLS/at-rest encryption (infra).

## Commands
```
cd services/api
uv venv --python 3.11 .venv && . .venv/bin/activate && uv pip install -r requirements-dev.txt   # or python3.11 -m venv + pip
pytest -q                                                              # SQLite, no services
TEST_DATABASE_URL=postgresql+psycopg://u:p@localhost/smaran_test pytest -q   # WIPES that DB
export DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/smaran REDIS_URL=redis://localhost:6379/0 JWT_SECRET=$(openssl rand -hex 32)
export MODULE_STUBS_PATH=$PWD/../../mocks/api_stubs                    # until A2 lands media + insights
alembic upgrade head && python seed.py
uvicorn app.main:app --port 8000
python scripts/smoke.py http://localhost:8000
scripts/gen_contracts.sh                                               # after A2: regenerate openapi.json + TS types
```

## NEXT FOR A2
1. Copy 1.3 (`modules/media`, `core/crypto.py`) and 1.5 (`modules/insights/{router,pipeline}.py`, `infra/`) in; delete `app/core/crypto.py` stub, `insights/pipeline.py` stub, `mocks/api_stubs`.
2. 1.3 must call `record_change` (real, `app.modules.sync.changelog`) on every reminder/routine/media write; soft-delete reminders with history (`active=false`).
3. 1.5 must make `process_synced_data(session, patient_id, session_ids)` safe to call after commit (push already swallows its errors).
4. Set `STRICT_MODULES=1` in CI; re-run `pytest`, `scripts/smoke.py`, then `scripts/gen_contracts.sh`.
5. Test fixtures: `tests/sync_coop/conftest.py::world()` builds minimal rows; update if 1.3/1.5 add NOT NULL columns.
