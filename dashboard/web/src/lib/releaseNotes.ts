export const RELEASE = {
  version: "v1.0",
  date: "2026-09-01",
  intro:
    "JobArcade combines a high-velocity Kanban pipeline, probabilistic conversion modeling, " +
    "zero-hallucination Ollama CV & cover letter tailoring, and sub-second Typst vector PDF compilation.",
  pages: [
    { name: "Today", body: "Your daily queue — apply-today picks, an energy ring for your daily goal, and a one-line odds snapshot." },
    { name: "Pipeline", body: "A kanban board from discovered to applied. Moving a card forward logs a pull." },
    { name: "Jobs", body: "The full searchable board — fit bands, scores, artifact status, and the Create Draft action." },
    { name: "Odds", body: "The motivating centerpiece: a maturity-aware odds curve, an expected-value ETA to your next interview, follow-up signals, and a streak rail." },
    { name: "System", body: "Integration settings for local Ollama models, Firecrawl API, and Gmail lifecycle tracking." },
  ],
  notes: [
    "Every status change is logged to SQLite, so Odds streaks and cadence are real, not simulated.",
    "Maturity-aware odds: applications incubate before entering the calibrated sample, with follow-up and ghosted lifecycle signals surfaced directly on Odds.",
    "Gmail evidence layer: connect your inbox through OAuth, sync receipts/rejections/interview signals, and review matched lifecycle evidence.",
    "Zero-hallucination AI tailoring strictly grounds every CV bullet and cover letter in config/profile.yaml.",
    "Brand Chameleon extracts target-company palettes and typography to compile brand-matched vector PDFs via Typst.",
  ],
};
