import type { Goals } from "./api";
import { DEFAULT_PRIOR } from "./odds";

export const STEPS = ["welcome", "ai", "profile", "style", "chameleon", "goal"] as const;
export type Step = (typeof STEPS)[number];

export function nextStep(s: Step): Step | null {
  const i = STEPS.indexOf(s);
  return i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null;
}

export function prevStep(s: Step): Step | null {
  const i = STEPS.indexOf(s);
  return i > 0 ? STEPS[i - 1] : null;
}

export function isStep(value: string): value is Step {
  return (STEPS as readonly string[]).includes(value);
}

export function shouldShowOnboarding(status: string, route: string): boolean {
  return status === "pending" || route === "setup";
}

export function needsSetupBanner(status: string, checks: { ai: boolean }): boolean {
  return status === "skipped" && !checks.ai;
}

/** Split on newlines/commas, trim, drop empties, dedupe case-insensitively (first spelling wins). */
export function linesToList(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of text.split(/[\n,]/)) {
    const item = part.trim();
    const key = item.toLowerCase();
    if (!item || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

export const DEFAULT_DAILY_GOAL = 3;

/** Starting values for the goal step: the saved goals when configured, otherwise the defaults. */
export function initialGoalValues(goals: Pick<Goals, "configured" | "daily_goal" | "odds_cadence" | "odds_prior"> | null | undefined) {
  if (!goals || !goals.configured) return { goal: DEFAULT_DAILY_GOAL, cadence: DEFAULT_DAILY_GOAL, prior: DEFAULT_PRIOR };
  return { goal: goals.daily_goal, cadence: goals.odds_cadence, prior: goals.odds_prior };
}

export type AiTestOutcome = { kind: "ok" } | { kind: "unreachable"; detail: string } | { kind: "save-error"; message: string };

/** A failed save/validation is the user's input problem; only a failed connection test means "not reachable". */
export function aiTestOutcome(stage: "save" | "test", result: { ok: boolean; error?: string } | Error): AiTestOutcome {
  if (stage === "save") return { kind: "save-error", message: result instanceof Error ? result.message : result.error || "Could not save." };
  if (result instanceof Error) return { kind: "unreachable", detail: result.message };
  return result.ok ? { kind: "ok" } : { kind: "unreachable", detail: result.error || "" };
}

/** Build the Ollama settings payload, clearing any per-function model override that equals the chosen default model. */
export function aiSavePayload(
  url: string,
  models: { draft: string; refine: string; classify: string },
  key: string
) {
  const defaultModel = models.draft.trim();
  const override = (v: string) => {
    const trimmed = v.trim();
    return trimmed === defaultModel ? "" : trimmed;
  };
  return {
    base_url: url.trim(),
    model: defaultModel,
    models: {
      draft: "",
      refine: override(models.refine),
      classify: override(models.classify),
    },
    ...(key.trim() ? { api_key: key.trim() } : {}),
  };
}

