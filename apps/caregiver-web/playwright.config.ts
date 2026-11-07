import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Mock-backed UI specs (MSW): runs on its own port with VITE_USE_MOCKS=true so the real API is NOT used.
// The real-API golden path lives in /e2e (repo root).
const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
const dir = root && fs.existsSync(root) ? fs.readdirSync(root).find((d) => /^chromium-\d+$/.test(d)) : undefined;
const bin = process.env.PW_CHROMIUM ?? (dir ? path.join(root!, dir, "chrome-linux64", "chrome") : undefined);

export default defineConfig({
  testDir: "e2e",
  use: { baseURL: "http://localhost:5184", launchOptions: { executablePath: bin && fs.existsSync(bin) ? bin : undefined } },
  webServer: { command: "VITE_USE_MOCKS=true pnpm exec vite --port 5184", url: "http://localhost:5184", reuseExistingServer: false }
});
