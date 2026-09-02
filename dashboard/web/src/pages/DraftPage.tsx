import { useEffect, useState } from "react";
import "../styles/draft.css";
import { Grainient } from "../components/Grainient";
import { Loading } from "../components/Sprite";
import { DraftHeader } from "../components/draft/DraftHeader";
import { DraftTabs, type TabKey } from "../components/draft/DraftTabs";
import { CVEditor, type CvState } from "../components/draft/CVEditor";
import { CVBuilder } from "../components/draft/CVBuilder";
import { ChameleonLaunchCard } from "../components/draft/ChameleonLaunchCard";
import { LetterEditor, type LetterState } from "../components/draft/LetterEditor";
import { RepromptModal } from "../components/draft/RepromptModal";
import { DeleteModal } from "../components/draft/DeleteModal";
import {
  getDraft,
  saveDraft,
  buildApplication,
  extractBrandTheme,
  resetBrandTheme,
  setBrandThemeMode,
  setBrandTypography,
  setBrandUrl,
  markDraftReady,
  type DraftDoc,
  type CvData,
  type LetterData,
} from "../lib/api";
import { uuid } from "../lib/uuid";
import type { SortableRole } from "../components/draft/SortableRoleBlock";

const CHAMELEON_LAUNCH_KEY = "angelica.chameleon.launch.v1";

// ── Converters between API shape and sortable-state shape ──

function toSortableRole(r: {
  role: string;
  company: string;
  period: string;
  location: string;
  include?: boolean;
  bullets: string[];
}): SortableRole {
  return {
    id: uuid(),
    role: r.role ?? "",
    company: r.company ?? "",
    period: r.period ?? "",
    location: r.location ?? "",
    include: r.include !== false,
    bullets: (r.bullets ?? []).map((text) => ({ id: uuid(), text })),
  };
}

function docToCvState(doc: DraftDoc): CvState {
  const variant = doc.cv.variant ?? (doc.cv.max_pages <= 1 ? "compact_one_page" : "classic_two_page");
  return {
    max_pages: doc.cv.max_pages ?? (variant === "compact_one_page" || variant === "grotesk_one_page" ? 1 : 2),
    variant,
    role_focus: doc.cv.role_focus ?? "",
    title: doc.cv.title ?? "",
    tagline: doc.cv.tagline ?? "",
    profile: doc.cv.profile ?? "",
    selected_highlights: doc.cv.selected_highlights ?? [],
    experience: (doc.cv.experience ?? []).map(toSortableRole),
    additional: (doc.cv.additional ?? []).map(toSortableRole),
  };
}

function docToLetterState(doc: DraftDoc): LetterState {
  return {
    subtitle: doc.letter.subtitle ?? "",
    paragraphs: (doc.letter.paragraphs ?? []).map((text) => ({
      id: uuid(),
      text,
    })),
  };
}

function cvStateToPayload(cv: CvState): CvData {
  return {
    max_pages: cv.max_pages,
    variant: cv.variant,
    role_focus: cv.role_focus,
    title: cv.title,
    tagline: cv.tagline,
    profile: cv.profile,
    selected_highlights: cv.selected_highlights.filter(Boolean),
    experience: cv.experience.map((r) => ({
      role: r.role,
      company: r.company,
      period: r.period,
      location: r.location,
      include: r.include,
      bullets: r.bullets.map((b) => b.text).filter(Boolean),
    })),
    additional: cv.additional.map((r) => ({
      role: r.role,
      company: r.company,
      period: r.period,
      location: r.location,
      include: r.include,
      bullets: r.bullets.map((b) => b.text).filter(Boolean),
    })),
  };
}

function letterStateToPayload(letter: LetterState): LetterData {
  return {
    max_pages: 1,
    subtitle: letter.subtitle,
    paragraphs: letter.paragraphs.map((p) => p.text).filter(Boolean),
  };
}

// ── Page component ──

export function DraftPage() {
  const params = new URLSearchParams(window.location.search);
  const folder = params.get("folder") ?? "";
  const jobId = params.get("jobId") ? Number(params.get("jobId")) : undefined;

  const [doc, setDoc] = useState<DraftDoc | null>(null);
  const [cvState, setCvState] = useState<CvState | null>(null);
  const [letterState, setLetterState] = useState<LetterState | null>(null);
  const [tab, setTab] = useState<TabKey>("builder");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [brandBusy, setBrandBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [showChameleonLaunch, setShowChameleonLaunch] = useState(() => localStorage.getItem(CHAMELEON_LAUNCH_KEY) !== "dismissed");
  const [buildAt, setBuildAt] = useState(0);
  const [repromptOpen, setRepromptOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!folder) {
      setLoadError("No folder specified.");
      return;
    }
    getDraft(folder)
      .then((d) => {
        setDoc(d);
        setCvState(docToCvState(d));
        setLetterState(docToLetterState(d));
      })
      .catch((err) => setLoadError((err as Error).message));
  }, [folder]);

  function applyDoc(d: DraftDoc) {
    setDoc(d);
    setCvState(docToCvState(d));
    setLetterState(docToLetterState(d));
    setDirty(false);
  }

  function dismissChameleonLaunch() {
    localStorage.setItem(CHAMELEON_LAUNCH_KEY, "dismissed");
    setShowChameleonLaunch(false);
  }

  function focusChameleonPanel() {
    setTab("builder");
    dismissChameleonLaunch();
    window.setTimeout(() => {
      document.getElementById("chameleon-panel")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
  }

  async function handleSave() {
    if (!cvState || !letterState || !folder) return;
    setBusy(true);
    setStatusMsg("Saving…");
    try {
      const d = await saveDraft(folder, {
        cv: cvStateToPayload(cvState),
        letter: letterStateToPayload(letterState),
      });
      applyDoc(d);
      setStatusMsg("Draft saved.");
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleBuild() {
    if (!cvState || !letterState || !folder) return;
    const hasExisting = doc?.artifact?.has_cv || doc?.artifact?.has_letter;
    if (hasExisting) {
      if (!window.confirm("This will overwrite the existing CV and letter PDFs. Continue?")) return;
    }
    setBusy(true);
    setStatusMsg("Saving…");
    try {
      await saveDraft(folder, {
        cv: cvStateToPayload(cvState),
        letter: letterStateToPayload(letterState),
      });
      setStatusMsg("Building PDFs…");
      const result = await buildApplication(folder);
      setDoc((d) => (d ? { ...d, artifact: result.artifact } : d));
      if (result.ok) {
        setBuildAt(Date.now());
        setStatusMsg("Build complete — switch to Preview to view.");
      } else {
        setStatusMsg(result.error ?? "Build failed.");
      }
      setDirty(false);
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleExtractBrandTheme() {
    if (!folder) return;
    setBusy(true);
    setBrandBusy(true);
    setStatusMsg("Extracting company branding…");
    try {
      const result = await extractBrandTheme(folder, { ...(jobId ? { job_id: jobId } : {}), provider: "auto" });
      setDoc((d) => (d ? { ...d, brand_theme: result.brand_theme, brand_source: result.brand_source } : d));
      setStatusMsg(result.brand_theme.enabled ? "Chameleon theme ready. Build PDFs to preview it." : "No strong brand theme found; using base.");
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBrandBusy(false);
      setBusy(false);
    }
  }

  async function handleSetBrandUrl(brandUrl: string) {
    if (!folder) return;
    setBusy(true);
    setStatusMsg(brandUrl.trim() ? "Saving brand URL…" : "Clearing brand URL override…");
    try {
      const result = await setBrandUrl(folder, brandUrl);
      setDoc((d) => (d ? { ...d, brand_source: result.brand_source } : d));
      setStatusMsg("Brand URL saved. Extract the Chameleon theme to use it.");
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleResetBrandTheme() {
    if (!folder) return;
    setBusy(true);
    setStatusMsg("Resetting to base theme…");
    try {
      const result = await resetBrandTheme(folder);
      setDoc((d) => (d ? { ...d, brand_theme: result.brand_theme } : d));
      setStatusMsg("Base theme selected. Build PDFs to refresh output.");
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSetBrandThemeMode(mode: "light" | "dark") {
    if (!folder) return;
    setBusy(true);
    setStatusMsg(mode === "dark" ? "Selecting dark Chameleon mode…" : "Selecting light Chameleon mode…");
    try {
      const result = await setBrandThemeMode(folder, mode);
      setDoc((d) => (d ? { ...d, brand_theme: result.brand_theme } : d));
      setStatusMsg(
        mode === "dark"
          ? "Dark Chameleon selected. Build PDFs to preview it."
          : "Light Chameleon selected. Build PDFs to preview it."
      );
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSetBrandTypography(enabled: boolean) {
    if (!folder) return;
    setBusy(true);
    setStatusMsg(enabled ? "Applying Chameleon typography…" : "Turning Chameleon typography off…");
    try {
      const result = await setBrandTypography(folder, enabled);
      setDoc((d) => (d ? { ...d, brand_theme: result.brand_theme } : d));
      setStatusMsg(
        enabled
          ? "Chameleon typography selected. Build PDFs to preview it."
          : "Default CV typography selected. Build PDFs to refresh output."
      );
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleMarkReady() {
    if (!folder) return;
    setBusy(true);
    setStatusMsg("Marking as ready for review…");
    try {
      await markDraftReady(folder, jobId);
      window.location.href = jobId ? `/#/jobs/job-${jobId}` : "/";
    } catch (err) {
      setStatusMsg((err as Error).message);
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className="draft-page">
        <Grainient />
        <div className="draft-canvas">
          <p className="draft-error">{loadError}</p>
          <a className="btn ghost sm" href="/">
            ← Dashboard
          </a>
        </div>
      </div>
    );
  }

  if (!doc || !cvState || !letterState) {
    return (
      <div className="draft-page">
        <Grainient />
        <Loading message="Loading draft…" />
      </div>
    );
  }

  return (
    <div className="draft-page">
      <Grainient />
      <DraftHeader
        folder={folder}
        dirty={dirty}
        busy={busy}
        onSave={handleSave}
        onBuild={handleBuild}
        onMarkReady={handleMarkReady}
        onReprompt={() => setRepromptOpen(true)}
        onDelete={() => setDeleteOpen(true)}
      />
      <div className="draft-canvas">
        {statusMsg && <p className="draft-status-msg">{statusMsg}</p>}
        {doc.warnings.length > 0 && (
          <ul className="draft-warnings">
            {doc.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
        {showChameleonLaunch && <ChameleonLaunchCard onTry={focusChameleonPanel} onDismiss={dismissChameleonLaunch} />}
        <DraftTabs active={tab} onChange={setTab} />
        {tab === "builder" && (
          <CVBuilder
            cv={cvState}
            limits={doc.limits}
            review={doc.cv_review}
            brandTheme={doc.brand_theme}
            brandSource={doc.brand_source}
            busy={busy}
            brandBusy={brandBusy}
            onExtractBrandTheme={handleExtractBrandTheme}
            onResetBrandTheme={handleResetBrandTheme}
            onSetBrandThemeMode={handleSetBrandThemeMode}
            onSetBrandTypography={handleSetBrandTypography}
            onSetBrandUrl={handleSetBrandUrl}
            onChange={(cv) => {
              setCvState(cv);
              setDirty(true);
            }}
          />
        )}
        {tab === "cv" && (
          <CVEditor
            cv={cvState}
            limits={doc.limits}
            onChange={(cv) => {
              setCvState(cv);
              setDirty(true);
            }}
          />
        )}
        {tab === "letter" && (
          <LetterEditor
            letter={letterState}
            limits={doc.limits}
            onChange={(letter) => {
              setLetterState(letter);
              setDirty(true);
            }}
          />
        )}
        {tab === "listing" && (
          <pre className="listing-preview">{doc.listing || "(No listing saved)"}</pre>
        )}
        {tab === "preview" &&
          (doc.artifact?.has_cv || doc.artifact?.has_letter ? (
            <div className="preview-grid">
              {doc.artifact.has_cv && (
                <iframe
                  key={`cv-${buildAt}`}
                  title="CV preview"
                  src={`/applications/${encodeURIComponent(folder)}/cv.pdf?v=${buildAt}`}
                />
              )}
              {doc.artifact.has_letter && (
                <iframe
                  key={`letter-${buildAt}`}
                  title="Letter preview"
                  src={`/applications/${encodeURIComponent(folder)}/motivation-letter.pdf?v=${buildAt}`}
                />
              )}
            </div>
          ) : (
            <p className="draft-status-msg">Build the PDFs to preview them here.</p>
          ))}
      </div>

      {repromptOpen && (
        <RepromptModal
          folder={folder}
          jobId={jobId}
          currentCv={cvState}
          currentLetter={letterState}
          onSuccess={(d) => {
            applyDoc(d);
            setRepromptOpen(false);
            setStatusMsg("Draft reprompted.");
          }}
          onClose={() => setRepromptOpen(false)}
        />
      )}
      {deleteOpen && (
        <DeleteModal
          folder={folder}
          jobId={jobId}
          onSuccess={() => {
            window.location.href = "/";
          }}
          onClose={() => setDeleteOpen(false)}
        />
      )}
    </div>
  );
}
