import { useState } from "react";
import { Dice } from "../Sprite";
import { repromptDraft, warmupOllama, type DraftDoc, type CvData, type LetterData } from "../../lib/api";
import type { CvState } from "./CVEditor";
import type { LetterState } from "./LetterEditor";

type Props = {
  folder: string;
  jobId?: number;
  currentCv: CvState;
  currentLetter: LetterState;
  onSuccess: (doc: DraftDoc) => void;
  onClose: () => void;
};

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

export function RepromptModal({
  folder,
  jobId,
  currentCv,
  currentLetter,
  onSuccess,
  onClose,
}: Props) {
  const [mode, setMode] = useState<"fresh" | "refine">("refine");
  const [instructions, setInstructions] = useState("");
  const [generating, setGenerating] = useState(false);
  const [warming, setWarming] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate() {
    setGenerating(true);
    setWarming(false);
    setError("");
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const body =
          mode === "fresh"
            ? { mode: "fresh" as const, instructions, job_id: jobId }
            : {
                mode: "refine" as const,
                instructions,
                current_draft: {
                  cv: cvStateToPayload(currentCv),
                  letter: letterStateToPayload(currentLetter),
                },
              };
        const doc = await repromptDraft(folder, body);
        onSuccess(doc);
        return;
      } catch (err) {
        const msg = (err as Error).message;
        if (attempt === 0 && msg === "Failed to fetch") {
          setWarming(true);
          await warmupOllama().catch(() => {});
          await new Promise((r) => setTimeout(r, 20000));
          setWarming(false);
          continue;
        }
        setError(msg);
        setGenerating(false);
        return;
      }
    }
  }

  if (generating) {
    return (
      <div className="modal-backdrop is-busy" role="status" aria-live="polite">
        <section className="draft-loading-card">
          <Dice size="md" state="work" />
          <div>
            <h2>{warming ? "Warming up AI engine" : "Reprompting draft"}</h2>
            <p>
              {warming
                ? "Loading model into memory — will retry automatically…"
                : mode === "fresh"
                  ? "Generating fresh draft…"
                  : "Refining current draft…"}
            </p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="draft-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reprompt-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="reprompt-title">Reprompt this draft</h2>

        <fieldset className="reprompt-modes">
          <legend className="field-label">Mode</legend>
          {(["fresh", "refine"] as const).map((m) => (
            <label key={m} className="reprompt-mode-option">
              <input
                type="radio"
                name="reprompt-mode"
                value={m}
                checked={mode === m}
                onChange={() => setMode(m)}
              />
              <div>
                <strong>{m === "fresh" ? "Fresh start" : "Refine"}</strong>
                <p className="panel-sub" style={{ margin: "2px 0 0" }}>
                  {m === "fresh"
                    ? "Ignore current edits — generate a new draft from the job listing."
                    : "Use my current edits as context; ask Ollama to improve with these instructions."}
                </p>
              </div>
            </label>
          ))}
        </fieldset>

        <label className="field">
          Instructions (optional)
          <textarea
            rows={4}
            placeholder="e.g. Emphasize the LEGO retail experience more prominently"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>

        {error && <p className="draft-error">{error}</p>}

        <div className="draft-modal-actions">
          <button type="button" className="btn ghost sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn rose sm" onClick={handleGenerate}>
            Generate →
          </button>
        </div>
      </section>
    </div>
  );
}
