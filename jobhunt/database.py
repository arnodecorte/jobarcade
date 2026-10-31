from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobhunt.config import DB_PATH
from jobhunt.models import Job


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db(conn: sqlite3.Connection | Path | str | None = None) -> sqlite3.Connection:
    if conn is None:
        conn = connect()
    elif not isinstance(conn, sqlite3.Connection):
        conn = connect(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT,
            country TEXT,
            remote_type TEXT,
            department TEXT,
            employment_type TEXT,
            date_posted TEXT,
            description TEXT,
            requirements TEXT,
            apply_url TEXT,
            source_url TEXT,
            source_platform TEXT,
            source_job_id TEXT,
            scraper_type TEXT,
            discovered_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            expired_at TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            dedupe_key TEXT NOT NULL UNIQUE,
            miss_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            priority TEXT NOT NULL DEFAULT 'Low',
            score INTEGER NOT NULL DEFAULT 0,
            fit_band TEXT NOT NULL DEFAULT 'stretch',
            score_reasons TEXT
        )
        """
    )
    _ensure_column(conn, "jobs", "priority", "TEXT NOT NULL DEFAULT 'Low'")
    _ensure_column(conn, "jobs", "score", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "jobs", "fit_band", "TEXT NOT NULL DEFAULT 'stretch'")
    _ensure_column(conn, "jobs", "score_reasons", "TEXT")
    _ensure_column(conn, "jobs", "notes", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT,
            country TEXT,
            remote_type TEXT,
            department TEXT,
            employment_type TEXT,
            date_posted TEXT,
            description TEXT,
            requirements TEXT,
            apply_url TEXT,
            source_url TEXT,
            source_platform TEXT,
            source_job_id TEXT,
            scraper_type TEXT,
            dedupe_key TEXT NOT NULL,
            is_relevant INTEGER NOT NULL DEFAULT 0,
            assessment_summary TEXT
        )
        """
    )
    _ensure_column(conn, "raw_jobs", "assessment_summary", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_jobs_company ON raw_jobs(company)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_jobs_relevant ON raw_jobs(is_relevant)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scraper_health (
            company TEXT PRIMARY KEY,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL,
            scraper_type TEXT,
            strategy TEXT,
            raw_count INTEGER NOT NULL DEFAULT 0,
            relevant_count INTEGER NOT NULL DEFAULT 0,
            message TEXT,
            error TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scraper_health_status ON scraper_health(status)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status_events_created ON status_events(created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            page TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            encrypted_refresh_token TEXT NOT NULL,
            scopes TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_sync_at TEXT,
            sync_cursor TEXT,
            last_error TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_gmail_accounts_email ON gmail_accounts(email)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT NOT NULL UNIQUE,
            gmail_thread_id TEXT,
            account_email TEXT,
            sender TEXT,
            subject TEXT,
            received_at TEXT,
            snippet TEXT,
            body_hash TEXT,
            classification TEXT NOT NULL DEFAULT 'unknown',
            confidence REAL NOT NULL DEFAULT 0,
            matched_job_id INTEGER,
            match_reason TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gmail_messages_classification ON gmail_messages(classification)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gmail_messages_job ON gmail_messages(matched_job_id)")
    for name, definition in (
        ("classification_confidence", "REAL NOT NULL DEFAULT 0"),
        ("match_confidence", "REAL NOT NULL DEFAULT 0"),
        ("classifier_source", "TEXT NOT NULL DEFAULT 'rules'"),
        ("classifier_version", "TEXT"),
        ("classification_reason", "TEXT"),
        ("inferred_company", "TEXT"),
        ("inferred_role", "TEXT"),
        ("supporting_excerpts", "TEXT"),
        ("classifier_error", "TEXT"),
    ):
        _ensure_column(conn, "gmail_messages", name, definition)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT NOT NULL UNIQUE,
            job_id INTEGER,
            evidence_type TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            occurred_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_evidence_status ON email_evidence(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_evidence_job ON email_evidence(job_id)")
    for name, definition in (
        ("classification_confidence", "REAL NOT NULL DEFAULT 0"),
        ("match_confidence", "REAL NOT NULL DEFAULT 0"),
        ("original_evidence_type", "TEXT"),
        ("original_job_id", "INTEGER"),
        ("corrected_by_user", "INTEGER NOT NULL DEFAULT 0"),
        ("automation_outcome", "TEXT"),
        ("target_status", "TEXT"),
    ):
        _ensure_column(conn, "email_evidence", name, definition)
    conn.execute("UPDATE email_evidence SET evidence_type = 'unknown' WHERE evidence_type = 'ambiguous'")
    conn.execute("UPDATE gmail_messages SET classification = 'unknown' WHERE classification = 'ambiguous'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_settings (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            encrypted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            website_url TEXT,
            careers_url TEXT,
            logo_url TEXT,
            location_hint TEXT,
            industry_tags TEXT,
            aspiration_tags TEXT,
            role_signals TEXT,
            source_names TEXT,
            source_type TEXT NOT NULL DEFAULT 'curated',
            score INTEGER NOT NULL DEFAULT 0,
            score_reasons TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_checked_at TEXT,
            added_at TEXT
        )
        """
    )
    _ensure_column(conn, "company_candidates", "source_type", "TEXT NOT NULL DEFAULT 'curated'")
    _ensure_column(conn, "company_candidates", "suggested_careers_url", "TEXT")
    _ensure_column(conn, "company_candidates", "suggested_careers_url_reason", "TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_company_candidates_company_nocase ON company_candidates(company COLLATE NOCASE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_company_candidates_status_score ON company_candidates(status, score DESC)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_cursors (
            source TEXT PRIMARY KEY,
            last_discovered_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def normalize_key(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def dedupe_key(job: Job) -> str:
    if job.apply_url:
        return "url:" + normalize_key(job.apply_url)
    if job.source_job_id:
        return f"source:{normalize_key(job.company)}:{normalize_key(job.source_platform)}:{normalize_key(job.source_job_id)}"
    return f"fuzzy:{normalize_key(job.company)}:{normalize_key(job.title)}:{normalize_key(job.location)}"


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


ACTED_UPON_STATUSES = ("ready", "applied", "interviewing", "rejected", "offer", "skipped", "expired", "scrape_failed")


def find_acted_upon_duplicate(conn: sqlite3.Connection, job: Job) -> sqlite3.Row | None:
    """A re-scraped job can resurface under a new apply_url (aggregators like
    englishjobsearch.nl reuse the same listing across keyword searches, and a
    manually-added row for the same role may already exist with a different
    URL entirely). Match on normalized company+title against rows the user has
    already acted on, so a stale exact-URL dedupe_key miss doesn't re-surface
    something already applied to/skipped/expired as 'new'."""
    fuzzy = f"{normalize_key(job.company)}:{normalize_key(job.title)}"
    placeholders = ",".join("?" for _ in ACTED_UPON_STATUSES)
    candidates = conn.execute(
        f"SELECT id, company, title, status, dedupe_key FROM jobs WHERE status IN ({placeholders})",
        ACTED_UPON_STATUSES,
    ).fetchall()
    for row in candidates:
        if f"{normalize_key(row['company'])}:{normalize_key(row['title'])}" == fuzzy:
            return row
    return None


def upsert_jobs(conn: sqlite3.Connection, jobs: list[Job]) -> tuple[int, int]:
    now = utc_now()
    new = 0
    existing = 0
    for job in jobs:
        key = dedupe_key(job)
        row = conn.execute("SELECT id, status FROM jobs WHERE dedupe_key = ?", (key,)).fetchone()
        if not row:
            duplicate = find_acted_upon_duplicate(conn, job)
            if duplicate:
                conn.execute("UPDATE jobs SET last_seen_at = ? WHERE id = ?", (now, duplicate["id"]))
                existing += 1
                continue
        if row:
            conn.execute(
                """
                UPDATE jobs
                SET last_seen_at = ?,
                    expired_at = NULL,
                    miss_count = 0,
                    location = COALESCE(?, location),
                    description = COALESCE(?, description),
                    apply_url = COALESCE(?, apply_url),
                    source_job_id = COALESCE(?, source_job_id),
                    last_error = NULL,
                    priority = ?,
                    score = ?,
                    fit_band = ?,
                    score_reasons = ?
                WHERE id = ?
                """,
                (
                    now,
                    job.location,
                    job.description,
                    job.apply_url,
                    job.source_job_id,
                    job.priority,
                    job.score,
                    job.fit_band,
                    job.score_reasons,
                    row["id"],
                ),
            )
            existing += 1
            continue

        conn.execute(
            """
            INSERT INTO jobs (
                company, title, location, country, remote_type, department, employment_type,
                date_posted, description, requirements, apply_url, source_url, source_platform,
                source_job_id, scraper_type, discovered_at, last_seen_at, expired_at, status,
                dedupe_key, miss_count, last_error, priority, score, fit_band, score_reasons
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 0, NULL, ?, ?, ?, ?)
            """,
            (
                job.company,
                job.title,
                job.location,
                job.country,
                job.remote_type,
                job.department,
                job.employment_type,
                job.date_posted,
                job.description,
                job.requirements,
                job.apply_url,
                job.source_url,
                job.source_platform,
                job.source_job_id,
                job.scraper_type,
                now,
                now,
                job.status,
                key,
                job.priority,
                job.score,
                job.fit_band,
                job.score_reasons,
            ),
        )
        new += 1
    conn.commit()
    return new, existing


def replace_raw_jobs(conn: sqlite3.Connection, company: str, jobs: list[Job], relevant_keys: set[str]) -> None:
    now = utc_now()
    from jobhunt.assessment import apply_assessment, assess_job

    conn.execute("DELETE FROM raw_jobs WHERE company = ?", (company,))
    conn.executemany(
        """
        INSERT INTO raw_jobs (
            captured_at, company, title, location, country, remote_type, department,
            employment_type, date_posted, description, requirements, apply_url,
            source_url, source_platform, source_job_id, scraper_type, dedupe_key,
            is_relevant, assessment_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                now,
                job.company,
                job.title,
                job.location,
                job.country,
                job.remote_type,
                job.department,
                job.employment_type,
                job.date_posted,
                job.description,
                job.requirements,
                job.apply_url,
                job.source_url,
                job.source_platform,
                job.source_job_id,
                job.scraper_type,
                dedupe_key(job),
                1 if dedupe_key(job) in relevant_keys else 0,
                (job.assessment_summary or apply_assessment(job, assess_job(job)).assessment_summary),
            )
            for job in jobs
            if job.title
        ],
    )
    conn.commit()


def expire_filtered_out_jobs(conn: sqlite3.Connection, raw_keys: set[str], relevant_keys: set[str]) -> int:
    """Expire existing active jobs that were seen again but no longer pass filters.

    Generated or submitted applications are intentionally preserved: `ready`,
    `applied`, and `interviewing` represent human interaction, not scraper fit.
    """
    filtered_out = raw_keys - relevant_keys
    if not filtered_out:
        return 0
    now = utc_now()
    placeholders = ",".join("?" for _ in filtered_out)
    protected = ("ready", "applied", "interviewing", "rejected", "offer", "skipped", "expired", "scrape_failed")
    protected_placeholders = ",".join("?" for _ in protected)
    cursor = conn.execute(
        f"""
        UPDATE jobs
        SET status = 'expired',
            expired_at = ?,
            miss_count = 0
        WHERE dedupe_key IN ({placeholders})
          AND status NOT IN ({protected_placeholders})
        """,
        (now, *filtered_out, *protected),
    )
    conn.commit()
    return cursor.rowcount


def record_company_failure(conn: sqlite3.Connection, company: str, error: str) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO jobs (
            company, title, source_platform, scraper_type, discovered_at, last_seen_at,
            status, dedupe_key, last_error
        )
        VALUES (?, ?, ?, ?, ?, ?, 'scrape_failed', ?, ?)
        ON CONFLICT(dedupe_key) DO UPDATE SET
            last_seen_at = excluded.last_seen_at,
            status = 'scrape_failed',
            last_error = excluded.last_error
        """,
        (company, "__scrape_failure__", "internal", "failure", now, now, f"failure:{normalize_key(company)}", error[:1000]),
    )
    conn.commit()


def record_scraper_health(
    conn: sqlite3.Connection,
    company: str,
    status: str,
    scraper_type: str | None = None,
    strategy: str | None = None,
    raw_count: int = 0,
    relevant_count: int = 0,
    message: str | None = None,
    error: str | None = None,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO scraper_health (
            company, checked_at, status, scraper_type, strategy, raw_count,
            relevant_count, message, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company) DO UPDATE SET
            checked_at = excluded.checked_at,
            status = excluded.status,
            scraper_type = excluded.scraper_type,
            strategy = excluded.strategy,
            raw_count = excluded.raw_count,
            relevant_count = excluded.relevant_count,
            message = excluded.message,
            error = excluded.error
        """,
        (
            company,
            now,
            status,
            scraper_type,
            strategy,
            raw_count,
            relevant_count,
            message[:1000] if message else None,
            error[:1000] if error else None,
        ),
    )
    conn.commit()


def mark_missing_expired(conn: sqlite3.Connection, seen_keys: set[str], max_misses: int = 3) -> None:
    now = utc_now()
    rows = conn.execute(
        "SELECT id, dedupe_key, miss_count, status FROM jobs WHERE status != 'scrape_failed' AND expired_at IS NULL"
    ).fetchall()
    for row in rows:
        if row["dedupe_key"] in seen_keys:
            continue
        miss_count = int(row["miss_count"] or 0) + 1
        expired_at = now if miss_count >= max_misses else None
        if expired_at and row["status"] not in ("ready", "applied", "interviewing", "rejected", "offer", "skipped"):
            conn.execute(
                "UPDATE jobs SET miss_count = ?, expired_at = ?, status = 'expired' WHERE id = ?",
                (miss_count, expired_at, row["id"]),
            )
        else:
            conn.execute("UPDATE jobs SET miss_count = ? WHERE id = ?", (miss_count, row["id"]))
    conn.commit()


def fetch_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT date(discovered_at) AS date, company, title AS role, location, apply_url AS url, status,
               source_platform, source_job_id, date_posted, last_seen_at, priority, score, fit_band
        FROM jobs
        WHERE title != '__scrape_failure__'
        ORDER BY discovered_at DESC, company ASC, title ASC
        """
    ).fetchall()


def fetch_raw_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT captured_at, company, title AS role, location, department, employment_type,
               date_posted, apply_url AS url, source_platform, source_job_id, is_relevant
        FROM raw_jobs
        ORDER BY company ASC, is_relevant DESC, title ASC, location ASC
        """
    ).fetchall()


def fetch_scraper_health_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT company, checked_at, status, scraper_type, strategy, raw_count,
               relevant_count, message, error
        FROM scraper_health
        ORDER BY
            CASE status
                WHEN 'failed' THEN 0
                WHEN 'warning' THEN 1
                WHEN 'manual_review' THEN 2
                WHEN 'unknown' THEN 3
                WHEN 'ok' THEN 4
                ELSE 5
            END,
            company ASC
        """
    ).fetchall()
