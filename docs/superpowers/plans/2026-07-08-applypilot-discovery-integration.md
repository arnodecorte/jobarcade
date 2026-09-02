# ApplyPilot Discovery Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ApplyPilot's already-running discovery pipeline (`/opt/applypilot`, a separate system, JobSpy + Workday + direct-site adapters) the primary job-discovery source for this repo, re-filtered through this repo's own stricter NL location/role gate, while leaving the existing dedicated-scraper fleet running unmaintained rather than removed.

**Architecture:** A new read-only import path (`jobhunt/applypilot_import.py` + `jobhunt import-applypilot` CLI command) queries ApplyPilot's SQLite database directly (same box, no API), maps rows to this repo's `Job` model, re-filters through the existing `assess_job`/`location_ok` gate (never trusting ApplyPilot's own known-unreliable `location_fit`), ranks by dream-company match then fit_score then recency, and writes through the existing `replace_raw_jobs`/`upsert_jobs`/`record_scraper_health` plumbing — the same functions `sweep` and the old `fallback` command already use. A new watermark table prevents importing the 3,252-job historical backlog.

**Tech Stack:** Python 3, sqlite3 (stdlib), pytest, existing `jobhunt` package conventions.

## Global Constraints

- ApplyPilot's database (`/opt/applypilot/data/applypilot.db`) is opened **read-only** (`mode=ro` URI) — this repo never writes to a system it doesn't own.
- ApplyPilot's `location_fit` column is never read or trusted anywhere in this integration — NL relevance is decided solely by this repo's own `jobhunt.assessment.assess_job`/`location_ok`.
- The historical ApplyPilot backlog (rows discovered before this integration ships) must not be bulk-imported — the watermark seeds to "now" on first run.
- `config/companies.yaml` and `sweep` behavior are unchanged by this plan — the dedicated fleet keeps running, it is documented as unmaintained, not disabled.
- Default per-run cap on jobs promoted to the `jobs` table: 50 (matches existing `auto-draft --limit 50` convention).

---

### Task 1: Watermark cursor storage (`jobhunt/database.py`)

**Files:**
- Modify: `jobhunt/database.py` (add `import_cursors` table to `init_db()`, add two new functions)
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: `utc_now()` (already defined in this file, `jobhunt/database.py:12`)
- Produces: `get_import_cursor(conn: sqlite3.Connection, source: str) -> str`, `advance_import_cursor(conn: sqlite3.Connection, source: str, discovered_at: str) -> None` — both used by Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_database.py` (extend the existing `from jobhunt.database import (...)` block with `advance_import_cursor, get_import_cursor`):

```python
def test_import_cursor_seeds_to_start_of_today_then_is_stable(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")

    first = get_import_cursor(conn, "applypilot")
    assert first.endswith("T00:00:00+00:00")  # start of the current UTC day,
    # not the exact seed instant -- so the first real run still captures
    # "this morning's" already-discovered ApplyPilot rows instead of finding
    # nothing (it only skips the multi-week historical backlog before today).

    second = get_import_cursor(conn, "applypilot")
    assert second == first  # calling again does not reseed


def test_advance_import_cursor_moves_forward_only(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    get_import_cursor(conn, "applypilot")  # seed

    advance_import_cursor(conn, "applypilot", "2026-07-09T10:00:00+00:00")
    assert get_import_cursor(conn, "applypilot") == "2026-07-09T10:00:00+00:00"

    advance_import_cursor(conn, "applypilot", "2020-01-01T00:00:00+00:00")
    assert get_import_cursor(conn, "applypilot") == "2026-07-09T10:00:00+00:00"


def test_import_cursor_is_per_source(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    get_import_cursor(conn, "applypilot")
    advance_import_cursor(conn, "applypilot", "2026-07-09T10:00:00+00:00")

    other = get_import_cursor(conn, "some_other_source")
    assert other != "2026-07-09T10:00:00+00:00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/test_database.py -k import_cursor -v`
Expected: FAIL with `ImportError: cannot import name 'get_import_cursor'`

- [ ] **Step 3: Add the table and functions**

In `jobhunt/database.py`, inside `init_db()`, add the new table right after the `company_candidates` block and before `conn.commit()` (currently ends at line 165 with the `idx_company_candidates_status_score` index):

```python
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_cursors (
            source TEXT PRIMARY KEY,
            last_discovered_at TEXT NOT NULL
        )
        """
    )
```

Then add these two functions after `dedupe_key()` (`jobhunt/database.py:183-188`):

```python
def get_import_cursor(conn: sqlite3.Connection, source: str) -> str:
    row = conn.execute(
        "SELECT last_discovered_at FROM import_cursors WHERE source = ?", (source,)
    ).fetchone()
    if row:
        return row["last_discovered_at"]
    # Seed to the start of *today* (UTC), not the exact instant -- this skips
    # the multi-week historical backlog while still letting the very first
    # real run pick up whatever was already discovered earlier this morning,
    # instead of finding nothing until tomorrow.
    seed = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
    conn.execute(
        "INSERT INTO import_cursors (source, last_discovered_at) VALUES (?, ?)",
        (source, seed),
    )
    conn.commit()
    return seed


def advance_import_cursor(conn: sqlite3.Connection, source: str, discovered_at: str) -> None:
    conn.execute(
        """
        INSERT INTO import_cursors (source, last_discovered_at) VALUES (?, ?)
        ON CONFLICT(source) DO UPDATE SET last_discovered_at = excluded.last_discovered_at
        WHERE excluded.last_discovered_at > import_cursors.last_discovered_at
        """,
        (source, discovered_at),
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/test_database.py -k import_cursor -v`
Expected: 3 passed

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/ -v`
Expected: all existing tests still pass (same pass count as before plus 3 new)

- [ ] **Step 6: Commit**

```bash
git add jobhunt/database.py tests/test_database.py
git commit -m "feat(jobhunt): add per-source import watermark cursor"
```

---

### Task 2: ApplyPilot row mapping and ranking (`jobhunt/applypilot_import.py`)

**Files:**
- Create: `jobhunt/applypilot_import.py`
- Test: `tests/test_applypilot_import.py`

**Interfaces:**
- Consumes: `jobhunt.config.load_companies()` (`jobhunt/config.py:96`), `jobhunt.models.Job` (`jobhunt/models.py:22`)
- Produces: `DEFAULT_APPLYPILOT_DB: Path`, `fetch_candidates(applypilot_db: Path, watermark: str, min_fit_score: int = 6) -> list[sqlite3.Row]`, `rows_to_ranking_rows(rows: Iterable[sqlite3.Row]) -> list[tuple[Job, int, str]]`, `rank_and_limit(rows: list[tuple[Job, int, str]], limit: int) -> list[Job]` — all used by Task 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_applypilot_import.py`:

```python
import sqlite3

from jobhunt.applypilot_import import fetch_candidates, rank_and_limit, rows_to_ranking_rows
from jobhunt.config import load_companies


def _make_applypilot_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE jobs (
            company TEXT, title TEXT, location TEXT, url TEXT, application_url TEXT,
            full_description TEXT, description TEXT, date_posted TEXT, site TEXT,
            dedup_key TEXT, discovered_at TEXT, fit_score INTEGER, expired_at TEXT
        )
        """
    )
    rows = [
        # kept candidate: NL-plausible location, high fit_score, recent
        ("Nike Netherlands B.V.", "Brand Marketing Coordinator", "Amsterdam, Netherlands",
         "https://indeed.com/job/1", "https://nike.com/apply/1", "Full NL marketing role.",
         "short", "2026-07-08", "indeed", "dk1", "2026-07-08T09:00:00+00:00", 8, None),
        # excluded by SQL-level fit_score floor
        ("Random BV", "Marketing Assistant", "Amsterdam, Netherlands",
         "https://indeed.com/job/2", None, "desc", "desc", "2026-07-08", "indeed",
         "dk2", "2026-07-08T09:05:00+00:00", 3, None),
        # excluded: before the watermark
        ("Random BV", "Marketing Manager", "Amsterdam, Netherlands",
         "https://indeed.com/job/3", None, "desc", "desc", "2026-07-01", "indeed",
         "dk3", "2026-07-01T09:00:00+00:00", 9, None),
        # excluded: expired
        ("Random BV", "Marketing Lead", "Amsterdam, Netherlands",
         "https://indeed.com/job/4", None, "desc", "desc", "2026-07-08", "indeed",
         "dk4", "2026-07-08T10:00:00+00:00", 9, "2026-07-08T11:00:00+00:00"),
        # kept candidate: non-dream company, lower fit_score, US location (location
        # filtering itself is asserted at the assess_job layer in Task 3's test, not here)
        ("Some Startup Inc", "Content Coordinator", "Austin, TX, US",
         "https://indeed.com/job/5", None, "desc", "desc", "2026-07-08", "indeed",
         "dk5", "2026-07-08T08:00:00+00:00", 6, None),
    ]
    conn.executemany(
        """
        INSERT INTO jobs (company, title, location, url, application_url, full_description,
                           description, date_posted, site, dedup_key, discovered_at, fit_score, expired_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_fetch_candidates_applies_fit_score_watermark_and_expiry(tmp_path):
    db_path = tmp_path / "applypilot.db"
    _make_applypilot_db(db_path)

    rows = fetch_candidates(db_path, watermark="2026-07-08T00:00:00+00:00", min_fit_score=6)

    kept_keys = {row["dedup_key"] for row in rows}
    assert kept_keys == {"dk1", "dk5"}  # dk2 (low score), dk3 (before watermark), dk4 (expired) excluded


def test_rank_and_limit_prefers_dream_company_then_fit_score(tmp_path):
    db_path = tmp_path / "applypilot.db"
    _make_applypilot_db(db_path)
    rows = fetch_candidates(db_path, watermark="2026-07-08T00:00:00+00:00", min_fit_score=6)

    ranking_rows = rows_to_ranking_rows(rows)
    assert {job.source_job_id for job, _, _ in ranking_rows} == {"dk1", "dk5"}

    ranked = rank_and_limit(ranking_rows, limit=10)
    # "Nike" matches a company in config/companies.yaml -> ranked first even
    # though both candidates pass the fit_score floor.
    assert ranked[0].company == "Nike Netherlands B.V."
    assert ranked[0].source_platform == "applypilot:indeed"
    assert ranked[0].apply_url == "https://nike.com/apply/1"


def test_rank_and_limit_respects_limit():
    from jobhunt.models import Job

    rows = [
        (Job(company="A", title="X", source_job_id="a"), 9, "2026-07-08T09:00:00+00:00"),
        (Job(company="B", title="Y", source_job_id="b"), 8, "2026-07-08T09:00:00+00:00"),
        (Job(company="C", title="Z", source_job_id="c"), 7, "2026-07-08T09:00:00+00:00"),
    ]
    assert len(rank_and_limit(rows, limit=2)) == 2


def test_nike_is_a_configured_dream_company():
    # sanity check the test fixture's assumption holds against the real config
    names = [c.company.lower() for c in load_companies()]
    assert any("nike" in name for name in names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/test_applypilot_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobhunt.applypilot_import'`

- [ ] **Step 3: Write the implementation**

Create `jobhunt/applypilot_import.py`:

```python
"""ApplyPilot discovery import.

ApplyPilot (/opt/applypilot) is a separate, already-running system that
discovers postings for this same candidate via JobSpy (Indeed/LinkedIn/
Google), Workday, and direct career sites, then scores them 1-10 with an
LLM. It has never run its own auto-apply stage; this module pulls its
scored discoveries into this repo's own jobs table.

ApplyPilot's own `location_fit` classification is known-unreliable (US and
Philippines postings have leaked through as "fits" before). This module
never reads that column. Candidates are pre-filtered here only by
`fit_score` (a coarse topical/role signal); NL relevance is decided
entirely by this repo's own `jobhunt.assessment.assess_job`/`location_ok`
gate downstream, in `jobhunt/cli.py`'s `cmd_import_applypilot` (via the
existing `jobhunt.scrape.filtered_jobs_with_keys`), same as every other
source.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from jobhunt.config import load_companies
from jobhunt.models import Job

DEFAULT_APPLYPILOT_DB = Path("/opt/applypilot/data/applypilot.db")
MIN_FIT_SCORE = 6


def fetch_candidates(
    applypilot_db: Path, watermark: str, min_fit_score: int = MIN_FIT_SCORE
) -> list[sqlite3.Row]:
    """Read-only query against ApplyPilot's own database. Never writes to it."""
    uri = f"file:{Path(applypilot_db).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT company, title, location, url, application_url, full_description,
                   description, date_posted, site, dedup_key, discovered_at, fit_score
            FROM jobs
            WHERE fit_score >= ?
              AND expired_at IS NULL
              AND discovered_at > ?
            ORDER BY discovered_at DESC
            """,
            (min_fit_score, watermark),
        ).fetchall()
    finally:
        conn.close()


def _row_to_job(row: sqlite3.Row) -> Job | None:
    title = (row["title"] or "").strip()
    if not title:
        return None
    url = row["application_url"] or row["url"]
    if not url:
        return None
    return Job(
        company=(row["company"] or "").strip() or "Unknown",
        title=title,
        location=row["location"],
        description=row["full_description"] or row["description"],
        date_posted=row["date_posted"],
        apply_url=url,
        source_url=row["url"],
        source_platform=f"applypilot:{row['site'] or 'unknown'}",
        source_job_id=row["dedup_key"],
        scraper_type="applypilot_import",
    )


def rows_to_ranking_rows(rows: Iterable[sqlite3.Row]) -> list[tuple[Job, int, str]]:
    result: list[tuple[Job, int, str]] = []
    for row in rows:
        job = _row_to_job(row)
        if job:
            result.append((job, row["fit_score"] or 0, row["discovered_at"] or ""))
    return result


def _is_dream_company(job: Job, tokens: set[str]) -> bool:
    company_lower = job.company.lower()
    return any(token and token in company_lower for token in tokens)


def _company_tokens() -> set[str]:
    return {company.company.lower().split()[0] for company in load_companies() if company.company}


def rank_and_limit(rows: list[tuple[Job, int, str]], limit: int) -> list[Job]:
    """Dream-company match first, then fit_score desc, then recency desc.

    Three stable sorts applied in reverse priority order, since Python's
    sort is stable and this avoids needing to invert an ISO date string for
    descending order in a single compound key.
    """
    tokens = _company_tokens()
    entries = list(rows)
    entries.sort(key=lambda entry: entry[2], reverse=True)  # discovered_at desc
    entries.sort(key=lambda entry: entry[1], reverse=True)  # fit_score desc
    entries.sort(key=lambda entry: 0 if _is_dream_company(entry[0], tokens) else 1)
    return [job for job, _, _ in entries[:limit]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/test_applypilot_import.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add jobhunt/applypilot_import.py tests/test_applypilot_import.py
git commit -m "feat(jobhunt): map and rank ApplyPilot discoveries"
```

---

### Task 3: Wire the `import-applypilot` CLI command (`jobhunt/cli.py`)

**Files:**
- Modify: `jobhunt/cli.py` (imports around line 22-36, new `cmd_import_applypilot` function, new subparser registration near line 1062)
- Test: `tests/test_cli_import_applypilot.py`

**Interfaces:**
- Consumes: `fetch_candidates`, `rows_to_ranking_rows`, `rank_and_limit`, `DEFAULT_APPLYPILOT_DB` (Task 2), `get_import_cursor`, `advance_import_cursor` (Task 1), `filtered_jobs_with_keys` (`jobhunt/scrape.py:276`, already imported in `cli.py:36`), `replace_raw_jobs`/`upsert_jobs`/`record_scraper_health`/`dedupe_key`/`init_db`/`connect` (already imported in `cli.py:22-32`), `export_all` (already imported, `cli.py:35`).
- Produces: `python -m jobhunt import-applypilot [--db PATH] [--applypilot-db PATH] [--limit N] [--export]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_import_applypilot.py`:

```python
import sqlite3

from jobhunt.cli import main
from jobhunt.database import connect, init_db


def _make_applypilot_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE jobs (
            company TEXT, title TEXT, location TEXT, url TEXT, application_url TEXT,
            full_description TEXT, description TEXT, date_posted TEXT, site TEXT,
            dedup_key TEXT, discovered_at TEXT, fit_score INTEGER, expired_at TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO jobs (company, title, location, url, application_url, full_description,
                           description, date_posted, site, dedup_key, discovered_at, fit_score, expired_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            # passes fit_score floor AND this repo's own location/role gate
            ("Nike Netherlands B.V.", "Brand Marketing Coordinator", "Amsterdam, Netherlands",
             "https://indeed.com/job/1", "https://nike.com/apply/1", "Great NL marketing role in Amsterdam.",
             "short", "2026-07-08", "indeed", "dk1", "2026-07-08T09:00:00+00:00", 8, None),
            # passes ApplyPilot's fit_score floor but must be dropped by this
            # repo's own location_ok gate (Philippines) -- the known leakage bug
            ("Some Corp", "Marketing Manager", "Manila, Philippines",
             "https://indeed.com/job/2", None, "Great marketing role in Manila.",
             "short", "2026-07-08", "indeed", "dk2", "2026-07-08T09:00:00+00:00", 9, None),
        ],
    )
    conn.commit()
    conn.close()


def _seed_old_watermark(jobhunt_db):
    """get_import_cursor() seeds a brand-new source to *now* on first call --
    correct for production (skips the historical backlog) but useless for a
    test that wants to exercise "does a fetch happen at all" without waiting
    for a future timestamp. Pre-seed an old cursor to simulate "a previous
    run already happened", same as any run after the very first one."""
    conn = init_db(connect(jobhunt_db))
    conn.execute(
        "INSERT INTO import_cursors (source, last_discovered_at) VALUES (?, ?)",
        ("applypilot", "2000-01-01T00:00:00+00:00"),
    )
    conn.commit()


def test_import_applypilot_drops_non_nl_rows_and_writes_jobs_table(tmp_path):
    applypilot_db = tmp_path / "applypilot.db"
    _make_applypilot_db(applypilot_db)
    jobhunt_db = tmp_path / "jobs.sqlite"
    _seed_old_watermark(jobhunt_db)

    exit_code = main([
        "import-applypilot",
        "--db", str(jobhunt_db),
        "--applypilot-db", str(applypilot_db),
    ])
    assert exit_code == 0

    conn = init_db(connect(jobhunt_db))
    rows = conn.execute("SELECT company, source_platform, scraper_type FROM jobs").fetchall()
    companies = {row["company"] for row in rows}
    assert "Nike Netherlands B.V." in companies
    assert "Some Corp" not in companies  # Philippines row dropped by location_ok
    nike_row = next(row for row in rows if row["company"] == "Nike Netherlands B.V.")
    assert nike_row["source_platform"] == "applypilot:indeed"
    assert nike_row["scraper_type"] == "applypilot_import"


def test_import_applypilot_watermark_prevents_reimport(tmp_path):
    applypilot_db = tmp_path / "applypilot.db"
    _make_applypilot_db(applypilot_db)
    jobhunt_db = tmp_path / "jobs.sqlite"
    _seed_old_watermark(jobhunt_db)

    main(["import-applypilot", "--db", str(jobhunt_db), "--applypilot-db", str(applypilot_db)])
    # second run: nothing new should be discovered since the watermark advanced
    exit_code = main(["import-applypilot", "--db", str(jobhunt_db), "--applypilot-db", str(applypilot_db)])
    assert exit_code == 0

    conn = init_db(connect(jobhunt_db))
    count = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
    assert count == 1  # still just the one Nike row, not duplicated or re-added
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/test_cli_import_applypilot.py -v`
Expected: FAIL with `argparse` error (`invalid choice: 'import-applypilot'`) since the subcommand doesn't exist yet.

- [ ] **Step 3: Add imports**

In `jobhunt/cli.py`, extend the existing `from jobhunt.database import (...)` block (`cli.py:22-32`) to also import `advance_import_cursor` and `get_import_cursor`:

```python
from jobhunt.database import (
    connect,
    dedupe_key,
    init_db,
    expire_filtered_out_jobs,
    mark_missing_expired,
    record_company_failure,
    record_scraper_health,
    replace_raw_jobs,
    upsert_jobs,
    advance_import_cursor,
    get_import_cursor,
)
```

Add a new import line right after the existing `from jobhunt.discover import discover_sites` (`cli.py:34`):

```python
from jobhunt.applypilot_import import DEFAULT_APPLYPILOT_DB, fetch_candidates, rank_and_limit, rows_to_ranking_rows
```

- [ ] **Step 4: Add `cmd_import_applypilot`**

Add this function right after `cmd_fallback` (currently ends at `cli.py:397`, right before `def cmd_export`):

```python
def cmd_import_applypilot(args: argparse.Namespace) -> int:
    """Pull fresh, scored postings from ApplyPilot's own discovery pipeline
    (a separate system at /opt/applypilot). Re-filters through this repo's
    own location/role gate -- ApplyPilot's own location_fit is never
    trusted here, it has leaked non-NL postings through before."""
    conn = init_db(connect(args.db))
    watermark = get_import_cursor(conn, "applypilot")
    rows = fetch_candidates(args.applypilot_db, watermark)
    if not rows:
        print(f"No new ApplyPilot rows since {watermark}")
        return 0

    ranking_rows = rows_to_ranking_rows(rows)
    candidates = [job for job, _, _ in ranking_rows]
    filtered, seen_keys = filtered_jobs_with_keys(candidates)

    filtered_ids = {id(job) for job in filtered}
    kept_rows = [entry for entry in ranking_rows if id(entry[0]) in filtered_ids]
    limited = rank_and_limit(kept_rows, args.limit)

    replace_raw_jobs(conn, "ApplyPilot", candidates, seen_keys)
    new, existing = upsert_jobs(conn, limited)
    record_scraper_health(
        conn, "ApplyPilot", "ok",
        scraper_type="applypilot_import", strategy="applypilot",
        raw_count=len(rows), relevant_count=len(filtered),
    )
    advance_import_cursor(conn, "applypilot", rows[0]["discovered_at"])

    if args.export:
        count = export_all(conn)
        print(f"Exported {count} jobs")
    print(
        f"ApplyPilot import: fetched={len(rows)} passed_filters={len(filtered)} "
        f"kept={len(limited)} new={new} existing={existing}"
    )
    return 0
```

- [ ] **Step 5: Register the subparser**

In `jobhunt/cli.py`, add this right after the `fallback` subparser block (`cli.py:1056-1062`, which Task 4 will delete) — for now, add it directly after that block, before the `dashboard` subparser:

```python
    import_applypilot = sub.add_parser(
        "import-applypilot",
        help="Pull fresh, scored postings from ApplyPilot's own discovery pipeline "
             "(a separate system at /opt/applypilot), re-filtered through this repo's own location/role gate.",
    )
    import_applypilot.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    import_applypilot.add_argument(
        "--applypilot-db", type=Path, default=DEFAULT_APPLYPILOT_DB,
        help="Path to ApplyPilot's SQLite database (opened read-only).",
    )
    import_applypilot.add_argument("--limit", type=int, default=50, help="Max jobs promoted to the jobs table per run.")
    import_applypilot.add_argument("--export", action="store_true", help="Export after the run.")
    import_applypilot.set_defaults(func=cmd_import_applypilot)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/test_cli_import_applypilot.py -v`
Expected: 2 passed

- [ ] **Step 7: Run the full test suite**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add jobhunt/cli.py tests/test_cli_import_applypilot.py
git commit -m "feat(jobhunt): add import-applypilot CLI command"
```

---

### Task 4: Remove the superseded `jobspy_fallback` path

ApplyPilot (Task 1-3) now covers what this path was for, better-tuned (multi-tier queries, 7-day recency window, 3 boards). It produced zero rows in its lifetime and `python-jobspy` was never installed for it.

**Files:**
- Delete: `jobhunt/jobspy_fallback.py`
- Modify: `jobhunt/cli.py` (remove `cmd_fallback`, its subparser registration, and the now-unused `_add_common_company_arg` call site if no longer used elsewhere)
- Modify: `tests/test_dedicated_adapters.py` (remove `test_jobspy_fallback_row_mapping_and_filters`)
- Modify: `pyproject.toml` (remove the `[fallback]` extra)

- [ ] **Step 1: Confirm nothing else references the module**

Run: `cd /opt/angelica-jobhunt && grep -rn "jobspy_fallback\|cmd_fallback\|scrape_jobspy" --include="*.py" .`
Expected output: only `jobhunt/jobspy_fallback.py` itself, `jobhunt/cli.py` (the `cmd_fallback` function + import + subparser registration), and `tests/test_dedicated_adapters.py`'s one test — confirms the removal surface matches this task before deleting anything.

- [ ] **Step 2: Delete the module**

```bash
git rm jobhunt/jobspy_fallback.py
```

- [ ] **Step 3: Remove `cmd_fallback` and its subparser from `jobhunt/cli.py`**

Delete the `cmd_fallback` function (`jobhunt/cli.py:355-397`, the full function from `def cmd_fallback(args: argparse.Namespace) -> int:` through its closing `return 0 if failures == 0 else 2`).

Delete the subparser registration block added in Task 3, Step 5's surrounding context (`jobhunt/cli.py:1056-1062`):

```python
    fallback = sub.add_parser("fallback", help="Job-board (JobSpy) fallback for manual_review dead-ends. Not part of daily sweep.")
    _add_common_company_arg(fallback)
    fallback.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    fallback.add_argument("--results", type=int, default=40, help="Results wanted per company.")
    fallback.add_argument("--proxy", help="Optional proxy host:port[:user:pass] for JobSpy.")
    fallback.add_argument("--export", action="store_true", help="Export after the run.")
    fallback.set_defaults(func=cmd_fallback)
```

- [ ] **Step 4: Remove the obsolete test**

In `tests/test_dedicated_adapters.py`, delete `test_jobspy_fallback_row_mapping_and_filters` (lines 91-119, from `def test_jobspy_fallback_row_mapping_and_filters():` through the line before `def test_production_config_uses_only_dedicated_or_manual_review():`).

- [ ] **Step 5: Remove the pyproject extra**

In `pyproject.toml`, delete:

```toml
# Optional: only needed for `python -m jobhunt fallback` (job-board discovery
# for manual_review dead-ends). Daily `sweep` does not import this.
fallback = [
    "python-jobspy>=1.1.80",
]
```

- [ ] **Step 6: Run the full test suite**

Run: `cd /opt/angelica-jobhunt && .venv/bin/pytest tests/ -v`
Expected: all tests pass, no `ImportError`/`ModuleNotFoundError` referencing `jobspy_fallback`

- [ ] **Step 7: Run `jobhunt validate` to confirm the CLI still builds cleanly**

Run: `cd /opt/angelica-jobhunt && python -m jobhunt validate`
Expected: `OK` (no `fallback` subcommand listed in `python -m jobhunt --help` anymore)

- [ ] **Step 8: Commit**

```bash
git add -A jobhunt/ tests/ pyproject.toml
git commit -m "chore(jobhunt): remove superseded jobspy_fallback path"
```

---

### Task 5: Documentation updates (`CLAUDE.md` + `AGENTS.md`)

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md` (mirror the same edits — the file header states "AGENTS.md mirrors this file")

- [ ] **Step 1: Replace the `fallback` line in the Automated Scraper Macro list**

In `CLAUDE.md`, replace list item 5 (`CLAUDE.md:155`):

```markdown
5. `python -m jobhunt fallback [--company "<C>"] [--export]` — **not part of daily sweep.** Job-board (JobSpy/Indeed) discovery for the `manual_review` dead-ends only; rows are tagged `source_platform=jobspy:*`, `scraper_type=fallback`. Requires the optional `python-jobspy` dependency (`pip install -e .[fallback]`).
```

with:

```markdown
5. `python -m jobhunt import-applypilot [--limit 50] [--export]` — pulls fresh, scored postings from ApplyPilot (`/opt/applypilot`), a separate discovery pipeline (JobSpy + Workday + direct sites) already running daily for this candidate. Rows are re-filtered through this repo's own `location_ok`/`assess_job` gate — ApplyPilot's own `location_fit` field is known-unreliable (US/Philippines postings have leaked through) and is never trusted here. A watermark (`import_cursors` table) means only postings discovered since the last run are pulled; the historical backlog was deliberately not bulk-imported. Rows are tagged `source_platform=applypilot:*`, `scraper_type=applypilot_import`.
```

Apply the identical replacement to `AGENTS.md` at its corresponding Automated Scraper Macro list item.

- [ ] **Step 2: Add a maintenance-freeze note for the dedicated fleet**

In `CLAUDE.md`, immediately after the numbered Automated Scraper Macro list (after what is currently item 7, `CLAUDE.md:157`, and before the blank line preceding "Prefer **location-only** source queries..."), add:

```markdown

**Dedicated scraper fleet status (2026-07-08):** the 98 per-company `dedicated`
scrapers combined produced 18 applications in 4 weeks vs. 28 manual + 12 from
the `englishjobsearch` aggregator board — the fleet is not worth its
maintenance cost. It keeps running in daily `sweep` unchanged, but is now in
**maintenance freeze**: don't proactively repair broken scrapers or use
`promote-careers-scraper` on new companies unless explicitly asked. A rare
high-scoring hit from it still flows through the same dashboard ranking as
anything else.
```

Apply the identical addition to `AGENTS.md`.

- [ ] **Step 3: Update the "Browser-flow / JobSpy are last resorts" playbook bullet**

In `CLAUDE.md`, replace (`CLAUDE.md:341-343`):

```markdown
- **Browser-flow / JobSpy are last resorts.** A deterministic ATS/API adapter beats
  driving a browser; `python -m jobhunt fallback` (JobSpy/Indeed) is only for
  `manual_review` dead-ends and never runs in the daily `sweep`.
```

with:

```markdown
- **Browser-flow scraping is a last resort; JobSpy-style discovery is now
  ApplyPilot's job, not this repo's.** This repo's own `jobhunt fallback`
  (JobSpy/Indeed) command was removed 2026-07-08 — it produced zero rows in
  its lifetime and is fully superseded by `python -m jobhunt
  import-applypilot`, which pulls from ApplyPilot's already-running,
  better-tuned JobSpy pipeline (`/opt/applypilot`) instead of reimplementing it.
```

Apply the identical replacement to `AGENTS.md`.

- [ ] **Step 4: Verify the edits landed identically in both files**

Run: `cd /opt/angelica-jobhunt && grep -n "import-applypilot\|maintenance freeze\|ApplyPilot's job" CLAUDE.md AGENTS.md`
Expected: matching lines present in both files.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: document ApplyPilot import path and dedicated-fleet maintenance freeze"
```

---

### Task 6: Wire `import-applypilot` into the daily cron script

**Files:**
- Modify: `daily-jobhunt.sh`

- [ ] **Step 1: Add the new step**

In `daily-jobhunt.sh`, insert a new block after the existing `sweep` step (currently lines 15-19) and before the `auto-draft` step (currently starting at line 21):

```bash
echo "--- import-applypilot ---"
python -m jobhunt import-applypilot --limit 50 --export || echo "WARNING: ApplyPilot import failed — continuing with existing data"
```

- [ ] **Step 2: Verify the script is still syntactically valid**

Run: `bash -n /opt/angelica-jobhunt/daily-jobhunt.sh`
Expected: no output (exit code 0 means no syntax errors)

- [ ] **Step 3: Commit**

```bash
git add daily-jobhunt.sh
git commit -m "chore(daily): pull fresh ApplyPilot discoveries in the daily run"
```

---

### Task 7: Sync ApplyPilot's timer with the daily cron

This task edits a systemd unit file outside this git repo (`/opt/applypilot` is a separate system) — call out each command's effect before running it.

**Files:**
- Modify: `/etc/systemd/system/applypilot-pipeline.timer` (system file, not tracked by this repo)

- [ ] **Step 1: Confirm current state**

Run: `systemctl list-timers applypilot-pipeline.timer && crontab -l | grep daily-jobhunt`
Expected: shows the timer's next run at 06:00 and the cron line `3 5 * * * /opt/angelica-jobhunt/daily-jobhunt.sh`.

- [ ] **Step 2: Edit the timer's `OnCalendar`**

In `/etc/systemd/system/applypilot-pipeline.timer`, change:

```ini
[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true
```

to:

```ini
[Timer]
OnCalendar=*-*-* 05:00:00
Persistent=true
```

- [ ] **Step 3: Reload systemd and verify**

```bash
systemctl daemon-reload
systemctl list-timers applypilot-pipeline.timer
```

Expected: next run listed at 05:00 the following day.

- [ ] **Step 4: Leave the jobhunt cron untouched**

No change needed — `3 5 * * * /opt/angelica-jobhunt/daily-jobhunt.sh` already runs at 5:03am, a deliberate 3-minute stagger after ApplyPilot's new 05:00 start (avoids both processes hitting network/CPU at the exact same instant; the Task 1 watermark means any of ApplyPilot's still-in-progress rows for that morning are simply picked up on the next day's run, nothing is lost).

---

### Task 8: End-to-end verification against the real ApplyPilot database

**Files:** none (verification only, read-only against both real databases via scratch copies)

- [ ] **Step 1: Smoke-test against a copy of the real jobhunt db and read-only against the real ApplyPilot db**

```bash
cd /opt/angelica-jobhunt
cp data/jobs.sqlite /tmp/jobhunt-smoke.sqlite
python -m jobhunt import-applypilot --db /tmp/jobhunt-smoke.sqlite --limit 20
```

Expected: prints `ApplyPilot import: fetched=<N> passed_filters=<M> kept=<K> new=<J> existing=<E>` with `K <= 20`. Since this is the first-ever run, the watermark seeds to start-of-today (UTC) — expect `N` to reflect roughly today's ApplyPilot discovery volume (historically ~100-400 rows/day pre-fit_score-filter; check `data/raw-jobs.md`'s discovered-today range if `N` is unexpectedly 0, which would mean ApplyPilot's pipeline hasn't run yet today).

- [ ] **Step 2: Spot-check the imported rows for NL relevance**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/jobhunt-smoke.sqlite')
conn.row_factory = sqlite3.Row
for row in conn.execute(\"SELECT company, title, location FROM jobs WHERE scraper_type='applypilot_import'\"):
    print(row['company'], '|', row['title'], '|', row['location'])
"
```

Expected: every printed `location` is NL-plausible (Dutch city, "Netherlands", or a recognized remote token) — specifically confirm none show a non-NL country (this is the direct check against the previously-reported US/Philippines leakage; if any appear, `jobhunt.assessment.location_ok` needs a follow-up fix before this ships, not a reason to relax the gate).

- [ ] **Step 3: Confirm the watermark advanced and a second run finds nothing new**

```bash
python -m jobhunt import-applypilot --db /tmp/jobhunt-smoke.sqlite --limit 20
```

Expected: `No new ApplyPilot rows since <timestamp>` (the watermark from Step 1 already covers everything currently in ApplyPilot's db).

- [ ] **Step 4: Clean up the scratch database**

```bash
rm /tmp/jobhunt-smoke.sqlite
```

- [ ] **Step 5: Report back**

Summarize for Angelica: how many jobs were fetched vs. kept, and confirm (or flag) whether the NL-relevance spot-check in Step 2 passed clean.
