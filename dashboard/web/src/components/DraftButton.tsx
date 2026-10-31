import { useDraft } from "../lib/draftContext";

type Props = { jobId: number; title: string; company: string };

/** "Create Draft" — opens the global draft-generation modal for a job with no artifact yet. */
export function DraftButton({ jobId, title, company }: Props) {
  const { openForm } = useDraft();
  return (
    <button type="button" className="tag draft-create-btn" onClick={() => openForm({ id: jobId, title, company })}>
      + Create draft
    </button>
  );
}
