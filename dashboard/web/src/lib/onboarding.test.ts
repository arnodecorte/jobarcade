import { describe, expect, it } from "vitest";
import { aiTestOutcome, initialGoalValues, linesToList, needsSetupBanner, nextStep, prevStep, shouldShowOnboarding } from "./onboarding";

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

  it("prefills goals from the server only when configured", () => {
    expect(initialGoalValues({ configured: false, daily_goal: 9, odds_cadence: 9, odds_prior: 0.05 })).toEqual({ goal: 3, cadence: 3, prior: 0.03 });
    expect(initialGoalValues({ configured: true, daily_goal: 5, odds_cadence: 4, odds_prior: 0.02 })).toEqual({ goal: 5, cadence: 4, prior: 0.02 });
    expect(initialGoalValues(null).goal).toBe(3);
  });

  it("separates save errors from an unreachable Ollama", () => {
    expect(aiTestOutcome("save", new Error("Invalid URL"))).toEqual({ kind: "save-error", message: "Invalid URL" });
    expect(aiTestOutcome("test", { ok: false, error: "refused" })).toEqual({ kind: "unreachable", detail: "refused" });
    expect(aiTestOutcome("test", { ok: true })).toEqual({ kind: "ok" });
    expect(aiTestOutcome("test", new Error("network"))).toEqual({ kind: "unreachable", detail: "network" });
  });
});
