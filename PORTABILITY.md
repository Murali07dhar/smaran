# PORTABILITY.md — path to the React Native (entry-level Android) app

Backends (`services/api`, `services/ai`, `services/voice`) are permanent and serve the native app unchanged: bearer-token auth, versioned `/api/v1`, JSON only, no cookies.

## Reusable as-is (framework-agnostic TypeScript, no react/DOM/window imports)
| Area | Path |
|---|---|
| Contracts (generated OpenAPI types + hand-written domain/wire/AI/sync rules) | `packages/contracts` |
| Sync queue, backoff, conflict rules, UUIDv7 | `packages/sync-core` |
| Design tokens (JSON + Tailwind preset; RN reads `tokens.json`) | `packages/design-tokens` |
| Game rules, scoring, cue randomisation, difficulty, co-op protocol/state, string tables | `packages/games/src/{logic,coop,i18n,types.ts,sdk.ts}` |
| Content packs + validator | `packages/content` |
| Reminder engine (RRULE, snooze, escalation), scheduler glue, VoiceClient, intents, voice packs, family audio, AES-GCM `Cipher` interface | `packages/voice-i18n/core` |
| Patient app logic | `apps/patient-web/src/core/**` (API client, auth/PIN, session + event recording, reminder state, media cache, game inputs, co-op transport, emotion capture gate, consent rules) |
| Caregiver app logic | `apps/caregiver-web/src/core/*` |

## Needs rewriting for React Native
- All `components/**` and screens (patient), `App/Panels/Content/Coop/Login/Plot` (caregiver; Plotly has no RN equivalent: use victory-native / skia).
- `packages/games/src/ui/**` (React DOM views → RN views; keep `GameShell` contract: `GameProps`).
- `apps/*/src/adapters/web/*`, Dexie `db.ts`, VitePWA/Workbox, `public/` icons, MSW browser workers, `vite.config.ts` proxies (RN needs an absolute API base URL; `VITE_API_BASE_URL` → app config).
- `packages/voice-i18n/src/adapters/web/*` (Web Speech, MediaRecorder, WebCrypto, IndexedDB).
- Content assets are served at `/assets/*` by a Vite plugin; RN needs bundled assets and `setAssetBase`/`assetUrl` replaced by a resolver (the module is documented as the swap point).

## Adapter interfaces (implement natively)
Patient app (`apps/patient-web/src/adapters/types.ts`): `StorageAdapter` (Dexie → SQLite/WatermelonDB/MMKV), `AudioAdapter`, `NotificationAdapter` (→ Notifee/WorkManager: **real background reminders are possible on native, unlike the PWA**), `CameraAdapter`, `MicAdapter`, `FileAdapter` (now includes `url(path)`; → `file://`).
Voice (`packages/voice-i18n/core/types.ts`): `AudioAdapter`, `MicAdapter`, `NotificationAdapter`, `KeyValueAdapter`, `FileAdapter`, `Cipher`, `BrowserSTTAdapter` (→ on-device ASR or always call services/voice).
Games: `AudioAdapter` via `setAudioAdapter`.
**Unify before RN:** the caregiver app has its own small adapters (`get/set storage`, `FileAdapter`, `MicAdapter`) that are not the patient app's six-interface set.

## Things that will bite
1. `import.meta.env`, `navigator.onLine`, `URL.createObjectURL`, `window.location` appear only in adapters/launchers (`GameLauncher`, `adapters/web/voice.ts`, `mediaCache` uses `fetch` + adapters). Replace `navigator.onLine` with NetInfo.
2. The reminder engine state is in memory; persist it through `KeyValueAdapter` (it is plain JSON) and drive `tick(now)` from a background task.
3. Mic gating: `createVoice({micAllowed})` hands `MicAdapter`/STT to `VoiceClient` only after a recorded `mic` consent. Keep that rule.
4. Co-op uses the global `WebSocket` (present in RN); the ws token comes from `POST /coop/rooms/join`.
5. Media: signed URLs are relative; native must prefix an absolute origin (`absoluteUrl` in `core/media/mediaCache.ts`).
6. IDs are client-generated UUIDv7 (`uuid7` in sync-core); dates ISO-8601 UTC; JSON snake_case. Regenerate types with `services/api/scripts/gen_contracts.sh` after any API change.
