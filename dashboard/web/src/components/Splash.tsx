import { RELEASE } from "../lib/releaseNotes";
import { Angie } from "./Sprite";

export function Splash({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="splash-backdrop" role="dialog" aria-modal="true" aria-labelledby="splash-title">
      <section className="splash-card">
        <Angie size="md" />
        <span className="pill" style={{ background: "var(--berry-soft)", color: "var(--berry-deep)" }}>
          {RELEASE.version} release · {RELEASE.date}
        </span>
        <h1 id="splash-title">Welcome to Job Hunt HQ</h1>
        <p className="splash-intro">{RELEASE.intro}</p>

        <div className="splash-grid">
          {RELEASE.pages.map((p) => (
            <div key={p.name} className="splash-feature">
              <strong>{p.name}</strong>
              <span>{p.body}</span>
            </div>
          ))}
        </div>

        <button className="btn rose" type="button" onClick={onDismiss}>
          Let's go →
        </button>
        <p className="muted" style={{ fontSize: 11.5 }}>
          Shown once. Find the full release notes anytime on the System page.
        </p>
      </section>
    </div>
  );
}
