import { describe, expect, it } from "vitest";
import { localIsoDate, shouldCelebrate } from "./celebrate";

describe("shouldCelebrate", () => {
  it("is false below goal", () => expect(shouldCelebrate(4, 5, "", "2026-05-01")).toBe(false));
  it("is true at goal when not yet celebrated", () => expect(shouldCelebrate(5, 5, "", "2026-05-01")).toBe(true));
  it("is false when already celebrated today", () => expect(shouldCelebrate(7, 5, "2026-05-01", "2026-05-01")).toBe(false));
  it("is true when celebrated yesterday", () => expect(shouldCelebrate(5, 5, "2026-04-30", "2026-05-01")).toBe(true));
  it("is false for a zero goal", () => expect(shouldCelebrate(0, 0, "", "2026-05-01")).toBe(false));
});

describe("localIsoDate", () => {
  it("uses local calendar fields, zero padded", () => expect(localIsoDate(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05"));
});
