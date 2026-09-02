import type { Job } from "./api";
import { FIT_RANK } from "./format";

const FOLLOWUP_DAYS = 14;

export function needsFollowUp(job: Job): boolean {
  if (job.status !== "applied" && job.status !== "interviewing") return false;
  if (!job.applied_at) return false;
  const ms = Date.now() - new Date(job.applied_at.replace(" ", "T")).getTime();
  return ms / 86_400_000 >= FOLLOWUP_DAYS;
}

const PROTECTED = ["ready", "applied", "interviewing", "rejected", "offer"];

export type JobFilters = { query: string; status: string; showStretch: boolean };

/** Shared ordering: fit band, then score, then freshness — newest first. */
function compareByFitScoreFreshness(a: Job, b: Job): number {
  const band = (FIT_RANK[a.fit_band] ?? 9) - (FIT_RANK[b.fit_band] ?? 9);
  if (band) return band;
  const score = Number(b.score || 0) - Number(a.score || 0);
  if (score) return score;
  return String(b.discovered_at || "").localeCompare(String(a.discovered_at || ""));
}

/** Mirrors the old dashboard: hide stretch by default, sort by fit→score→freshness. */
export function filterAndSort(jobs: Job[], f: JobFilters): Job[] {
  const query = f.query.trim().toLowerCase();
  return jobs
    .filter((job) => {
      const matchesStatus = !f.status || job.status === f.status;
      const isProtected = PROTECTED.includes(job.status);
      const matchesFit = isProtected || f.showStretch || job.fit_band !== "stretch";
      const haystack = [job.company, job.title, job.location, job.department, job.source_platform]
        .join(" ")
        .toLowerCase();
      return matchesStatus && matchesFit && (!query || haystack.includes(query));
    })
    .sort(compareByFitScoreFreshness);
}

/** Jobs discovered on the same calendar date as the most recent sweep's finds. */
export function freshJobs(jobs: Job[]): { date: string | null; rows: Job[] } {
  const dates = jobs.map((j) => j.discovered_at).filter(Boolean) as string[];
  if (!dates.length) return { date: null, rows: [] };
  const maxDate = dates.reduce((a, b) => (b > a ? b : a));
  const date = maxDate.slice(0, 10);
  const rows = jobs.filter((j) => (j.discovered_at || "").slice(0, 10) === date).sort(compareByFitScoreFreshness);
  return { date, rows };
}

/** Top "apply today" picks: actionable statuses, already fit/score/freshness sorted. */
export function applyTodayQueue(jobs: Job[], limit = 6): Job[] {
  const actionable = ["new", "reviewed", "tailoring", "ready"];
  return filterAndSort(jobs.filter((j) => actionable.includes(j.status)), {
    query: "",
    status: "",
    showStretch: false,
  }).slice(0, limit);
}
