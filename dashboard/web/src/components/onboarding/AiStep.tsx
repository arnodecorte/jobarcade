import { useState } from "react";
import { saveOllamaIntegration, testOllamaIntegration } from "../../lib/api";
import { aiSavePayload, aiTestOutcome } from "../../lib/onboarding";
import { StepFooter, StepHead } from "./StepFooter";
import type { StepProps } from "./types";

type Models = { draft: string; refine: string; classify: string };

const ROLES: Array<[keyof Models, string]> = [
  ["draft", "Drafting CV & letter"],
  ["refine", "Refining"],
  ["classify", "Email classification"],
];

export function AiStep({ integrations, onBack, onSkip, onContinue, reload }: StepProps) {
  const o = integrations.ollama;
  const [url, setUrl] = useState(o.base_url);
  const [key, setKey] = useState("");
  const [models, setModels] = useState<Models>({
    draft: o.models?.draft || o.model,
    refine: o.models?.refine || o.model,
    classify: o.models?.classify || o.model,
  });
  const [available, setAvailable] = useState<string[]>([]);
  const [tested, setTested] = useState<"idle" | "ok" | "fail">("idle");
  const [testMsg, setTestMsg] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function persist() {
    await saveOllamaIntegration(aiSavePayload(url, models, key));
  }

  async function runTest() {
    setTesting(true);
    setError("");
    try {
      await persist(); // the server tests whatever is saved
    } catch (err) {
      const out = aiTestOutcome("save", err as Error);
      setTested("idle");
      if (out.kind === "save-error") setError(out.message);
      setTesting(false);
      return;
    }
    setKey("");
    let result: { ok: boolean; models?: string[]; model: string; model_present?: boolean; error?: string } | Error;
    try {
      result = await testOllamaIntegration();
    } catch (err) {
      result = err as Error;
    }
    const out = aiTestOutcome("test", result);
    if (out.kind === "ok" && !(result instanceof Error)) {
      const list = result.models || [];
      setAvailable(list);
      setTested("ok");
      setTestMsg(result.model_present === false ? `Connected, but ${result.model} is not pulled yet.` : "Connected.");
      // Point any role at a model that isn't installed to the first one that is.
      if (list.length) {
        setModels((m) => {
          const fix = (v: string) => (list.includes(v) ? v : list[0]);
          return { draft: fix(m.draft), refine: fix(m.refine), classify: fix(m.classify) };
        });
      }
    } else if (out.kind === "unreachable") {
      setTested("fail");
      setTestMsg(out.detail);
    }
    setTesting(false);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await persist();
      reload();
      await onContinue();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const options = (current: string) => (available.includes(current) || !available.length ? available : [current, ...available]);

  return (
    <>
      <StepHead
        kicker="Step 1 · Local AI"
        title="Connect your Ollama"
        sub="JobArcade drafts your CVs and letters with a model running on your own machine. Nothing leaves it unless you point this at Ollama cloud."
      />
      <div className="ob-body">
        <label className="field">
          Ollama URL
          <input value={url} onChange={(e) => { setUrl(e.target.value); setTested("idle"); }} placeholder="http://host.docker.internal:11434" />
        </label>
        <label className="field">
          API key (optional)
          <input
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={o.api_key_set ? "Saved. Type to replace" : "Only for Ollama cloud"}
          />
        </label>
        <div className="ob-row">
          <button type="button" className="btn ghost" onClick={runTest} disabled={testing || !url.trim()}>
            {testing ? "Testing…" : "Test connection"}
          </button>
          {tested === "ok" && <span className="ob-ok">{testMsg}</span>}
        </div>

        {tested === "ok" && available.length > 0 && (
          <>
            <div className="ob-chips" aria-label="Installed models">
              {available.map((m) => <span key={m} className="ob-chip">{m}</span>)}
            </div>
            <div className="ob-grid3">
              {ROLES.map(([role, label]) => (
                <label key={role} className="field">
                  {label}
                  <select value={models[role]} onChange={(e) => setModels({ ...models, [role]: e.target.value })}>
                    {options(models[role]).map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </label>
              ))}
            </div>
          </>
        )}

        {tested === "fail" && (
          <div className="ob-callout" role="alert">
            <strong>Ollama not reachable</strong>
            {testMsg && <span className="ob-callout-detail">{testMsg}</span>}
            <ol>
              <li>Install Ollama from <a href="https://ollama.com/download" target="_blank" rel="noreferrer">ollama.com/download</a>.</li>
              <li>Run <code>ollama pull qwen2.5:7b</code> in a terminal.</li>
              <li>Come back and test again, or save now and fix it later.</li>
            </ol>
          </div>
        )}
        {error && <p className="ob-error" role="alert">{error}</p>}
      </div>
      <StepFooter onBack={onBack} onSkip={onSkip} onContinue={save} busy={saving} continueDisabled={!url.trim()} />
    </>
  );
}
