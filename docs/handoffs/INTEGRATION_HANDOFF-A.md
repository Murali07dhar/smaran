# INTEGRATION_HANDOFF (Integrator A2: backend part 2 of 2)

**Status: DONE (backend).** 1.1 + 1.2 + 1.3 + 1.4 + 1.5 merged in `services/api`. Original builder handoffs: `HANDOFF_1.1.md`, `HANDOFF_1.3.md`, `HANDOFF_1.5.md`.

## What was merged
- A1 base (1.1 core, 1.2 auth_consent, 1.4 sync/coop) + **1.3** `modules/media` (media, reminders, routines) and `core/crypto.py` + **1.5** `modules/insights` and `infra/`, Makefile, CI.
- Deleted: all core_stubs, `mocks/api_stubs`, crypto stub, no-op pipeline, `infra/requirements/api.txt`, `requirements.media.txt`.

## Conflicts and resolutions
1. 1.3 tests used a stub recorder (`changelog.CALLS`): conftest now wraps the real `record_change` (DB write kept).
2. Real RBAC needs a `caregiver_links` row for health_workers (stub gave them all access): test fixtures link them.
3. 1.3 `client_for` shared one app across users (last user won): one app per client.
4. 1.3 stored a UUID in `reminders.voice_clip_id` (String(64)): now `str()`.
5. 1.5 test teardown `drop_all` wiped the shared Postgres test schema: truncates on Postgres, drop only on SQLite.
6. 1.1 `test_app` assumed media/insights stubs: expects `loaded`; stub-fallback test uses a temp ghost module.
7. Settings: added `MEDIA_DIR`, `MEDIA_URL_TTL_SECONDS` (1.3 CCR-1, 1.5 CCR-4 accepted).
8. Requirements: single `services/api/requirements.txt` (+cryptography, python-dateutil, Pillow, httpx). Dockerfile/compose/CI/Makefile point to it.
9. Compose api env: `STRICT_MODULES=true`, `ENVIRONMENT`, media TTL, `SYNC_PULL_HOLDBACK_SECONDS` (read via os.getenv by sync, so must be real env).
10. `export_openapi.py`: `--with-stubs` removed, runs with `STRICT_MODULES=1`.

## CONTRACT DECISIONS (for other integrators)
- No schema, route-shape or shared-signature change. Only additive Settings fields (above).
- Sync entity names: `reminders`, `routines`, `media_assets`, `alerts`, `memory_triggers`. Delete payload `{id, patient_id, server_version}`. Media sync payload is metadata only (no enc_path/nonce).
- Reminder JSON: `schedule` (RRULE); DB column `schedule_rrule`; input also accepts `schedule_rrule`. Adds `active`, `updated_at`, `server_version`. `escalate_after_misses` default 3 (0 = never).
- `routines.steps`: free list (1-50) of strings or objects, suggested `{order, title, media_id?}`. **Claude 3/4/5 must agree on one shape.**
- Media URL from `GET /media/{id}/url` is **relative** (`/api/v1/media/{id}/content?sig&exp`); clients prefix the API base. Content endpoint needs no bearer; proxy must not log its query string. Reverse proxy body limit ~21 MB.
- `cue_id` is an opaque string (VARCHAR), not UUID. `memory_triggers` unique (patient_id, cue_id).
- Alert semantics (1.5): one open alert per (patient, kind), escalated in place, never downgraded; `missed_reminders` = most recent N events all missed; `activity_drop` only fires from the periodic scan (`insights-scan` compose service / `python -m app.modules.insights.scan --loop`).
- Dashboard must show the disclaimer next to scores/severity (severity endpoint returns it). Day buckets are UTC.
- Frontends: use relative API base `/api/v1` behind the nginx proxy; co-op WS at `/ws/coop/{room_id}`.

## Stubs / mocks still in place
| Mock | Replaced by |
|---|---|
| `mocks/fake_ai/server.py` (HTTP fake of services/ai, smoke) and `mocks/fake_ai/client.py` (in-process, unit tests) | real `services/ai` (Integrator B) |
| `mocks/fake_data/fill_fake_data.py` | demo tool, keep |
No route stubs remain.

## Commands
```
cd services/api
uv venv --python 3.11 .venv && . .venv/bin/activate && uv pip install -r requirements-dev.txt
pytest -q                                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://u:p@localhost/smaran_test pytest -q   # WIPES that DB
export DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/smaran REDIS_URL=redis://localhost:6379/0 \
  JWT_SECRET=$(openssl rand -hex 32) AI_SERVICE_URL=http://localhost:8001 STRICT_MODULES=1 \
  MEDIA_DIR=/data/media MEDIA_KEY_B64=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
alembic upgrade head && python seed.py
(cd ../.. && uvicorn mocks.fake_ai.server:app --port 8001 &)   # until real AI lands
uvicorn app.main:app --port 8000 &
SMOKE_MEDIA_DIR=$MEDIA_DIR python scripts/smoke.py http://localhost:8000
python scripts/check_routes.py                              # OpenAPI vs ROUTES
scripts/gen_contracts.sh                                    # openapi.json + TS types
# Docker: cd repo root; make env && make secrets; make config; make up
```

## Results
- pytest: **350 passed** on SQLite and on PostgreSQL 16 (Python 3.11.15, Redis 7).
- Alembic upgrade + seed OK on Postgres.
- `check_routes.py`: OK, 35 ROUTES operations present with response keys (+ /healthz, /readyz). `packages/contracts/openapi.json`: 31 paths; TS types regenerated.
- `smoke.py`: 34/34 PASS (live uvicorn + Postgres + Redis + fake AI): encrypted-on-disk photo, GPS stripped, signed URL, Range 206, forged/expired 403, RBAC, reminder + RRULE validation, PIN login, push session/events/missed reminder_events, replay idempotent, pull delivers reminder + media metadata, dashboard shapes, one missed_reminders alert, ack, alert synced, co-op join.
- AI down: push still 200, dashboard still serves, no tracebacks; only trigger update is skipped.

## Known gaps
- **Not run:** `docker compose config`, Docker image builds, Caddy prod override (no Docker in sandbox); `ruff`. Compose/CI only YAML-parsed and env-var coverage checked.
- Real `services/ai` and `services/voice` not tested against this backend (fake AI only). `/ai/severity/estimate` gets only `{patient_id, window_days}`: the real AI must read the DB. Cue type/valence per event are inferred (1.5 CCR-2).
- No `DELETE /media/{id}` (1.3 request); no audit-log table; no consent check on upload; patient deletion does not remove files (DPDP erasure job needed).
- Media: no key rotation (losing `MEDIA_KEY_B64` loses all media); whole-file decrypt in memory (max 20 MB); no malware scan; audio metadata not stripped; no upload rate limit.
- No rate limit on co-op join / WS messages; WS token is in the query string (mask in logs); refresh reuse revokes only the reused token; Postgres cursor gap on /sync/pull (use `SYNC_PULL_HOLDBACK_SECONDS`).
- `process_synced_data` holds the DB transaction during up to two 3 s AI calls (move to background later).
- TLS 1.3 only via the prod Caddy override; at-rest disk encryption depends on host. Tests used bcrypt rounds 4; requirements use ranges (pin in CI).
- Support tool, not a diagnosis; model bias and unverified translations remain open (AI/voice owners).
