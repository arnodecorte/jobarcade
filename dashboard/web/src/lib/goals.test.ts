import { describe, expect, it } from "vitest";
import { localGoalsToMigrate } from "./goals";
import type { Goals } from "./api";

const server = (configured: boolean): Goals => ({
  daily_goal: 3,
  odds_prior: 0.03,
  odds_cadence: 3,
  last_celebrated_date: "",
  configured,
});
const store = (m: Record<string, string>) => ({ getItem: (k: string) => (k in m ? m[k] : null) });

describe("localGoalsToMigrate", () => {
  it("returns null when the server is already configured", () => {
    expect(localGoalsToMigrate(store({ "energy.goal": "5" }), server(true))).toBeNull();
  });
  it("migrates a valid local goal", () => {
    expect(localGoalsToMigrate(store({ "energy.goal": "5" }), server(false))).toEqual({ daily_goal: 5 });
  });
  it("ignores non-numeric and out-of-range values", () => {
    expect(localGoalsToMigrate(store({ "energy.goal": "abc", "odds.p": "9" }), server(false))).toBeNull();
  });
});
