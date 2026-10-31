import { createContext, useContext, useRef, useState, type ReactNode } from "react";
import { createDraftPack, warmupOllama } from "./api";

type Phase = "form" | "generating" | "warming" | "ready" | "error";

export type DraftState = {
  jobId: number;
  title: string;
  company: string;
  phase: Phase;
  minimized: boolean;
  error: string;
  folderName: string | null;
};

type DraftJob = { id: number; title: string; company: string };

type DraftCtx = {
  draft: DraftState | null;
  openForm: (job: DraftJob) => void;
  closeForm: () => void;
  generate: (instructions: string) => Promise<void>;
  minimize: () => void;
  restore: () => void;
  dismiss: () => void;
};

const Ctx = createContext<DraftCtx | null>(null);

/**
 * Lives above the router so the "minimize" chip survives page navigation,
 * matching the old single-page app's global generating-state behaviour.
 */
export function DraftProvider({ children, onGenerated }: { children: ReactNode; onGenerated?: () => void }) {
  const [draft, setDraft] = useState<DraftState | null>(null);
  const minimizedRef = useRef(false);

  function openForm(job: DraftJob) {
    minimizedRef.current = false;
    setDraft({ jobId: job.id, title: job.title, company: job.company, phase: "form", minimized: false, error: "", folderName: null });
  }

  function closeForm() {
    setDraft((d) => (d?.phase === "form" ? null : d));
  }

  function minimize() {
    minimizedRef.current = true;
    setDraft((d) => (d ? { ...d, minimized: true } : d));
  }

  function restore() {
    minimizedRef.current = false;
    setDraft((d) => (d ? { ...d, minimized: false } : d));
  }

  function dismiss() {
    setDraft(null);
  }

  async function generate(instructions: string) {
    if (!draft) return;
    const { jobId, title, company } = draft;
    minimizedRef.current = false;
    setDraft({ jobId, title, company, phase: "generating", minimized: false, error: "", folderName: null });
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const result = await createDraftPack(jobId, instructions);
        if (minimizedRef.current) {
          setDraft({ jobId, title, company, phase: "ready", minimized: true, error: "", folderName: result.folder_name });
          onGenerated?.();
        } else {
          window.location.href = `/draft?folder=${encodeURIComponent(result.folder_name)}&jobId=${jobId}`;
        }
        return;
      } catch (err) {
        const msg = (err as Error).message;
        if (attempt === 0 && msg === "Failed to fetch") {
          setDraft({ jobId, title, company, phase: "warming", minimized: false, error: "", folderName: null });
          await warmupOllama().catch(() => {});
          await new Promise((r) => setTimeout(r, 20000));
          setDraft({ jobId, title, company, phase: "generating", minimized: false, error: "", folderName: null });
          continue;
        }
        setDraft({ jobId, title, company, phase: "error", minimized: false, error: msg, folderName: null });
        return;
      }
    }
  }

  return (
    <Ctx.Provider value={{ draft, openForm, closeForm, generate, minimize, restore, dismiss }}>
      {children}
    </Ctx.Provider>
  );
}

export function useDraft(): DraftCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useDraft must be used within DraftProvider");
  return ctx;
}
