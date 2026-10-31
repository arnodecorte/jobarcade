import type { Goals } from "./api";

const BOUNDS = {
  "energy.goal": ["daily_goal", 1, 50],
  "odds.p": ["odds_prior", 0.005, 0.08],
  "odds.cadence": ["odds_cadence", 0.5, 50],
} as const;

/** One-time migration: legacy localStorage goals, offered only while the server has none configured. */
export function localGoalsToMigrate(storage: Pick<Storage, "getItem">, server: Goals): Partial<Goals> | null {
  if (server.configured) return null;
  const out: Record<string, number> = {};
  for (const [key, [field, lo, hi]] of Object.entries(BOUNDS)) {
    const raw = storage.getItem(key);
    if (raw == null || raw.trim() === "") continue;
    const v = Number(raw);
    if (Number.isFinite(v) && v >= lo && v <= hi) out[field] = v;
  }
  return Object.keys(out).length ? (out as Partial<Goals>) : null;
}

/** Remove the legacy localStorage goal keys once they are safely on the server. */
export function clearLegacyGoals(storage: Pick<Storage, "removeItem">): void {
  for (const key of Object.keys(BOUNDS)) {
    try {
      storage.removeItem(key);
    } catch {
      /* storage unavailable; nothing to clean */
    }
  }
}
