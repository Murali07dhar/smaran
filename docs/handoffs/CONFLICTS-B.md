# CONFLICTS.md — Integrator B (services + packages)

Scope: services/ai, services/voice, packages/games, packages/content, packages/voice-i18n.
None of the items below change a DATABASE SCHEMA or ROUTES shape, so per working rules I
continued rather than stopping to ask. CONTRACT DECISIONS section at the bottom is what the
Final Integrator needs to reconcile against the other integrators (backend, apps).

## 1. Conflicts found between the three HANDOFFs, and resolution

### 1.1 VoiceAPI.listen() shape mismatch (games vs voice-i18n) — FIXED
- games/src/types.ts declared `listen(opts?: {locale?: string; expected_intents?: string[]})
  -> {transcript, intent: string|null}` (opts optional, unused `expected_intents` field,
  loose `intent` type).
- voice-i18n/core/types.ts (the canonical owner per MONOREPO LAYOUT: "packages/voice-i18n/core
  ... VoiceAPI types (Claude 6)") declares `listen(opts: ListenOpts) -> ListenResult` where
  `ListenOpts = {locale: AnyLocale; maxMs?: number}` and `ListenResult = {transcript: string;
  intent: Intent}` (`Intent` a closed union: yes/no/next/repeat/help/done/unknown).
- Resolution: module owner wins (voice-i18n/Claude 6). Patched packages/games/src/types.ts to
  mirror the real shape exactly (structural duplicate, not an import, to avoid a build-time
  dependency from games -> voice-i18n), and fixed src/mocks/voice.ts's `listen()` to accept
  the now-required `opts` and return `intent: 'unknown'`. No call sites existed yet (the games
  UI never wires voice input), so this was a type-only fix. Reran games tests: 47/47 still
  pass after the change.

### 1.2 CCR-4 (games HANDOFF): "All games.* keys must exist in voice-i18n"
- games keeps its own self-contained i18n table (packages/games/src/i18n/strings.ts, 105
  `games.*` keys, en+as, its own test enforces en/as key parity and that every literal
  `games.*` key used in src resolves).
- voice-i18n's own locale files (packages/voice-i18n/src/locales/{en,as,bn,ne,brx,mni}.json)
  are a *different*, app-chrome-focused namespace (app/common/greeting/voice/reminder/
  family/language/disclaimer) used by react-i18next. Zero `games.*` keys exist there, and
  zero collisions exist either way (checked both directions).
- VoiceClient.speak(keyOrText, locale) resolves `keyOrText` via an **injected**
  `StringTable { t(key, locale) }` (VoiceClientDeps.strings), not a hardwired import of
  voice-i18n's own locale JSON. So the literal requirement in CCR-4 is satisfiable, but only
  by whoever constructs the VoiceClient for the running app: they must pass a StringTable that
  composes voice-i18n's i18next table with games' `strings.en/as` table (e.g. by trying games'
  `t()` first, falling back to i18next). That composition is apps/patient-web's job (Claude 3),
  not something that lives inside either package I own. See CONTRACT DECISIONS below.

### 1.3 CoopTransport / WebSocket shape — verified compatible, no fix needed
- games/src/types.ts: `CoopMessage {type, seq: number, payload}` (incoming, server-authoritative
  seq, required) and `CoopOutgoing {type, payload, seq?}` (outgoing, seq optional) — this matches
  the CO-OP WEBSOCKET contract (`{type, seq, payload}`, "Server is authoritative on seq") exactly.
- Only the in-memory mock bus (`createCoopBus`) exists; no real `WebSocket` CoopTransport
  implementation ships in packages/games, which is correct and expected — CCR-3 in the games
  HANDOFF already documents the assumed message payloads (join/leave/state_patch/hint/encourage)
  for whoever builds the real `/ws/coop/{room_id}` client (1.4's server + the app layer).

### 1.4 games tests/i18n.test.mjs and overall games suite
- Confirmed to exist and pass: 47/47 (`tsc -p tsconfig.logic.json` clean, `node --test
  tests/*.test.mjs`), matching Claude 4's HANDOFF claim exactly, both before and after the
  VoiceAPI fix in 1.1.

## 2. CONTRACT CHANGE REQUESTS carried over from the three HANDOFFs (not resolved by me —
   these require a contract edit or a decision beyond my scope; proceeding on each builder's
   labelled assumption as instructed)

From games (Claude 4): CCR-1 (ContentItem/Cue shapes not in openapi), CCR-2 (Observation.cue_id
nullable for without-cue trials — services/ai's `Observation` schema currently requires
`cue_id: str` non-null; this is a real mismatch, see CONTRACT DECISIONS), CCR-3 (co-op payload
shapes), CCR-5 (10th game `routine_next`, already reflected in the registry).

From AI engine (Claude 2): CCR-AI-1 (severity `samples` — present in schemas.py as documented),
CCR-AI-2 (`/ai/emotion/analyze`, not mounted), CCR-AI-3 (`data_sufficient`/structured `drivers`
— not present; `drivers: list[str]` only, as today's contract specifies), CCR-AI-4 (`session_id`
+ per-item `difficulty`/`ts` in `recent` — not present; `RecentItem` only has
`correct/response_ms/hints` today), CCR-AI-5 (Baseline shape — implemented exactly as the
HANDOFF's proposed shape; schemas.py `Baseline` has `extra="allow"` so additive fields are safe).

From voice (Claude 6): voice routes under `/voice/*` not `/api/v1/voice/*` (as documented;
gateway must proxy or contract must be amended), Alert-from-reminder-escalation via
`/sync/push` (unconfirmed, owned by 1.4, out of my scope), `listen(opts)` takes
`{locale, maxMs?}` (now also what games expects, per 1.1 above), `AnyLocale` adds lus/kha/grt.

## 3. CONTRACT DECISIONS (for the Final Integrator to reconcile with the backend/app integrators)

1. **Observation.cue_id nullability (CCR-2).** services/ai's `Observation` Pydantic schema
   requires `cue_id: str` (min_length=1). The games HANDOFF's `toObservations()` emits
   `cue_id: null` for without-cue trials. As written, posting a without-cue observation from
   the real pipeline to `/ai/triggers/update` will fail schema validation. Someone must either
   (a) relax `Observation.cue_id` to `str | None` in services/ai/app/schemas.py (my scope, but
   I did not make this edit myself since it changes a contract-adjacent schema and the working
   rules say not to change shared contracts unilaterally — flagging instead), or (b) have the
   caller (services/api 1.5 insights pipeline, which calls `/ai/triggers/update`) always
   synthesize a stand-in cue_id for without-cue trials matching `cue.item_id` per CCR-2's own
   fallback note ("or the item-linked cue when cue.item_id matches"). Recommend (b) to avoid
   touching services/ai's contract.
2. **StringTable composition (games.* + voice-i18n locales).** Whoever constructs the
   `VoiceClient` for the running app (apps/patient-web, Claude 3 / its integrator) must compose
   a `StringTable` from both packages/games's `strings.en/as` (via its exported `t()`/`strings`)
   and voice-i18n's i18next instance, so that `voice.speak('games.praise.1', locale)` resolves
   correctly. Neither package can do this alone without creating a cross-package runtime
   dependency, which the portability rules disallow (games has no business importing
   voice-i18n or vice versa).
3. **services/voice route prefix.** Routes are `/voice/*` (no `/api/v1`), same as flagged in
   the voice HANDOFF. Needs either a contract amendment or an API-gateway proxy rule
   (`/api/v1/voice/* -> /voice/*`) from whoever owns the gateway/BFF layer.
4. **services/ai live endpoint test coverage.** This sandbox has no network and could not
   install fastapi/starlette/pydantic/httpx/river/pytest, so the documented "85 pytest tests
   pass" could not be independently re-run end-to-end here. I instead built throwaway offline
   stand-ins (`services/ai/.offline-stubs/`, NOT part of the deliverable — see
   INTEGRATION_HANDOFF.md) and exercised the real `app/core/*` logic directly (bypassing
   FastAPI's TestClient layer), confirming the trigger-decay math, severity disclaimer-always
   guarantee, and difficulty adaptation all behave as documented, including running the actual
   `scripts/demo_trigger_decay.py` to completion. The Final Integrator (or CI, which will have
   network) should rerun the real `pytest` suite before merge sign-off.

## 4. Mocks currently in place (per package) and what replaces them

- games: `createMockVoice` -> real `VoiceClient` from `@smaran/voice-i18n` (type-compatible as
  of the fix in 1.1); `mockCues` -> caregiver-upload-derived cues; `createCoopBus` -> real
  WebSocket CoopTransport against `/ws/coop/{room_id}` (not built in my scope); `demo_photos.json`
  -> caregiver `ContentItem{source:'caregiver'}`.
- services/ai: `scripts/mock_client.py` -> replaced once services/api calls `/ai/*` for real
  with the bearer token.
- voice-i18n / services/voice: `mocks/voice/server.mjs` (canned ASR transcripts, beep WAV)
  -> replaced by the real `services/voice` (already present in this merge; the mock remains
  useful for apps/patient-web local dev without the Python service running).
