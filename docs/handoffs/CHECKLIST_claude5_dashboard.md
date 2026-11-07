# Checklist (apps/caregiver-web)
## Done
- [x] Scaffold, tokens.json, .env.example, VITE_API_BASE_URL switch
- [x] Auth login, role-aware patient list sorted by alert priority
- [x] Patient detail: cognitive trend (Plotly), disclaimer
- [x] Photo upload -> reminder builder (RRULE, per-reminder locale)
- [x] MSW handlers (auth, sync pull/push), seeded 30 days, 3 patients
- [x] Offline read cache, i18n en+as (core keys), Playwright golden test
- [x] Alerts inbox ack+note, 3 extra charts, GDS band, emotion-memory profile confirm/reject, co-op room + code + QR
- [x] Consent toggles (gate mic), voice recording, routines builder, CSV export + print-to-PDF
- [x] Tailwind preset from tokens.json, tsconfig, adapter interfaces + web impl, CI workflow, i18n keys for panels (as falls back to en)
- [x] Login split out; Content uses mic/file adapters; as translations added (unreviewed)
- [x] api.ts cache uses injected storage adapter
- [x] Fixed Plotly import (factory + basic dist), qrcode types, msw postinstall; Coop split out; alert-ack e2e test
## Remaining
- [ ] Run install/build/e2e (never executed); real-API run; native-speaker review of as strings
