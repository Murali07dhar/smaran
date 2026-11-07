# INTEGRATION_HANDOFF: Integrator C (patient-web + caregiver-web)

## Run (needs network once)
pnpm install && npx msw init apps/patient-web/public/ --save
pnpm dev:patient (5173) | pnpm dev:caregiver (5174; mocks on when VITE_API_BASE_URL is empty)
pnpm typecheck && pnpm test:unit && pnpm test:e2e   # NONE of these were run in the sandbox

## Changed
- Both apps use shared packages/design-tokens (caregiver's local tokens.json deleted).
- Routes/entities/shapes aligned to ROUTES + SCHEMA (see CONFLICTS.md). Sync: devices push only game_sessions, game_events, emotion_samples, reminder_events; enforced in sync-core. IDs are UUIDv7 (`uuid7` in sync-core).
- Patient: ack = reminder_events op; consent online-only per kind, default off; display name from login `user.name`.
- Caregiver: data layer rewritten from sync-push to REST (api.ts, App, Panels, Content, Coop, handlers). Charts use /dashboard/* shapes; severity disclaimer comes from the response.

## CONTRACT DECISIONS / REQUESTS: CONFLICTS.md (P5, D1-D6)

## Portability (React Native)
Reusable: packages/sync-core, patient-web src/core/**, caregiver src/core/*, design-tokens/tokens.json, contracts.
Web-only (rewrite/drop): all components/**, caregiver App/Panels/Content/Coop/Login/Plot (Plotly), src/adapters/web/*, Dexie db.ts, VitePWA + public/icons, MSW browser workers, caregiver localStorage cache. Caregiver adapters (get/set storage, FileAdapter, MicAdapter) are not the patient app's six-interface set; unify before RN.

## Known gaps
- Unrun: install/build/e2e/vitest/lint (no eslint configured). Real vitest never ran; a shim did.
- .tsx files not type-checked (no React types offline). Possible leftovers: FamilyScreen vs new MediaAsset fields.
- Emotion capture is not called by any patient component (consent gate exists, unused).
- Patient QR login UI, real web push, co-op wiring, PWA PNG icons still missing (unchanged from Claude 3).
- Caregiver: no PDF generation (browser print), photo/audio bytes now go to POST /media but untested against real server; Assamese strings in both apps unverified by a native speaker; caregiver Tailwind not used in markup.
- Patient UI audit was grep-level only (56px target via min-h-touch, 20px base, removed text-sm, softened sync error copy); no timers or failure messaging found in game code, but the mock game is the only one checked.
