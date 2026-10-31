import { useState } from "react";
import { seedDemo } from "../../lib/api";
import { Angie } from "../Sprite";
import type { StepProps } from "./types";

export const PITCH = "Local AI tailors every application. Every no gets you closer to a yes — it only needs to work once.";

export function WelcomeStep({ onContinue, reload }: StepProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function explore() {
    setBusy(true);
    setError("");
    try {
      await seedDemo();
      reload();
      await onContinue();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ob-welcome">
      <Angie size="lg" state="wave" />
      <span className="pill" style={{ background: "var(--berry-soft)", color: "var(--berry-deep)" }}>
        Welcome to JobArcade
      </span>
      <h2>Let's get you set up</h2>
      <p className="ob-pitch">{PITCH}</p>
      <p className="ob-note">Recommended: about 5 minutes. Every step is skippable, and you can finish later from the System page.</p>
      <div className="ob-welcome-actions">
        <button type="button" className="btn rose" onClick={() => onContinue()} disabled={busy}>
          Let's set up
        </button>
        <button type="button" className="btn ghost" onClick={explore} disabled={busy}>
          {busy ? "Adding sample data…" : "Explore with sample data"}
        </button>
      </div>
      {error && <p className="ob-error" role="alert">{error}</p>}
    </section>
  );
}
