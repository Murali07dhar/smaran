import { describe, expect, it } from "vitest";
import { uuid7 } from "@smaran/sync-core";
import { consentFromRecords, hasValidConsent, NO_CONSENT } from "../../src/core/validation/consent";

const rec = (kind: "camera" | "mic" | "data_sharing", granted: boolean, ts: string) => ({
  id: `${kind}-${ts}`, patient_id: "p", kind, granted, granted_by: "u", ts
});

describe("consent", () => {
  it("defaults to everything off", () => {
    expect(consentFromRecords([])).toEqual(NO_CONSENT);
    expect(hasValidConsent(undefined, "camera")).toBe(false);
  });
  it("latest record per kind wins (revocation honoured)", () => {
    const s = consentFromRecords([rec("camera", true, "2026-01-01T00:00:00Z"), rec("camera", false, "2026-02-01T00:00:00Z")]);
    expect(hasValidConsent(s, "camera")).toBe(false);
  });
});

describe("uuid7", () => {
  it("is a v7 UUID and time-ordered", () => {
    const a = uuid7(1_700_000_000_000), b = uuid7(1_700_000_001_000);
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(a < b).toBe(true);
  });
});
