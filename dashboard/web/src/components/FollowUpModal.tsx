import { useState, useEffect, useRef } from "react";
import type { Job } from "../lib/api";
import { buildFollowUpEmail } from "../lib/followup";

type Props = { job: Job; onClose: () => void };

export function FollowUpModal({ job, onClose }: Props) {
  const [hiringManager, setHiringManager] = useState("");
  const [copied, setCopied] = useState(false);
  const backdropRef = useRef<HTMLDivElement>(null);

  const { subject, body } = buildFollowUpEmail(job, hiringManager);
  const mailtoHref = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleBackdropClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (e.target === backdropRef.current) onClose();
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="modal-backdrop" ref={backdropRef} onClick={handleBackdropClick}>
      <div className="draft-modal followup-modal">
        <div className="followup-modal-header">
          <div>
            <strong>Follow-up email</strong>
            <span className="followup-modal-sub">{job.title} · {job.company}</span>
          </div>
          <button className="followup-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="field" style={{ marginBottom: 10 }}>
          <label>Hiring manager name <span style={{ fontWeight: 400, color: "var(--ink-faint)" }}>(optional)</span></label>
          <input
            type="text"
            placeholder="e.g. Sophie van den Berg"
            value={hiringManager}
            onChange={(e) => setHiringManager(e.target.value)}
            autoFocus
          />
        </div>

        <div className="field" style={{ marginBottom: 14 }}>
          <label>Subject</label>
          <input type="text" value={subject} readOnly />
        </div>

        <div className="field" style={{ marginBottom: 16 }}>
          <label>Body</label>
          <textarea
            className="followup-body"
            value={body}
            readOnly
            rows={10}
          />
        </div>

        <div className="followup-modal-actions">
          <button className="btn sm ghost" onClick={handleCopy}>
            {copied ? "Copied!" : "Copy body"}
          </button>
          <a className="btn sm" href={mailtoHref}>
            Open in mail client
          </a>
        </div>
      </div>
    </div>
  );
}
