type Props = {
  folder: string;
  dirty: boolean;
  busy: boolean;
  onSave: () => void;
  onBuild: () => void;
  onMarkReady: () => void;
  onReprompt: () => void;
  onDelete: () => void;
};

export function DraftHeader({
  folder,
  dirty,
  busy,
  onSave,
  onBuild,
  onMarkReady,
  onReprompt,
  onDelete,
}: Props) {
  return (
    <header className="draft-topbar">
      <div className="draft-topbar-info">
        <p className="draft-kicker">Angelica Job Hunt HQ</p>
        <h1 className="draft-topbar-title">{folder}</h1>
      </div>
      <div className="draft-topbar-actions">
        <a className="btn ghost sm" href="/">
          ← Dashboard
        </a>
        <button type="button" className="btn ghost sm" onClick={onReprompt} disabled={busy}>
          Reprompt
        </button>
        <button type="button" className="btn ghost sm" onClick={onMarkReady} disabled={busy}>
          Mark Ready
        </button>
        <button type="button" className="btn ghost sm" onClick={onBuild} disabled={busy}>
          Build PDF
        </button>
        <button
          type="button"
          className={`btn sm ${dirty ? "rose" : "ghost"}`}
          onClick={onSave}
          disabled={busy || !dirty}
        >
          {dirty ? "Save *" : "Saved"}
        </button>
        <button
          type="button"
          className="btn ghost sm draft-delete-btn"
          onClick={onDelete}
          disabled={busy}
        >
          Delete
        </button>
      </div>
    </header>
  );
}
