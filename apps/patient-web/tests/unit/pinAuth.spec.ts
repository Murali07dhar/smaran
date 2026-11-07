import { describe, expect, it } from "vitest";
import { isValidPin } from "../../src/core/auth/pinAuth";

describe("isValidPin", () => {
  it("accepts 4 to 6 digit codes", () => {
    expect(isValidPin("1234")).toBe(true);
    expect(isValidPin("123456")).toBe(true);
  });

  it("rejects too short, too long, or non-numeric codes", () => {
    expect(isValidPin("123")).toBe(false);
    expect(isValidPin("1234567")).toBe(false);
    expect(isValidPin("12a4")).toBe(false);
    expect(isValidPin("")).toBe(false);
  });

  it("trims surrounding whitespace before validating", () => {
    expect(isValidPin("  1234  ")).toBe(true);
  });
});
