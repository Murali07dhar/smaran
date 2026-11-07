# HANDOFF: Claude 1.5 (Insights + Infra)

## 0. Verification status (read this first)
The build sandbox had **no network**, so `fastapi`, `sqlalchemy`, `pytest`, `httpx` and Docker could not be installed.

| Check | Status |
|---|---|
| All Python files compile (`compileall`) | done |
| Pure alert rules (`rules.py`) + `uuid7`: executed directly, all thresholds/boundaries pass | done |
| `docker-compose.yml`, prod override, CI workflow parse as YAML; every `depends_on` and volume resolves; every `${VAR}` is in `.env.example` | done |
| `check_env.sh` (rejects placeholders, accepts generated secrets), `healthcheck.py`, entrypoint syntax, `make -n up` | done |
| **pytest suite (43 test functions, one parametrized x5)** | **written, NOT executed**: run `make install-dev && make test` first |
| **`docker compose config`** | **NOT executed** (no Docker): run `make config` |
| **Docker image builds, Caddy prod override** | **NOT built / untested** |

Expect small first-run fixes in the SQL/ORM layer (that is the part I could not execute).

## 1. What is built
**Part A: `services/api/app/modules/insights/`**
- `pipeline.py`: `process_synced_data(session, patient_id, session_ids) -> None` (exact contract signature). Builds cue observations from new events, calls services/ai, upserts `memory_triggers` and appends `severity_indicators`, then evaluates the 4 alert rules. Commits its own work and **never raises**. Extras: `scan_all_patients()` for periodic runs.
- `rules.py`: pure rule functions and thresholds (no DB), `ai_client.py`: httpx client (3 s timeout, any failure returns `None`), `schemas.py`: response models, `router.py`: routes, `scan.py`: `python -m app.modules.insights.scan [--loop]`.
- `tests/insights/` (under `services/api/tests/insights`): rules, AI client (httpx MockTransport), pipeline, router tests.

**Part B: `infra/`, root `Makefile`, `.github/workflows/ci.yml`, `.dockerignore`**
- Dockerfiles: api, ai, voice, patient-web, caregiver-web (+ shared `nginx.conf`, `healthcheck.py`, `api-entrypoint.sh` that runs Alembic).
- `docker-compose.yml`: postgres 16, redis 7 (password), api, ai, voice, both web apps, optional `insights-scan`, shared `media_data` volume, healthchecks on everything.
- `docker-compose.prod.yml` + `caddy/Caddyfile`: TLS 1.3-only reverse proxy, no other ports published. Needs Compose >= 2.24.
- `.env.example` (all 6 settings vars + extras), `scripts/gen_secrets.sh`, `scripts/check_env.sh`.
- Makefile: `up down seed seed-fake test` (+ `env secrets config build logs ps lint install-dev`).

## 2. How to run
```bash
make install-dev && make test         # insights tests: core_stub + in-memory SQLite
make config                           # validates compose with the example env
make env && make secrets              # paste output into infra/.env
make up                               # refuses to start while secrets are placeholders
make seed-fake                        # demo data + insights scan (rules only)
```
Without Docker: `PYTHONPATH=mocks/core_stub:services/api DATABASE_URL=sqlite+pysqlite:///./fake.db python mocks/fake_data/fill_fake_data.py --create-tables --run-pipeline`

Env vars: see `infra/.env.example`. Settings consumed by my module: `AI_SERVICE_URL` (via `settings`). `TEST_DATABASE_URL` points the tests at Postgres after integration.

## 3. Endpoints exposed (all `/api/v1`, shapes exactly as in ROUTES)
`GET /alerts?patient_id=&status=open|all`, `POST /alerts/{id}/ack {note?}`, `GET /patients/{id}/dashboard/trends?days=30|cue-comparison|triggers|severity`, `GET /patients/{id}/report.csv`.
`main.py` must `include_router(insights.router, prefix="/api/v1")`.

Behaviours worth knowing:
- **RBAC**: every route requires caregiver / health_worker / admin (elder-facing `patient` role gets 403), then `assert_can_access_patient`. `GET /alerts` without `patient_id` returns alerts of linked patients (admin: all).
- `trends`: dense list, one entry per **UTC** day; empty days have `sessions: 0`, `avg_score: null`, `engagement_minutes: 0.0`.
- `cue-comparison`: counts answered items only (`correct IS NOT NULL`), all-time; `accuracy` is a **0..1 fraction**; `by_domain` accuracy is `null` when one side has no data.
- `severity` with no data yet returns 200 with nulls (+ disclaimer) instead of 404. The disclaimer is always included.
- `report.csv`: daily table for the last 90 UTC days; the final row is the "not a diagnosis" disclaimer.
- `ack` is idempotent (second ack changes nothing) and calls `record_change` so devices get the update.

## 4. Alert rules and my assumptions (the spec left these open)
| Rule | Spec | My additions (all constants in `rules.py`) |
|---|---|---|
| score_drop | 7-day avg down > 20% vs previous 7 days | strictly greater than 20%; `alert` severity at >= 40%, else `watch`; min 1 scored session per window (raise after pilot: single-session comparisons are noisy) |
| activity_drop | no sessions for 3 days | `alert` at >= 7 days; patients with zero sessions ever are not flagged |
| missed_reminders | missed reaching `escalate_after_misses` | = the **most recent N events are all `missed`** (a `done`/`later` breaks the streak); 14-day look-back; `escalate_after_misses < 1` disables; `alert` if any medicine reminder, else `watch`; one alert per patient |
| severity | band watch/alert | stable creates nothing; severity = band |
- De-dup: at most one **open** alert per (patient, kind). If a more severe decision arrives, the open alert is **escalated in place** (and re-synced); never downgraded. After an ack, a new alert may be created.
- **activity_drop can't fire from a sync** (a sync means the patient just played). Hence `scan_all_patients` + the `insights-scan` compose service (every 6 h; stops calling the AI after its first failure).
- Day boundaries are UTC; NER is UTC+5:30, so a late-evening session lands on the next UTC day.
- Severity history is append-only (one row per run); the dashboard reads the latest.

## 5. Mocks used and what replaces them
| Mock | Replaced by |
|---|---|
| `mocks/core_stub/app/{core/config,core/db,core/security,models}.py` | 1.1's real modules. **Delete the folder.** `X-Test-User` header auth in the stub is test-only |
| `mocks/core_stub/app/modules/sync/changelog.py` | 1.4's `record_change` (tests patch it with a recorder anyway) |
| `mocks/fake_ai/client.py` (`FakeAIClient`) | real services/ai (tests only) |
| `mocks/fake_data/fill_fake_data.py` | n/a: demo/dev tool (4 fictional patients: stable / declining / inactive / missed meds) |

## 6. CONTRACT CHANGE REQUESTS (proposals; I proceeded with the labelled assumption)
1. **`memory_triggers` unique (patient_id, cue_id)**: the upsert assumes one row per cue. Stub has it; please add to the real model/migration.
2. **Cue metadata missing from `game_events`**: `/ai/triggers/update` needs `cue_type` and `valence_label` per observation, but events only carry `cue_id`. I reuse the existing trigger's metadata, else `cue_type="unknown"` and `valence_label` = the session's dominant positive emotion label (else `neutral`). Proposal: a cue catalog (packages/content ids -> type/valence) or add these to the event payload. **Also: `cue_id` is treated as an opaque string** (content ids are probably not UUIDs; stub uses `String(100)`). The "all ids are UUID" line needs clarifying.
3. **`/ai/severity/estimate` receives only `{patient_id, window_days}`**: the AI service must read the DB itself (or I need to send data). I send `window_days=14`. Needs confirmation with Claude 2. Also `/ai/triggers/update` returns no `cue_type`, so I keep the one I sent.
4. **Settings**: proposing `MEDIA_DIR` (compose sets `/data/media`) and optionally `CORS_ORIGINS` (not needed when using the nginx same-origin proxy; needed for `vite dev` on :5173/:5174 against :8000).
5. **Health endpoints**: no `/health` in the contract. Healthchecks accept any HTTP status < 500 on `/openapi.json` (api, ai) or a TCP connect (voice). Proposal: `GET /health` unversioned on api, ai, voice.
6. **`record_change` entity names**: I pass the table names `"alerts"` and `"memory_triggers"` (constants `ENTITY_ALERT`, `ENTITY_TRIGGER` in `pipeline.py`). Claude 1.4 must confirm the strings.

## 7. Assumptions about 1.1 / others
- Column names are exactly the briefing's. Types are my reading (see stub); recommended indexes are declared in the stub models:
  `game_sessions(patient_id, started_at)`, `game_events(patient_id, ts)` + `(session_id)`, `reminder_events(patient_id, due_at)` + `(reminder_id, due_at)`, `alerts(patient_id, kind, acknowledged_at)` + `(patient_id, created_at)`, `severity_indicators(patient_id, computed_at)`, `emotion_samples(patient_id, ts)`, `memory_triggers` unique `(patient_id, cue_id)`.
- Auth: I use `get_current_user` plus a local role check instead of `require_roles(...)`, so I don't depend on whether it returns a dependency or a decorator. `health_worker` access is assumed to live in `caregiver_links` like caregivers.
- `get_session` is a generator function (the scan CLI wraps it with `contextlib.contextmanager`).
- Real DB is PostgreSQL: SQL uses dialect switches (`timezone('UTC', ts)::date`, `extract(epoch ...)`); SQLite branches exist only for tests.
- `process_synced_data` holds the DB transaction during up to two 3 s AI calls: fine at prototype scale; move to a background task later. It is not idempotent per session: call it only for newly accepted sessions (the sync `op_id` dedup does that).

## 8. Infra notes and known gaps
- Build context is the repo root. Each service needs `requirements.txt` (api falls back to `infra/requirements/api.txt`, ranges not pins: replace with 1.1's lock). ai/voice assume an ASGI app at `app.main:app` (override with `APP_MODULE`). Web builds need a committed `pnpm-lock.yaml` and assume package dirs `apps/<name>` with a `build` script emitting `dist/`.
- Web containers (nginx-unprivileged, :8080) proxy `/api/` and `/ws/` to `api:8000`, so the apps should call a **relative** API base (`VITE_API_BASE_URL=/api/v1`; the variable name is my assumption). Camera/mic Permissions-Policy is `self` only.
- Secrets come from `infra/.env` only; `make up` runs `check_env.sh` (min lengths, 32-byte AES key, URL-safe passwords). Postgres/Redis/AI/Voice ports bind to 127.0.0.1.
- TLS 1.3 is only provided by the optional prod override (Caddy). Dev compose is plain HTTP. At-rest encryption of the Postgres/media volumes depends on the host (disk encryption); only media files are app-level AES-256-GCM (Claude 1.3).
- voice image: AI4Bharat models are large (multi-GB image / first-run download); unverified here.
- Alert messages are caregiver-facing and gentle but they do contain "watch"/"alert" levels; the dashboard must still show `DISCLAIMER` next to scores/severity (the severity endpoint returns it).
- CI `docker-build` skips services whose directory is not present; the `web` job runs only when `pnpm-workspace.yaml` exists.

## 9. PORTABILITY NOTES
- Reusable as-is for the native app: all HTTP routes (bearer-token, versioned, JSON only; CSV is plain text) and `rules.py` (pure Python; the thresholds could be mirrored in TypeScript for on-device nudges).
- Not applicable to React Native: nginx config, Caddy, web Dockerfiles. These only serve the PWA.
- Adapters defined by me: none (backend + infra only). The API is cookie-free, so the native app needs no backend change.
