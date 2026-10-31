import type { Goals, IntegrationStatus, OnboardingState } from "../../lib/api";

/** Props every setup step receives. Steps persist their own data, then call onContinue. */
export type StepProps = {
  integrations: IntegrationStatus;
  onboarding: OnboardingState;
  goals: Goals;
  /** null on the first step. */
  onBack: (() => void) | null;
  /** Move on without saving anything on this step. */
  onSkip: () => void;
  /** Called after the step has saved its data. */
  onContinue: () => void | Promise<void>;
  reload: () => void;
};
