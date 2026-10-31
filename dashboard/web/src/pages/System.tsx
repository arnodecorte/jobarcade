import { useState } from "react";
import type { PageProps } from "../App";
import type { Company } from "../lib/api";
import { addCompany, clearDemo, setScraperFeature } from "../lib/api";
import { navigate } from "../lib/hooks";
import { PageHeader } from "../components/PageHeader";
import { CompanyLogo } from "../components/CompanyLogo";
import { GmailEvidencePanel } from "../components/GmailEvidencePanel";
import { IntegrationSettings } from "../components/IntegrationSettings";
import { SystemDisclosure } from "../components/SystemDisclosure";
import { domainFromUrl, faviconUrl } from "../lib/format";
import { RELEASE } from "../lib/releaseNotes";

const HEALTH_RANK: Record<string, number> = { failed: 0, warning: 1, manual_review: 2, unknown: 3, ok: 4 };
const HEALTH_LABEL: Record<string, string> = {
  ok: "Healthy",
  warning: "Needs check",
  failed: "Broken",
  manual_review: "Manual",
  unknown: "Unchecked",
};

function sortCompanies(companies: Company[]): Company[] {
  return [...companies].sort((a, b) => {
    const ra = HEALTH_RANK[a.health?.status || "unknown"] ?? 5;
    const rb = HEALTH_RANK[b.health?.status || "unknown"] ?? 5;
    if (ra !== rb) return ra - rb;
    if (a.scraper_type !== b.scraper_type) return a.scraper_type === "manual_review" ? -1 : 1;
    return a.company.localeCompare(b.company);
  });
}

export function System({ data, reload, refreshing }: PageProps) {
  const { companies, coverage, summary } = data;
  const [msg, setMsg] = useState("");
  const [togglingScraper, setTogglingScraper] = useState(false);
  const [clearingDemo, setClearingDemo] = useState(false);
  const scraperOn = data.integrations.features?.scraper ?? false;
  const demoJobs = data.onboarding.demo_jobs ?? 0;
  const health = summary.scraper_health_counts || {};
  const rows = sortCompanies(companies);

  function rerunSetup() {
    navigate("setup");
  }

  async function removeSampleData() {
    setClearingDemo(true);
    setMsg("");
    try {
      await clearDemo();
      setMsg("Sample data removed.");
      reload();
    } catch (err) {
      setMsg((err as Error).message);
    } finally {
      setClearingDemo(false);
    }
  }

  async function toggleScraper(on: boolean) {
    setTogglingScraper(true);
    try {
      await setScraperFeature(on);
      reload();
    } catch (err) {
      setMsg((err as Error).message);
    } finally {
      setTogglingScraper(false);
    }
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries()) as Record<string, string>;
    const domain = domainFromUrl(body.careers_url || "");
    setMsg("Adding company…");
    try {
      await addCompany({
        company: body.company,
        careers_url: body.careers_url,
        notes: body.notes || "",
        logo_url: faviconUrl(domain),
      });
      form.reset();
      setMsg("Company added.");
      reload();
    } catch (err) {
      setMsg((err as Error).message);
    }
  }


  return (
    <>
      <PageHeader
        kicker="Under the hood"
        title="System"
        sub={scraperOn ? "Scraper coverage, company directory, and the engineering views." : "Settings, integrations and health."}
        onRefresh={reload}
        refreshing={refreshing}
      />

      <div className="system-stack">
        {msg && <p className="muted" role="status" style={{ fontSize: 12.5, margin: 0 }}>{msg}</p>}

        <section className="panel ob-rerun">
          <div>
            <h2>First-run setup</h2>
            <p className="panel-sub">Walk through the AI, profile, CV style and goal steps again. Your data stays as it is until you save.</p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {demoJobs > 0 && (
              <button type="button" className="btn ghost" onClick={removeSampleData} disabled={clearingDemo}>
                {clearingDemo ? "Removing…" : "Remove sample data"}
              </button>
            )}
            <button type="button" className="btn ghost" onClick={rerunSetup}>Re-run setup</button>
          </div>
        </section>

        <section className="panel ob-rerun">
          <div>
            <h2>Features</h2>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={scraperOn}
                disabled={togglingScraper}
                onChange={(e) => toggleScraper(e.target.checked)}
              />
              Experimental: URL scraping (may break on some sites)
            </label>
          </div>
        </section>

        <SystemDisclosure
          title="Gmail intelligence"
          summary={`${data.gmail.metrics.pending_review} need review · ${data.gmail.metrics.auto_applied} auto-applied`}
          status={data.gmail.connected ? "Connected" : "Disconnected"}
        >
          <GmailEvidencePanel gmail={data.gmail} evidence={data.gmailEvidence} jobs={data.jobs} reload={reload} />
        </SystemDisclosure>

        <SystemDisclosure
          title="Integrations"
          summary={`Gmail ${data.integrations.gmail.configured ? "configured" : "needs setup"} · Ollama ${data.integrations.ollama.model}`}
          status={data.integrations.vault.ready ? "Vault ready" : "Check vault"}
        >
          <IntegrationSettings integrations={data.integrations} reload={reload} />
        </SystemDisclosure>

        {scraperOn && (
          <>
            <SystemDisclosure
              title="Companies"
              summary={`${companies.length} tracked · sorted by scraper health`}
              status={`${health.failed || 0} broken`}
            >
              <div className="system-company-list">
              {rows.slice(0, 60).map((c) => (
                <a key={c.company} className="company-row" href={c.careers_url} target="_blank" rel="noreferrer">
                  <CompanyLogo company={c.company} domain={c.logo_domain} url={c.logo_url} size="sm" />
                  <div className="meta">
                    <strong>{c.company}</strong>
                    <span>{c.job_count} roles · {c.health?.strategy || c.scraper_type}</span>
                    {(c.health?.error || c.health?.message) && (
                      <span style={{ color: "var(--rose-deep)" }}>{c.health.error || c.health.message}</span>
                    )}
                  </div>
                  <span className={`health ${c.health?.status || (c.scraper_type === "manual_review" ? "manual_review" : "unknown")}`}>
                    {HEALTH_LABEL[c.health?.status || (c.scraper_type === "manual_review" ? "manual_review" : "unknown")]}
                  </span>
                </a>
              ))}
              </div>
            </SystemDisclosure>

            <SystemDisclosure
              title="Scraper health"
              summary={`${coverage.dedicated} dedicated · ${coverage.manual_review} manual · ${coverage.disabled} disabled`}
              status={`${coverage.promoted_percent}% coverage`}
            >
              <div className="system-compact-metric">
                <div className="metric" style={{ border: "none", boxShadow: "none", padding: "8px 0" }}>
                  <div className="value" style={{ fontSize: 40 }}>{coverage.promoted_percent}%</div>
                  <div className="cap">dedicated scraper coverage</div>
                </div>
                <div className="coverage-meter" aria-label={`${coverage.promoted_percent}% coverage`}>
                  <span style={{ width: `${coverage.promoted_percent}%` }} />
                </div>
                <div className="muted" style={{ fontSize: 12.5 }}>
                  {coverage.dedicated} dedicated · {coverage.manual_review} manual · {coverage.disabled} disabled
                </div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                  {health.failed || 0} broken · {health.warning || 0} need check · {health.ok || 0} healthy
                </div>
              </div>
            </SystemDisclosure>
          </>
        )}

        {scraperOn && (
          <SystemDisclosure title="Add company" summary="Extend the tracked careers directory">
              <form onSubmit={onSubmit}>
                <label className="field">
                  Company
                  <input name="company" required placeholder="e.g. Mollie" />
                </label>
                <label className="field">
                  Careers URL
                  <input name="careers_url" required type="url" placeholder="https://…/careers" />
                </label>
                <label className="field">
                  Notes
                  <textarea name="notes" rows={2} placeholder="Optional" />
                </label>
                <button className="btn rose" type="submit">Add company</button>
                {msg && <p className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>{msg}</p>}
              </form>
          </SystemDisclosure>
        )}

        <SystemDisclosure title="Engineering" summary="Draft-builder tools">
            <p className="panel-sub">The developer surfaces, kept separate from the daily flow.</p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <a className="btn ghost sm" href="/draft">Draft builder →</a>
            </div>
        </SystemDisclosure>

        <SystemDisclosure title="Release notes" summary={RELEASE.date} status={RELEASE.version}>
            <p className="panel-sub">{RELEASE.date}</p>
            <p style={{ fontSize: 12.5, color: "var(--ink-soft)", marginBottom: 12 }}>{RELEASE.intro}</p>
            <div style={{ display: "grid", gap: 6, marginBottom: 12 }}>
              {RELEASE.pages.map((p) => (
                <div key={p.name} style={{ fontSize: 12.5 }}>
                  <strong style={{ color: "var(--ink)" }}>{p.name}</strong>{" "}
                  <span className="muted">— {p.body}</span>
                </div>
              ))}
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>
              {RELEASE.notes.map((n) => (
                <li key={n} style={{ fontSize: 12, color: "var(--ink-soft)" }}>{n}</li>
              ))}
            </ul>
        </SystemDisclosure>
      </div>
    </>
  );
}
