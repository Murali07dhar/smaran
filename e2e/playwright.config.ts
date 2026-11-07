import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Golden-path UI test. Needs: api :8000, ai :8001, voice :8002 (scripts/native-up.sh) and both Vite dev servers
// (started by webServer below, proxying /api and /ws to :8000). PW_CHROMIUM overrides the browser binary
// (useful when the installed Playwright and the preinstalled browser revisions differ).
function chromiumPath(): string | undefined {
  if (process.env.PW_CHROMIUM) return process.env.PW_CHROMIUM;
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !fs.existsSync(root)) return undefined;
  const dir = fs.readdirSync(root).find((d) => /^chromium-\d+$/.test(d));
  const bin = dir && path.join(root, dir, "chrome-linux64", "chrome");
  return bin && fs.existsSync(bin) ? bin : undefined;
}

export default defineConfig({
  testDir: ".",
  timeout: 180_000,
  workers: 1,
  reporter: [["list"]],
  use: { launchOptions: { executablePath: chromiumPath() }, serviceWorkers: "block", trace: "retain-on-failure" },
  webServer: [
    { command: "pnpm --filter @smaran/patient-web exec vite --port 5173", url: "http://localhost:5173", reuseExistingServer: true, cwd: ".." },
    { command: "pnpm --filter @smaran/caregiver-web exec vite --port 5174", url: "http://localhost:5174", reuseExistingServer: true, cwd: ".." }
  ]
});
