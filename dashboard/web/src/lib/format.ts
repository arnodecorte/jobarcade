export const STATUS_LABELS: Record<string, string> = {
  new: "New",
  reviewed: "Reviewing",
  tailoring: "Tailoring",
  ready: "Ready",
  applied: "Applied",
  interviewing: "Interviewing",
  rejected: "Rejected",
  offer: "Offer",
  skipped: "Skipped",
  expired: "Expired",
  scrape_failed: "Scrape Failed",
};

export const PIPELINE_STATUSES = ["new", "reviewed", "tailoring", "ready", "applied"];
export const OUTCOME_STATUSES = ["rejected", "offer"];
export const EDITABLE_STATUSES = [
  "new",
  "reviewed",
  "tailoring",
  "ready",
  "applied",
  "interviewing",
  "rejected",
  "offer",
  "skipped",
  "expired",
];

export const FIT_LABELS: Record<string, string> = {
  core_fit: "Core fit",
  adjacent_plausible: "Adjacent",
  stretch: "Stretch",
};
export const FIT_RANK: Record<string, number> = {
  core_fit: 0,
  adjacent_plausible: 1,
  stretch: 2,
};

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

export function ageBucket(value: string | null | undefined): { label: string; tone: string } {
  if (!value) return { label: "—", tone: "old" };
  const days = (Date.now() - new Date(value).getTime()) / 86_400_000;
  if (days < 1) return { label: "today", tone: "fresh" };
  if (days < 4) return { label: "1–3 days", tone: "warm" };
  if (days < 8) return { label: "4–7 days", tone: "cool" };
  return { label: "stale", tone: "old" };
}

export function initials(company: string): string {
  return String(company || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
}

export function faviconUrl(domain: string | null): string {
  return domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64` : "";
}

export function domainFromUrl(value: string): string {
  if (!value) return "";
  try {
    const url = new URL(value.startsWith("http") ? value : `https://${value}`);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
