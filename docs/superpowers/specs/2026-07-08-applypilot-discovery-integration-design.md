# Design Spec: ApplyPilot as Discovery Engine

**Date**: 2026-07-08
**Status**: Approved

## Context

The per-company dedicated scraper fleet (98 companies in `config/companies.yaml`)
was built on the premise that a bespoke, targeted scrape of each dream
company's careers page would beat generic job-board aggregation. Four weeks
of data refute that premise: of 58 "applied" events since 2026-06-12, manual
entries account for 28 and the `englishjobsearch` NL aggregator board accounts
for 12 — 69% combined — while all 98 dedicated company scrapers *combined*
produced only 18, none individually exceeding 3. The one interview secured
(Sungrow) was a fully manual entry, never touched by any scraper, applied
within ~48 hours of posting.

Separately, `/opt/applypilot` (the `arnodecorte/ApplyPilot` project) has been
running live on this same box since 2026-06-09 — a systemd timer at 06:00
daily, targeting this same candidate (`searches.yaml` header: "ApplyPilot
search configuration for Angelica Barasoain") via JobSpy (Indeed/LinkedIn/
Google) plus Workday + direct-site adapters. It has discovered 10,083 jobs,
scored 8,493 of them, and never once run its own auto-apply stage (the daily
job only runs `discover…cover`, never `apply`) — so it's an orphaned
discovery-and-scoring pile, not a competing autonomous applier. 2,386 jobs
score 8-9; only 496 have been tailored.

Its own location classification is known-unreliable (US/Philippines postings
have leaked through as "fits" before), so its `location_fit` field cannot be
the relevance gate for anything we import.

The goal: stop treating "targeted scrape fleet" as the primary discovery
engine. Make ApplyPilot's already-running, already-proven-broader net the
discovery source; keep this repo doing what it's good at — strict NL/role
filtering, CV/letter tailoring via Typst, and the dashboard. Do this without
flooding the pipeline with the historical backlog, and without ripping out
the dedicated fleet (it stays running, just unmaintained).

## Proposed Changes

### 1. New import command: `jobhunt/applypilot_import.py`

A new module, structured like the existing `jobhunt/jobspy_fallback.py`
(same "map external rows -> `Job` -> reuse `filtered_jobs_with_keys`" shape),
reading `/opt/applypilot/data/applypilot.db` **read-only**
(`sqlite3.connect("file:...applypilot.db?mode=ro", uri=True)`) — no write
access to a system this repo doesn't own.

Candidate query:
```sql
SELECT * FROM jobs
WHERE fit_score >= 6
  AND expired_at IS NULL
  AND scored_at > :watermark
ORDER BY scored_at DESC
```
(Filtered/ordered on `scored_at`, not `discovered_at` — see the watermark
rationale in #2.)

Each row maps to a `Job` (`jobhunt/models.py`) the same way
`jobspy_fallback._job_from_row` does today: `company`, `title`,
`location=row["location"]`, `description=row["full_description"] or
row["description"]`, `date_posted=row["date_posted"]`,
`apply_url=row["application_url"] or row["url"]`, `source_url=row["url"]`,
`source_platform=f"applypilot:{row['site']}"`, `scraper_type=
"applypilot_import"`, `source_job_id=row["dedup_key"]`.

**Critically, `location_fit` from ApplyPilot is never read/trusted.** The
mapped `Job` list is passed through the existing
`jobhunt.scrape.filtered_jobs_with_keys()` — the same `assess_job`/
`location_ok` gate every other source (dedicated scrapers, the old fallback)
already goes through. This is the fix for the US/Philippines leakage: NL
relevance is decided once, by the one filter this repo already trusts, not
by ApplyPilot's own (known-flawed) classification.

`fit_score` is kept only as a **ranking signal**, not a filter: after the
assessment pass, survivors are ordered by (a) dream-company match boost, see
#2, (b) `fit_score` desc, (c) `discovered_at` desc, then truncated to
`--limit` (default 50, mirrors `auto-draft --limit 50`) before being written.

Writing reuses existing plumbing exactly like `cmd_fallback` does today:
`replace_raw_jobs`, `upsert_jobs`, `record_scraper_health(...,
scraper_type="applypilot_import", strategy="applypilot")`.

### 2. Watermark (no backlog flood)

New table, added via the existing `init_db()` migration pattern (see
`2026-06-19` spec's `ALTER TABLE`/`CREATE TABLE IF NOT EXISTS` precedent):

```sql
CREATE TABLE IF NOT EXISTS import_cursors (
    source TEXT PRIMARY KEY,
    last_discovered_at TEXT NOT NULL
)
```

On first run, if no `applypilot` row exists, the cursor is seeded to
**start-of-today (UTC)**, not the earliest row and not the exact seeding
instant — the 3,252-job multi-week historical backlog (fit_score >= 7, not
expired) is deliberately left un-imported, while the very first real run
still captures whatever ApplyPilot already discovered earlier this morning
(seeding to the exact instant would make the first run always find zero
rows). The watermark is filtered and advanced on `scored_at`, not
`discovered_at`: ApplyPilot scores rows asynchronously and out of discovery
order, so a `discovered_at`-based watermark could permanently skip a
genuinely high-fit row that happened to be scored after the cursor had
already advanced past its (earlier) discovery time. After each run, the
cursor advances to `MAX(scored_at)` of the rows just fetched (before the
relevance filter — so a low-scoring or off-location row still advances the
watermark and is never re-checked).

### 3. Dream-company ranking boost

`config/companies.yaml`'s existing company list is reused purely as a
ranking signal for this path: before truncating to `--limit`, a candidate
whose `company` matches an entry in `load_companies()` on the full,
lowercased company name using word-boundary regex matching (not a naive
substring test) is sorted ahead of non-matches, before the `fit_score` sort.
Matching on the full name rather than a substring/first-word token avoids
false positives such as "Marsh McLennan" matching on "mars" or an unrelated
company matching on "just" from "Just Eat Takeaway". This is exactly the
"let a high-scoring dedicated-fleet or dream-company hit jump the queue"
behavior requested — applies uniformly regardless of which engine surfaced
the job.

### 4. CLI wiring (`jobhunt/cli.py`)

New `cmd_import_applypilot(args)`, registered as `import-applypilot` in the
subparser setup, following `cmd_fallback`'s structure exactly: `--db`,
`--limit` (default 50), `--export`, `--applypilot-db` (default
`/opt/applypilot/data/applypilot.db`, overridable for smoke-testing against
a copy). No `--company` filtering needed — this pulls across all companies
ApplyPilot found, that's the point.

### 5. Dedicated scraper fleet: unchanged, unmaintained

No edits to `config/companies.yaml`. `sweep` keeps running all 98 dedicated
+ `englishjobsearch` entries exactly as today — this is deliberately *not* a
shutdown, it's a maintenance freeze. Update `CLAUDE.md`'s Scraper Playbook
section with a short note: the dedicated fleet is no longer actively
repaired/promoted (skip `promote-careers-scraper` and proactive `audit`
fixes going forward); a rare hit from it still flows through the same
dashboard ranking as anything else.

### 6. Remove the now-superseded `jobspy_fallback` path

Delete `jobhunt/jobspy_fallback.py`, the `fallback` CLI command (`cmd_fallback`
and its subparser registration) in `cli.py`, and the `[fallback]` extra +
`python-jobspy` dependency in `pyproject.toml`. It produced zero rows in its
lifetime and is fully superseded by #1-#4 above (ApplyPilot already does
multi-tier queries, a 7-day recency window, and 3 boards — better-tuned than
this repo's single-board single-term implementation ever was). Remove its
CLAUDE.md documentation section and the `tests/test_jobspy_fallback.py`
fixture if one exists (check before assuming).

### 7. Scheduling: sync both pipelines to ~5am

- `/etc/systemd/system/applypilot-pipeline.timer`: `OnCalendar` moves from
  `06:00:00` to `05:00:00`.
- `/opt/angelica-jobhunt`'s cron (`crontab -l`: `3 5 * * *
  /opt/angelica-jobhunt/daily-jobhunt.sh`) stays at `5:03am` — a deliberate
  3-minute stagger rather than an exact-instant collision between two
  processes hitting the network/CPU simultaneously on the same box. Both are
  "at 5am" per the requested sync; the watermark design (#2) means if
  ApplyPilot's run is still mid-discovery when jobhunt's import fires, that
  day's tail end simply gets picked up on the next run — nothing is lost.
- `systemctl daemon-reload` after the timer file edit (system-level change
  outside this git repo — call this out explicitly when executing).

### 8. `daily-jobhunt.sh` — new step

Insert `python -m jobhunt import-applypilot --limit 50 --export` after the
existing `sweep --export` line and before `auto-draft`. `sweep` line is
otherwise untouched (per #5).

## Out of Scope

- Bulk backlog triage of the 3,252 existing high-scoring ApplyPilot rows —
  explicitly deferred; may be a separate future ask.
- Any change to ApplyPilot's own code/pipeline/apply stage.
- Changes to the CV/letter Typst tailoring workflow, the dashboard, or the
  Odds engine — this spec is discovery-layer only.

## Verification

- `python -m jobhunt import-applypilot --db data/company-smoke.sqlite --applypilot-db /opt/applypilot/data/applypilot.db --limit 10` against a scratch DB copy first; confirm rows written have `scraper_type='applypilot_import'`, sane NL locations (spot-check a handful — specifically checking for the previously-observed US/Philippines leakage *not* recurring), and no duplicate `dedupe_key` collisions with existing `data/jobs.sqlite` entries.
- `python -m jobhunt validate` after removing `jobspy_fallback.py` to confirm no dangling imports.
- `pytest` full suite (confirm no test references the removed fallback module).
- Manual timer check: `systemctl list-timers applypilot-pipeline.timer` shows next run at 05:00; `crontab -l` unchanged at `3 5 * * *`.
