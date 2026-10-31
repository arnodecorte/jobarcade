/** True once per local day, when today's applications reach the daily goal. */
export function shouldCelebrate(pullsToday: number, goal: number, lastCelebrated: string, todayIso: string): boolean {
  return goal > 0 && pullsToday >= goal && lastCelebrated !== todayIso;
}

/** Local calendar date as YYYY-MM-DD (toISOString would give the UTC date). */
export function localIsoDate(d: Date = new Date()): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}
