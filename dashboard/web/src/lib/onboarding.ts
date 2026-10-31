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
