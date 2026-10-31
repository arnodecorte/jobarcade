import { useState } from "react";
import type { Job } from "../lib/api";
import { setJobNotes } from "../lib/api";
import { ageBucket, FIT_LABELS, formatDate } from "../lib/format";
import { needsFollowUp } from "../lib/jobs";
import { CompanyLogo } from "./CompanyLogo";
import { StatusSelect } from "./StatusSelect";
import { DraftButton } from "./DraftButton";
import { FollowUpModal } from "./FollowUpModal";

function Artifacts({ job }: { job: Job }) {
  const a = job.artifact;
  if (!a) return <DraftButton jobId={job.id} title={job.title} company={job.company} />;
  const base = `/applications/${encodeURIComponent(a.folder_name)}`;
  return (
    <div className="artifacts">
      {a.draft_state === "ready_for_review" && <span className="tag review">Review</span>}
      {a.draft_origin === "ollama" && a.draft_state !== "ready_for_review" && <span className="tag ai">AI draft</span>}
      {a.has_cv && (
        <a className="tag ready" href={`${base}/cv.pdf`} target="_blank" rel="noreferrer">CV</a>
      )}
      {a.has_letter && (
        <a className="tag ready" href={`${base}/motivation-letter.pdf`} target="_blank" rel="noreferrer">Letter</a>
      )}
      {a.has_cv && a.has_letter && (
        <a className="tag" href={`${base}/bundle.zip`}>Bundle</a>
      )}
      {(a.has_draft_data || a.draft_origin === "ollama") && (
        <a className="tag" href={`/draft?folder=${encodeURIComponent(a.folder_name)}&jobId=${job.id}`}>Open draft</a>
      )}
      {!a.has_draft_data && !a.has_cv && !a.has_letter && a.draft_origin !== "ollama" && (
        <>
          {a.has_job_listing && <span className="tag">Listing saved</span>}
          <DraftButton jobId={job.id} title={job.title} company={job.company} />
        </>
      )}
    </div>
  );
}

const OUTCOME_STATUSES = ["rejected", "offer"];

function NotesField({ jobId, notes, onSaved }: { jobId: number; notes: string | null; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(notes ?? "");

  async function save() {
    setEditing(false);
    if (value !== (notes ?? "")) {
      try {
        await setJobNotes(jobId, value);
        onSaved();
      } catch {
        // non-critical; don't alert on a note save failure
      }
    }
  }

  return editing ? (
    <textarea
      className="notes-field"
      value={value}
      placeholder="Why rejected, or what are the offer terms?"
      autoFocus
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => { if (e.key === "Escape") { setValue(notes ?? ""); setEditing(false); } }}
    />
  ) : (
    <span
      className={`notes-text ${value ? "has-notes" : "notes-empty"}`}
      title="Click to edit note"
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}
    >
      {value || "Add note…"}
    </span>
  );
}

type Props = { job: Job; onChanged: () => void; onSelect?: () => void; selected?: boolean };

export function JobRow({ job, onChanged, onSelect, selected }: Props) {
  const [showFollowUp, setShowFollowUp] = useState(false);
  const age = ageBucket(job.discovered_at);
  const reasons = Array.isArray(job.score_reasons) ? job.score_reasons.slice(0, 3) : [];
  const dupes = job.possible_duplicate ? job.duplicate_of ?? [] : [];
  const dupTitle = dupes.length
    ? `Same role also harvested from: ${dupes
        .map((d) => `${d.source_platform ?? "unknown"} (${d.status})`)
        .join(", ")}. Skip the redundant one to keep your pipeline clean.`
    : "";
  return (
    <article
      id={`job-${job.id}`}
      className={`job-row ${selected ? "is-selected" : ""} ${onSelect ? "is-clickable" : ""}`}
      onClick={
        onSelect
          ? (e) => {
              if ((e.target as HTMLElement).closest("a, select, button")) return;
              onSelect();
            }
          : undefined
      }
    >
      <div className="job-id">
        <CompanyLogo company={job.company} domain={job.company_logo_domain} url={job.company_logo_url} />
        <div className="meta">
          {job.apply_url ? (
            <a className="title" href={job.apply_url} target="_blank" rel="noreferrer">{job.title}</a>
          ) : (
            <span className="title">{job.title}</span>
          )}
          <div className="who">{job.company} · {job.location || job.country || "Unknown"}</div>
          <div className="chips">
            <span className={`pill ${job.fit_band}`}>{FIT_LABELS[job.fit_band] || job.fit_band}</span>
            <span className="pill score">{job.score ?? 0}</span>
            {dupes.length > 0 && (
              <span className="pill dup" title={dupTitle}>⚠ Possible duplicate</span>
            )}
            {reasons.map((r) => <span key={r} className="reason-chip">{r}</span>)}
          </div>
          {(OUTCOME_STATUSES.includes(job.status) || !!job.notes) && (
            <div className="notes-row">
              <NotesField jobId={job.id} notes={job.notes} onSaved={onChanged} />
            </div>
          )}
        </div>
      </div>
      <StatusSelect jobId={job.id} status={job.status} onChanged={onChanged} />
      <div className="artifacts-col">
        <Artifacts job={job} />
        {needsFollowUp(job) && (
          <button className="followup-btn" onClick={(e) => { e.stopPropagation(); setShowFollowUp(true); }}>
            Follow up?
          </button>
        )}
      </div>
      <div className="age" title={`Discovered ${formatDate(job.discovered_at)}`}>
        <span className={`age ${age.tone}`}>{age.label}</span>
      </div>
      {showFollowUp && <FollowUpModal job={job} onClose={() => setShowFollowUp(false)} />}
    </article>
  );
}
