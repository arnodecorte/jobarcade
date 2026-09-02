// Single source of truth for the first-visit splash AND the System "Release
// notes" panel, so the two never drift out of sync.
export const RELEASE = {
  version: "Beta",
  date: "2026-07-08",
  intro:
    "Congrats on the first interview: Sungrow proves the odds engine was not " +
    "wishful thinking. It is not a victory lap yet. It is the new bar-setter: " +
    "keep applying hard, use the interview to calibrate the market, and only " +
    "accept an offer that clears Angelica's threshold.",
  pages: [
    { name: "Today", body: "Your daily queue — apply-today picks, an energy ring for your daily goal, and a one-line odds snapshot." },
    { name: "Pipeline", body: "A kanban board from discovered to applied. Moving a card forward logs a pull." },
    { name: "Jobs", body: "The full searchable board — fit bands, scores, artifact status, fresh jobs from the latest sweep, and the Create Draft action." },
    { name: "Odds", body: "The motivating centerpiece: a maturity-aware odds curve, an expected-value ETA to your next interview, follow-up signals, and a streak rail." },
    { name: "System", body: "Company directory, scraper health, Gmail evidence capture, and links out to the engineering views." },
  ],
  notes: [
    "Every status change is now logged, so Odds streaks and cadence are real, not simulated.",
    "New maturity-aware odds: applications now incubate before entering the calibrated sample, with follow-up and ghosted lifecycle signals surfaced directly on Odds.",
    "New Gmail evidence layer: connect Angelica's inbox through app-owned OAuth, sync receipts/rejections/interview signals, and review matched lifecycle evidence.",
    "Gmail intelligence now uses local Ollama classification, dual-confidence automation, editable lifecycle evidence, and visible auto-match metrics.",
    "System is now a compact disclosure workspace, with encrypted in-app setup for Gmail OAuth and Ollama.",
    "The Create Draft flow is back — a minimizable generating card and a status chip that follows you across pages.",
    "Visual refresh: a calm cream-and-pastel base with one glowing 'felt' table for the Odds page.",
    "Strategy update: Sungrow is a B-minus-on-paper benchmark, not an automatic yes and not a sacrifice. Interview seriously, keep the sprint moving, and compare future options against this bar.",
    "Application posture: the next week is about throughput with guard rails. More applications now may not mature before July 16, but fast responses happen and optionality matters.",
    "Dashboard flow: the Fresh jobs view and higher auto-draft cap make daily discovery-to-draft work faster.",
    "Discovery and drafting: Discover can auto-resolve likely careers URLs, while Chameleon gained stronger typography/font-weight inheritance for branded CV drafts.",
    "Scraper housekeeping: ASICS and Patagonia fixes restored NL/EMEA visibility where the previous source was under-capturing.",
  ],
};
