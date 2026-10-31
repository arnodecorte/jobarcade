import { useState } from "react";
import { setJobStatus } from "../lib/api";
import { EDITABLE_STATUSES, STATUS_LABELS } from "../lib/format";

type Props = { jobId: number; status: string; onChanged: () => void };

export function StatusSelect({ jobId, status, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  return (
    <select
      className="status-select"
      value={status}
      disabled={busy}
      aria-label="Job status"
      onChange={async (e) => {
        setBusy(true);
        try {
          await setJobStatus(jobId, e.target.value);
          if (e.target.value === "rejected") window.dispatchEvent(new CustomEvent("jobarcade:rejected"));
          onChanged();
        } catch (err) {
          alert((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {EDITABLE_STATUSES.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  );
}
