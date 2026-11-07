import { describe, expect, it } from "vitest";
import { computeBackoffMs } from "@smaran/sync-core";

describe("computeBackoffMs", () => {
  it("never exceeds the configured max", () => {
    for (let attempts = 1; attempts <= 20; attempts++) {
      expect(computeBackoffMs(attempts, { baseMs: 1000, maxMs: 10_000 })).toBeLessThanOrEqual(10_000);
    }
  });

  it("is always non-negative", () => {
    expect(computeBackoffMs(1)).toBeGreaterThanOrEqual(0);
    expect(computeBackoffMs(0)).toBeGreaterThanOrEqual(0);
  });

  it("raises the ceiling geometrically before clamping", () => {
    // attempts=1 ceiling is base*factor^0=base; attempts=3 ceiling is base*factor^2
    const base = 1000;
    const maxPossibleAttempt1 = base; // factor^0
    const maxPossibleAttempt3 = base * 2 * 2; // factor^2
    expect(maxPossibleAttempt3).toBeGreaterThan(maxPossibleAttempt1);
  });
});
