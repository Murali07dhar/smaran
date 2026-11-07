# KNOWN_GAPS.md — ranked by SIH demo risk

Legend: **H** = could break or embarrass the live demo, **M** = visible if someone pokes, **L** = polish / post-demo.

## What was actually run
| Check | Result |
|---|---|
| services/api pytest (SQLite) | 352 pass |
| services/ai pytest | 85 pass |
| services/voice pytest (`VOICE_MODELS_MODE=off`) | 10 pass |
| packages/games (node --test) / voice-i18n (vitest) | 47 / 45 pass |
| apps unit (vitest) | patient 18, caregiver 3 pass |
| `pnpm -r typecheck`, `pnpm -r build` | clean |
| Native run: api+ai+voice+Postgres 16+Redis 7 | `scripts/native-up.sh` |
| `services/api/scripts/smoke_golden.py` (real AI) | 24/24 pass |
| `services/api/scripts/smoke.py` (original, now against real AI) | 32/32 pass |
| `scripts/smoke_coop_ws.py` | pass |
| **Playwright golden path in real Chromium** (`pnpm test:golden`) | pass, ~60 s |
| Caregiver MSW e2e (`pnpm --filter @smaran/caregiver-web test:e2e`) | 4 pass |
| **NOT RUN:** `docker compose up/config`, image builds, Caddy prod override, ruff, ESLint (not configured), Postgres test-suite on the final tree (last PG run was Integrator A's 350) | — |

## Gaps
| # | Risk | Gap | Fastest fix |
|---|---|---|---|
| 1 | **H** | Docker/compose/Caddy/nginx were never run in this environment (the voice proxy rule and the web Dockerfiles against the new single workspace are untested). | On a Docker machine: `make env && make secrets && make up`, then `python services/api/scripts/smoke_golden.py`. Fall back to `scripts/native-up.sh` + two `vite` servers for the demo. |
| 2 | **H** | Demo laptop needs Postgres 16 + Redis for the native path (SQLite is test-only). | Keep the Docker path as primary; `scripts/native-up.sh` documents the exact env. |
| 3 | **H** | Patient PIN is 6 digits and **expires in 10 min** (`PATIENT_PIN_TTL_MIN`). A PIN issued before the stage walk-up will be dead. | Issue the PIN right before logging in; or raise `PATIENT_PIN_TTL_MIN=1440` for the demo. |
| 4 | **H** | The `missed_reminders` alert only appears if the patient app stayed open past a reminder's 30-min grace (engine state is in memory, not persisted) or after the periodic scan runs. The UI test does not assert an alert; the API smoke does (via pushed `missed` events). | Seed a missed-reminder history with `mocks/fake_data/fill_fake_data.py` for the dashboard demo; persist `ReminderEngine` state in the KV store (small change in `reminderState.ts`). |
| 5 | M | `activity_drop` alerts only come from the `insights-scan` loop (a compose service). Not started by `native-up.sh`. | `python -m app.modules.insights.scan --loop` in `services/api`. |
| 6 | M | Caregiver upload tags are the file name, so every cue defaults to valence `familiarity`. No emotion picker. | Add an emotion `<select>` to the photo upload in `App.tsx` (tags already honour `joy`, `comfort`, `label:<text>`, `item:<id>`). |
| 7 | M | Co-op: patient joins by code and the **default** memory game opens; the room's `game_id` is not read (join response has no game_id) and the family-side flow was only tested at the relay level. | Add `game_id` to the join response (additive) and pass it as `?game=`. |
| 8 | M | Models are placeholders: the FER ONNX is a smoke model, AI4Bharat voice models are off (`VOICE_MODELS_MODE=off`) so speech falls back to browser TTS/STT; Assamese voice depends on the device having an `as` voice. | Install `requirements-models.txt` on a GPU/CPU box and set `VOICE_MODELS_MODE=on`; pre-record caregiver voice clips for the demo. |
| 9 | M | Emotion capture is not called by any patient component (consent gate exists, off by default) — D8. | Wire `captureEmotion` after `onComplete`, only when `hasValidConsent`. |
| 10 | M | Assamese/Bodo/Meitei strings unverified by native speakers; some patient chrome (e.g. the sync indicator) is English-only. | Native-speaker review pass; move the sync strings into `i18n/locales`. |
| 11 | M | Elder-UI audit was grep-level; real memory game checked manually in Assamese only. No timers/failure copy found in the games' strings. | 30-minute walkthrough of all 10 games at 56 px / 20 px. |
| 12 | M | `process_synced_data` holds the DB transaction during up to two 3 s AI calls; severity posts up to 5000 samples per sync (AI de-duplicates, but it is O(n) per push). | Move to a background task / send only samples newer than the last run. |
| 13 | L | Caregiver shows no media thumbnails (no use of signed URLs in the dashboard). | `<img src={BASE_ORIGIN + url}>` after `GET /media/{id}/url`. |
| 14 | L | D8 items: patient QR login UI, real web push, PWA PNG icons, `DELETE /media`, audit-log table, key rotation. | Post-demo. |
| 15 | L | Media: 20 MB whole-file decrypt in memory, no malware scan, audio metadata not stripped, no upload rate limit; losing `MEDIA_KEY_B64` loses all media. | See backend handoff A. |
| 16 | L | No rate limit on co-op join / WS messages; WS token in query string (mask in logs); content endpoint needs no bearer (mask `sig` in proxy logs). | Reverse-proxy rules. |
| 17 | L | Support tool, not a diagnosis. Reference norms are synthetic; severity bands are rule-based. | Clinical validation before any real-world use. |
| 18 | L | `ruff`/ESLint not configured for the TS apps; CI runs `typecheck` + unit only, not the Playwright golden path. | Add a CI job with services up. |
