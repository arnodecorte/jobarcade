import { describe, expect, it } from "vitest";
import {
  appsForConfidence,
  cumulativeProb,
  effectiveRate,
  etaDays,
  expectedNeeded,
} from "./odds";

describe("odds math", () => {
  it("cumulative probability follows 1-(1-p)^n", () => {
    expect(cumulativeProb(0, 0.02)).toBe(0);
    expect(cumulativeProb(1, 0.02)).toBeCloseTo(0.02, 6);
    expect(cumulativeProb(50, 0.02)).toBeCloseTo(1 - Math.pow(0.98, 50), 6);
    // More pulls strictly raise the odds.
    expect(cumulativeProb(100, 0.02)).toBeGreaterThan(cumulativeProb(50, 0.02));
  });

  it("expected value is 1/p (≈50 pulls at 2%)", () => {
    expect(expectedNeeded(0.02)).toBeCloseTo(50, 6);
  });

  it("ETA counts down remaining expected pulls over cadence", () => {
    // 50 expected − 12 sent = 38 left, at 3/day ≈ 12.67 days.
    expect(etaDays(12, 0.02, 3)).toBeCloseTo(38 / 3, 6);
    // Past the expected count → no wait.
    expect(etaDays(60, 0.02, 3)).toBe(0);
    // No cadence → never.
    expect(etaDays(0, 0.02, 0)).toBe(Infinity);
  });

  it("confidence threshold needs more pulls than expected value", () => {
    // 75% confidence at 2% is well past the 50-pull expected value.
    expect(appsForConfidence(0.02, 0.75)).toBeGreaterThan(50);
  });

  it("keeps the prior until enough mature evidence exists", () => {
    expect(effectiveRate(0.02, 0, 50)).toBe(0.02);
    expect(effectiveRate(0.02, 0.05, 12)).toBe(0.02);
    expect(effectiveRate(0.02, 0.05, 20)).toBe(0.05);
  });
});
