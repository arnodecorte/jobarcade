import { type FormEvent, useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { PageProps } from "../App";
import type { CompanyCandidate, CompanyCandidateStats } from "../lib/api";
import { addCompanyCandidateToScrapers, decideCompanyCandidate, getCompanyCandidates, resolveCompanyCandidateCareersUrl, suggestCompanyCandidateCareersUrl } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { PageHeader } from "../components/PageHeader";
import { CompanyLogo } from "../components/CompanyLogo";

const ACTIVE = new Set(["new", "maybe"]);

function displaySourceType(candidate: CompanyCandidate) {
  return (candidate.source_type || "curated").replace(/_/g, " ");
}

function Icon({ type }: { type: "hide" | "maybe" | "add" | "open" | "resolve" | "edit" }) {
  const paths = {
    hide: <path d="M6 6l12 12M18 6 6 18" />,
    maybe: <path d="M7 6.5c0-1.4 1.2-2.5 2.8-2.5 1.5 0 2.7 1 2.7 2.4 0 2.8-3.5 2.6-3.5 5.1M12 19h.01M17 7h3m-1.5-1.5v3" />,
    add: <path d="m5 12 4 4L19 6" />,
    open: <path d="M8 6h10v10M18 6 7 17M6 10v8h8" />,
    resolve: <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />,
    edit: <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />,
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[type]}
    </svg>
  );
}

function nextActive(candidates: CompanyCandidate[]) {
  return (
    candidates.find((candidate) => candidate.status === "new" && !candidate.is_tracked) ||
    candidates.find((candidate) => candidate.status === "maybe" && !candidate.is_tracked)
  );
}

function candidateTags(candidate: CompanyCandidate) {
  return [
    candidate.location_hint,
    ...candidate.industry_tags.slice(0, 2),
    ...candidate.aspiration_tags.slice(0, 1),
  ].filter(Boolean) as string[];
}

function displayUrl(candidate: CompanyCandidate) {
  const raw = candidate.careers_url || candidate.website_url || "";
  try {
    const url = new URL(raw);
    return `${url.hostname.replace(/^www\./, "")}${url.pathname === "/" ? "" : url.pathname}`;
  } catch {
    return raw || "No URL";
  }
}

function statsAfterFilter(stats: CompanyCandidateStats | undefined, candidates: CompanyCandidate[]) {
  if (stats) return stats;
  return candidates.reduce<CompanyCandidateStats>(
    (acc, candidate) => {
      if (candidate.status in acc) acc[candidate.status as keyof CompanyCandidateStats] += 1;
      if (ACTIVE.has(candidate.status)) acc.active += 1;
      return acc;
    },
    { new: 0, maybe: 0, added: 0, rejected: 0, hidden: 0, active: 0 }
  );
}

function EvidenceRail({ candidate, onResolve }: { candidate: CompanyCandidate; onResolve: () => void }) {
  return (
    <aside className="discover-evidence panel">
      <section>
        <h2>Why this surfaced</h2>
        <div className="evidence-list">
          {candidate.score_reasons.map((reason) => <span key={reason}>{reason}</span>)}
        </div>
      </section>
      <section>
        <h2>Role signals</h2>
        <div className="evidence-list">
          {candidate.role_signals.map((signal) => <span key={signal}>{signal}</span>)}
        </div>
      </section>
      <section>
        <h2>Scraper path</h2>
        <div className="candidate-url-line">
          <span>{displayUrl(candidate)}</span>
          <button type="button" className="icon-btn mini" onClick={onResolve} title="Edit careers URL" aria-label={`Edit careers URL for ${candidate.company}`}>
            <Icon type="edit" />
          </button>
        </div>
        <p>
          {candidate.needs_careers_url
            ? "Resolve the real careers page first, then add as manual review."
            : "Add as manual review first. A deterministic scraper can be promoted after a targeted smoke test."}
        </p>
        <div className="evidence-actions">
          <button type="button" className="btn ghost sm" onClick={onResolve}>
            {candidate.needs_careers_url ? "Resolve URL" : "Edit URL"}
          </button>
        </div>
      </section>
      {candidate.source_names.length > 0 && (
        <section>
          <h2>Sources · {displaySourceType(candidate)}</h2>
          <div className="evidence-list compact">
            {candidate.source_names.map((source) => <span key={source}>{source}</span>)}
          </div>
        </section>
      )}
    </aside>
  );
}

function CandidateCard({
  candidate,
  busy,
  onDecision,
  onAdd,
  onResolve,
}: {
  candidate: CompanyCandidate;
  busy: boolean;
  onDecision: (status: "maybe" | "rejected" | "hidden") => void;
  onAdd: () => void;
  onResolve: () => void;
}) {
  const tags = candidateTags(candidate);
  return (
    <motion.section
      className="discover-card"
      initial={{ opacity: 0, y: 16, rotate: -1 }}
      animate={{ opacity: 1, y: 0, rotate: -0.6 }}
      transition={{ type: "spring", stiffness: 190, damping: 20 }}
    >
      <div className="discover-card-top">
        <CompanyLogo company={candidate.company} domain={candidate.logo_domain} url={candidate.logo_url} />
        <div className="discover-score">
          <strong>{candidate.score}</strong>
          <span>fit</span>
        </div>
      </div>
      <div className="discover-card-main">
        <h2>{candidate.company}</h2>
        <p>{candidate.notes || "A Netherlands-footprint employer with signals worth reviewing."}</p>
        <div className="candidate-url-line card-url">
          <span>{displayUrl(candidate)}</span>
          <button type="button" className="icon-btn mini" onClick={onResolve} disabled={busy} title="Edit careers URL" aria-label={`Edit careers URL for ${candidate.company}`}>
            <Icon type="edit" />
          </button>
        </div>
        <div className="chips">
          {tags.map((tag) => <span className="pill" key={tag}>{tag}</span>)}
        </div>
      </div>
      <div className="discover-proof">
        {candidate.score_reasons.slice(0, 3).map((reason) => (
          <span key={reason}>{reason}</span>
        ))}
      </div>
      <div className="discover-actions" aria-label={`Actions for ${candidate.company}`}>
        <button className="discover-action reject" type="button" disabled={busy} onClick={() => onDecision("rejected")} title="Reject">
          <Icon type="hide" />
          <span>Reject</span>
        </button>
        <button className="discover-action maybe" type="button" disabled={busy} onClick={() => onDecision("maybe")} title="Maybe">
          <Icon type="maybe" />
          <span>Maybe</span>
        </button>
        <button
          className={`discover-action ${candidate.needs_careers_url ? "resolve" : "add"}`}
          type="button"
          disabled={busy}
          onClick={candidate.needs_careers_url ? onResolve : onAdd}
          title={candidate.needs_careers_url ? "Resolve careers URL" : "Add to scrapers"}
        >
          <Icon type={candidate.needs_careers_url ? "resolve" : "add"} />
          <span>{candidate.needs_careers_url ? "Resolve" : "Add"}</span>
        </button>
        <a className="discover-action open" href={candidate.careers_url || candidate.website_url || "#"} target="_blank" rel="noreferrer" title="Open careers">
          <Icon type="open" />
          <span>Careers</span>
        </a>
      </div>
    </motion.section>
  );
}

export function Discover({ reload }: PageProps) {
  const { data, error, loading, reload: reloadCandidates } = useAsync(getCompanyCandidates);
  const [local, setLocal] = useState<CompanyCandidate[] | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [resolver, setResolver] = useState<CompanyCandidate | null>(null);
  const [careersUrl, setCareersUrl] = useState("");
  const [autofixMessage, setAutofixMessage] = useState("");
  const [autofixingId, setAutofixingId] = useState<number | null>(null);
  const candidates = local ?? data?.candidates ?? [];
  const stats = statsAfterFilter(local ? undefined : data?.stats, candidates);
  const active = useMemo(() => nextActive(candidates), [candidates]);
  const upcoming = candidates.filter((candidate) => candidate.id !== active?.id && ACTIVE.has(candidate.status)).slice(0, 3);

  function patchCandidate(id: number, updates: Partial<CompanyCandidate>) {
    setLocal((current) => (current ?? candidates).map((candidate) => candidate.id === id ? { ...candidate, ...updates } : candidate));
  }

  async function decide(status: "maybe" | "rejected" | "hidden") {
    if (!active) return;
    setBusyId(active.id);
    setMessage("");
    try {
      await decideCompanyCandidate(active.id, status);
      patchCandidate(active.id, { status });
      setMessage(status === "maybe" ? "Saved for later." : "Candidate moved out of the deck.");
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function add() {
    if (!active) return;
    if (active.needs_careers_url) {
      setResolver(active);
      setCareersUrl("");
      setMessage("");
      return;
    }
    setBusyId(active.id);
    setMessage("");
    try {
      await addCompanyCandidateToScrapers(active.id);
      patchCandidate(active.id, { status: "added", is_tracked: true });
      setMessage(`${active.company} added to the scraper wishlist.`);
      reload();
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  function openResolver(candidate: CompanyCandidate) {
    setResolver(candidate);
    setCareersUrl(candidate.careers_url || candidate.suggested_careers_url || "");
    setAutofixMessage(
      !candidate.careers_url && candidate.suggested_careers_url
        ? `Pre-filled guess: ${candidate.suggested_careers_url_reason || "matched a likely careers page"}. Confirm or correct it.`
        : ""
    );
    setMessage("");
  }

  async function autofixCareersUrl() {
    if (!resolver) return;
    setAutofixingId(resolver.id);
    setAutofixMessage("Testing likely careers URLs...");
    setMessage("");
    try {
      const result = await suggestCompanyCandidateCareersUrl(resolver.id);
      if (result.suggestion) {
        setCareersUrl(result.suggestion.final_url || result.suggestion.url);
        setAutofixMessage(`Suggested ${displayUrl({ ...resolver, careers_url: result.suggestion.final_url || result.suggestion.url })} (${result.suggestion.reason}).`);
      } else {
        setAutofixMessage(`No strong careers URL found after ${result.attempts.length} checks.`);
      }
    } catch (err) {
      setAutofixMessage((err as Error).message);
    } finally {
      setAutofixingId(null);
    }
  }

  async function resolveCareersUrl(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resolver) return;
    setBusyId(resolver.id);
    setMessage("");
    try {
      const result = await resolveCompanyCandidateCareersUrl(resolver.id, careersUrl);
      patchCandidate(resolver.id, {
        careers_url: result.careers_url,
        needs_careers_url: result.needs_careers_url,
      });
      setResolver(null);
      setCareersUrl("");
      setMessage(`${resolver.company} careers URL saved.`);
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageHeader
        kicker="Company sourcing"
        title="Discover"
        sub="Keep the company pool warm."
        onRefresh={() => {
          setLocal(null);
          reloadCandidates();
        }}
        refreshing={loading}
      />

      {error && <div className="banner-error">Could not load company candidates: {error}</div>}

      <div className="discover-stats">
        <div className="metric blue"><div className="label">New candidates</div><div className="value">{stats.new}</div><div className="cap">ready to review</div></div>
        <div className="metric butter"><div className="label">Maybe</div><div className="value">{stats.maybe}</div><div className="cap">saved for later</div></div>
        <div className="metric mint"><div className="label">Added</div><div className="value">{stats.added}</div><div className="cap">in scraper list</div></div>
        <div className="metric coral"><div className="label">Hidden</div><div className="value">{stats.rejected + stats.hidden}</div><div className="cap">out of rotation</div></div>
      </div>

      {!active && !loading && (
        <section className="panel discover-empty">
          <h2>No active candidates</h2>
          <p className="panel-sub">Import more curated seeds with <code>python -m jobhunt discover-companies --seed data/company-seeds.yaml</code>.</p>
        </section>
      )}

      {active && (
        <div className="discover-layout">
          <div className="discover-stage">
            <CandidateCard candidate={active} busy={busyId === active.id} onDecision={decide} onAdd={add} onResolve={() => openResolver(active)} />
            {message && <p className="discover-message">{message}</p>}
            <section className="discover-mobile-evidence">
              <EvidenceRail candidate={active} onResolve={() => openResolver(active)} />
            </section>
            <section className="panel discover-queue">
              <h2>Up next</h2>
              {upcoming.length === 0 ? <p className="empty">No more active candidates in this queue.</p> : upcoming.map((candidate) => (
                <div className="discover-queue-row" key={candidate.id}>
                  <CompanyLogo company={candidate.company} domain={candidate.logo_domain} url={candidate.logo_url} size="sm" />
                  <div>
                    <strong>{candidate.company}</strong>
                    <span>{candidate.location_hint || "Netherlands"} · {candidate.industry_tags[0] || "Company"}</span>
                  </div>
                  <button type="button" className="icon-btn mini" onClick={() => openResolver(candidate)} title="Edit careers URL" aria-label={`Edit careers URL for ${candidate.company}`}>
                    <Icon type="edit" />
                  </button>
                  <b>{candidate.score}</b>
                </div>
              ))}
            </section>
          </div>
          <EvidenceRail candidate={active} onResolve={() => openResolver(active)} />
        </div>
      )}
      {resolver && (
        <div className="modal-backdrop" role="presentation" onClick={() => busyId !== resolver.id && setResolver(null)}>
          <form className="draft-modal resolve-modal" role="dialog" aria-modal="true" aria-labelledby="resolve-title" onSubmit={resolveCareersUrl} onClick={(e) => e.stopPropagation()}>
            <div className="followup-modal-header">
              <strong id="resolve-title">{resolver.needs_careers_url ? "Resolve careers URL" : "Edit careers URL"}</strong>
              <span className="followup-modal-sub">{resolver.company}</span>
            </div>
            <label className="field">
              Careers URL
              <input
                type="url"
                required
                value={careersUrl}
                placeholder="https://company.com/careers"
                onChange={(event) => setCareersUrl(event.target.value)}
                disabled={busyId === resolver.id}
              />
            </label>
            <div className="resolve-hint">
              Paste the real careers page. Search-result URLs are blocked from scraper promotion.
            </div>
            {autofixMessage && <div className="resolve-autofix-message">{autofixMessage}</div>}
            <div className="followup-modal-actions">
              <button className="btn ghost sm" type="button" onClick={autofixCareersUrl} disabled={busyId === resolver.id || autofixingId === resolver.id}>
                {autofixingId === resolver.id ? "Testing..." : "Autofix"}
              </button>
              <button className="btn ghost sm" type="button" onClick={() => setResolver(null)} disabled={busyId === resolver.id}>Cancel</button>
              <button className="btn rose sm" type="submit" disabled={busyId === resolver.id}>Save URL</button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
