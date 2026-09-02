import json

import pytest

from jobhunt.dashboard import create_feedback, create_manual_job
from jobhunt.database import init_db


def test_create_manual_job_requires_company_and_title(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    with pytest.raises(ValueError):
        create_manual_job(conn, {"title": "Brand Manager"})
    with pytest.raises(ValueError):
        create_manual_job(conn, {"company": "Acme"})


def test_create_manual_job_rejects_unknown_status(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    with pytest.raises(ValueError):
        create_manual_job(conn, {"company": "Acme", "title": "Brand Manager", "status": "bogus"})


def test_create_manual_job_is_scored_and_tagged_manual(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    result = create_manual_job(conn, {"company": "Acme", "title": "Brand Manager", "location": "Amsterdam"})

    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (result["id"],)).fetchone()
    assert row["source_platform"] == "manual"
    assert row["scraper_type"] == "manual"
    assert row["status"] == "new"
    assert row["fit_band"] in ("core_fit", "adjacent_plausible", "stretch")
    assert row["fit_band"] != "excluded"


def test_create_manual_job_falls_back_to_stretch_when_assessment_excludes_it(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    # No description/location at all is the likeliest path to a hard-fail in assess_job.
    result = create_manual_job(conn, {"company": "Acme", "title": "Director of Global Strategy"})

    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (result["id"],)).fetchone()
    assert row["fit_band"] == "stretch"
    assert row["score"] >= 40
    assert "Manually added" in json.loads(row["score_reasons"])


def test_create_manual_job_logs_a_status_event(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    result = create_manual_job(conn, {"company": "Acme", "title": "Brand Manager", "status": "applied"})

    events = conn.execute("SELECT job_id, status FROM status_events WHERE job_id = ?", (result["id"],)).fetchall()
    assert [(e["job_id"], e["status"]) for e in events] == [(result["id"], "applied")]


def test_create_manual_job_backdates_applied_event(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    result = create_manual_job(
        conn,
        {"company": "Acme", "title": "Brand Manager", "status": "applied", "applied_at": "2026-06-15"},
    )

    row = conn.execute("SELECT created_at FROM status_events WHERE job_id = ?", (result["id"],)).fetchone()
    assert row["created_at"].startswith("2026-06-15")


def test_create_manual_job_merges_with_a_later_scrape_of_the_same_url(tmp_path):
    from jobhunt.database import upsert_jobs
    from jobhunt.models import Job

    conn = init_db(tmp_path / "jobs.sqlite")
    manual = create_manual_job(conn, {"company": "Acme", "title": "Brand Manager", "apply_url": "https://acme.com/jobs/1"})

    scraped = Job(company="Acme", title="Brand Manager", apply_url="https://acme.com/jobs/1", source_platform="Greenhouse")
    new, existing = upsert_jobs(conn, [scraped])

    assert (new, existing) == (0, 1)
    assert conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"] == 1
    row = conn.execute("SELECT id FROM jobs").fetchone()
    assert row["id"] == manual["id"]


def test_create_feedback_requires_message(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    with pytest.raises(ValueError):
        create_feedback(conn, {"page": "odds"})


def test_create_feedback_stores_message_and_page(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    create_feedback(conn, {"message": "love the odds page", "page": "odds"})

    row = conn.execute("SELECT message, page FROM feedback").fetchone()
    assert row["message"] == "love the odds page"
    assert row["page"] == "odds"
