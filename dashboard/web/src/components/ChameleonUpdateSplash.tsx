import { navigate } from "../lib/hooks";
import { ChameleonMascotAnimation } from "./draft/ChameleonMascotAnimation";

export function ChameleonUpdateSplash({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="splash-backdrop chameleon-update-backdrop" role="dialog" aria-modal="true" aria-labelledby="chameleon-update-title">
      <section className="splash-card chameleon-update-card">
        <ChameleonMascotAnimation />
        <span className="pill" style={{ background: "var(--mint-soft)", color: "var(--mint-deep)" }}>
          Chameleon CV
        </span>
        <h1 id="chameleon-update-title">Brand-aware CVs have landed</h1>
        <p className="splash-intro">
          Draft Builder can now sample a company site, create a subtle color theme, suggest dark mode, and optionally
          cache a safe matching font for Typst.
        </p>
        <div className="splash-grid">
          <div className="splash-feature">
            <strong>Subtle resonance</strong>
            <span>Colors are sanitized into safe CV tokens instead of copying a brand outright.</span>
          </div>
          <div className="splash-feature">
            <strong>Typography opt-in</strong>
            <span>Matched fonts are cached locally, and you can turn them off anytime.</span>
          </div>
        </div>
        <div className="chameleon-update-actions">
          <button
            className="btn rose"
            type="button"
            onClick={() => {
              onDismiss();
              navigate("jobs");
            }}
          >
            Open jobs
          </button>
          <button className="btn ghost" type="button" onClick={onDismiss}>
            Not now
          </button>
        </div>
      </section>
    </div>
  );
}
