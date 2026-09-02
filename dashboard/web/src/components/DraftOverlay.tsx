import { useState } from "react";
import { useDraft } from "../lib/draftContext";
import { Angie } from "./Sprite";

const THINKING_LINES = [
  "Reading the job listing",
  "Applying your guidance",
  "Preparing editable CV and letter YAML",
  "Checking guardrails",
];

function ThinkingLine({ mini = false }: { mini?: boolean }) {
  return (
    <span className={`draft-thinking-line ${mini ? "mini" : ""}`} aria-label="Draft generation status">
      {THINKING_LINES.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </span>
  );
}

/** Global draft-creation modal + minimized status chip — one instance, mounted above the router. */
export function DraftOverlay() {
  const { draft, closeForm, generate, minimize, restore, dismiss } = useDraft();
  const [instructions, setInstructions] = useState("");

  if (!draft) return null;

  if (draft.phase === "form") {
    return (
      <div className="modal-backdrop" role="presentation" onClick={closeForm}>
        <section className="draft-modal" role="dialog" aria-modal="true" aria-labelledby="draft-modal-title" onClick={(e) => e.stopPropagation()}>
          <h2 id="draft-modal-title">Create Draft Pack</h2>
          <p className="panel-sub" style={{ marginBottom: 14 }}>
            {draft.title} · {draft.company}
          </p>
          <label className="field">
            Optional guidance for the local draft model
            <textarea
              rows={5}
              placeholder="e.g. Emphasize trade marketing execution over the CRM bullets."
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
            <button className="btn ghost sm" type="button" onClick={closeForm}>Cancel</button>
            <button className="btn rose sm" type="button" onClick={() => generate(instructions)}>Generate draft</button>
          </div>
        </section>
      </div>
    );
  }

  if (draft.phase === "warming") {
    return (
      <div className="modal-backdrop is-busy" role="status" aria-live="polite">
        <section className="draft-loading-card">
          <Angie size="md" />
          <div>
            <h2>Warming up AI engine</h2>
            <p>Loading model into memory — will retry automatically…</p>
          </div>
        </section>
      </div>
    );
  }

  if (draft.phase === "generating" && !draft.minimized) {
    return (
      <div className="modal-backdrop is-busy" role="status" aria-live="polite">
        <section className="draft-loading-card">
          <button type="button" className="draft-minimize-button" onClick={minimize}>Minimize</button>
          <Angie size="md" />
          <div>
            <h2>Generating draft pack</h2>
            <p>{draft.title} · {draft.company}</p>
          </div>
          <ThinkingLine />
          <p className="draft-loading-note">You can minimize this and keep browsing jobs.</p>
        </section>
      </div>
    );
  }

  if (draft.phase === "generating" && draft.minimized) {
    return (
      <aside className="draft-status-chip" role="status" aria-live="polite">
        <button type="button" className="draft-chip-main" onClick={restore} aria-label="Restore draft generation status">
          <Angie size="sm" />
          <div>
            <strong>Generating draft pack</strong>
            <span>{draft.title} · {draft.company}</span>
            <ThinkingLine mini />
          </div>
        </button>
      </aside>
    );
  }

  if (draft.phase === "ready") {
    return (
      <aside className="draft-status-chip is-ready" aria-live="polite">
        <Angie size="sm" />
        <div>
          <strong>Draft pack ready</strong>
          <span>{draft.title} · {draft.company}</span>
        </div>
        <a className="btn sm" href={`/draft?folder=${encodeURIComponent(draft.folderName ?? "")}&jobId=${draft.jobId}`}>
          Open
        </a>
        <button type="button" className="draft-chip-close" onClick={dismiss} aria-label="Dismiss draft status">
          &times;
        </button>
      </aside>
    );
  }

  return (
    <aside className="draft-status-chip is-error" aria-live="polite">
      <Angie size="sm" />
      <div>
        <strong>Draft generation failed</strong>
        <span>{draft.error}</span>
      </div>
      <button type="button" className="draft-chip-close" onClick={dismiss} aria-label="Dismiss draft status">
        &times;
      </button>
    </aside>
  );
}
