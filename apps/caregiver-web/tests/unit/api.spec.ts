import { describe, expect, it } from "vitest";
import { login, listAlerts, ackAlert, uploadMedia, setConsent, createRoom } from "../../src/core/api";

type Call = { url: string; init: any };
const calls: Call[] = [];
(globalThis as any).fetch = async (url: string, init: any = {}) => {
  calls.push({ url, init });
  const body = url.endsWith("/auth/login") ? { access_token: "tok", refresh_token: "r", token_type: "bearer", user: { id: "u", role: "caregiver", name: "N", language: "en" } } : [];
  return { ok: true, status: 200, json: async () => body, text: async () => "" };
};
const last = () => calls[calls.length - 1];

describe("caregiver REST client matches ROUTES", () => {
  it("logs in via POST /auth/login with email|phone JSON and sends bearer after", async () => {
    const r = await login("a@b.in", "pw");
    expect(last().url).toBe("/api/v1/auth/login");
    expect(JSON.parse(last().init.body)).toEqual({ email: "a@b.in", password: "pw" });
    expect(r.role).toBe("caregiver");
    await login("9876543210", "pw");
    expect(JSON.parse(last().init.body)).toEqual({ phone: "9876543210", password: "pw" });
    await listAlerts("p1");
    expect(last().url).toBe("/api/v1/alerts?patient_id=p1&status=all");
    expect(last().init.headers.Authorization).toBe("Bearer tok");
  });
  it("acks, consents and creates rooms with the contract bodies", async () => {
    await ackAlert("a1", "called");
    expect(last().url).toBe("/api/v1/alerts/a1/ack");
    expect(JSON.parse(last().init.body)).toEqual({ note: "called" });
    await setConsent("p1", "mic", true);
    expect(last().url).toBe("/api/v1/patients/p1/consents");
    expect(JSON.parse(last().init.body)).toEqual({ kind: "mic", granted: true });
    await createRoom("p1", "g");
    expect(JSON.parse(last().init.body)).toEqual({ patient_id: "p1", game_id: "g" });
  });
  it("uploads media as multipart (no JSON content-type)", async () => {
    await uploadMedia("p1", "photo", new Blob(["x"]), "home.png", ["home.png"]);
    expect(last().url).toBe("/api/v1/media");
    expect(last().init.body instanceof FormData).toBe(true);
    expect(last().init.headers["Content-Type"]).toBeUndefined();
  });
});
