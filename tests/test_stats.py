from datetime import date, timedelta

from jobhunt.dashboard import audit_status_event_hygiene, fetch_lifecycle_stats, fetch_stats, update_job_status
from jobhunt.database import init_db, upsert_jobs
from jobhunt.models import Job


def test_update_job_status_logs_an_event(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(conn, [Job(company="A", title="Content Coordinator", location="Amsterdam", apply_url="https://x/1")])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]

    update_job_status(conn, job_id, "applied")

    events = conn.execute("SELECT job_id, status FROM status_events").fetchall()
    assert [(e["job_id"], e["status"]) for e in events] == [(job_id, "applied")]


def _seed_apply_day(conn, day: date, count: int = 1) -> None:
    for _ in range(count):
        conn.execute(
            "INSERT INTO status_events (job_id, status, created_at) VALUES (?, 'applied', ?)",
            (1, f"{day.isoformat()} 12:00:00"),
        )
    conn.commit()


def test_fetch_stats_counts_sent_streaks_and_cadence(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(
        conn,
        [
            Job(company="A", title="Brand Manager", location="Amsterdam", apply_url="https://x/a", status="applied"),
            Job(company="A", title="Campaign Lead", location="Amsterdam", apply_url="https://x/b", status="interviewing"),
            Job(company="A", title="CRM Specialist", location="Amsterdam", apply_url="https://x/c", status="new"),
        ],
    )
    today = date.today()
    # 3-day current streak ending today, plus an older isolated day (gap = streak resets).
    _seed_apply_day(conn, today, count=2)
    _seed_apply_day(conn, today - timedelta(days=1))
    _seed_apply_day(conn, today - timedelta(days=2))
    _seed_apply_day(conn, today - timedelta(days=10))

    stats = fetch_stats(conn)

    assert stats["applications_sent"] == 2  # applied + interviewing
    assert stats["pulls_today"] == 2
    assert stats["current_streak"] == 3
    assert stats["best_streak"] == 3
    # 4 applied events fall within the trailing 7 days (today x2, -1, -2); /7.
    assert stats["actual_cadence_7d"] == round(4 / 7, 2)
    assert "lifecycle" in stats


def test_lifecycle_stats_separate_immature_pending_from_mature_denominator(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(
        conn,
        [
            Job(company="A", title="Fresh Pending", apply_url="https://x/fresh", status="applied"),
            Job(company="A", title="Mature Pending", apply_url="https://x/mature", status="applied"),
            Job(company="A", title="Known Rejection", apply_url="https://x/rej", status="rejected"),
            Job(company="A", title="Interview", apply_url="https://x/int", status="interviewing"),
        ],
    )
    ids = {row["title"]: row["id"] for row in conn.execute("SELECT id, title FROM jobs").fetchall()}
    conn.executemany(
        "INSERT INTO status_events (job_id, status, created_at) VALUES (?, 'applied', ?)",
        [
            (ids["Fresh Pending"], "2026-07-01 12:00:00"),
            (ids["Mature Pending"], "2026-06-01 12:00:00"),
            (ids["Known Rejection"], "2026-07-01 12:00:00"),
            (ids["Interview"], "2026-07-01 12:00:00"),
        ],
    )
    conn.execute(
        "INSERT INTO status_events (job_id, status, created_at) VALUES (?, 'rejected', ?)",
        (ids["Known Rejection"], "2026-07-03 12:00:00"),
    )
    conn.commit()

    lifecycle = fetch_lifecycle_stats(conn, today=date(2026, 7, 5))

    assert lifecycle["submitted_total"] == 4
    assert lifecycle["pending_total"] == 2
    assert lifecycle["immature_pending"] == 1
    assert lifecycle["matured_no_response"] == 1
    # Known rejection + interview count immediately; mature pending silence also enters denominator.
    assert lifecycle["matured_denominator"] == 3
    assert lifecycle["interviews"] == 1
    assert lifecycle["rejections"] == 1
    assert lifecycle["response_rate_observed"] == round(1 / 3, 4)


def test_lifecycle_bucket_boundaries(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    jobs = [
        Job(company="A", title="D0", apply_url="https://x/0", status="applied"),
        Job(company="A", title="D7", apply_url="https://x/7", status="applied"),
        Job(company="A", title="D14", apply_url="https://x/14", status="applied"),
        Job(company="A", title="D30", apply_url="https://x/30", status="applied"),
        Job(company="A", title="D45", apply_url="https://x/45", status="applied"),
    ]
    upsert_jobs(conn, jobs)
    ids = {row["title"]: row["id"] for row in conn.execute("SELECT id, title FROM jobs").fetchall()}
    conn.executemany(
        "INSERT INTO status_events (job_id, status, created_at) VALUES (?, 'applied', ?)",
        [
            (ids["D0"], "2026-07-05 12:00:00"),
            (ids["D7"], "2026-06-28 12:00:00"),
            (ids["D14"], "2026-06-21 12:00:00"),
            (ids["D30"], "2026-06-05 12:00:00"),
            (ids["D45"], "2026-05-21 12:00:00"),
        ],
    )
    conn.commit()

    buckets = fetch_lifecycle_stats(conn, today=date(2026, 7, 5))["buckets"]

    assert buckets == {
        "fresh_0_6d": 1,
        "early_7_13d": 1,
        "aging_14_29d": 1,
        "mature_30_44d": 1,
        "ghosted_45d_plus": 1,
    }


def test_status_event_hygiene_audit_flags_event_gaps(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(
        conn,
        [
            Job(company="A", title="Duplicate Applied", apply_url="https://x/dup", status="applied"),
            Job(company="A", title="Rejected Missing Apply", apply_url="https://x/missing", status="rejected"),
        ],
    )
    ids = {row["title"]: row["id"] for row in conn.execute("SELECT id, title FROM jobs").fetchall()}
    conn.executemany(
        "INSERT INTO status_events (job_id, status, created_at) VALUES (?, 'applied', ?)",
        [
            (ids["Duplicate Applied"], "2026-07-01 12:00:00"),
            (ids["Duplicate Applied"], "2026-07-01 13:00:00"),
        ],
    )
    conn.commit()

    audit = audit_status_event_hygiene(conn)

    assert audit["counts"]["duplicate_applied"] == 1
    assert audit["duplicate_applied"][0]["title"] == "Duplicate Applied"
    assert audit["counts"]["missing_applied_event"] == 1
    assert audit["missing_applied_event"][0]["title"] == "Rejected Missing Apply"
    assert audit["counts"]["rejected_without_rejected_event"] == 1
