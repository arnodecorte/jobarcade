from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from jobhunt.config import DB_PATH
from jobhunt.database import connect, init_db
from jobhunt.dashboard import serve_dashboard
from jobhunt.export import export_all


def cmd_validate(args: argparse.Namespace) -> int:
    errors: list[str] = []
    try:
        from jobhunt.onboarding import ensure_profile_file
        from jobhunt.profile import load_candidate_profile
        if ensure_profile_file():
            print("Profile: created config/profile.yaml from the example")
        profile = load_candidate_profile()
        print(f"Profile: OK (candidate: {profile.name})")
    except Exception as exc:
        errors.append(f"profile config failed: {exc}")

    try:
        conn = init_db(connect(args.db))
        conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
        print(f"Database: OK ({args.db})")
    except Exception as exc:
        errors.append(f"database failed: {exc}")

    typst = shutil.which("typst")
    if typst:
        print(f"Typst CLI: OK ({typst})")
    else:
        print("WARNING: typst binary not found in PATH", file=sys.stderr)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK")
    return 0


def cmd_clean_db(args: argparse.Namespace) -> int:
    """Clean up existing database rows that no longer pass the filters."""
    from jobhunt.assessment import assess_job
    from jobhunt.models import Job

    conn = init_db(connect(args.db))
    protected = ("ready", "applied", "interviewing")
    placeholders = ",".join("?" for _ in protected)
    rows = conn.execute(
        f"""
        SELECT id, company, title, location, country, remote_type, department,
               employment_type, date_posted, description, requirements, apply_url,
               source_url, source_platform, source_job_id, scraper_type, dedupe_key, status
        FROM jobs
        WHERE status NOT IN ({placeholders})
        """,
        protected,
    ).fetchall()

    deleted_count = 0
    for row in rows:
        job = Job(
            company=row["company"],
            title=row["title"],
            location=row["location"],
            country=row["country"],
            remote_type=row["remote_type"],
            department=row["department"],
            employment_type=row["employment_type"],
            date_posted=row["date_posted"],
            description=row["description"],
            requirements=row["requirements"],
            apply_url=row["apply_url"],
            source_url=row["source_url"],
            source_platform=row["source_platform"],
            source_job_id=row["source_job_id"],
            scraper_type=row["scraper_type"],
        )
        assessment = assess_job(job)
        if not assessment.included:
            conn.execute("DELETE FROM jobs WHERE id = ?", (row["id"],))
            conn.execute(
                "UPDATE raw_jobs SET is_relevant = 0, assessment_summary = ? WHERE dedupe_key = ?",
                (assessment.summary_json(), row["dedupe_key"]),
            )
            deleted_count += 1
            print(f"Purged: {row['company']} - {row['title']} ({assessment.hard_fail_reason})")

    conn.commit()
    print(f"Done. Purged {deleted_count} jobs from the database.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = init_db(connect(args.db))
    count = export_all(conn)
    print(f"Exported {count} jobs to careers-directory.md, data/jobs.csv, data/raw-jobs.md, and data/raw-jobs.csv")
    return 0


def cmd_outcome_audit(args: argparse.Namespace) -> int:
    from jobhunt.dashboard import audit_status_event_hygiene, fetch_lifecycle_stats

    conn = init_db(connect(args.db))
    lifecycle = fetch_lifecycle_stats(conn)
    hygiene = audit_status_event_hygiene(conn)
    if args.json:
        print(json.dumps({"lifecycle": lifecycle, "hygiene": hygiene}, indent=2))
        return 0

    print("Lifecycle")
    print(f"  submitted_total:      {lifecycle['submitted_total']}")
    print(f"  pending_total:        {lifecycle['pending_total']}")
    print(f"  matured_denominator:  {lifecycle['matured_denominator']}")
    print(f"  immature_pending:     {lifecycle['immature_pending']}")
    print(f"  matured_no_response:  {lifecycle['matured_no_response']}")
    print(f"  ghosted:              {lifecycle['ghosted']}")
    print(f"  follow_up_due:        {lifecycle['follow_up_due']}")
    print(f"  interviews:           {lifecycle['interviews']}")
    print(f"  rejections:           {lifecycle['rejections']}")
    print(
        "  response_rate:        "
        f"{lifecycle['response_rate_observed'] * 100:.1f}% "
        f"(95% range {lifecycle['response_rate_low'] * 100:.1f}%–{lifecycle['response_rate_high'] * 100:.1f}%)"
    )
    print("  buckets:              " + ", ".join(f"{k}={v}" for k, v in lifecycle["buckets"].items()))

    print("\nEvent hygiene")
    for key, count in hygiene["counts"].items():
        print(f"  {key}: {count}")
    for key in ("duplicate_applied", "missing_applied_event", "rejected_without_rejected_event", "orphan_events"):
        rows = hygiene[key]
        if not rows:
            continue
        print(f"\n{key} (showing first {min(args.limit, len(rows))})")
        for row in rows[: args.limit]:
            if "company" in row:
                print(f"  #{row['job_id']} {row['company']} — {row['title']}")
            else:
                print(f"  event #{row['id']} job_id={row['job_id']} status={row['status']} at {row['created_at']}")
    return 0


def cmd_gmail_oauth_url(args: argparse.Namespace) -> int:
    from jobhunt.gmail_integration import build_auth_url, load_gmail_config

    conn = init_db(connect(args.db))
    payload = build_auth_url(load_gmail_config(conn))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Open this URL to connect Gmail:")
        print(payload["auth_url"])
        print()
        print(f"Redirect URI: {payload['redirect_uri']}")
    return 0


def cmd_gmail_key(args: argparse.Namespace) -> int:
    from jobhunt.gmail_integration import generate_encryption_key

    print(generate_encryption_key())
    return 0


def cmd_gmail_exchange_code(args: argparse.Namespace) -> int:
    from jobhunt.gmail_integration import exchange_code_for_token, load_gmail_config, save_oauth_token

    conn = init_db(connect(args.db))
    config = load_gmail_config(conn)
    result = save_oauth_token(conn, exchange_code_for_token(args.code, config), config)
    print(json.dumps(result, indent=2))
    return 0


def cmd_gmail_sync(args: argparse.Namespace) -> int:
    from jobhunt.gmail_integration import evidence_rows, gmail_status, sync_gmail

    conn = init_db(connect(args.db))
    if args.status:
        print(json.dumps(gmail_status(conn), indent=2))
        return 0
    result = sync_gmail(conn, max_results=args.max_results, after=args.after)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Gmail sync saved {result['saved']} message(s).")
        print(f"Query: {result['query']}")
        print(f"Classifications: {result['classifications']}")
        recent = evidence_rows(conn, limit=5)["evidence"]
        if recent:
            print("\nRecent evidence:")
            for item in recent:
                print(
                    f"- {item['status']} {item['evidence_type']} "
                    f"{item['confidence']:.2f}: {item.get('company') or 'unmatched'} / {item.get('subject')}"
                )
    return 0


def cmd_seed_demo(args: argparse.Namespace) -> int:
    from jobhunt.dashboard import APPLICATIONS_DIR
    from jobhunt.demo_seed import clear_demo, seed_demo

    conn = init_db(connect(DB_PATH))
    try:
        if args.clear:
            print(f"Removed {clear_demo(conn, APPLICATIONS_DIR)['removed']} demo job(s).")
        else:
            result = seed_demo(conn, APPLICATIONS_DIR)
            if result["jobs"]:
                print(f"Seeded {result['jobs']} demo jobs and a draft at {result['draft_folder']}.")
            else:
                print("Demo data already present; nothing seeded.")
    finally:
        conn.close()
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    serve_dashboard(host=args.host, port=args.port)
    return 0


def _default_theme_input(root, font_paths):
    """Fall back to the user's default style theme when no Chameleon theme applies."""
    from jobhunt.font_theme import font_paths_for_theme
    from jobhunt.style_defaults import default_theme_path

    path = default_theme_path()
    if not path.is_file():
        return None, font_paths
    try:
        default_theme = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        print("WARNING: default-theme.yaml is unreadable; using the base theme.", file=sys.stderr)
        return None, font_paths
    if not isinstance(default_theme, dict) or not default_theme.get("enabled", True):
        return None, font_paths
    root = Path(root).resolve()
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        copy = root / "data" / ".preview" / "default-theme.yaml"
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copy)
        rel = copy.relative_to(root)
    return "/" + rel.as_posix(), font_paths_for_theme(default_theme)


def cmd_build(args: argparse.Namespace) -> int:
    from jobhunt.config import ROOT
    from jobhunt.brand_theme import read_theme
    from jobhunt.font_theme import font_paths_for_theme

    app = args.app
    app_dir = ROOT / "Applications" / app

    # Locate typst binary
    typst = shutil.which("typst")
    if typst is None:
        print("ERROR: typst not found in PATH. Install: https://github.com/typst/typst", file=sys.stderr)
        return 1

    # Validate application directory
    if not app_dir.is_dir():
        print(f"ERROR: Application folder not found: {app_dir}", file=sys.stderr)
        return 1

    # Validate data files
    cv_data = app_dir / "cv-data.yaml"
    letter_data = app_dir / "letter-data.yaml"
    for path in (cv_data, letter_data):
        if not path.is_file():
            print(f"ERROR: Missing data file: {path}", file=sys.stderr)
            return 1

    theme = read_theme(app_dir)
    theme_input = f"/Applications/{app}/brand-theme.yaml" if theme and theme.get("enabled") and not theme.get("fallback") else None
    font_paths = font_paths_for_theme(theme)
    if theme and theme.get("enabled") and theme.get("fallback"):
        print("WARNING: brand-theme.yaml is enabled but invalid or low-confidence; using the base theme.", file=sys.stderr)
    if theme_input is None:
        theme_input, font_paths = _default_theme_input(ROOT, font_paths)

    from jobhunt.profile import export_profile_for_typst, load_candidate_profile
    profile = load_candidate_profile()
    profile_data = export_profile_for_typst(profile)
    runtime_profile = ROOT / "data" / ".typst_profile.yaml"
    runtime_profile.parent.mkdir(parents=True, exist_ok=True)
    runtime_profile.write_text(yaml.safe_dump(profile_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    profile_input = "/data/.typst_profile.yaml"

    # Build specs: (template, output filename, data file, label)
    builds = [
        (ROOT / "Base" / "cv.typ", app_dir / "cv.pdf", f"/Applications/{app}/cv-data.yaml", "CV"),
        (ROOT / "Base" / "letter.typ", app_dir / "motivation-letter.pdf", f"/Applications/{app}/letter-data.yaml", "Motivation Letter"),
    ]

    for template, output, data_input, label in builds:
        print(f"Compiling {label}...")
        cmd = [
            typst, "compile",
            "--root", str(ROOT),
            str(template),
            str(output),
            "--input", f"data={data_input}",
            "--input", f"profile={profile_input}",
        ]
        for font_path in font_paths:
            cmd.extend(["--font-path", str(font_path)])
        if theme_input:
            cmd.extend(["--input", f"theme={theme_input}"])
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"ERROR: {label} compilation failed (exit {result.returncode})", file=sys.stderr)
            return 1
        print(f"  -> {output}")

    print("OK")
    return 0


def cmd_auto_draft(args: argparse.Namespace) -> int:
    """Generate Ollama draft packs for new core_fit/adjacent_plausible jobs without existing artifacts."""
    from jobhunt.dashboard import create_draft_pack, _ollama_await_ready

    conn = init_db(connect(args.db))
    rows = conn.execute(
        """SELECT id, company, title, fit_band, score
           FROM jobs
           WHERE status = 'new'
             AND fit_band IN ('core_fit', 'adjacent_plausible')
           ORDER BY score DESC, id DESC
           LIMIT ?""",
        (args.limit,),
    ).fetchall()

    if not rows:
        print("No eligible new jobs for auto-draft.")
        return 0

    print(f"Found {len(rows)} candidate job(s) — generating drafts via Ollama...")
    print("Waiting for Ollama to become available...")
    if not _ollama_await_ready(max_wait=180):
        print("ERROR: Ollama unavailable after 180s. Aborting auto-draft.", file=sys.stderr)
        return 1
    succeeded = 0
    skipped = 0
    failed = 0

    for row in rows:
        label = f"[{row['company']}] {row['title']} (fit={row['fit_band']}, score={row['score']})"
        print(f"  {label}")
        try:
            result = create_draft_pack(conn, row["id"])
            print(f"    → {result['artifact']['folder_name']}")
            succeeded += 1
        except ValueError as exc:
            if "already has generated" in str(exc):
                print(f"    skip: artifact exists")
                skipped += 1
            else:
                print(f"    FAILED: {exc}", file=sys.stderr)
                failed += 1
        except Exception as exc:
            print(f"    FAILED: {exc}", file=sys.stderr)
            failed += 1

    print(f"Done: {succeeded} drafted, {skipped} skipped (existing), {failed} failed")
    return 0 if failed == 0 else 1


def cmd_scrape_listing(args: argparse.Namespace) -> int:
    from jobhunt.job_scrape import scrape_job_listing

    print(
        "Note: URL scraping is deprecated and may break on some sites. "
        "Paste the job description into the dashboard instead.",
        file=sys.stderr,
    )
    try:
        result = scrape_job_listing(args.url)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    description = result.get("description") or ""
    if not args.full and len(description) > 500:
        description = description[:500] + f"… [{len(result['description'])} chars total, use --full]"
    print(f"source:      {result.get('source')}")
    print(f"title:       {result.get('title') or '-'}")
    print(f"company:     {result.get('company') or '-'}")
    print(f"location:    {result.get('location') or '-'}")
    for warning in result.get("warnings") or []:
        print(f"warning:     {warning}")
    print(f"description: {description or '-'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m jobhunt")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Check candidate profile config, database, and dependencies.")
    validate.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    validate.set_defaults(func=cmd_validate)

    dashboard = sub.add_parser("dashboard", help="Run the local Job Hunt dashboard.")
    dashboard.add_argument("--host", default="127.0.0.1", help="Host/interface to bind.")
    dashboard.add_argument("--port", type=int, default=8765, help="Port to bind.")
    dashboard.set_defaults(func=cmd_dashboard)

    seed_demo_cmd = sub.add_parser("seed-demo", help="Add (or --clear) fictional sample jobs and a draft.")
    seed_demo_cmd.add_argument("--clear", action="store_true", help="Remove the demo jobs and draft instead.")
    seed_demo_cmd.set_defaults(func=cmd_seed_demo)

    build = sub.add_parser("build", help="Compile Typst CV and motivation letter PDFs for an application.")
    build.add_argument("--app", required=True, help="Application folder name, e.g. Paramount-Content-Coordinator.")
    build.set_defaults(func=cmd_build)

    scrape_listing = sub.add_parser(
        "scrape-listing",
        help="Extract title/company/location/description from a single job-posting URL.",
    )
    scrape_listing.add_argument("url", help="Job posting URL.")
    scrape_listing.add_argument("--full", action="store_true", help="Print the full description instead of a 500-char preview.")
    scrape_listing.set_defaults(func=cmd_scrape_listing)

    auto_draft = sub.add_parser(
        "auto-draft",
        help="Generate Ollama draft packs for new core_fit/adjacent_plausible jobs without existing artifacts.",
    )
    auto_draft.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    auto_draft.add_argument("--limit", type=int, default=50, help="Max jobs to draft per run (default 50).")
    auto_draft.set_defaults(func=cmd_auto_draft)

    tailor_drafts = sub.add_parser(
        "tailor-drafts",
        help="Generate Ollama draft packs for new jobs (alias for auto-draft).",
    )
    tailor_drafts.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    tailor_drafts.add_argument("--limit", type=int, default=50, help="Max jobs to draft per run (default 50).")
    tailor_drafts.set_defaults(func=cmd_auto_draft)

    export = sub.add_parser("export", help="Export SQLite jobs to CSV and careers-directory.md.")
    export.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    export.set_defaults(func=cmd_export)

    outcome_audit = sub.add_parser("outcome-audit", help="Report application lifecycle stats and status-event hygiene.")
    outcome_audit.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    outcome_audit.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    outcome_audit.add_argument("--limit", type=int, default=10, help="Rows to show per anomaly group.")
    outcome_audit.set_defaults(func=cmd_outcome_audit)

    gmail_oauth = sub.add_parser("gmail-oauth-url", help="Print the app-owned Google OAuth consent URL.")
    gmail_oauth.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    gmail_oauth.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    gmail_oauth.set_defaults(func=cmd_gmail_oauth_url)

    gmail_key = sub.add_parser("gmail-key", help="Generate a GMAIL_TOKEN_ENCRYPTION_KEY value.")
    gmail_key.set_defaults(func=cmd_gmail_key)

    gmail_code = sub.add_parser("gmail-exchange-code", help="Exchange a Google OAuth code and store the Gmail refresh token.")
    gmail_code.add_argument("code", help="OAuth authorization code from Google.")
    gmail_code.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    gmail_code.set_defaults(func=cmd_gmail_exchange_code)

    gmail_sync = sub.add_parser("gmail-sync", help="Sync Gmail evidence into the job-hunt database.")
    gmail_sync.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    gmail_sync.add_argument("--max-results", type=int, default=50, help="Maximum Gmail messages to inspect.")
    gmail_sync.add_argument("--after", help="Optional Gmail after: date in YYYY/MM/DD format.")
    gmail_sync.add_argument("--status", action="store_true", help="Only print connection/sync status.")
    gmail_sync.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    gmail_sync.set_defaults(func=cmd_gmail_sync)

    clean_db = sub.add_parser("clean-db", help="Purge jobs from the database that no longer pass the current filters.")
    clean_db.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path.")
    clean_db.set_defaults(func=cmd_clean_db)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
