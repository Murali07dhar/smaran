# INTEGRATION_STATE — Final Integrator

**Phase:** Sessions 1 + 2 done in one run (assemble → build/test → D1–D7 → native run → golden path → docs). Remaining = items in KNOWN_GAPS.md.

## Done
- One root pnpm workspace (`apps/*`, `packages/*`); Python services in `services/{api,ai,voice}` with own venvs. Stubs for games / voice-i18n / contracts removed; real packages wired.
- Typecheck, build (both apps + games), all test suites green (see KNOWN_GAPS.md table).
- D1–D7 applied (details + file paths in CONFLICTS.md); ten real defects found only by running (CONFLICTS.md "Found while running").
- Native run: `scripts/native-up.sh` (Postgres 16 + Redis 7 + api/ai/voice). `services/api/scripts/smoke_golden.py` 24/24 and original `smoke.py` 32/32 against the **real** AI; `smoke_coop_ws.py` OK.
- Playwright golden path passes in real Chromium (`pnpm test:golden`).
- Docs: README.md, CONFLICTS.md, KNOWN_GAPS.md, PORTABILITY.md.

## Not run
`docker compose config/up`, image builds, Caddy prod override, ruff, ESLint (none configured), Postgres run of the final api test suite.

## Decisions
D1–D8 as briefed; D5 implemented via optional `samples` on `/ai/severity/estimate` (no AI→DB access). `domain.ts::Reminder` keeps DB name `schedule_rrule` (locked by `test_contracts.py`); wire type is `ReminderOut` (`schedule`).

## Next (if resuming)
1. On a Docker host: `make env && make secrets && make up`, run `pnpm smoke`; fix whatever the web Dockerfiles/nginx do against the single workspace.
2. KNOWN_GAPS #4 (persist ReminderEngine state), #6 (emotion tag picker), #7 (co-op game_id).
3. Native-speaker review of Assamese strings.

## Environment notes
Services run with `scripts/native-up.sh`; the sandbox may reset between turns (Postgres/Redis/uvicorn/vite stop) — restart with `service postgresql start; redis-server --daemonize yes; scripts/native-up.sh`.
Do not use `pkill -f`/`pgrep -f` with a pattern that also appears in the same command line (it kills the shell).
