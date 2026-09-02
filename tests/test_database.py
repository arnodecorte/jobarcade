from datetime import datetime, timedelta

from jobhunt.database import (
    advance_import_cursor,
    dedupe_key,
    expire_filtered_out_jobs,
    fetch_scraper_health_rows,
    get_import_cursor,
    init_db,
    mark_missing_expired,
    record_scraper_health,
    upsert_jobs,
)
from jobhunt.models import Job


def test_upsert_preserves_discovered_at_and_refreshes_last_seen(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(company="Paramount", title="Content Coordinator", location="Amsterdam", apply_url="https://x/jobs/1")

    new, existing = upsert_jobs(conn, [job])
    assert (new, existing) == (1, 0)
    first = conn.execute("SELECT discovered_at, last_seen_at FROM jobs WHERE apply_url = ?", (job.apply_url,)).fetchone()

    job.description = "Updated description"
    new, existing = upsert_jobs(conn, [job])
    assert (new, existing) == (0, 1)
    second = conn.execute("SELECT discovered_at, last_seen_at, description FROM jobs WHERE apply_url = ?", (job.apply_url,)).fetchone()

    assert second["discovered_at"] == first["discovered_at"]
    assert second["last_seen_at"] >= first["last_seen_at"]
    assert second["description"] == "Updated description"


def test_dedupe_prefers_url_then_source_id_then_fuzzy():
    by_url = Job(company="A", title="Marketing Manager", apply_url="https://example.com/job/1", source_job_id="REQ")
    by_source = Job(company="A", title="Marketing Manager", source_platform="workday", source_job_id="REQ")
    by_fuzzy = Job(company="A", title="Marketing Manager", location="Amsterdam")

    assert dedupe_key(by_url).startswith("url:")
    assert dedupe_key(by_source).startswith("source:")
    assert dedupe_key(by_fuzzy).startswith("fuzzy:")


def test_upsert_skips_acted_upon_duplicate_resurfacing_under_new_url(tmp_path):
    # Pearl Abyss scenario: a manually-tracked, already-applied job re-surfaces
    # via a scraper (e.g. an aggregator clickout link) under a different
    # apply_url than the one Angie actually applied through. The exact
    # dedupe_key won't match, but company+title fuzzy matching should still
    # recognize it and skip creating a duplicate 'new' row.
    conn = init_db(tmp_path / "jobs.sqlite")
    applied = Job(
        company="Pearl Abyss",
        title="Social media manager",
        location="Amstelveen",
        apply_url="https://apply.workable.com/pearlabyss-europe/j/9D1C67A46B/",
        source_platform="manual",
        status="applied",
    )
    upsert_jobs(conn, [applied])

    rescraped = Job(
        company="Pearl Abyss",
        title="Social media manager",
        location="Amstelveen",
        apply_url="https://englishjobsearch.nl/clickout/abc123",
        source_platform="englishjobsearch",
        status="new",
    )
    new, existing = upsert_jobs(conn, [rescraped])

    assert (new, existing) == (0, 1)
    rows = conn.execute("SELECT company, title, status, apply_url FROM jobs").fetchall()
    assert len(rows) == 1  # no duplicate row created
    assert rows[0]["status"] == "applied"
    assert rows[0]["apply_url"] == "https://apply.workable.com/pearlabyss-europe/j/9D1C67A46B/"


def test_missing_jobs_do_not_expire_ready_applied_or_interviewing(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    jobs = [
        Job(company="A", title="Content Coordinator", location="Amsterdam", apply_url="https://x/ready", status="ready"),
        Job(company="A", title="Brand Manager", location="Amsterdam", apply_url="https://x/applied", status="applied"),
        Job(company="A", title="Campaign Specialist", location="Amsterdam", apply_url="https://x/interview", status="interviewing"),
        Job(company="A", title="CRM Specialist", location="Amsterdam", apply_url="https://x/new", status="new"),
    ]
    upsert_jobs(conn, jobs)

    mark_missing_expired(conn, set(), max_misses=1)

    statuses = {
        row["apply_url"]: row["status"]
        for row in conn.execute("SELECT apply_url, status FROM jobs").fetchall()
    }
    assert statuses["https://x/ready"] == "ready"
    assert statuses["https://x/applied"] == "applied"
    assert statuses["https://x/interview"] == "interviewing"
    assert statuses["https://x/new"] == "expired"


def test_filtered_out_jobs_expire_unless_human_protected(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    active = Job(company="A", title="Technical Account Manager", location="Amsterdam", apply_url="https://x/active", status="new")
    ready = Job(company="A", title="Senior Brand Manager", location="Amsterdam", apply_url="https://x/ready", status="ready")
    applied = Job(company="A", title="Regional Marketing Manager", location="Amsterdam", apply_url="https://x/applied", status="applied")
    upsert_jobs(conn, [active, ready, applied])
    raw_keys = {dedupe_key(active), dedupe_key(ready), dedupe_key(applied)}

    assert expire_filtered_out_jobs(conn, raw_keys, set()) == 1

    statuses = {
        row["apply_url"]: row["status"]
        for row in conn.execute("SELECT apply_url, status FROM jobs").fetchall()
    }
    assert statuses["https://x/active"] == "expired"
    assert statuses["https://x/ready"] == "ready"
    assert statuses["https://x/applied"] == "applied"


def test_init_db_adds_priority_column_if_missing(tmp_path):
    import sqlite3
    db_file = tmp_path / "jobs.sqlite"
    
    # 1. Create a legacy database without the priority column
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, company TEXT NOT NULL, title TEXT NOT NULL, discovered_at TEXT, last_seen_at TEXT, status TEXT DEFAULT 'new', dedupe_key TEXT UNIQUE)")
    conn.commit()
    conn.close()
    
    # 2. Run init_db which should execute the migration
    from jobhunt.database import init_db
    conn = init_db(db_file)
    
    # 3. Check if assessment columns exist
    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()] # row[1] is name
    assert "priority" in columns
    assert "score" in columns
    assert "fit_band" in columns
    assert "score_reasons" in columns
    
    conn.close()

def test_upsert_saves_and_updates_priority(tmp_path):
    from jobhunt.database import init_db, upsert_jobs
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(
        company="Paramount",
        title="Content Coordinator",
        location="Amsterdam",
        apply_url="https://x/jobs/1",
        priority="⭐ High",
        score=88,
        fit_band="core_fit",
        score_reasons='["Core fit"]',
    )
    
    upsert_jobs(conn, [job])
    row = conn.execute("SELECT priority, score, fit_band, score_reasons FROM jobs WHERE apply_url = ?", (job.apply_url,)).fetchone()
    assert row["priority"] == "⭐ High"
    assert row["score"] == 88
    assert row["fit_band"] == "core_fit"
    
    job.priority = "Medium"
    job.score = 66
    job.fit_band = "adjacent_plausible"
    upsert_jobs(conn, [job])
    row = conn.execute("SELECT priority, score, fit_band FROM jobs WHERE apply_url = ?", (job.apply_url,)).fetchone()
    assert row["priority"] == "Medium"
    assert row["score"] == 66
    assert row["fit_band"] == "adjacent_plausible"
    
    conn.close()


def test_export_includes_priority(tmp_path):
    from jobhunt.database import init_db, upsert_jobs
    from jobhunt.export import export_csv, export_markdown
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(company="Paramount", title="Content Coordinator", location="Amsterdam", apply_url="https://x/jobs/1", priority="⭐ High", score=88, fit_band="core_fit")
    upsert_jobs(conn, [job])
    
    csv_path = tmp_path / "jobs.csv"
    md_path = tmp_path / "careers-directory.md"
    
    export_csv(conn, csv_path)
    export_markdown(conn, md_path)
    
    # Check CSV contents
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "priority" in csv_text
    assert "fit_band" in csv_text
    assert "⭐ High" in csv_text
    
    # Check Markdown contents
    from datetime import datetime, timezone
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_text = md_path.read_text(encoding="utf-8")
    assert "| date | company | role | location | url | status | priority | score | fit_band |" in md_text
    assert f"| {today_str} | Paramount | Content Coordinator | Amsterdam | https://x/jobs/1 | new | ⭐ High | 88 | core_fit |" in md_text
    
    conn.close()


def test_raw_export_includes_unfiltered_snapshot(tmp_path):
    from jobhunt.database import init_db, replace_raw_jobs
    from jobhunt.export import export_raw_csv, export_raw_markdown
    conn = init_db(tmp_path / "jobs.sqlite")
    relevant = Job(company="Adyen", title="Marketing Manager", location="Amsterdam", apply_url="https://x/jobs/1")
    non_relevant = Job(company="Adyen", title="Backend Engineer", location="Berlin", apply_url="https://x/jobs/2")
    replace_raw_jobs(conn, "Adyen", [relevant, non_relevant], {dedupe_key(relevant)})
    row = conn.execute("SELECT assessment_summary FROM raw_jobs WHERE title = ?", ("Marketing Manager",)).fetchone()
    assert row["assessment_summary"]

    csv_path = tmp_path / "raw-jobs.csv"
    md_path = tmp_path / "raw-jobs.md"

    assert export_raw_csv(conn, csv_path) == 2
    assert export_raw_markdown(conn, md_path) == 2

    csv_text = csv_path.read_text(encoding="utf-8")
    assert "Marketing Manager" in csv_text
    assert "Backend Engineer" in csv_text
    assert "is_relevant" in csv_text

    md_text = md_path.read_text(encoding="utf-8")
    assert "## Adyen (2 raw, 1 relevant)" in md_text
    assert "| yes | Marketing Manager | Amsterdam" in md_text
    assert "|  | Backend Engineer | Berlin" in md_text

    conn.close()


def test_record_scraper_health_upserts_latest_company_state(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")

    record_scraper_health(
        conn,
        "Adyen",
        "warning",
        scraper_type="dedicated",
        strategy="greenhouse",
        raw_count=0,
        relevant_count=0,
        message="Dedicated scraper returned zero raw jobs.",
    )
    record_scraper_health(
        conn,
        "Adyen",
        "ok",
        scraper_type="dedicated",
        strategy="greenhouse",
        raw_count=8,
        relevant_count=2,
    )

    rows = fetch_scraper_health_rows(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["company"] == "Adyen"
    assert row["status"] == "ok"
    assert row["raw_count"] == 8
    assert row["relevant_count"] == 2

    conn.close()


def test_load_companies_accepts_optional_brand_and_logo_urls(tmp_path):
    from jobhunt.config import load_companies

    path = tmp_path / "companies.yaml"
    path.write_text(
        """
companies:
  - company: Spotify
    careers_url: https://lifeatspotify.com
    scraper_type: manual_review
    enabled: true
    logo_url: https://www.google.com/s2/favicons?domain=lifeatspotify.com&sz=64
    brand_url: https://spotify.com
""",
        encoding="utf-8",
    )

    companies = load_companies(path)

    assert companies[0].logo_url == "https://www.google.com/s2/favicons?domain=lifeatspotify.com&sz=64"
    assert companies[0].brand_url == "https://spotify.com"


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
    seed = get_import_cursor(conn, "applypilot")  # today's date at UTC midnight

    # Both timestamps must be relative to the real seed (today), not hardcoded --
    # a hardcoded "later" date eventually becomes the past and the test starts
    # failing on its own (caught 2026-07-10: seed was 2026-07-10, "later" was
    # hardcoded to 2026-07-09).
    later = (datetime.fromisoformat(seed) + timedelta(days=1)).isoformat()
    advance_import_cursor(conn, "applypilot", later)
    assert get_import_cursor(conn, "applypilot") == later

    earlier = (datetime.fromisoformat(seed) - timedelta(days=365)).isoformat()
    advance_import_cursor(conn, "applypilot", earlier)
    assert get_import_cursor(conn, "applypilot") == later


def test_import_cursor_is_per_source(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    get_import_cursor(conn, "applypilot")
    advance_import_cursor(conn, "applypilot", "2026-07-09T10:00:00+00:00")

    other = get_import_cursor(conn, "some_other_source")
    assert other != "2026-07-09T10:00:00+00:00"
