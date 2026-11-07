# HANDOFF - Claude 1.1: Backend Core

Scope owned: `services/api/{app/main.py, app/core/*, app/models.py, alembic/, seed.py}`, `packages/contracts`, plus `mocks/api_stubs`.
(File name is `HANDOFF_1.1.md` so it does not collide with the other builders' handoffs.)

## 1. What is built
| Area | Files |
|---|---|
| App | `app/main.py` - factory, tolerant module loader, `GET /healthz`, `GET /readyz`, CORS from env, RFC 7807 errors, nosniff + `Cache-Control: no-store` on `/api/v1` |
| Core | `app/core/config.py` (settings), `db.py` (Base, engine, SessionLocal, get_session), `redis.py`, `security.py`, `errors.py`, `ids.py` (UUIDv7) |
| Models | `app/models.py` - all 16 tables, exact column names |
| Migration | `alembic/versions/0001_initial_schema.py` (hand-reviewed autogenerate; up/down verified on PostgreSQL 16 and SQLite; `alembic check` shows zero drift) |
| Seed | `seed.py` - idempotent, deterministic ids, 30 days of data |
| Contracts | `packages/contracts` - `openapi.json` + generated `src/schema.d.ts` + hand-written `src/domain.ts`, `src/wire.ts` |
| Mocks | `mocks/api_stubs/*` - 501 stub routers + no-op `record_change` / `process_synced_data` |
| Tests | `services/api/tests` - 106 tests, all green on SQLite **and** PostgreSQL 16 |

## 2. Model list (class -> table)
`User`->users, `PatientProfile`->patient_profiles, `CaregiverLink`->caregiver_links, `ConsentRecord`->consent_records, `MediaAsset`->media_assets, `Routine`->routines, `Reminder`->reminders, `ReminderEvent`->reminder_events, `GameSession`->game_sessions, `GameEvent`->game_events, `EmotionSample`->emotion_samples, `MemoryTrigger`->memory_triggers, `Alert`->alerts, `SeverityIndicator`->severity_indicators, `SyncChange`->sync_changes, `SyncOp`->sync_ops. `app.models.ALL_MODELS` lists them; enum tuples (`ROLES, LOCALES, EMOTION_LABELS, ...`) live at the top of `models.py` - import them instead of retyping strings.

## 3. Shared interfaces (exact signatures)
```python
# app.core.db
class Base(DeclarativeBase): ...
def get_session() -> Iterator[Session]            # FastAPI dependency; routes call session.commit()
engine, SessionLocal                              # also exported

# app.core.security
def get_current_user(credentials=Depends(bearer_scheme), session=Depends(get_session)) -> User
def require_roles(*roles: str) -> Callable[..., User]          # Depends(require_roles("caregiver","admin"))
def assert_can_access_patient(session: Session, user: User, patient_id: UUID | str) -> None  # raises HTTPException 403
def hash_password(password: str) -> str
def verify_password(password: str, password_hash: str | None) -> bool
def hash_pin(pin: str) -> str                      # 4-8 digits, else ValueError
def verify_pin(pin: str, pin_hash: str | None) -> bool
def create_tokens(user: User) -> tuple[str, str]   # (access 15 min, refresh 14 days)
def decode_token(token: str, expected_type: str | None = None) -> dict   # raises TokenError

# additive helpers (not in the contract, optional to use)
create_token(subject, token_type, expires_delta, **claims) -> str      # e.g. token_type="qr" for patient QR login
TokenError; can_access_patient(...) -> bool; accessible_patient_ids(session, user) -> set[UUID] | None  # None = admin/all
# app.core.config: `settings` (DATABASE_URL, REDIS_URL, JWT_SECRET, AI_SERVICE_URL, VOICE_SERVICE_URL, MEDIA_KEY_B64, ...)
# app.core.redis:  get_redis(), get_async_redis(), redis_ping()
# app.core.ids:    uuid7()
# app.core.errors: problem_response(request, status, detail), install_exception_handlers(app)
```
Token claims: `iss, sub (user id), role, type ('access'|'refresh'), iat, exp, jti`. The role in a token is informational; `get_current_user` always re-reads the user (and role) from the DB.

## 4. How to run
```bash
cd services/api
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
cp .env.example .env            # set JWT_SECRET (>=32 chars); MEDIA_KEY_B64 is required only in production
alembic upgrade head            # needs PostgreSQL 16 at DATABASE_URL (infra/ from 1.5 provides it)
python seed.py                  # demo data (add --reset to rebuild); refuses ENVIRONMENT=production
uvicorn app.main:app --port 8000 --reload
pytest -q                                                       # SQLite (no services needed)
TEST_DATABASE_URL=postgresql+psycopg://u:p@host/db pytest -q    # real target DB (WIPES that DB)
scripts/gen_contracts.sh [--with-stubs]                         # openapi.json + TS types
```
Seed credentials (DEV ONLY): `caregiver@smaran.demo` / `healthworker@smaran.demo`, password `Smaran-Demo-123` (override with `SEED_PASSWORD`). Patient PINs: Bimala Das `2468`, Tomba Singh `1357`. Both staff users are linked to both patients. Patient ids are deterministic (uuid5): printed by `seed.py`.

Seed story: Bimala (as, mild) stable, camera consent granted, 53 emotion samples, cues beat no-cue accuracy. Tomba (mni, moderate) declines over the last ~10 days, fewer sessions in the last 7, no camera consent (so no emotion samples), 3 open alerts (`watch`/`alert`) + 1 acknowledged, severity band `watch`. Also seeds `sync_changes` for reminders/routines/memory_triggers/alerts so a fresh device can `/sync/pull`.

## 5. Endpoints exposed by this workstream
`GET /healthz` (liveness), `GET /readyz` (DB required -> 503 if down; Redis down -> `degraded`; includes per-module load status), `/docs`, `/redoc`, `/openapi.json` (disabled when `ENVIRONMENT=production`). Everything else comes from modules 1.2-1.5, included with prefix `/api/v1`.

**Module loader rules** (`load_modules`): `app.modules.<name>.router` must expose `router` (APIRouter). It MAY expose `ws_router` (included **without** prefix). Missing module -> warning + continue; broken module (import error inside it) -> error log + continue; `STRICT_MODULES=1` makes both fatal (use in CI/integration). Duplicate (method, path) across modules is logged as a warning. Module names: `auth_consent, media, sync, coop, insights`. An `__init__.py` in each module folder is optional (namespace packages work) but harmless.

## 6. Mocks used and what replaces them
`mocks/api_stubs/{auth_consent,media,sync,coop,insights}.py` answer 501 problem+json for every contract route (enable with `MODULE_STUBS_PATH=/abs/path/to/mocks/api_stubs`; only used when the real module is missing). `sync_changelog_stub.py` -> real `app/modules/sync/changelog.py` (1.4); `insights_pipeline_stub.py` -> real `app/modules/insights/pipeline.py` (1.5). Integrator: delete `mocks/api_stubs` after merge.

## 7. CONTRACT CHANGE REQUESTS and labelled assumptions
I did not edit the contract. Where it was silent or ambiguous I assumed the following; please confirm or reject:

**CCR-1 (needs action by 1.4): co-op WebSocket path.** The briefing says `main.py` includes every module with prefix `/api/v1`, yet the WebSocket is `/ws/coop/{room_id}` (no prefix). If the websocket lived on `coop.router` it would end up at `/api/v1/ws/coop/...`. Assumption implemented: coop exports `router` (HTTP, prefixed) **and** `ws_router` (WebSocket, not prefixed). Tested.

**CCR-2 (needs action by 1.2): `POST /auth/patient-pin-login {pin | qr_token}`.** `users.pin_hash` is salted bcrypt, so a PIN alone cannot identify a patient (it would need a scan over all patients, and PINs are not unique). Proposal: `qr_token` (JWT made with `create_token(patient_id, "qr", ...)`) is the primary path; the PIN path takes an extra field (`patient_id`, or a short pairing code). The schema was left untouched.

**Assumed column/constraint decisions** (cheap to change now, painful later):
1. `game_events.item_id`, `game_events.cue_id`, `memory_triggers.cue_id`, `reminders.voice_clip_id` are `VARCHAR(64)` (not UUID): content/cue ids come from content packs (slugs) or may be uuid strings.
2. `memory_triggers` has `UNIQUE(patient_id, cue_id)` so AI updates are upserts.
3. `media_assets.nonce` is `BYTEA` (raw 12-byte GCM nonce, as returned by `encrypt_bytes`). `tags`/`steps`/`drivers`/`payload` are JSONB (JSON on SQLite).
4. Enumerations are `VARCHAR` + `CHECK` (no PG enums). `severity_indicators.band` and `game_events.type` are intentionally not CHECKed (AI/SDK can extend); `gds_style_indicator` is CHECKed 1..7, `difficulty` 1..10, `age` 0..130.
5. **`server_version` auto-increments on every UPDATE** of `reminders` / `routines` (column `onupdate`), and `updated_at` is refreshed on `routines`, `reminders`, `memory_triggers`. Do not set them manually unless you intend to override.
6. **Naive datetimes are rejected** on write (`ValueError` -> `StatementError`); reads always return aware UTC. Use `datetime.now(timezone.utc)`.
7. Append-only tables are append-only by convention, not by trigger (the contract itself needs later writes to `game_sessions.ended_at/score` and `emotion_samples.caregiver_confirmed`).
8. FK policy: patient-owned rows `ON DELETE CASCADE` from `users` (DPDP erasure = delete the patient user); `alerts.acknowledged_by` `SET NULL`; `uploader_id/created_by/granted_by` restrict deletion of the staff user while rows exist.
9. `sync_changes.entity` values: the seed uses table names (`reminders`, `routines`, `memory_triggers`, `alerts`, `media_assets`). 1.4 owns the final vocabulary.

## 8. Notes for the other backend owners
- **1.2**: build routes on `security.py`. Lowercase/normalise emails before insert (unique index is case-sensitive; no citext). Rate-limit login and PIN endpoints (Redis helper provided). Validate `language` against `LOCALES + VOICE_PACK_LOCALES` (DB does not).
- **1.3**: `Reminder.escalate_after_misses` has no default (required by the REMINDER contract). Call `record_change` on every reminder/routine/media write. `voice_clip_id` is a string.
- **1.4**: `sync_changes.cursor` is BIGSERIAL; concurrent transactions can commit out of cursor order, so a client that stores `max(cursor)` may miss a row from a still-open transaction. Take a `pg_advisory_xact_lock` around `record_change` or only serve cursors below the lowest in-flight txn. Deliver `ws_router` (CCR-1). `sync_ops` is the idempotency ledger (insert-or-ignore on `op_id`).
- **1.5**: `ix_alerts_open_patient` is a partial index for "open alerts per patient"; `ix_game_*_patient_ts` serve dashboard windows.

## 9. Known gaps / honest limits
- **Not tested**: Redis itself (no Redis server in my sandbox; only the "down" path of `/readyz` is exercised), Python 3.11 (verified on 3.12.3), SQLAlchemy 2.0.x (verified on 2.1.5), Docker. Verified versions: fastapi 0.157.0, starlette 1.9.0, sqlalchemy 2.1.5, alembic 1.20.0, psycopg 3.3.6, pydantic 2.14.1, pydantic-settings 2.16.1, PyJWT 2.15.1, bcrypt 5.0.0, redis-py 8.1.0, pytest 9.1.1. `requirements.txt` uses ranges; pin with a lock file in CI.
- **No refresh-token rotation/revocation**: refresh tokens are stateless JWTs and the schema has no token table. If needed, 1.2 can keep a `jti` deny-list in Redis (`jti` is in every token).
- **No rate limiting or account lockout** in core. PINs (4-8 digits) have little entropy; bcrypt does not fix that.
- **At-rest encryption and TLS 1.3** are deployment/infra concerns (1.5) and media encryption is 1.3's `crypto.py`; the DB layer here does not encrypt columns. `password_hash`/`pin_hash` are bcrypt (SHA-256 pre-hashed to avoid the 72-byte truncation).
- No audit-log table exists in the fixed schema (relevant to DPDP accountability); consider a CCR.
- `domain.ts`/`wire.ts` are hand-written until modules publish full OpenAPI schemas. `domain.ts` is drift-tested against the models; `wire.ts` is not (it comes from the briefing's prose).
- The checked-in `openapi.json` contains only core routes (`/healthz`, `/readyz`). The Integrator must regenerate it after merge (`scripts/gen_contracts.sh`, without `--with-stubs`).
- Seeded game ids, cue ids, routine `steps` shape and severity `drivers` shape are placeholders owned by workstreams 4 / 1.3 / 2.
- Emotion/severity values in the seed are synthetic. Nothing in this workstream produces clinical output; score/severity alert messages in the seed carry the "not a diagnosis" disclaimer.

## 10. PORTABILITY NOTES (for the future React Native app)
- **Reusable as-is**: the whole backend (API-first, `/api/v1`, bearer-token auth only, no cookies/sessions, JSON snake_case, RFC 7807 errors, no web-only response formats) and `packages/contracts` (pure TS types/constants, no DOM/React imports).
- **Needs rewriting for React Native**: nothing in this workstream. Clients should consume `@smaran/contracts` types and the generated `paths` for a typed API client (the client itself belongs to the sync-core/app workstreams).
- **Adapters defined by 1.1**: none (StorageAdapter, AudioAdapter, NotificationAdapter, CameraAdapter, MicAdapter, FileAdapter are client-side).
- CORS is irrelevant for native clients; `CORS_ORIGINS` only serves the two web apps.

## 11. Test inventory (106)
security helpers + JWT attack cases (alg=none, wrong key/issuer, expired, wrong type, missing claims) - `assert_can_access_patient` matrix (14 cases) + HTTP 401/403 behaviour - model constraints, cascades, `server_version` bump, tz handling, BIGSERIAL cursor - exact column list per table - migration up/down/up, drift vs models, indexes - app startup with every module missing, broken/missing/stub module handling, strict mode, duplicate routes, CORS, problem+json, settings validation - seed content/idempotency/reset/story/consent rule - contracts parity (fields, nullability, enums, no secret fields).
