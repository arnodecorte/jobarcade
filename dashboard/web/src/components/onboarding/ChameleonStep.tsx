import { useState } from "react";
import { saveFirecrawlKey, testFirecrawl } from "../../lib/api";
import { ChameleonMascotAnimation } from "../draft/ChameleonMascotAnimation";
import { StepFooter, StepHead } from "./StepFooter";
import type { StepProps } from "./types";

type Result = { ok: boolean; accent?: string; dark_recommended?: boolean; error?: string };

export function ChameleonStep({ integrations, onBack, onSkip, onContinue, reload }: StepProps) {
  const configured = !!integrations.firecrawl?.configured;
  const [key, setKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  async function tryIt() {
    setTesting(true);
    setError("");
    try {
      if (key.trim()) {
        await saveFirecrawlKey(key.trim());
        setKey("");
        reload();
      }
      setResult(await testFirecrawl("https://www.netflix.com"));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      if (key.trim()) {
        await saveFirecrawlKey(key.trim());
        reload();
      }
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
        kicker="Step 4 · The Chameleon"
        title="Dress each CV in the company's colours"
        sub="With a Firecrawl key, the Chameleon reads a company's website and tints your CV and letter to match its brand. It's optional, and your CV looks great without it."
      />
      <div className="ob-body ob-chameleon">
        <ChameleonMascotAnimation compact />
        <div>
          <p className="ob-note">
            <a href="https://www.firecrawl.dev/" target="_blank" rel="noreferrer" className="btn ghost sm">Get a free Firecrawl key</a>
            {" "}The free tier comfortably covers one person's applications.
          </p>
          <label className="field">
            Firecrawl API key
            <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={configured ? "Saved. Type to replace" : "fc-…"} />
          </label>
          <div className="ob-row">
            <button type="button" className="btn ghost" onClick={tryIt} disabled={testing || (!key.trim() && !configured)}>
              {testing ? "Reading netflix.com…" : "Try it on Netflix"}
            </button>
            {result?.ok && result.accent && (
              <span className="ob-result">
                <span className="ob-swatch static" style={{ background: result.accent }} aria-hidden="true" />
                <code>{result.accent}</code>
                {result.dark_recommended && <span className="pill" style={{ background: "var(--berry-soft)", color: "var(--berry-deep)" }}>dark theme recommended</span>}
              </span>
            )}
          </div>
          {result && !result.ok && <p className="ob-error" role="alert">{result.error || "That did not work. Check the key and try again."}</p>}
          {error && <p className="ob-error" role="alert">{error}</p>}
        </div>
      </div>
      <StepFooter onBack={onBack} onSkip={onSkip} onContinue={save} busy={saving} />
    </>
  );
}
