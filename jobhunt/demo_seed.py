"""Seed (and remove) a fictional demo workspace so a new install has something to explore."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import yaml

from jobhunt.brand_theme import write_theme
from jobhunt.config import ROOT
from jobhunt.database import upsert_jobs
from jobhunt.models import Job

DEMO_SOURCE = "demo"
DEMO_DRAFT_COMPANY = "Lumen Collective"
DEMO_DRAFT_TITLE = "Brand Designer"

# (company, title, status, days_ago of the applied/rejected event or None)
_DEMO_JOBS = [
    ("Northstar Cloud", "Platform Engineer", "applied", 2),
    ("Veloce Mobility", "Operations Analyst", "applied", 1),
    ("Studio Kinetix", "Motion Designer", "applied", 1),
    ("Harbor & Pine", "Customer Success Lead", "rejected", 1),
    (DEMO_DRAFT_COMPANY, DEMO_DRAFT_TITLE, "new", None),
]

_DEMO_DESCRIPTION = (
    "A fictional sample role created by JobArcade's demo workspace. "
    "Open it to see how a draft, a tailored CV and a motivation letter fit together."
)


def demo_folder_name() -> str:
    """Folder name per the dashboard's own convention, so the draft links to the demo job."""
    from jobhunt.dashboard import _application_folder_name

    return _application_folder_name(DEMO_DRAFT_COMPANY, DEMO_DRAFT_TITLE)


def _is_demo_folder(folder: Path) -> bool:
    if folder.is_symlink() or not folder.is_dir():
        return False
    theme = folder / "brand-theme.yaml"
    try:
        data = yaml.safe_load(theme.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and data.get("provider") == DEMO_SOURCE


def _event_time(days_ago: int) -> str:
    return f"{(date.today() - timedelta(days=days_ago)).isoformat()} 12:00:00"


def seed_demo(conn: sqlite3.Connection, applications_dir: Path) -> dict:
    existing = conn.execute("SELECT COUNT(*) AS n FROM jobs WHERE source_platform = ?", (DEMO_SOURCE,)).fetchone()["n"]
    if existing:
        return {"jobs": 0, "draft_folder": str(applications_dir / demo_folder_name())}

    jobs = [
        Job(
            company=company,
            title=title,
            location="Remote",
            remote_type="remote",
            description=_DEMO_DESCRIPTION,
            apply_url=f"https://example.com/demo/{i}",
            source_url=f"https://example.com/demo/{i}",
            source_platform=DEMO_SOURCE,
            source_job_id=f"demo-{i}",
            status=status,
        )
        for i, (company, title, status, _days) in enumerate(_DEMO_JOBS, start=1)
    ]
    upsert_jobs(conn, jobs)
    for i, (_c, _t, status, days_ago) in enumerate(_DEMO_JOBS, start=1):
        if days_ago is None:
            continue
        row = conn.execute(
            "SELECT id FROM jobs WHERE source_platform = ? AND source_job_id = ?", (DEMO_SOURCE, f"demo-{i}")
        ).fetchone()
        conn.execute(
            "INSERT INTO status_events (job_id, status, created_at) VALUES (?, ?, ?)",
            (row["id"], status, _event_time(days_ago)),
        )
    conn.commit()

    folder = applications_dir / demo_folder_name()
    if not folder.exists() or _is_demo_folder(folder):
        folder.mkdir(parents=True, exist_ok=True)
        reference = ROOT / "Base" / "reference"
        for name in ("cv-data.yaml", "letter-data.yaml"):
            shutil.copyfile(reference / name, folder / name)
        (folder / "job-listing.md").write_text(
            f"# {DEMO_DRAFT_TITLE} - {DEMO_DRAFT_COMPANY}\n\n{_DEMO_DESCRIPTION}\n", encoding="utf-8"
        )
        write_theme(
            folder,
            {
                "enabled": True,
                "mode": "dark",
                "accent": "#E50914",
                "confidence": 0.9,
                "provider": "demo",
            },
        )
    return {"jobs": len(jobs), "draft_folder": str(folder)}


def clear_demo(conn: sqlite3.Connection, applications_dir: Path) -> dict:
    ids = [r["id"] for r in conn.execute("SELECT id FROM jobs WHERE source_platform = ?", (DEMO_SOURCE,)).fetchall()]
    if ids:
        marks = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM status_events WHERE job_id IN ({marks})", ids)
        conn.execute(f"DELETE FROM jobs WHERE id IN ({marks})", ids)
        conn.commit()
    folder = applications_dir / demo_folder_name()
    if _is_demo_folder(folder):
        shutil.rmtree(folder)
    return {"removed": len(ids)}
