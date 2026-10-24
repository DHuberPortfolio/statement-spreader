import { describe, expect, it } from "vitest";
import { IDLE_AFTER_MS, isActive } from "./timer";

describe("active time rule", () => {
  const now = 1_000_000;

  it("counts a visible tab used in the last minute", () => {
    expect(isActive(true, now - 1_000, now)).toBe(true);
    expect(isActive(true, now - IDLE_AFTER_MS, now)).toBe(true);
  });

  it("stops counting after a minute without interaction", () => {
    expect(isActive(true, now - IDLE_AFTER_MS - 1, now)).toBe(false);
  });

  it("never counts a hidden tab, however recent the interaction", () => {
    expect(isActive(false, now, now)).toBe(false);
  });
});
