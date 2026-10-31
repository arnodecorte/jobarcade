import { useRef, useState } from "react";
import { addJob, scrapeJobUrl } from "../lib/api";
import { useScraperEnabled } from "../lib/features";
import { EDITABLE_STATUSES, STATUS_LABELS } from "../lib/format";

const ADD_STATUSES = EDITABLE_STATUSES.filter((s) => s !== "skipped" && s !== "expired" && s !== "scrape_failed");

/** "+ Add Job" — lets Angie track a role the scrapers never saw, next to Refresh on every page. */
export function AddJobButton({ onAdded }: { onAdded: () => void }) {
  const scraper = useScraperEnabled();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("new");
  const [scraping, setScraping] = useState(false);
  const [scrapeNote, setScrapeNote] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const showAppliedDate = status === "applied" || status === "interviewing";

  async function onScrape() {
    const form = formRef.current;
    const urlInput = form?.elements.namedItem("apply_url") as HTMLInputElement | null;
    const url = urlInput?.value.trim() || "";
    if (!url) {
      setScrapeNote({ kind: "error", text: "Paste the job posting URL first." });
      return;
    }
    setScraping(true);
    setScrapeNote(null);
    try {
      const res = await scrapeJobUrl(url);
      const fill = (name: string, value: string | null) => {
        const el = form!.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement | null;
        if (el && value) el.value = value;
      };
      fill("company", res.company);
      fill("title", res.title);
      fill("location", res.location);
      fill("notes", res.description);
      setScrapeNote(
        res.warnings.length
          ? { kind: "info", text: res.warnings.join(" ") }
          : { kind: "info", text: "Fields filled from the posting — give them a quick check." },
      );
    } catch (err) {
      setScrapeNote({ kind: "error", text: (err as Error).message });
    } finally {
      setScraping(false);
    }
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries()) as Record<string, string>;
    setBusy(true);
    setError("");
    try {
      await addJob({
        company: body.company,
        title: body.title,
        location: body.location || undefined,
        apply_url: body.apply_url || undefined,
        notes: body.notes || undefined,
        status: body.status,
        applied_at: showAppliedDate ? body.applied_at || undefined : undefined,
      });
      setOpen(false);
      setStatus("new");
      form.reset();
      onAdded();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="btn ghost sm" type="button" onClick={() => setOpen(true)}>
        + Add Job
      </button>
      {open && (
        <div className="modal-backdrop" role="presentation" onClick={() => !busy && !scraping && setOpen(false)}>
          <section className="draft-modal" role="dialog" aria-modal="true" aria-labelledby="add-job-title" onClick={(e) => e.stopPropagation()}>
            <h2 id="add-job-title">Add a job</h2>
            <p className="panel-sub" style={{ marginBottom: 14 }}>
              Found something the scrapers missed? Track it here so it counts.
            </p>
            <form ref={formRef} onSubmit={onSubmit}>
              <label className="field">
                Company
                <input name="company" required placeholder="e.g. Mollie" />
              </label>
              <label className="field">
                Title
                <input name="title" required placeholder="e.g. Brand Manager" />
              </label>
              <label className="field">
                Location
                <input name="location" placeholder="e.g. Amsterdam" />
              </label>
              <label className="field">
                Apply URL
                <div className="add-job-url-row">
                  <input name="apply_url" type="url" placeholder="https://…" />
                  {scraper && (
                    <button
                      className="btn ghost sm add-job-scrape-btn"
                      type="button"
                      onClick={onScrape}
                      disabled={scraping || busy}
                      aria-label={scraping ? "Scraping job posting" : "Scrape job posting"}
                      title={scraping ? "Scraping job posting" : "Scrape job posting"}
                    >
                      <span className="add-job-scrape-label">{scraping ? "Scraping…" : "Scrape"}</span>
                      <span className="add-job-scrape-icon" aria-hidden="true">{scraping ? "…" : "↗"}</span>
                    </button>
                  )}
                </div>
              </label>
              {scraper && scrapeNote && (
                <p className={scrapeNote.kind === "error" ? "banner-error" : "panel-sub"} style={{ marginBottom: 12 }}>
                  {scrapeNote.text}
                </p>
              )}
              <label className="field">
                {scraper ? "Notes" : "Job description"}
                <textarea
                  name="notes"
                  rows={4}
                  placeholder={scraper ? "Optional — the job description lands here and feeds CV drafting" : "Paste the job description — it feeds CV & letter drafting"}
                />
              </label>
              <label className="field">
                Status
                <select name="status" value={status} onChange={(e) => setStatus(e.target.value)}>
                  {ADD_STATUSES.map((s) => (
                    <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                  ))}
                </select>
              </label>
              {showAppliedDate && (
                <label className="field">
                  Date applied (optional — defaults to today)
                  <input name="applied_at" type="date" max={new Date().toISOString().slice(0, 10)} />
                </label>
              )}
              {error && <p className="banner-error" style={{ marginBottom: 12 }}>{error}</p>}
              <div className="add-job-actions">
                <button className="btn ghost sm" type="button" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
                <button className="btn rose sm" type="submit" disabled={busy}>{busy ? "Adding…" : "Add job"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
