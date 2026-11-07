# INTEGRATION_STATE: Integrator C (Apps)

**Scope:** apps/patient-web (Claude 3) + apps/caregiver-web (Claude 5), merged with shared packages.
**Status:** static integration complete; runtime verification pending (sandbox had no network or pnpm).
**Priority rule:** DATABASE SCHEMA > ROUTES > signatures. Fix clients and handlers, never the contract.

## Steps
| Step | Status |
|---|---|
| 1. Read handoffs, merge zips, drop duplicate root/env/checklist files | Done (no overlapping files; per-app HANDOFF/CHECKLIST moved to docs/handoffs/) |
| 2. Remove caregiver local tokens.json, use shared design-tokens | Done |
| 3. Align routes, entity names, shapes (patient) | Done |
| 4. Align caregiver data layer to REST routes | Done |
| 5. Sync-core rules (push list, append-only, UUIDv7, cursor) | Done |
| 6. Patient UI audit (56px targets, 20px base, calm copy) | Partial: grep-level only |
| 7. Run build, lint, unit, e2e | **Not run** |
| 8. Zip + INTEGRATION_HANDOFF.md | Done |

## Conflicts (short list; full table in CONFLICTS.md)
- FIXED: patient login/consent/reminders routes; reminder ack as `reminder_events` op; PascalCase entity names -> snake_case; UUIDv4 -> UUIDv7; contracts stub fields -> schema; cursor number|string.
- FIXED: caregiver `/auth/token` -> `/auth/login`; sync push/pull data layer -> REST; media -> `POST /media`; co-op room -> `POST /coop/rooms`; consent -> `/patients/{id}/consents`; local tokens.json removed.
- DECISION: `/content` has no route (mock only); session score = % correct 0-100; health_worker view-only for consent.
- REQUEST: route for caregiver confirm/override of emotion samples/triggers (buttons removed); real `game_id` list for co-op rooms.
- RISK: caregiver caches PII unencrypted in localStorage.

## Verified
- 20 unit tests pass (patient core, sync-core, caregiver api) under a vitest stand-in, not real vitest.
- Pure-TS core typechecks; both apps bundle with esbuild.

## Not verified
- pnpm install, `tsc -b` on .tsx (no React types offline), vite build, real vitest, Playwright e2e (patient + caregiver), lint (not configured).
- Possible leftover: FamilyScreen vs new MediaAsset fields.

## Next
1. `pnpm install && npx msw init apps/patient-web/public/ --save`
2. `pnpm typecheck && pnpm test:unit && pnpm test:e2e`; fix one failure at a time.
3. Wire emotion capture into a component (gate exists, unused).
4. Replace stubs (`@smaran/contracts`, `games`, `voice-i18n`) with Claude 1/4/6 packages.
5. Native-speaker review of Assamese strings.
