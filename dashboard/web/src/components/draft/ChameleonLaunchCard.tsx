import { ChameleonMascotAnimation } from "./ChameleonMascotAnimation";

type Props = {
  onTry: () => void;
  onDismiss: () => void;
};

export function ChameleonLaunchCard({ onTry, onDismiss }: Props) {
  return (
    <section className="chameleon-launch-card" aria-labelledby="chameleon-launch-title">
      <ChameleonMascotAnimation />
      <div className="chameleon-launch-copy">
        <span className="chameleon-launch-kicker">New</span>
        <h2 id="chameleon-launch-title">Chameleon CV is here</h2>
        <p>
          Extract company brand colors, optionally switch into dark mode, and build the real Typst CV and letter when the
          theme feels right.
        </p>
        <div className="chameleon-launch-actions">
          <button type="button" className="btn primary sm" onClick={onTry}>
            Try Chameleon
          </button>
          <button type="button" className="btn ghost sm" onClick={onDismiss}>
            Dismiss
          </button>
        </div>
      </div>
    </section>
  );
}
