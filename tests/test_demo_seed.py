import yaml

from jobhunt import dashboard
from jobhunt.dashboard import fetch_stats
from jobhunt.database import connect, init_db, upsert_jobs
from jobhunt.demo_seed import DEMO_SOURCE, clear_demo, seed_demo
from jobhunt.models import Job


def _conn(tmp_path):
    return init_db(connect(tmp_path / "jobs.sqlite"))


def test_seed_demo_creates_five_jobs_and_one_draft(tmp_path):
    conn = _conn(tmp_path)
    apps = tmp_path / "Applications"
    result = seed_demo(conn, apps)
    assert result["jobs"] == 5
    rows = conn.execute("SELECT status FROM jobs WHERE source_platform = ?", (DEMO_SOURCE,)).fetchall()
    statuses = sorted(r["status"] for r in rows)
    assert statuses == ["applied", "applied", "applied", "new", "rejected"]
    folder = apps / "Lumen-Collective-Demo-Role"
    assert result["draft_folder"] == str(folder)
    for name in ("cv-data.yaml", "letter-data.yaml", "brand-theme.yaml", "job-listing.md"):
        assert (folder / name).is_file()
    theme = yaml.safe_load((folder / "brand-theme.yaml").read_text())
    assert theme["enabled"] is True and theme["mode"] == "dark" and theme["provider"] == "demo"


def test_seed_demo_is_idempotent(tmp_path):
    conn = _conn(tmp_path)
    apps = tmp_path / "Applications"
    seed_demo(conn, apps)
    again = seed_demo(conn, apps)
    assert again["jobs"] == 0
    assert conn.execute("SELECT COUNT(*) n FROM jobs").fetchone()["n"] == 5


def test_clear_demo_removes_only_demo_rows(tmp_path):
    conn = _conn(tmp_path)
    apps = tmp_path / "Applications"
    upsert_jobs(conn, [Job(company="Real Co", title="Real Role", source_platform="manual")])
    other = apps / "Real-Co-Real-Role"
    other.mkdir(parents=True)
    seed_demo(conn, apps)
    assert clear_demo(conn, apps) == {"removed": 5}
    assert conn.execute("SELECT COUNT(*) n FROM jobs").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) n FROM jobs WHERE source_platform='demo'").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) n FROM status_events WHERE job_id NOT IN (SELECT id FROM jobs)").fetchone()["n"] == 0
    assert not (apps / "Lumen-Collective-Demo-Role").exists()
    assert other.exists()


def test_seeded_applied_events_feed_stats(tmp_path):
    conn = _conn(tmp_path)
    seed_demo(conn, tmp_path / "Applications")
    stats = fetch_stats(conn)
    assert stats["applications_sent"] >= 4
    assert sum(d["count"] for d in stats["daily"]) == 3


def test_demo_routes(dashboard_server, tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    status, body, _ = dashboard_server("POST", "/api/demo/seed", {})
    assert status == 200 and body["jobs"] == 5
    assert (apps / "Lumen-Collective-Demo-Role" / "cv-data.yaml").is_file()
    status, body, _ = dashboard_server("POST", "/api/demo/seed", {})
    assert status == 200 and body["jobs"] == 0
    status, body, _ = dashboard_server("DELETE", "/api/demo")
    assert status == 200 and body["removed"] == 5
    assert not (apps / "Lumen-Collective-Demo-Role").exists()
