# CONFLICTS (Integrator C: Apps)
Rule: DATABASE SCHEMA > ROUTES > signatures. Fix handlers/clients, never the contract. Status: OPEN / FIXED / DECISION.

## Patient web (Claude 3)
| # | Conflict | Resolution | Status |
|---|---|---|---|
| P1 | `/auth/pin-login` | -> `POST /auth/patient-pin-login {pin\|qr_token}` -> `{access_token,refresh_token,token_type,user{id,role,name,language}}` | FIXED |
| P2 | `POST /consent` | -> `GET/POST /patients/{id}/consents {kind,granted}`; ConsentRecord stub shape (camera/mic/data_sharing columns) wrong vs schema | FIXED |
| P3 | `GET /reminders?patient_id=` | -> `GET /patients/{id}/reminders`; field `schedule` -> `schedule_rrule` | FIXED |
| P4 | CCR1 reminder ack endpoint | Not needed: ack = append-only `reminder_events` op via `/sync/push` (schema has the table) | FIXED |
| P5 | `GET /content` not in ROUTES | No server route exists; content is packages/content (Claude 4). Mock kept, flagged in CONTRACT DECISIONS | DECISION |
| P6 | Entity names PascalCase | wire names = schema tables: game_sessions, game_events, emotion_samples, reminder_events (push); reminders, routines, media_assets, memory_triggers, alerts (pull) | FIXED |
| P7 | IDs/op_ids via crypto.randomUUID (v4) | contract says UUIDv7 -> `uuid7()` in sync-core | FIXED |
| P8 | `packages/contracts` stub fields differ from schema (Reminder.schedule, ConsentRecord, GameSession.locale/no domain/device_id, PatientProfile.id, User.display_name...) | align stub to schema; real openapi types replace it later | FIXED |
| P9 | CCR2 no display_name | `user.name` from login response / `GET /patients/{id}` `name` is the source | FIXED |
| P10 | CCR3 consent not in sync | Agree: consent is online-only (not in push list). Offline fallback must NOT count as granted | FIXED |
| P11 | `server_cursor` typed string | server cursor is BIGSERIAL; accept number or string | FIXED |

## Caregiver web (Claude 5)
| # | Conflict | Resolution | Status |
|---|---|---|---|
| C1 | `POST /auth/token` (form) | -> `POST /auth/login {email\|phone,password}` JSON; role+user_id come from `user{}` (CCR1 resolved) | FIXED |
| C2 | Whole data layer on sync push/pull with assumed shapes (PatientProfile.band, GameSession.date/score, Alert.text/acknowledged, MemoryTrigger.cue...) | Rewrite api layer to ROUTES: GET /patients, GET /alerts, POST /alerts/{id}/ack, dashboard/{trends,cue-comparison,triggers,severity}, report.csv; caregiver never pushes via sync | FIXED |
| C3 | Media: metadata-only push (CCR3) | `POST /media` multipart {patient_id,kind,file,tags}; list `GET /patients/{id}/media` | FIXED |
| C4 | Reminders/routines pushed via sync | `/patients/{id}/reminders` and `/routines` CRUD; `schedule_rrule` | FIXED |
| C5 | Co-op room client-side only (CCR4) | `POST /coop/rooms {patient_id,game_id}` -> `{room_id,join_code,expires_at}` | FIXED |
| C6 | Consent via sync push (CCR5) | `GET/POST /patients/{id}/consents` | FIXED |
| C7 | Local tokens.json | removed; shared `@smaran/design-tokens` preset | FIXED |
| C8 | Disclaimer next to severity | must render `disclaimer` from `/dashboard/severity` response | FIXED |
| C9 | Add patient / PIN+QR | `POST /patients`, `POST /patients/{id}/pin` (not built by C5) | FIXED |

## Mocks in play
MSW per app (patient: mocks/api/handlers.ts; caregiver: src/mocks/handlers.ts). Stubs: @smaran/games, @smaran/voice-i18n (re-export mocks/), @smaran/contracts (hand stub). Real ones: Integrator B / Claude 1.

## New decisions / open requests (for Integrator A/B)
- D1 No route for caregiver confirm/override of emotion samples or triggers (`emotion_samples.caregiver_confirmed` is append-only/device-pushed). Confirm/Reject buttons removed from dashboard; REQUEST: `POST /emotion-samples/{id}/confirm`.
- D2 `/coop/rooms` needs a real `game_id`; dashboard sends placeholder `memory-match` until @smaran/games lists ids.
- D3 health_worker is view-only for consent (DPDP: guardian grants). Not stated in contract; confirm.
- D4 Patient `GET /content` has no route; mock-only (see P5).
- D5 `score` = % correct 0-100 from SessionSummary (patient). Dashboard treats avg_score as server-provided.
- D6 Caregiver caches last GET responses (incl. PII) in localStorage unencrypted for offline read; needs encrypted storage before real data.
