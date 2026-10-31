import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { IntegrationStatus, OnboardingState } from "../lib/api";
import { setOnboardingStep, skipOnboarding } from "../lib/api";
import { navigate } from "../lib/hooks";
import { isStep, nextStep, prevStep, STEPS } from "../lib/onboarding";
import type { Step } from "../lib/onboarding";
import { WelcomeStep } from "../components/onboarding/WelcomeStep";
import { AiStep } from "../components/onboarding/AiStep";
import { ProfileStep } from "../components/onboarding/ProfileStep";
import { StyleStep } from "../components/onboarding/StyleStep";
import { ChameleonStep } from "../components/onboarding/ChameleonStep";
import { GoalStep } from "../components/onboarding/GoalStep";
import type { StepProps } from "../components/onboarding/types";

const LABELS: Record<Step, string> = {
  welcome: "Welcome", ai: "Local AI", profile: "About you", style: "CV style", chameleon: "Chameleon", goal: "Your pace",
};

type Props = { onboarding: OnboardingState; integrations: IntegrationStatus; reload: () => void };

export function Onboarding({ onboarding, integrations, reload }: Props) {
  const reduce = useReducedMotion();
  const [step, setStep] = useState<Step>(isStep(onboarding.step) ? onboarding.step : "welcome");
  const [dir, setDir] = useState(1);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState("");
  const index = STEPS.indexOf(step);

  async function go(target: Step | null, direction: number) {
    if (!target) {
      navigate("today"); // finished the last step
      reload();
      return;
    }
    setDir(direction);
    setStep(target);
    window.scrollTo({ top: 0 });
    // Persist so a reload resumes here. Best effort: the UI has already moved on.
    setOnboardingStep(target).catch(() => undefined);
  }

  async function leave() {
    setLeaving(true);
    setError("");
    try {
      // Re-running setup from System must not downgrade a completed install to "skipped".
      if (onboarding.status !== "complete") await skipOnboarding();
      reload();
      navigate("today");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLeaving(false);
    }
  }

  const advance = () => go(nextStep(step), 1);
  const stepProps: StepProps = {
    integrations, onboarding, reload,
    onBack: prevStep(step) ? () => go(prevStep(step), -1) : null,
    onSkip: advance,
    onContinue: advance,
  };

  const body = {
    welcome: <WelcomeStep {...stepProps} />,
    ai: <AiStep {...stepProps} />,
    profile: <ProfileStep {...stepProps} />,
    style: <StyleStep {...stepProps} />,
    chameleon: <ChameleonStep {...stepProps} />,
    goal: <GoalStep {...stepProps} />,
  }[step];

  const slide = reduce ? 0 : 36 * dir;
  return (
    <div className="onboarding">
      <header className="ob-top">
        <div className="ob-brand">
          <span className="brand-badge" aria-hidden="true">J</span>
          <strong>JobArcade</strong>
        </div>
        <button type="button" className="ob-leave" onClick={leave} disabled={leaving}>
          {onboarding.status === "complete" ? "Back to the dashboard" : "Skip setup — take me to the dashboard"}
        </button>
      </header>

      <nav className="ob-progress" aria-label="Setup progress">
        {STEPS.map((s, i) => (
          <div key={s} className={`ob-dot${i < index ? " done" : ""}${i === index ? " current" : ""}`} aria-current={i === index ? "step" : undefined}>
            <span className="ob-dot-mark">{i < index ? "✓" : i + 1}</span>
            <span className="ob-dot-label">{LABELS[s]}</span>
          </div>
        ))}
      </nav>

      <main className="ob-card">
        <AnimatePresence mode="wait" initial={false} custom={dir}>
          <motion.div
            key={step}
            initial={{ opacity: 0, x: slide }}
            animate={{ opacity: 1, x: 0, transition: { duration: reduce ? 0.01 : 0.24, ease: [0.22, 1, 0.36, 1] } }}
            exit={{ opacity: 0, x: -slide / 2, transition: { duration: reduce ? 0.01 : 0.12 } }}
          >
            {body}
          </motion.div>
        </AnimatePresence>
      </main>
      {error && <div className="banner-error" role="alert">{error}</div>}
      <p className="ob-foot-note">Everything here can be changed later. Nothing is shared with anyone.</p>
    </div>
  );
}
