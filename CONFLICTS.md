# CONFLICTS.md — Final Integrator resolutions

Sources: `docs/handoffs/INTEGRATION_HANDOFF-{A,B,C}.md`, `CONFLICTS-{B,C}.md`. Priority rule: DATABASE SCHEMA > ROUTES > signatures.
No schema or route-shape change was needed. Two *response-shape* facts the old handoffs missed were fixed in the clients (see "Found while running").

## Pre-made decisions
| # | Decision | Status | Where |
|---|---|---|---|
| D1 | `routines.steps` = `[{order, title, media_id?}]`; normalise legacy strings | Done, server-side on write **and** read (and in the sync payload). Caregiver builder now sends objects. | `services/api/app/modules/media/validation.py::normalize_steps`, `routines_routes.py`, caregiver `core/api.ts`, `Content.tsx` |
| D2 | `no_cue:<domain>` for without-cue trials | Done. Observations now cover every answered event; without-cue → `cue_id="no_cue:<domain>"`, `cue_type="none"`, `valence="neutral"`, `with_cue=false`. The synthetic trigger is never stored/synced. Cue metadata for real cues comes from the caregiver media asset (kind → cue_type, emotion-label tag → valence). | `insights/pipeline.py::_build_observations`, `_media_cues`, `_upsert_triggers` |
| D3 | One StringTable | Done in `apps/patient-web/src/adapters/web/voice.ts` (`composedStrings`: `games.*` first, then voice-i18n locale JSON) injected into `VoiceClient`. | patient-web |
| D4 | `/api/v1/voice/*` → services/voice `/voice/*` | Done: Vite dev proxy (both apps) + `infra/docker/nginx.conf`. Caddy sits in front of nginx so needs no rule. nginx rule NOT RUN (no Docker). | vite configs, nginx.conf |
| D5 | Severity data | Chose the **smaller change**: services/ai already accepts optional `samples` (its CCR-AI-1, idempotent by content hash). The insights pipeline now sends the window's answered events + the patient's first 30 as `samples`. No DB access for the AI service; request stays `{patient_id, window_days}` + optional `samples`. | `insights/ai_client.py`, `pipeline.py::_perf_samples` |
| D6 | Relative API base | Done: `VITE_API_BASE_URL=/api/v1` in both apps; patient `ApiClient` no longer appends `/api/v1`; Vite proxies `/api`, `/ws`, `/api/v1/voice`. Signed media URLs are relative and fetched through the same origin. | both apps |
| D7 | Real games registry | Done: `GameLauncher` uses `@smaran/games` (`games[]`, `?game=<id>`), content = `@smaran/content` + caregiver photos, cues = cached caregiver media, voice = real `VoiceClient`, `onEvent` → `game_events` op (1:1 column mapping), `onComplete` → session `score`. | `apps/patient-web/src/components/GameLauncher.tsx`, `core/games/*`, `core/media/mediaCache.ts` |
| D8 | Out of scope | Listed in KNOWN_GAPS.md | — |

## Contract decisions from the three handoffs
| Item | Resolution |
|---|---|
| A: routines.steps shape | = D1 |
| A: media URL relative, content endpoint needs no bearer | Patient app downloads via the signed URL once and stores the blob in its FileAdapter (offline cues). Proxy must not log the query string (README). |
| A: sync entity names `reminders, routines, media_assets, alerts, memory_triggers` | Verified equal to `PULL_ENTITIES` in `packages/contracts/src/sync-rules.ts` and what the real server emits (golden smoke). |
| A: reminder JSON `schedule` | Clients now use `schedule` (`ReminderOut` in contracts). `domain.ts::Reminder` keeps the DB column name `schedule_rrule` because `test_contracts.py` locks it to the models. Sync payload is canonicalised to `schedule` in `record_change`. |
| B: CCR-2 cue_id nullable | = D2 |
| B: StringTable composition | = D3 |
| B: voice route prefix | = D4 |
| B: services/ai 85 pytest never run | Run: 85 pass. |
| B: services/voice tests never run | Run: 10 pass. `services/voice/requirements.txt` was missing from Integrator B's zip (Dockerfile + CI need it) — added. |
| C: `/content` has no route | Removed the call. Content is bundled (`@smaran/content`); caregiver photos are media. |
| C: ROUTES gap — caregiver confirm/override of emotion samples | Not built (emotion capture not wired, D8). |
| C: real `game_id` list for co-op | `POST /coop/rooms` accepts any string; the games registry ids (`memory_pairs`, …) work. |
| C: session score = % correct 0–100 | Kept; computed from `correct_answers / answers`. |
| C: stubs for `@smaran/games`, `@smaran/voice-i18n`, `@smaran/contracts` | Deleted; C's hand-written AI/sync-rule types merged into the generated contracts package. |

## Found while running (never visible in static review)
1. **`GET /patients` returned HTTP 500** for the seeded patients: `estimated_stage` is TEXT in the model/seed (`'mild'`) but the response schema said `int`. Fixed to `str` (+ regression test, contracts regenerated).
2. **`GET /patients/{id}/consents` returns `{latest, history}`**, not a list. Both clients crashed on it (caregiver panel blank; patient `PatientProvider` unmounted). Both now accept the real shape.
3. **Reminders in `/sync/pull` carried `schedule_rrule`**, REST carried `schedule`. Now always `schedule`.
4. **Severity `drivers` are objects** → rendered `[object Object]`. Fixed.
5. **Seed printed 4-digit patient PINs that can never log in** (API: 6 digits, 10-minute TTL, issued per request). Seed message corrected.
6. **Patient app never emitted `missed` reminder events**, so the `missed_reminders` alert could not fire from real use. Wired (`recordMissedReminders`) + unit test.
7. Co-op join sent the join code straight to the WebSocket; now `POST /coop/rooms/join` → `ws_token` → socket (tested with `scripts/smoke_coop_ws.py`).
8. `tsc -b` emitted compiled `vite.config.js` next to the TS sources (would shadow the TS config) and the PostCSS/Tailwind CJS configs broke under `"type":"module"`. Fixed (`emitDeclarationOnly`, `.cjs`).
9. Design tokens `default` import from a CJS package failed in Rollup → import `tokens.json`.
10. Dead seed PIN docs, caregiver e2e specs written against a login that needed a password they never typed, and a patient e2e written for the mock game: fixed / replaced by `/e2e/golden-path.spec.ts`.
