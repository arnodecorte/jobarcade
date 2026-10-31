import { describe, expect, it } from "vitest";
import { visibleNav } from "./features";

const items = ["today", "pipeline", "jobs", "fresh", "odds", "discover", "system"].map((key) => ({ key }));

describe("visibleNav", () => {
  it("drops fresh and discover when the scraper is off, keeping order", () => {
    expect(visibleNav(items, false).map((i) => i.key)).toEqual(["today", "pipeline", "jobs", "odds", "system"]);
  });
  it("keeps everything when the scraper is on", () => {
    expect(visibleNav(items, true)).toEqual(items);
  });
});
