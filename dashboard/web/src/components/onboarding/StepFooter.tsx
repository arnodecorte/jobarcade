type Props = {
  onBack: (() => void) | null;
  onSkip: () => void;
  onContinue: () => void;
  busy?: boolean;
  continueLabel?: string;
  continueDisabled?: boolean;
  note?: string;
};

export function StepFooter({ onBack, onSkip, onContinue, busy, continueLabel = "Continue", continueDisabled, note }: Props) {
  return (
    <footer className="ob-footer">
      {note && <p className="ob-note">{note}</p>}
      <div className="ob-footer-row">
        <div className="ob-footer-left">
          {onBack && (
            <button type="button" className="btn ghost" onClick={onBack} disabled={busy}>
              ← Back
            </button>
          )}
        </div>
        <button type="button" className="ob-skip" onClick={onSkip} disabled={busy}>
          Skip this step
        </button>
        <button type="button" className="btn rose" onClick={onContinue} disabled={busy || continueDisabled}>
          {busy ? "Saving…" : `${continueLabel} →`}
        </button>
      </div>
    </footer>
  );
}

export function StepHead({ kicker, title, sub }: { kicker: string; title: string; sub: string }) {
  return (
    <div className="ob-head">
      <div className="kicker">{kicker}</div>
      <h2>{title}</h2>
      <p>{sub}</p>
    </div>
  );
}
