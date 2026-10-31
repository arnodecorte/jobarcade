import { useEffect, useRef, useState } from "react";
import { getStyle, previewStyle, saveStyle } from "../../lib/api";
import type { StyleState } from "../../lib/api";
import { StepFooter, StepHead } from "./StepFooter";
import type { StepProps } from "./types";

const VARIANT_INFO: Record<string, [string, string]> = {
  grotesk_one_page: ["Grotesk", "Compact single page. The default."],
  compact_one_page: ["Compact", "Dense single page with a sidebar."],
  classic_two_page: ["Classic", "Traditional two pages."],
  enriched_two_page: ["Enriched", "Two pages with expanded impact."],
};
// Deep tones only: the server rejects or darkens pale accents.
const SWATCHES = ["#950E25", "#82213E", "#422B78", "#205C83", "#177854", "#9B4808"]; // already contrast-safe, so the server returns them unchanged

export function StyleStep({ onBack, onSkip, onContinue, reload }: StepProps) {
  const [style, setStyle] = useState<StyleState | null>(null);
  const [loadError, setLoadError] = useState("");
  const [preview, setPreview] = useState("");
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "error">("idle");
  const [previewError, setPreviewError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const urlRef = useRef("");

  useEffect(() => {
    getStyle().then(setStyle).catch((e) => setLoadError((e as Error).message));
  }, []);

  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);

  useEffect(() => {
    if (!style) return;
    const ctrl = new AbortController();
    setPreviewState("loading");
    const timer = window.setTimeout(() => {
      previewStyle({ cv_variant: style.cv_variant, accent: style.accent, font: style.font, mode: style.mode }, ctrl.signal)
        .then((blob) => {
          const next = URL.createObjectURL(blob);
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = next;
          setPreview(next);
          setPreviewState("idle");
        })
        .catch((e) => {
          if ((e as Error).name === "AbortError") return;
          setPreviewState("error");
          setPreviewError((e as Error).message);
        });
    }, 600);
    return () => {
      window.clearTimeout(timer);
      ctrl.abort();
    };
  }, [style?.cv_variant, style?.accent, style?.font, style?.mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (p: Partial<StyleState>) => { setStyle((s) => (s ? { ...s, ...p } : s)); setError(""); };

  async function save() {
    if (!style) return;
    setSaving(true);
    setError("");
    try {
      const saved = await saveStyle({ cv_variant: style.cv_variant, accent: style.accent, font: style.font, mode: style.mode });
      setStyle({ ...style, ...saved }); // the server may deepen the accent for contrast
      reload();
      await onContinue();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <StepHead
        kicker="Step 3 · Your CV look"
        title="Pick a default style"
        sub="Every new draft starts here. You can still change it per application, and the Chameleon can match a company's brand."
      />
      {loadError && <p className="ob-error" role="alert">{loadError}</p>}
      {style && (
        <div className="ob-style">
          <div className="ob-body">
            <div className="ob-variants" role="radiogroup" aria-label="CV layout">
              {style.variants.map((v) => {
                const [label, blurb] = VARIANT_INFO[v] || [v, ""];
                return (
                  <button
                    key={v} type="button" role="radio" aria-checked={style.cv_variant === v}
                    className={`ob-variant${style.cv_variant === v ? " active" : ""}`}
                    onClick={() => patch({ cv_variant: v })}
                  >
                    <strong>{label}</strong>
                    <span>{blurb}</span>
                  </button>
                );
              })}
            </div>
            <div className="field">
              Accent colour
              <div className="ob-swatches">
                {SWATCHES.map((c) => (
                  <button
                    key={c} type="button" aria-label={`Use ${c}`} title={c}
                    className={`ob-swatch${style.accent.toLowerCase() === c.toLowerCase() ? " active" : ""}`}
                    style={{ background: c }} onClick={() => patch({ accent: c })}
                  />
                ))}
                <input type="color" aria-label="Custom accent colour" value={/^#[0-9a-f]{6}$/i.test(style.accent) ? style.accent : "#d65b80"} onChange={(e) => patch({ accent: e.target.value })} />
                <code>{style.accent}</code>
              </div>
            </div>
            <div className="ob-grid2">
              <label className="field">
                Font
                <select value={style.font} onChange={(e) => patch({ font: e.target.value })}>
                  {style.fonts.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </label>
              <div className="field">
                Theme
                <div className="ob-toggle" role="radiogroup" aria-label="Theme">
                  {(["light", "dark"] as const).map((m) => (
                    <button key={m} type="button" role="radio" aria-checked={style.mode === m} className={style.mode === m ? "active" : ""} onClick={() => patch({ mode: m })}>
                      {m === "light" ? "Light" : "Dark"}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {error && <p className="ob-error" role="alert">{error}</p>}
          </div>
          <div className="ob-preview" aria-live="polite">
            {preview && <img src={preview} alt="Preview of your CV" className={previewState === "loading" ? "dim" : ""} />}
            {!preview && previewState === "loading" && <p className="ob-note">Rendering preview…</p>}
            {previewState === "error" && <p className="ob-error">{previewError}</p>}
          </div>
        </div>
      )}
      <StepFooter onBack={onBack} onSkip={onSkip} onContinue={save} busy={saving} continueDisabled={!style} />
    </>
  );
}
