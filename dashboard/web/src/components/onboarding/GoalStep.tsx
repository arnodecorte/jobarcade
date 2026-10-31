import { useState } from "react";
import { completeOnboarding, saveGoals } from "../../lib/api";
import { DEFAULT_PRIOR, PRIOR_SOURCES } from "../../lib/odds";
import { StepFooter, StepHead } from "./StepFooter";
import type { StepProps } from "./types";

export function GoalStep({ onBack, onContinue, reload, onboarding }: StepProps) {
  const [goal, setGoal] = useState(3);
  const [prior, setPrior] = useState(DEFAULT_PRIOR);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const clamp = (n: number) => Math.min(20, Math.max(1, n));

  async function finish(save: boolean) {
    setSaving(true);
    setError("");
    try {
      if (save) await saveGoals({ daily_goal: goal, odds_cadence: goal, odds_prior: prior });
      await completeOnboarding();
      reload();
      await onContinue();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <StepHead
        kicker="Step 5 · Your pace"
        title="Set a daily goal you'd feel good about"
        sub="Small and steady beats big and rare. You can change both numbers any time on the Today and Odds pages."
      />
      <div className="ob-body">
        <div className="field">
          Applications per day
          <div className="ob-stepper">
            <button type="button" className="btn ghost" aria-label="Fewer" onClick={() => setGoal(clamp(goal - 1))} disabled={goal <= 1}>−</button>
            <output aria-live="polite">{goal}</output>
            <button type="button" className="btn ghost" aria-label="More" onClick={() => setGoal(clamp(goal + 1))} disabled={goal >= 20}>+</button>
          </div>
        </div>
        <div className="field">
          <label htmlFor="ob-prior">Chance a cold application reaches an interview <b>{(prior * 100).toFixed(1)}%</b></label>
          <input id="ob-prior" type="range" min={0.005} max={0.08} step={0.005} value={prior} onChange={(e) => setPrior(Number(e.target.value))} />
          <span className="ob-note">Starts at a cited 3%. It only needs to work once, and every application counts toward that.</span>
          <details className="ob-advanced">
            <summary>Why 3%?</summary>
            <ul>
              {PRIOR_SOURCES.map((src) => (
                <li key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.label}</a>: {src.figure}</li>
              ))}
            </ul>
          </details>
        </div>
        {error && <p className="ob-error" role="alert">{error}</p>}
      </div>
      <StepFooter
        onBack={onBack}
        onSkip={() => finish(false)}
        onContinue={() => finish(true)}
        busy={saving}
        continueLabel={onboarding.status === "complete" ? "Save" : "Finish setup"}
      />
    </>
  );
}
