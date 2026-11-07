Before `pnpm dev` with `VITE_USE_MOCKS=true`, generate MSW's browser worker
script once (requires network, not run in this session):

```sh
npx msw init public/ --save
```

This drops `public/mockServiceWorker.js`, which `src/mocks/browser.ts`
registers automatically. Delete this file once that's been done. Listed as a
known gap in HANDOFF.md.
