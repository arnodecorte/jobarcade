import { describe, expect, it } from "vitest";
import { linesToList, needsSetupBanner, nextStep, prevStep, shouldShowOnboarding } from "./onboarding";

describe("onboarding helpers", () => {
  it("walks the steps in order", () => {
    expect(nextStep("welcome")).toBe("ai");
    expect(nextStep("goal")).toBeNull();
    expect(prevStep("welcome")).toBeNull();
    expect(prevStep("goal")).toBe("chameleon");
  });

  it("shows onboarding when pending or when re-run via the setup route", () => {
    expect(shouldShowOnboarding("pending", "today")).toBe(true);
    expect(shouldShowOnboarding("complete", "setup")).toBe(true);
    expect(shouldShowOnboarding("skipped", "today")).toBe(false);
  });

  it("nudges only skipped installs without AI", () => {
    expect(needsSetupBanner("skipped", { ai: false })).toBe(true);
    expect(needsSetupBanner("skipped", { ai: true })).toBe(false);
    expect(needsSetupBanner("complete", { ai: false })).toBe(false);
  });

  it("splits, trims and dedupes list text", () => {
    expect(linesToList("A, b\nA\n\n c ")).toEqual(["A", "b", "c"]);
    expect(linesToList("")).toEqual([]);
  });
});
