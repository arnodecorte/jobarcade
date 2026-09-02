import { useEffect, useMemo, useRef, useState } from "react";
import type { GmailEvidence, GmailMatchCandidate, GmailStatus, GmailSyncProgress, Job } from "../lib/api";
import {
  applyGmailEvidence,
  disconnectGmail,
  getGmailEvidenceCandidates,
  getGmailSyncProgress,
  ignoreGmailEvidence,
  startGmailOAuth,
  syncGmail,
  updateGmailEvidence,
} from "../lib/api";

const CATEGORIES = [
  ["application_receipt", "Application receipt"],
  ["rejection", "Rejection"],
  ["interview_invite", "Interview invite"],
  ["assessment_invite", "Assessment invite"],
  ["recruiter_outreach", "Recruiter outreach"],
  ["information_request", "Information request"],
  ["offer", "Offer"],
  ["withdrawal_confirmation", "Withdrawal confirmation"],
  ["administrative_update", "Administrative update"],
  ["unknown", "Unknown"],
] as const;

const STATUS_BY_CATEGORY: Record<string, string> = {
  application_receipt: "Applied",
  rejection: "Rejected",
  interview_invite: "Interviewing",
  assessment_invite: "Interviewing",
  offer: "Offer",
};

type Props = {
  gmail: GmailStatus;
  evidence: GmailEvidence[];
  jobs: Job[];
  reload: () => void;
};

type EvidenceDraft = { evidence_type: string; job_id: number | null };

function Confidence({ label, value }: { label: string; value: number }) {
  const percent = Math.round(value * 100);
  return (
    <div className="gmail-confidence">
      <span>{label}</span>
      <strong>{percent}%</strong>
      <div aria-label={`${label} ${percent}%`}><span style={{ width: `${percent}%` }} /></div>
    </div>
  );
}

function metricLabel(value: string) {
  return value.replaceAll("_", " ");
}

export function GmailEvidencePanel({ gmail, evidence, jobs, reload }: Props) {
  const [message, setMessage] = useState("");
  const [drafts, setDrafts] = useState<Record<string, EvidenceDraft>>({});
  const [candidateMatches, setCandidateMatches] = useState<Record<string, GmailMatchCandidate[]>>({});
  const [syncProgress, setSyncProgress] = useState<GmailSyncProgress | null>(null);
  const pollingRef = useRef(false);
  // Set true in the mount effect's cleanup so an in-flight loop from a
  // detached (unmounted) instance stops itself at its next await, instead of
  // polling forever in the background or racing a fresh loop after remount.
  const cancelledRef = useRef(false);
  // Set when pollSyncProgress() is called while a loop is already active (e.g.
  // from the Sync now button while the mount-effect's loop is still in
  // flight). Lets that active loop know a fresh sync may have just started,
  // so a stale "not running" read doesn't cause it to stop prematurely.
  const pendingRestartRef = useRef(false);
  const submittedJobs = useMemo(
    () => jobs
      .filter((job) => ["applied", "interviewing", "rejected", "offer"].includes(job.status))
      .sort((a, b) => `${a.company} ${a.title}`.localeCompare(`${b.company} ${b.title}`)),
    [jobs],
  );

  function draftFor(item: GmailEvidence): EvidenceDraft {
    return drafts[item.gmail_message_id] || {
      evidence_type: item.evidence_type,
      job_id: item.job_id,
    };
  }

  function patchDraft(item: GmailEvidence, patch: Partial<EvidenceDraft>) {
    setDrafts((current) => ({
      ...current,
      [item.gmail_message_id]: { ...draftFor(item), ...patch },
    }));
  }

  async function loadCandidates(item: GmailEvidence) {
    if (candidateMatches[item.gmail_message_id]) return;
    try {
      const result = await getGmailEvidenceCandidates(item.gmail_message_id);
      setCandidateMatches((current) => ({ ...current, [item.gmail_message_id]: result.candidates }));
    } catch {
      // The complete submitted-application list remains available as a fallback.
    }
  }

  async function connect() {
    setMessage("Opening Google OAuth...");
    try {
      const result = await startGmailOAuth();
      window.open(result.auth_url, "_blank", "noopener,noreferrer");
      setMessage("OAuth opened. Return here after Google confirms the connection.");
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function pollSyncProgress() {
    if (pollingRef.current) {
      // A loop is already active. Rather than starting a second one, flag
      // that a fresh sync may have just been kicked off — if the active
      // loop's current in-flight GET resolves with a stale "not running"
      // (read before this call's syncGmail() POST took effect server-side),
      // it will re-check instead of stopping.
      pendingRestartRef.current = true;
      return;
    }
    pollingRef.current = true;
    try {
      for (;;) {
        const progress = await getGmailSyncProgress();
        if (cancelledRef.current) return;
        setSyncProgress(progress);
        console.debug("[gmail-sync]", progress.processed, "/", progress.total, progress.current_subject);
        if (!progress.running) {
          if (pendingRestartRef.current) {
            // A new sync was requested while this GET was in flight; its
            // effect may not be visible yet. Re-check immediately instead of
            // treating this as the sync's completion.
            pendingRestartRef.current = false;
            continue;
          }
          if (progress.error) {
            setMessage(progress.error);
          } else if (progress.result) {
            setMessage(`Processed ${progress.result.saved} messages.`);
          }
          reload();
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (cancelledRef.current) return;
      }
    } catch {
      // Progress polling is best-effort; the rest of the dashboard still works.
    } finally {
      pollingRef.current = false;
    }
  }

  useEffect(() => {
    cancelledRef.current = false;
    pollSyncProgress();
    return () => {
      cancelledRef.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function sync() {
    try {
      const result = await syncGmail({ max_results: 75 });
      setMessage(result.already_running ? "Sync already in progress." : "Syncing and classifying Gmail...");
      pollSyncProgress();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function disconnect() {
    setMessage("Disconnecting Gmail...");
    try {
      await disconnectGmail();
      setMessage("Gmail disconnected.");
      reload();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function review(item: GmailEvidence, action: "apply" | "ignore") {
    setMessage(action === "apply" ? "Saving and applying evidence..." : "Ignoring evidence...");
    try {
      if (action === "ignore") {
        await ignoreGmailEvidence(item.gmail_message_id);
      } else {
        const draft = draftFor(item);
        await updateGmailEvidence(item.gmail_message_id, draft);
        await applyGmailEvidence(item.gmail_message_id);
      }
      setDrafts((current) => {
        const next = { ...current };
        delete next[item.gmail_message_id];
        return next;
      });
      setMessage("Evidence reviewed.");
      reload();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  const metrics = gmail.metrics;

  return (
    <div className="gmail-intelligence">
      <div className="gmail-model-line">
        <p className="panel-sub">Semantic lifecycle evidence, matched against submitted applications.</p>
        <span className="health ok">{gmail.intelligence.model}</span>
      </div>

      {!gmail.configured ? (
        <div className="banner-error">Missing OAuth config: {gmail.missing_config.join(", ")}</div>
      ) : null}

      <div className="gmail-metrics">
        {[
          ["Scanned", metrics.scanned],
          ["Job related", metrics.job_related],
          ["Auto matched", metrics.auto_matched],
          ["Auto applied", metrics.auto_applied],
          ["Needs review", metrics.pending_review],
          ["Unmatched", metrics.unmatched],
          ["Corrected", metrics.corrected],
          ["Errors", metrics.errors],
        ].map(([label, value]) => (
          <div key={label}>
            <strong>{value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>

      <div className="gmail-toolbar">
        <div className="muted">
          {gmail.connected
            ? `Connected as ${gmail.account?.email || "Gmail"} · last sync ${gmail.account?.last_sync_at || "never"}`
            : "Gmail is not connected."}
        </div>
        <div>
          {gmail.connected ? (
            <>
              <button className="btn rose sm" type="button" onClick={sync} disabled={Boolean(syncProgress?.running)}>
                {syncProgress?.running ? "Syncing…" : "Sync now"}
              </button>
              <button className="btn ghost sm" type="button" onClick={disconnect} disabled={Boolean(syncProgress?.running)}>
                Disconnect
              </button>
            </>
          ) : (
            <button className="btn rose sm" type="button" onClick={connect} disabled={!gmail.configured}>
              Connect Gmail
            </button>
          )}
        </div>
      </div>
      {gmail.account?.last_error ? <div className="banner-error">{gmail.account.last_error}</div> : null}
      {message ? <p className="muted gmail-message">{message}</p> : null}

      {syncProgress?.running ? (
        <div className="gmail-sync-progress">
          <div className="gmail-sync-progress-bar">
            <span
              style={{
                width: syncProgress.total > 0
                  ? `${Math.round((syncProgress.processed / syncProgress.total) * 100)}%`
                  : "4%",
              }}
            />
          </div>
          <p className="muted">
            {syncProgress.total > 0
              ? `${syncProgress.processed} / ${syncProgress.total} messages`
              : "Starting sync…"}
            {syncProgress.current_subject ? ` · ${syncProgress.current_subject}` : ""}
          </p>
          {syncProgress.log.length ? (
            <ul className="gmail-sync-log">
              {syncProgress.log.slice().reverse().map((line) => <li key={line}>{line}</li>)}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="gmail-category-strip">
        {Object.entries(metrics.categories).map(([category, count]) => (
          <span key={category}><strong>{count}</strong> {metricLabel(category)}</span>
        ))}
      </div>

      <div className="gmail-evidence-list">
        {evidence.map((item) => {
          const draft = draftFor(item);
          const targetStatus = STATUS_BY_CATEGORY[draft.evidence_type];
          const isPending = item.status === "pending";
          return (
            <details className="gmail-evidence" key={item.gmail_message_id}>
              <summary className="gmail-evidence-head">
                <div>
                  <strong>{item.subject || "(no subject)"}</strong>
                  <span>{item.sender || "Unknown sender"} · {item.occurred_at || "Unknown date"}</span>
                </div>
                <span className={`health ${isPending ? "warning" : "ok"}`}>{metricLabel(item.status)}</span>
                <i aria-hidden="true">+</i>
              </summary>

              <div className="gmail-evidence-body">
                <p className="gmail-snippet">{item.snippet || "No preview available."}</p>

              <div className="gmail-confidence-grid">
                <Confidence label="Classification" value={item.classification_confidence} />
                <Confidence label="Application match" value={item.match_confidence} />
              </div>

              <div className="gmail-review-grid">
                <label className="field">
                  Category
                  <select
                    value={draft.evidence_type}
                    disabled={!isPending}
                    onChange={(event) => patchDraft(item, { evidence_type: event.target.value })}
                  >
                    {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="field">
                  Application
                  <select
                    value={draft.job_id ?? ""}
                    disabled={!isPending}
                    onFocus={() => loadCandidates(item)}
                    onChange={(event) => patchDraft(item, {
                      job_id: event.target.value ? Number(event.target.value) : null,
                    })}
                  >
                    <option value="">Unmatched</option>
                    {(candidateMatches[item.gmail_message_id] || []).length ? (
                      <optgroup label="Suggested matches">
                        {candidateMatches[item.gmail_message_id].map((candidate) => (
                          <option value={candidate.job_id} key={`suggested-${candidate.job_id}`}>
                            {Math.round(candidate.confidence * 100)}% · {candidate.company} · {candidate.title}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                    <optgroup label="All submitted applications">
                    {submittedJobs.map((job) => (
                      <option value={job.id} key={job.id}>{job.company} · {job.title}</option>
                    ))}
                    </optgroup>
                  </select>
                </label>
              </div>

              <div className="gmail-decision">
                <div>
                  <span>Result</span>
                  <strong>{targetStatus ? `Set application to ${targetStatus}` : "Record evidence only"}</strong>
                </div>
                {isPending ? (
                  <div>
                    <button className="btn ghost sm" type="button" onClick={() => review(item, "ignore")}>Ignore</button>
                    <button
                      className="btn rose sm"
                      type="button"
                      disabled={Boolean(targetStatus && !draft.job_id)}
                      onClick={() => review(item, "apply")}
                    >
                      Apply
                    </button>
                  </div>
                ) : null}
              </div>

              <div className="gmail-classification-details">
                <strong>Classification details</strong>
                <p>{item.classification_reason || item.reason}</p>
                <p className="muted">
                  {item.classifier_source} · {item.classifier_version || "unversioned"} · {item.automation_outcome || "pending"}
                </p>
                {item.inferred_company || item.inferred_role ? (
                  <p>Inferred: {[item.inferred_company, item.inferred_role].filter(Boolean).join(" · ")}</p>
                ) : null}
                {item.supporting_excerpts.map((excerpt) => <blockquote key={excerpt}>{excerpt}</blockquote>)}
                {item.classifier_error ? <div className="banner-error">{item.classifier_error}</div> : null}
              </div>
              </div>
            </details>
          );
        })}
        {evidence.length === 0 ? <p className="empty">No Gmail evidence yet.</p> : null}
      </div>
    </div>
  );
}
