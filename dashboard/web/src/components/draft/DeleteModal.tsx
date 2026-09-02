import { useState } from "react";
import { deleteDraft } from "../../lib/api";

type Props = {
  folder: string;
  jobId?: number;
  onSuccess: () => void;
  onClose: () => void;
};

export function DeleteModal({ folder, jobId, onSuccess, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleDelete() {
    setBusy(true);
    setError("");
    try {
      await deleteDraft(folder, jobId);
      onSuccess();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={!busy ? onClose : undefined}
    >
      <section
        className="draft-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-title">Delete this application?</h2>
        <p className="panel-sub" style={{ marginTop: 6 }}>
          This will permanently remove the <strong>{folder}</strong> folder and all its files.
          This cannot be undone.
        </p>
        {error && <p className="draft-error">{error}</p>}
        <div className="draft-modal-actions">
          <button type="button" className="btn ghost sm" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn rose sm" onClick={handleDelete} disabled={busy}>
            {busy ? "Deleting…" : "Delete"}
          </button>
        </div>
      </section>
    </div>
  );
}
