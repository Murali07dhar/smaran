# SMARAN — Understanding Memory Through Emotion

Offline-first, caregiver-managed AI platform (PWA) for elderly dementia patients in North-East India (SIH26003, team SMARAN_GH).
**Detect → Associate → Personalize.** A support tool, never a diagnosis: the disclaimer is shown wherever scores or severity appear.

## Architecture
```mermaid
flowchart LR
  subgraph Browser
    P["patient-web :5173<br/>React PWA, Dexie, sync-core,<br/>@smaran/games, VoiceClient"]
    C["caregiver-web :5174<br/>React, Plotly"]
  end
  P -- "/api/v1, /ws (relative)" --> X[(Vite proxy in dev / nginx+Caddy in Docker)]
  C -- "/api/v1" --> X
  X -- "/api, /ws" --> API["services/api :8000<br/>FastAPI, SQLAlchemy 2"]
  X -- "/api/v1/voice/* → /voice/*" --> V["services/voice :8002<br/>ASR / LID / TTS"]
  API --> PG[("PostgreSQL 16")]
  API --> R[("Redis 7<br/>PIN/QR, co-op pub/sub")]
  API -- "/ai/triggers/update<br/>/ai/severity/estimate (+samples)" --> AI["services/ai :8001<br/>triggers, difficulty,<br/>severity, emotion, content"]
  API --- M[("media volume<br/>AES-256-GCM")]
  P -. "offline: IndexedDB queue → POST /sync/push (game_sessions, game_events,<br/>emotion_samples, reminder_events); GET /sync/pull" .-> API
```
Packages: `contracts` (OpenAPI + TS types), `sync-core`, `design-tokens`, `games`, `content`, `voice-i18n`. One pnpm workspace (`apps/*`, `packages/*`); Python services sit beside it.

## Quick start (native — the path that was actually run)
Prereqs: Node ≥ 20, pnpm 9, Python 3.11 (+ `uv`), PostgreSQL 16, Redis 7.

```bash
pnpm install                                   # one root workspace
# Python venvs (one per service)
for s in api ai voice; do (cd services/$s && uv venv --python 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt); done
# Postgres: role smaran/smaran (password smaran), database smaran   |   redis-server running on :6379
scripts/native-up.sh                           # migrates + seeds, starts api :8000, ai :8001, voice :8002 (logs in .run/)
pnpm dev:patient &  pnpm dev:caregiver &       # :5173 / :5174, proxying /api, /ws, /api/v1/voice
```
Stop: `scripts/native-up.sh stop`. Secrets for the native run are generated into `.run/env` (git-ignored).

### Docker (NOT RUN in this build)
```bash
make env && make secrets && make config && make up     # infra/docker-compose.yml, Caddy override in docker-compose.prod.yml
```

## Seed and demo
`seed.py` (run by `native-up.sh`) creates: caregiver `caregiver@smaran.demo` / `Smaran-Demo-123`, health worker `healthworker@smaran.demo` (same password), patients Bimala Das and Tomba Singh with reminders, media, sessions and alerts.
Patient PINs are **6 digits and expire after 10 minutes**: issue one from the dashboard right before logging in.

Demo script (the golden path):
1. Caregiver app → log in → *Add patient* (name, age) → note the PIN.
2. Select the patient → *Upload photo* (the cue) → add a *medicine* reminder.
3. Patient app → enter the PIN → **Family** (photo is downloaded and cached) → go offline (DevTools → Offline).
4. **Play** → memory game runs from local content with the caregiver photo as a cue.
5. Go online → data syncs → AI updates triggers → caregiver dashboard shows trend, cue comparison, triggers, severity (with disclaimer) and alerts.

## Tests
| Command | What |
|---|---|
| `cd services/api && .venv/bin/pytest -q` | 352 tests (SQLite; `TEST_DATABASE_URL=postgresql+psycopg://…` for Postgres — **wipes that DB**) |
| `cd services/ai && .venv/bin/pytest -q` | 85 tests |
| `cd services/voice && VOICE_MODELS_MODE=off VOICE_REQUIRE_AUTH=false .venv/bin/pytest -q` | 10 tests |
| `pnpm -r typecheck && pnpm -r test:unit && pnpm --filter @smaran/games test && pnpm --filter @smaran/voice-i18n test` | TS |
| `pnpm -r build` | both apps + games |
| `pnpm smoke` | API golden path against the **real** AI (needs services up) |
| `services/api/.venv/bin/python services/api/scripts/smoke_coop_ws.py` | co-op relay |
| `pnpm test:golden` | Playwright, real Chromium: caregiver → patient offline play → sync → AI → dashboard (needs services up; starts both Vite servers; `PW_CHROMIUM=/path/to/chrome` to override the browser) |
| `pnpm --filter @smaran/caregiver-web test:e2e` | MSW-backed caregiver specs |
| `services/api/scripts/gen_contracts.sh` | regenerate `packages/contracts/openapi.json` + `schema.d.ts` (run with the API venv on PATH) |

## Environment variables
| Var | Used by | Purpose |
|---|---|---|
| `DATABASE_URL`, `REDIS_URL` | api | Postgres (psycopg3) / Redis |
| `JWT_SECRET`, `JWT_ALGORITHM` (HS256), `JWT_ISSUER` | api, voice | **One shared secret**: voice verifies tokens issued by the API |
| `ACCESS_TOKEN_MINUTES` (15), `REFRESH_TOKEN_DAYS` | api | token lifetimes |
| `MEDIA_KEY_B64` | api | 32-byte AES-256-GCM key (base64). Lose it → lose all media |
| `MEDIA_DIR`, `MEDIA_URL_TTL_SECONDS` | api | encrypted media store (shared volume) / signed-URL TTL |
| `AI_SERVICE_URL`, `VOICE_SERVICE_URL` | api | upstreams |
| `SYNC_PULL_HOLDBACK_SECONDS` | api | hides in-flight rows from `/sync/pull` (Postgres cursor gap); 0 for single-writer demos |
| `PATIENT_PIN_TTL_MIN`, `PATIENT_QR_TTL_MIN` | api | PIN/QR lifetime (10) |
| `CORS_ORIGINS` | api | allowed origins when not same-origin (default both dev ports) |
| `STRICT_MODULES` | api | fail fast if a router module fails to import |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MIN`, `BCRYPT_ROUNDS` | api | auth hardening |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | ai | optional; templates are used when unset |
| `AI_STATE_DB`, `AI_SERVICE_TOKEN`, `MLFLOW_TRACKING_URI` | ai | state SQLite path / optional bearer / optional tracking |
| `VOICE_MODELS_MODE` (`off`/`on`), `VOICE_REQUIRE_AUTH` | voice | models off → browser TTS/STT fallback |
| `VITE_API_BASE_URL` (`/api/v1`), `VITE_VOICE_BASE_URL`, `VITE_WS_BASE_URL` (empty = same host), `VITE_USE_MOCKS` | apps | client config (`apps/*/.env.example`) |
| `DEV_PROXY_API`, `DEV_PROXY_VOICE` | apps (dev) | Vite proxy targets |
| `POSTGRES_*`, `REDIS_PASSWORD`, `*_PORT`, `SMARAN_DOMAIN`, `ACME_EMAIL`, `INSIGHTS_SCAN_INTERVAL_MINUTES` | compose | see `infra/.env.example` |

No secret is committed; `.env` files are git-ignored (`.env.example` provided).

## Non-negotiables — where they are enforced
- Camera/mic only after a `ConsentRecord` (server-recorded, online-only, default off): `core/validation/consent.ts`; the voice client only receives a mic/STT adapter when `mic` consent is granted (`adapters/web/voice.ts`). Emotion capture is off by default and needs consent.
- AES-256-GCM media at rest (`app/core/crypto.py`; `smoke.py` proves ciphertext on disk). RBAC on every route (`assert_can_access_patient`, `require_roles`); a patient cannot read the dashboard or upload.
- Disclaimer from the API (`SUPPORT_DISCLAIMER`) rendered next to severity and trends in the caregiver app.
- Elder UI: 56 px targets, 20 px base, one action per screen, no timers, gentle copy (`games.gentle.*`).
- Only CC0/placeholder content and caregiver uploads.

See `CONFLICTS.md` (decisions), `KNOWN_GAPS.md` (ranked risks), `PORTABILITY.md` (React Native), `docs/handoffs/` (original handoffs).
