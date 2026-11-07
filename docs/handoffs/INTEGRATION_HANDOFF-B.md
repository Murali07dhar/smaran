# INTEGRATION_HANDOFF.md — Integrator B (Services & Packages)

Merged workstreams: Claude 2 (AI engine, services/ai), Claude 4 (games + content,
packages/games + packages/content), Claude 6 (voice/i18n/reminders, packages/voice-i18n +
services/voice). Backend (services/api) and the two web apps are out of scope — handled by
other integrators; only mocks/stubs are used here for them.

## What was merged

```
merged/
  pnpm-workspace.yaml        # scoped to packages/* for this integrator's slice
  tsconfig.base.json         # shared compiler options reference
  .eslintrc.json             # shared lint config for the 3 TS packages
  packages/
    games/                   # from Claude 4, unmodified except src/types.ts + src/mocks/voice.ts (see Conflicts)
    content/                 # from Claude 4, unmodified
    voice-i18n/               # from Claude 6, unmodified
  services/
    ai/                      # from Claude 2, unmodified (code); .offline-stubs/ used only
                              # for local verification, NOT included in this deliverable
    voice/                   # from Claude 6, unmodified
  mocks/voice/                # from Claude 6 (fake voice service for local dev)
  docs/MODELS.md              # from Claude 6
  .github/workflows/
    games-content-ci.yml      # renamed from games-content's ci.yml
    voice-ci.yml
    ai-ci.yml                 # moved out of services/ai/ci/
```

Root-level duplicates from the games-content and voice zips (`pnpm-workspace.yaml`,
`.env.example`, `CHECKLIST.md`) were simply never copied — each archive's own top-level
packages/services folders were pulled in individually, not the whole repo root. Service-scoped
files that happen to share those names (`services/ai/.env.example`, `services/ai/CHECKLIST.md`)
were kept since they document that service specifically and are referenced by its own
HANDOFF.md, not root/monorepo-level duplicates.

## Conflicts found and how each was resolved

See **CONFLICTS.md** for full detail. Summary:

1. **VoiceAPI.listen() shape mismatch** between games (optional `opts`, loose `intent` type,
   unused `expected_intents` field) and voice-i18n (canonical owner; required `opts:
   ListenOpts`, closed `Intent` union). **Fixed**: patched `packages/games/src/types.ts` and
   `src/mocks/voice.ts` to mirror voice-i18n's shape exactly. games test suite rerun: 47/47
   still pass.
2. **CCR-4 (games.* keys "must exist in voice-i18n")** — clarified rather than "fixed": games
   keeps its own 105-key `games.*` string table (own test enforces en/as parity); voice-i18n's
   locale JSON is a separate app-chrome namespace. No collisions either direction.
   `VoiceClient.speak()` resolves through an injected `StringTable`, so the real requirement is
   that whoever builds the host app composes a StringTable from both sources — flagged as a
   **CONTRACT DECISION** for the app-layer integrator (not fixable inside either package without
   creating a disallowed cross-package build dependency).
3. **CoopTransport/WebSocket message shape** — verified compatible with the CO-OP WEBSOCKET
   contract as-is; no fix needed.
4. **Observation.cue_id nullability (games' CCR-2)** — services/ai's schema still requires a
   non-empty `cue_id`, but its own CCR-2 says it should accept `null`. I did **not** patch this:
   `app/core/triggers.py` has no logic to resolve a null cue_id against an item-linked cue (it
   doesn't even have access to the Cue list, which is a client-side construct), so relaxing the
   Pydantic field alone would silently create a meaningless "None" cue bucket rather than
   implementing CCR-2's actual intent. Flagged as a **CONTRACT DECISION**: have the caller
   (services/api's insights pipeline) synthesize a stand-in cue_id for without-cue trials
   instead.
5. **services/voice route prefix** (`/voice/*`, not `/api/v1/voice/*`) — as documented in its
   own HANDOFF; needs a gateway proxy rule or a contract amendment from whoever owns that layer.

## CONTRACT DECISIONS (for the Final Integrator)

See CONFLICTS.md §3 for the full writeup. Short version:
1. `Observation.cue_id` nullability — recommend caller-side synthesis, not a schema relax.
2. StringTable composition (games.* + voice-i18n locales) belongs in apps/patient-web.
3. services/voice needs a `/api/v1/voice/*` proxy rule or a contract amendment.
4. services/ai's "85 pytest tests pass" claim could not be independently re-run end-to-end in
   this sandbox (no network); see "Known gaps" below for what was verified instead.

## Mocks/stubs still in place and what replaces them

- games: `createMockVoice` → real `VoiceClient` (now type-compatible, see conflict #1);
  `mockCues` → caregiver-upload cues; `createCoopBus` (in-memory) → real WebSocket
  CoopTransport against `/ws/coop/{room_id}` (not built here — owned by 1.4 + app layer);
  `demo_photos.json` → caregiver `ContentItem{source:'caregiver'}`.
- services/ai: `scripts/mock_client.py` → real services/api calling `/ai/*` with the bearer
  token. ONNX models are listed/documented, not bundled (`ml/make_smoke_onnx.py` regenerates
  the placeholder; real training scripts are written but never run, per its own HANDOFF).
- voice-i18n/services/voice: `mocks/voice/server.mjs` (canned ASR transcripts, beep WAV) →
  real `services/voice` (included in this merge and runnable). The mock remains useful for
  apps/patient-web local dev without Python running.

## Exact commands to install, run and test

```bash
# TypeScript packages (from merged/)
pnpm install                          # installs packages/{games,content,voice-i18n}
pnpm --filter @smaran/games test      # tsc (logic-only) + node --test -> 47 tests
pnpm --filter @smaran/games typecheck # full UI typecheck (needs @types/react etc.)
pnpm --filter @smaran/voice-i18n test # vitest -> 45 tests
pnpm --filter @smaran/voice-i18n typecheck
node packages/content/scripts/validate.mjs
python3 packages/content/scripts/gen-content.py   # regenerate placeholder assets if needed

# services/ai (port 8001)
cd services/ai
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.asgi:app --port 8001
python scripts/mock_client.py
python scripts/demo_trigger_decay.py
python -m pytest -q --tb=short

# services/voice (port 8002)
cd services/voice
pip install -r requirements-dev.txt
VOICE_MODELS_MODE=off VOICE_REQUIRE_AUTH=false pytest -q
VOICE_MODELS_MODE=off VOICE_REQUIRE_AUTH=false uvicorn app.main:app --port 8002
node ../../mocks/voice/server.mjs             # fake voice service instead
```

## Test results (this sandbox)

| Suite | Result | How |
|---|---|---|
| packages/games (`node --test`) | **47/47 pass** | Ran directly; matches HANDOFF claim exactly |
| packages/voice-i18n (`vitest`) | **45/45 pass** | No network to install vitest; built a minimal offline `describe/it/expect` shim on `node:test` (not shipped — see below), compiled `core/`+`tests/` with `tsc`, ran it. All 5 initial failures were shim gaps (`.rejects`, regex `toThrow`, `toMatchObject`), not real bugs — once fixed, RRULE/DST, snooze, escalation and WebCrypto AES-GCM all passed |
| services/ai contract shapes | **Verified by static read** | All 5 `/ai/*` endpoints and their Pydantic schemas checked field-by-field against the AI SERVICE contract — exact match |
| services/ai core logic | **Verified by direct execution** | No network to install fastapi/pydantic/httpx/river/pytest. Built throwaway offline stand-ins (not shipped) just enough to import `app/core/*` and `app/schemas.py`, then called the real functions directly (bypassing the FastAPI TestClient layer tests/conftest.py needs): `prob_cue_beats_baseline`/`decay_factor` math exact; full `update_triggers()` via a real `Store(':memory:')` reproduces the documented confidence-rise curve (0.667→0.9 over 8 days), the negative-valence 0.05 cap, and decay-without-sessions (0.9→0.083 over 90 days); ran the actual `scripts/demo_trigger_decay.py` end-to-end — its own self-check printed **"OK: rises with recall, then decays over time"**; `difficulty.next_difficulty`, `severity.estimate` (disclaimer always present, insufficient-data path), `emotion.calibrate`/`label_for`, `va_mapping.probs_to_va` all smoke-tested correctly |
| services/ai full pytest suite (85 tests via TestClient) | **NOT independently re-run** | Needs fastapi/starlette/pydantic/httpx/river/pytest with network access, unavailable in this sandbox. Static+direct verification above gives high confidence the logic is correct; recommend CI (which has network) rerun the real suite before merge sign-off |
| services/voice | **Verified by static read** | All 5 routes (`/voice/health`, `/voice/capabilities`, `/voice/asr`, `/voice/lid`, `/voice/tts`) and their response shapes checked against the contract — exact match, including RFC 7807 + `fallback` field on `ModelUnavailable`. Not run live (same missing-deps/no-network constraint) |

## Known gaps

- services/ai's full pytest suite (85 tests, endpoint-level via TestClient) and
  `docker build`/CI workflow were not re-run here — no network in this sandbox to install
  fastapi/starlette/pydantic/httpx/river/pytest. The underlying logic was verified by direct
  execution against the real `app/core/*` modules (see table above), which gives strong
  confidence, but this is not a substitute for the real suite. **Action for Final
  Integrator/CI: run `pip install -r requirements-dev.txt && pytest -q` for real before sign-off.**
- services/voice's own test suite and live server were not run for the same reason (no network
  for fastapi/pydantic/pytest); route and schema shapes were verified by static read only.
- All of Claude 2's and Claude 6's own "honest limits" sections carry forward unchanged (FER/
  Wav2Vec2 models untrained, translations unverified beyond en, PWA background limits, etc.) —
  see each package/service's own HANDOFF.md, left in place at its original path.
- Real WebSocket `CoopTransport` and real connection between `VoiceClient` and a host-composed
  `StringTable` are not built here — both are app-layer (apps/patient-web, Claude 3) work, out
  of this integrator's scope. The types are contract-compatible and ready for that wiring.
- `Observation.cue_id` nullability (games' CCR-2) is unresolved by design — see CONTRACT
  DECISIONS above; needs a decision from whoever builds the real services/api → services/ai
  trigger-update call path.
