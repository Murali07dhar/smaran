# HANDOFF — Claude 3 of 6: Patient Web App (elder UI)

## What is built

A complete, compilable (pending `pnpm install`, not run here — see "Known
gaps") Vite + React + TypeScript PWA at `apps/patient-web`, plus the shared
packages I was asked to create:

- **apps/patient-web** — the elder-facing offline-first PWA end to end:
  login (PIN), home (Play/Reminders/Family/Help), game launcher, full-screen
  reminder alert, consent screens, family photo gallery, help screen, co-op
  join screen, quiet sync indicator, i18n (English + Assamese), Dexie-backed
  offline storage, a sync queue with retry/backoff, and a Playwright e2e test
  proving offline play → sync.
- **packages/design-tokens** — `tokens.json` (exact values from the
  briefing) + a Tailwind preset reading it, so web now and React Native later
  share one source of truth.
- **packages/sync-core** — framework-agnostic sync queue (push/pull against
  the SYNC CONTRACT, idempotent by `op_id`, exponential backoff with jitter,
  append-only-entity guard for GameSession/GameEvent/EmotionSample). Zero
  react/DOM imports.
- **packages/contracts** — hand-written stub of the TS types Claude 1 will
  generate from `openapi.json` (entities, sync, AI service, Game SDK, co-op
  WS), so this app and the placeholder `games`/`voice-i18n` packages
  typecheck today.
- **packages/games**, **packages/voice-i18n** — placeholder packages that
  re-export the mocks below, so `@smaran/games` / `@smaran/voice-i18n`
  resolve now and can be replaced wholesale by Claude 4 / Claude 6 at merge.
- **mocks/** — `games/mockGameModule.tsx` (one playable memory-card game),
  `voice-i18n/mockVoiceAPI.ts` + `mockReminderEngine.ts` (Web Speech API TTS,
  naive daily-RRULE due-check), `ai/mockEmotionModel.ts` (random plausible
  fused-emotion reading, same response shape as the real ONNX model will
  return), `api/handlers.ts` (MSW handlers for every network call this app
  makes).

## How to run

```sh
# from the monorepo root
pnpm install
cp apps/patient-web/.env.example apps/patient-web/.env
npx msw init apps/patient-web/public/ --save   # one-time, needs network (see Known gaps)
pnpm dev:patient                                # http://localhost:5173
```

Env vars (see `.env.example`): `VITE_API_BASE_URL`, `VITE_VOICE_BASE_URL`,
`VITE_WS_BASE_URL`, `VITE_USE_MOCKS` (keep `true` until `services/api` is
reachable), `VITE_EMOTION_MODEL_URL`.

Tests:
```sh
pnpm --filter @smaran/patient-web test:unit   # vitest, core/* pure logic
pnpm --filter @smaran/patient-web test:e2e    # playwright, offline→sync
```
CI: `.github/workflows/patient-web-ci.yml` runs install → MSW init →
typecheck → unit → build → e2e on every PR touching this app or its shared
packages.

## Endpoints / components exposed

- Screens (React Router): `/login`, `/home`, `/play`, `/reminders`,
  `/family`, `/help`, `/consent`, `/coop`.
- `@smaran/sync-core`'s `SyncQueue` — importable by any future screen that
  needs to enqueue a sync op.
- `src/adapters/types.ts` — the six adapter interfaces
  (Storage/Audio/Notification/Camera/Mic/File), implemented for web under
  `src/adapters/web/`.
- `src/core/**` — all business logic (auth, API client/endpoints, sync
  wiring, reminders, emotion capture, consent, game session lifecycle,
  co-op transport), importable with zero react/DOM dependency.

## Mocks used and what replaces them

| Mock | File | Replaced by |
|---|---|---|
| Game module | `mocks/games/mockGameModule.tsx` | Claude 4's real `packages/games` (5 domains, cue system, co-op UI) |
| VoiceAPI (TTS only, no ASR) | `mocks/voice-i18n/mockVoiceAPI.ts` | Claude 6's AI4Bharat-backed `services/voice` + `packages/voice-i18n` |
| Reminder engine (daily-only RRULE) | `mocks/voice-i18n/mockReminderEngine.ts` | Claude 6's full RRULE reminder engine |
| Emotion model (random, same response shape) | `mocks/ai/mockEmotionModel.ts` | Claude 2's ONNX model via onnxruntime-web, loaded from `VITE_EMOTION_MODEL_URL` |
| Every backend call | `mocks/api/handlers.ts` (MSW) | Claude 1's `services/api`, reachable at `VITE_API_BASE_URL` once `VITE_USE_MOCKS=false` |
| `packages/contracts` | hand-written | Claude 1's openapi-generated types |

Swapping a mock for the real thing should mostly mean deleting the
placeholder package contents and dropping in the real package — the import
paths (`@smaran/games`, `@smaran/voice-i18n`, `@smaran/contracts`) don't
change.

## Contract deviations / CONTRACT CHANGE REQUESTS

1. **Reminder ack has no endpoint in the shared contract.** I call
   `POST /api/v1/reminders/{id}/ack {status: "done"|"later"}` (see
   `mocks/api/handlers.ts` and `core/api/endpoints.ts::ackReminder`) and,
   offline, queue it as a last-write-wins `Reminder` upsert carrying two
   extra fields (`last_ack_status`, `last_ack_at`) plus a locally-computed
   `miss_count`. **Request:** Claude 1, please confirm this endpoint or tell
   me the real one so I can swap it in (`core/reminders/reminderState.ts`).
2. **`PatientProfile` has no `display_name`.** The Game SDK's `GameProps.
   patient.display_name` is left as `""` in `GameLauncher.tsx` since the
   CORE ENTITIES list doesn't give the patient app a name field to show.
   **Request:** either add `display_name` to `PatientProfile`, or confirm
   it's intentionally omitted (DPDP data minimization?) and the elder UI
   should stay nameless/generic.
3. **Consent fallback has no sync path.** `ConsentScreen.tsx` posts to
   `/consent` directly (not through the sync queue, since `ConsentRecord`
   isn't append-only and isn't in my local `ENTITY_TABLE` sync map either —
   it's DPDP-sensitive enough that I didn't want it silently retried/queued
   without confirmation). If offline, it's cached locally only and NOT
   queued for sync; the patient will need to be online once to register
   consent server-side. **Request:** confirm whether `ConsentRecord` should
   go through the generic sync queue like other entities, or if consent
   genuinely needs a synchronous online round-trip for compliance reasons.

## PORTABILITY NOTES (React Native readiness)

**Reusable as-is** (no react/DOM/window/document imports, pure TypeScript):
- `packages/sync-core` — entire package.
- `apps/patient-web/src/core/**` — api/client.ts & endpoints.ts (uses only
  global `fetch`), auth/pinAuth.ts & tokenStore.ts, sync/syncClient.ts &
  queueStorageAdapter.ts, reminders/reminderState.ts, emotion/
  emotionCapture.ts, validation/consent.ts, games/sessionLogic.ts, coop/
  coopTransport.ts (uses only the global `WebSocket`).
- `packages/design-tokens/tokens.json` + `index.js` (the Tailwind preset is
  web-only; a React Native app reads `tokens.json` directly or via a
  NativeWind-style preset).
- `packages/contracts` — all type definitions.

**Needs rewriting for React Native:**
- All of `apps/patient-web/src/components/**` — Tailwind/JSX-DOM markup
  throughout; React Native would rebuild these as native components
  consuming the same `core/*` hooks/functions and the same context shape
  (`AuthContext`/`SyncContext`/`PatientContext` logic is portable, only the
  `<div>`/`<button>` JSX inside isn't).
- `src/adapters/web/*` — every file here is the web implementation of a
  portable interface (`src/adapters/types.ts`); React Native needs its own
  implementations (SQLite instead of Dexie, `react-native-sound` instead of
  `HTMLAudioElement`, `react-native-push-notification` instead of the
  `Notification` API, `react-native-vision-camera` instead of
  `getUserMedia`, etc.) behind the exact same six interfaces.
- `src/i18n/i18n.ts` — `react-i18next` itself is RN-compatible, but the
  bootstrap/config may need adjusting for RN's module resolution.
- PWA-specific files (`vite.config.ts`'s `VitePWA` block, `public/icons`,
  the MSW browser worker) have no RN equivalent and should be dropped, not
  ported.

**Adapters defined** (`src/adapters/types.ts`): `StorageAdapter`,
`AudioAdapter`, `NotificationAdapter`, `CameraAdapter`, `MicAdapter`,
`FileAdapter`. Web implementations of all six are in `src/adapters/web/`,
composed into one `PlatformAdapters` object in `src/adapters/web/index.ts`.
A React Native build should only need a parallel `src/adapters/native/`
implementing the same interfaces and a different composition point — no
changes to `core/*` or component logic beyond swapping which adapters object
gets passed in.

## Known gaps

- **Nothing in this build was actually run.** The container has no network
  access, so `pnpm install` was never executed and nothing was typechecked,
  built, or tested in-session. Everything above is written to compile and
  pass based on careful review, but hasn't been machine-verified. Run the
  commands in "How to run" first.
- **MSW's service worker file doesn't exist yet** (`public/mockServiceWorker
  .js`) — needs `npx msw init apps/patient-web/public/ --save`, which needs
  network access this session didn't have. Until that's run, `VITE_USE_MOCKS
  =true` will fail to intercept requests. See `public/MSW_SETUP.md`.
- **PWA icons are vector-only.** `public/icons/icon.svg` exists;
  `icon-192.png` / `icon-512.png` / `icon-512-maskable.png` referenced by the
  manifest still need rasterizing (no image tool available in-session). See
  `public/icons/README.md`.
- **PWA background notification limits** (as required to state honestly):
  browsers only reliably fire notifications for an installed PWA with an
  active service worker, and even then OS-level background kill can prevent
  delivery (notably iOS Safari). `NotificationAdapter.schedule()` here is a
  foreground-only `setTimeout`-based best effort — the full-screen in-app
  `FullScreenReminderAlert` (driven by a once-a-minute due-check while the
  app is open) is the reliable path, not background push. True background
  delivery needs real web push (a service worker push handler + a push
  subscription registered with `services/api`), which isn't implemented.
- **No QR scanner UI.** `core/auth/pinAuth.ts::loginWithQr` exists and is
  wired into `AuthContext`, but `LoginScreen.tsx` only exposes the PIN pad —
  no camera-based QR scanning component yet.
- **Co-op isn't wired end-to-end.** `CoopJoinScreen.tsx` connects to
  `/ws/coop/{room_id}` and joins successfully (or shows an error), but the
  resulting `CoopTransport` isn't passed into `GameLauncher`/a coop-capable
  `GameModule` yet — the mock game module doesn't support co-op
  (`supports_coop: false`), so this is blocked on Claude 4's real game
  modules more than on anything in this app.
- **Translations are machine-assisted, not native-reviewed.** `src/i18n/
  locales/as.json` (Assamese) should get a native-speaker review pass before
  this ships to real users — flagging per the briefing's "be honest about
  limits" instruction rather than presenting it as verified.
- **Unverified translations generally**: only `en` and `as` are implemented;
  `bn`, `ne`, `brx`, `mni` locale files don't exist yet (voice-only `lus`,
  `kha`, `grt` are out of scope for this app's UI strings per the briefing).
- **Model bias**: the emotion capture pipeline is entirely mocked
  (`mocks/ai/mockEmotionModel.ts` returns a random label), so no real
  bias/accuracy characteristics exist yet to evaluate — this becomes
  relevant once Claude 2's real ONNX model is wired in.
- **Service worker precaching is default Workbox config** — works for the
  app shell/static assets (needed for the "play fully offline" golden path),
  but hasn't been tuned beyond the one `StaleWhileRevalidate` rule for
  `/api/v1/content`.
