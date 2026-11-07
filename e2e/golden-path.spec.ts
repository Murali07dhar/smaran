import { test, expect, type Page } from "@playwright/test";

const CG = "http://localhost:5174";
const PT = "http://localhost:5173";
const API = "http://localhost:8000/api/v1";
// Valid 1x1 PNG (the API re-encodes images with Pillow and strips metadata).
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function playToEnd(page: Page) {
  for (let i = 0; i < 40; i++) {
    if (await page.getByText("Well done").or(page.getByTestId("game-done")).first().isVisible().catch(() => false)) return;
    const cards = page.locator('[data-testid="game-root"] button').filter({ hasText: "✦" });
    const n = await cards.count();
    if (!n) return;
    await cards.nth(0).click();
    await page.waitForTimeout(150);
    if (n > 1) await cards.nth(1).click().catch(() => undefined);
    await page.waitForTimeout(900);
  }
}

test("golden path: caregiver -> patient offline play -> sync -> AI -> dashboard", async ({ browser }) => {
  // ---------------- caregiver (seeded demo account)
  const cgCtx = await browser.newContext();
  const cg = await cgCtx.newPage();
  await cg.goto(CG);
  await cg.getByTestId("user").fill("caregiver@smaran.demo");
  await cg.getByLabel(/pass/i).fill("Smaran-Demo-123");
  await cg.getByTestId("login").click();
  const name = `E2E ${Date.now()}`;
  await cg.getByLabel("Name", { exact: true }).fill(name);
  await cg.getByLabel("Age", { exact: true }).fill("75");
  await cg.getByTestId("addpat").click();
  const pinText = await cg.getByTestId("pin").innerText();
  const pin = pinText.match(/\d{6}/)![0];
  await cg.getByRole("button", { name: new RegExp(name) }).click();
  await cg.getByTestId("photo").setInputFiles({ name: "wedding.png", mimeType: "image/png", buffer: PNG });
  await expect(cg.getByTestId("media").first()).toContainText("photo");
  await cg.getByTestId("rtitle").fill("Morning tablet");
  await cg.getByTestId("addrem").click();
  await expect(cg.getByTestId("rem").filter({ hasText: "Morning tablet" })).toBeVisible();

  // ---------------- patient: PIN login online, cache media, then go offline
  const ptCtx = await browser.newContext();
  const pt = await ptCtx.newPage();
  await pt.goto(PT);
  for (const d of pin) await pt.getByRole("button", { name: d, exact: true }).click();
  await pt.getByRole("button", { name: "Continue" }).click();
  await pt.waitForURL("**/home");
  await pt.getByText("Family").click();
  await expect(pt.locator("main img").first()).toBeVisible({ timeout: 20_000 }); // photo downloaded + cached locally
  await pt.getByRole("button").last().click(); // back to /home (SPA route; no network)
  await ptCtx.setOffline(true);
  await pt.getByText("Play").click();
  await expect(pt.getByTestId("game-root")).toBeVisible();
  await playToEnd(pt); // plays the real @smaran/games memory game with the caregiver photo as cue source, offline

  // ---------------- back online: sync -> API -> real AI
  await ptCtx.setOffline(false);
  await pt.evaluate(() => window.dispatchEvent(new Event("online")));
  const login = await (await cgCtx.request.post(`${API}/auth/login`, { data: { email: "caregiver@smaran.demo", password: "Smaran-Demo-123" } })).json();
  const auth = { Authorization: `Bearer ${login.access_token}` };
  const list = await (await cgCtx.request.get(`${API}/patients`, { headers: auth })).json();
  const pid = list.find((p: { name: string }) => p.name === name).id;
  await expect
    .poll(async () => {
      const t = await (await cgCtx.request.get(`${API}/patients/${pid}/dashboard/trends?days=30`, { headers: auth })).json();
      return t.days.reduce((a: number, d: { sessions: number }) => a + d.sessions, 0);
    }, { timeout: 60_000, intervals: [2000] })
    .toBeGreaterThanOrEqual(1);
  const cc = await (await cgCtx.request.get(`${API}/patients/${pid}/dashboard/cue-comparison`, { headers: auth })).json();
  expect(cc.with_cue.n).toBeGreaterThan(0); // the caregiver photo was used as a cue while offline
  await expect
    .poll(async () => (await (await cgCtx.request.get(`${API}/patients/${pid}/dashboard/triggers`, { headers: auth })).json()).length, { timeout: 30_000, intervals: [2000] })
    .toBeGreaterThanOrEqual(1); // real AI produced a memory trigger
  const trig = await (await cgCtx.request.get(`${API}/patients/${pid}/dashboard/triggers`, { headers: auth })).json();
  expect(trig.some((t: { cue_id: string }) => t.cue_id.startsWith("no_cue:"))).toBe(false); // D2
  const sev = await (await cgCtx.request.get(`${API}/patients/${pid}/dashboard/severity`, { headers: auth })).json();
  expect(sev.disclaimer).toBeTruthy();

  // ---------------- dashboard shows the patient, trend + disclaimer
  await cg.reload();
  await cg.getByTestId("user").fill("caregiver@smaran.demo");
  await cg.getByLabel(/pass/i).fill("Smaran-Demo-123");
  await cg.getByTestId("login").click();
  await cg.getByRole("button", { name: new RegExp(name) }).click();
  await expect(cg.getByTestId("disclaimer").first()).toBeVisible();
  await expect(cg.getByTestId("trigger").first()).toBeVisible();
});
