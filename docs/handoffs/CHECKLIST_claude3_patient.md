# SMARAN — Claude 3 (patient-web) build checklist

## Done
- [x] Monorepo root: package.json, pnpm-workspace.yaml
- [x] packages/design-tokens (tokens.json, tailwind preset, index.js/d.ts)
- [x] packages/contracts (stub types: entities, sync, ai, gameSdk, coop) + README flagging it as Claude 1's real job
- [x] packages/sync-core (types, conflictRules, backoff, SyncQueue) — framework-agnostic
- [x] packages/games, packages/voice-i18n — placeholder packages re-exporting mocks
- [x] mocks/games/mockGameModule.tsx
- [x] mocks/voice-i18n/mockVoiceAPI.ts, mockReminderEngine.ts
- [x] mocks/ai/mockEmotionModel.ts
- [x] mocks/api/handlers.ts (MSW, every API call)
- [x] apps/patient-web config: package.json, tsconfig(.node), vite.config.ts (PWA/Workbox), tailwind/postcss config, index.html, .env.example
- [x] public/icons/icon.svg + README (PNG generation noted as known gap)
- [x] src/adapters/types.ts (Storage/Audio/Notification/Camera/Mic/File interfaces)
- [x] src/adapters/web/db.ts (Dexie schema)
- [x] src/adapters/web/StorageAdapter.ts
- [x] src/adapters/web/AudioAdapter.ts
- [x] src/adapters/web/NotificationAdapter.ts
- [x] src/adapters/web/CameraAdapter.ts

## Remaining (priority order)
### P1 — golden path
- [x] src/adapters/web/MicAdapter.ts
- [x] src/adapters/web/FileAdapter.ts
- [x] src/adapters/web/index.ts (PlatformAdapters composition)
- [x] src/core/api/client.ts (bearer-token fetch client)
- [x] src/core/api/endpoints.ts (login, reminders, content, sync push/pull)
- [x] src/core/auth/pinAuth.ts + tokenStore.ts
- [x] src/core/sync/queueStorageAdapter.ts + syncClient.ts (wires sync-core to adapters)
- [x] src/core/reminders/reminderState.ts
- [x] src/core/emotion/emotionCapture.ts
- [x] src/core/validation/consent.ts
- [x] src/core/games/sessionLogic.ts
- [x] src/mocks/browser.ts (MSW setup, VITE_USE_MOCKS gate) + public/MSW_SETUP.md note
- [x] src/i18n/i18n.ts + locales/en.json, as.json
- [x] src/state/services.ts, AuthContext.tsx, SyncContext.tsx, PatientContext.tsx
- [x] src/components/BigButton.tsx (56px+ touch target primitive)
- [x] src/components/LoginScreen.tsx (PIN; QR login wired in core/auth, no scanner UI yet — see HANDOFF known gaps)
- [x] src/components/HomeScreen.tsx (Play/Reminders/Family/Help)
- [x] src/components/GameLauncher.tsx
- [x] src/components/RemindersScreen.tsx + FullScreenReminderAlert.tsx
- [x] src/components/ConsentScreen.tsx
- [x] src/components/SyncIndicator.tsx
- [x] src/routes/router.tsx
- [x] src/App.tsx, src/main.tsx, src/styles/index.css, src/vite-env.d.ts
- [x] Playwright: tests/e2e/offline-sync.spec.ts + playwright.config.ts

### P2 — remaining features
- [x] FamilyScreen.tsx, HelpScreen.tsx
- [x] CoopJoinScreen.tsx (join by code/QR) + src/core/coop/coopTransport.ts — connects and joins a room; not yet wired into GameLauncher's `coop` prop (see HANDOFF known gaps)
- [ ] Service worker background sync registration polish (beyond Workbox precache defaults)
- [x] Accessibility pass: aria labels/roles on inputs, buttons, alert dialog; reduced-motion CSS; focus-visible outline

### P3 — tests, CI, docs
- [x] Unit tests for core/* (vitest): pinAuth, conflictRules, backoff, reminderState
- [x] GitHub Actions workflow (.github/workflows/patient-web-ci.yml)
- [x] HANDOFF.md

## Not started (out of scope for this session or lower priority)
- [ ] QR scanner UI for login (camera-based) — pinAuth.loginWithQr exists but no scanning component
- [ ] Wiring CoopTransport into GameLauncher for an actual co-op game session
- [ ] Web push subscription flow (NotificationAdapter.schedule is foreground-only setTimeout)
- [ ] Generating public/icons/*.png from icon.svg (needs a rasterizer, no network in-session)
- [ ] Running public/MSW_SETUP.md's `npx msw init` (needs network, not run in-session)
- [ ] pnpm install / actually running the dev server, typecheck, or tests (no network/package registry access in this container)
