# Feedback Chip + Manual Job Add — Design

Branch: `feature/feedback-and-manual-job-entry` (off `main` post-Beta).

## Why

Two gaps in the Beta dashboard:
1. No way to capture improvement ideas while using it — they get lost.
2. Angie sometimes finds a role through LinkedIn/word-of-mouth that the
   scrapers never touch. Without a way to add it, the Odds engine's
   "applications sent" count, and the daily queue, are silently incomplete.

## Manual Job Add

**Entry point:** "+ Add Job" button next to Refresh in the shared
`PageHeader` (visible on Today/Pipeline/Jobs/Odds/System — wherever she
happens to be when she remembers a role).

**Form:** Company, Title (required). Location, Apply URL, Notes (optional).
Status dropdown (New/Reviewed/Tailoring/Ready/Applied/Interviewing),
default New. When status is Applied/Interviewing, an optional "date
applied" field appears (defaults to today) so backfilling past
applications doesn't fake today's pull count.

**Backend — `POST /api/jobs`:**
1. Build a `Job(source_platform="manual", scraper_type="manual", ...)`.
2. `apply_assessment(job)` — reuses the existing deterministic plausibility
   engine (`jobhunt/assessment.py`) so manual entries get a real
   score/fit_band/reasons, not a placeholder. This is the same function
   scraped jobs go through; no new scoring logic.
3. `upsert_jobs(conn, [job])` — reuses existing dedupe (by `apply_url`, then
   fuzzy company+title+location), so a later scraper hit on the same role
   merges instead of duplicating.
4. If status is Applied/Interviewing, insert one `status_events` row at the
   chosen date (or now) — the same table the Odds streak/cadence read from.

## Feedback Chip

**UI:** Small persistent icon chip, opposite corner from the Angie
companion, on all 5 pages. Click expands to a textbox + Send; collapses
back with a brief confirmation after submit.

**Backend:** New `feedback` table (`id, message, page, created_at`),
following the exact pattern of `status_events`. `POST /api/feedback`
stores the message and the page it was left on (captured automatically
from the current route — no extra form field). No in-app viewer yet;
queried directly via sqlite when reviewing notes. A list view can be added
later if the backlog grows enough to need one.

## Out of scope (deliberately)

- No feedback browsing UI yet.
- No bulk-import for manual jobs — one at a time, matching the rest of the
  dashboard's per-job interactions.
- No edit/delete for manually-added jobs beyond the existing status
  dropdown — they become ordinary rows once added.
