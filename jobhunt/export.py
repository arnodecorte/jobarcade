from __future__ import annotations

import csv

from jobhunt.config import CSV_PATH, DIRECTORY_PATH, RAW_CSV_PATH, RAW_MARKDOWN_PATH
from jobhunt.database import fetch_export_rows, fetch_raw_export_rows


def export_csv(conn, path=CSV_PATH) -> int:
    rows = fetch_export_rows(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "company",
        "role",
        "location",
        "url",
        "status",
        "priority",
        "score",
        "fit_band",
        "source_platform",
        "source_job_id",
        "date_posted",
        "last_seen_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})
    return len(rows)


def _escape_md(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def export_markdown(conn, path=DIRECTORY_PATH) -> int:
    rows = fetch_export_rows(conn)
    lines = [
        "# Careers Directory",
        "",
        "Human-readable export from `data/jobs.sqlite`. Run `python -m jobhunt export` to refresh.",
        "",
        "## Schema",
        "",
        "| Field | Notes |",
        "|---|---|",
        "| `date` | ISO date the role was first found (YYYY-MM-DD) |",
        "| `company` | Company name |",
        "| `role` | Job title as listed |",
        "| `location` | City / country |",
        "| `url` | Direct link to the posting |",
        "| `status` | `new` · `reviewed` · `tailoring` · `ready` · `applied` · `interviewing` · `rejected` · `offer` · `skipped` · `expired` · `scrape_failed` |",
        "| `priority` | `⭐ High` · `Medium` · `Low` derived from score |",
        "| `score` | 0-100 attainability-first score |",
        "| `fit_band` | `core_fit` · `adjacent_plausible` · `stretch` |",
        "",
        "---",
        "",
        "## Log",
        "",
        "| date | company | role | location | url | status | priority | score | fit_band |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {date} | {company} | {role} | {location} | {url} | {status} | {priority} | {score} | {fit_band} |".format(
                date=_escape_md(row["date"]),
                company=_escape_md(row["company"]),
                role=_escape_md(row["role"]),
                location=_escape_md(row["location"]),
                url=_escape_md(row["url"]),
                status=_escape_md(row["status"]),
                priority=_escape_md(row["priority"]),
                score=_escape_md(row["score"]),
                fit_band=_escape_md(row["fit_band"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def export_raw_csv(conn, path=RAW_CSV_PATH) -> int:
    rows = fetch_raw_export_rows(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "captured_at",
        "company",
        "role",
        "location",
        "department",
        "employment_type",
        "date_posted",
        "url",
        "source_platform",
        "source_job_id",
        "is_relevant",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})
    return len(rows)


def export_raw_markdown(conn, path=RAW_MARKDOWN_PATH) -> int:
    rows = fetch_raw_export_rows(conn)
    lines = [
        "# Raw Jobs Drilldown",
        "",
        "Latest unfiltered scraper snapshot from `data/jobs.sqlite`. This is browse-only; filtered application candidates remain in `careers-directory.md`.",
        "",
    ]
    current_company = None
    for row in rows:
        if row["company"] != current_company:
            current_company = row["company"]
            count = sum(1 for item in rows if item["company"] == current_company)
            relevant = sum(1 for item in rows if item["company"] == current_company and item["is_relevant"])
            lines.extend(
                [
                    f"## {current_company} ({count} raw, {relevant} relevant)",
                    "",
                    "| relevant | role | location | department | url | source |",
                    "|---|---|---|---|---|---|",
                ]
            )
        lines.append(
            "| {relevant} | {role} | {location} | {department} | {url} | {source} |".format(
                relevant="yes" if row["is_relevant"] else "",
                role=_escape_md(row["role"]),
                location=_escape_md(row["location"]),
                department=_escape_md(row["department"]),
                url=_escape_md(row["url"]),
                source=_escape_md(row["source_platform"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def export_all(conn) -> int:
    count = export_csv(conn)
    export_markdown(conn)
    export_raw_csv(conn)
    export_raw_markdown(conn)
    return count
