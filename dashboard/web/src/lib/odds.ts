// The "unlimited tries" math. Every application is an independent pull with a
// small success probability p. These are pure functions so they unit-test cleanly.

/** Probability of landing at least one interview after `n` applications. */
export function cumulativeProb(n: number, p: number): number {
  if (p <= 0 || n <= 0) return 0;
  if (p >= 1) return 1;
  return 1 - Math.pow(1 - p, n);
}

/** Applications needed for one interview on average (expected value, 1/p). */
export function expectedNeeded(p: number): number {
  if (p <= 0) return Infinity;
  return 1 / p;
}

/**
 * Expected-value ETA: days until the *next* interview at the current pace.
 * (1/p − already_sent) more pulls, divided by pulls/day. Clamped at 0.
 */
export function etaDays(sent: number, p: number, cadencePerDay: number): number {
  if (cadencePerDay <= 0) return Infinity;
  const remaining = Math.max(0, expectedNeeded(p) - sent);
  return remaining / cadencePerDay;
}

/** Use the calibrated observed rate when there is enough mature evidence; otherwise keep the prior. */
export function effectiveRate(prior: number, observed: number, matured: number, minMatured = 20): number {
  if (matured < minMatured || observed <= 0) return prior;
  return observed;
}

/** Applications a threshold-confidence interview needs: n where P(≥1) ≥ conf. */
export function appsForConfidence(p: number, conf: number): number {
  if (p <= 0) return Infinity;
  if (conf <= 0) return 0;
  if (conf >= 1) return Infinity;
  return Math.ceil(Math.log(1 - conf) / Math.log(1 - p));
}

/** Evenly-sampled points of the cumulative curve for the SVG hero. */
export function curvePoints(
  p: number,
  maxN: number,
  steps = 60,
): Array<{ n: number; prob: number }> {
  const out: Array<{ n: number; prob: number }> = [];
  for (let i = 0; i <= steps; i += 1) {
    const n = Math.round((maxN * i) / steps);
    out.push({ n, prob: cumulativeProb(n, p) });
  }
  return out;
}

export function formatEta(days: number): string {
  if (!Number.isFinite(days)) return "—";
  if (days <= 0) return "any day now";
  if (days < 1) return "today";
  if (days < 2) return "~1 day";
  if (days < 14) return `~${Math.round(days)} days`;
  if (days < 60) return `~${Math.round(days / 7)} weeks`;
  return `~${Math.round(days / 30)} months`;
}

/** Cited cold-application interview rate, used until the user tunes their own. */
export const DEFAULT_PRIOR = 0.03;

export type PriorSource = { label: string; figure: string; url: string };

export const PRIOR_SOURCES: PriorSource[] = [
  { label: "CareerPlug 2024 Recruiting Metrics (employer data, 10M+ applications)", figure: "≈3% of applicants reach an interview", url: "https://www.careerplug.com/recruiting-metrics-and-kpis/" },
  { label: "Huntr 2025 Annual Job Search Trends (job-seeker tracker data)", figure: "≈3.5% average; 2.7% (Jan) to 4.2% (Nov)", url: "https://huntr.co/research/2025-annual-job-search-trends-report" },
];

export type Celebration = { probBefore: number; probAfter: number; daysSaved: number; etaDays: number };

/** What a batch of newly sent applications bought: odds before/after and days shaved off the ETA. */
export function celebrationStats(sentBefore: number, sentAfter: number, p: number, cadence: number): Celebration {
  return {
    probBefore: cumulativeProb(sentBefore, p),
    probAfter: cumulativeProb(sentAfter, p),
    daysSaved: cadence > 0 ? (sentAfter - sentBefore) / cadence : 0,
    etaDays: etaDays(sentAfter, p, cadence),
  };
}

export function rejectionMessage(sentTotal: number, p: number): string {
  const n = Math.max(0, appsForConfidence(p, 0.8) - sentTotal);
  if (n === 0) return "Every no is a roll used, not a loss. The math is firmly on your side now — keep rolling.";
  const pct = Number((p * 100).toFixed(1));
  return `Every no is a roll used, not a loss. At ${pct}% per application, ${n} more gets you to an 80% chance of at least one interview.`;
}
