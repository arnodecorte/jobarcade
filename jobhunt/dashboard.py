from __future__ import annotations

import io
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import shutil
import sys
import threading
import time
import zipfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

import yaml

from jobhunt.brand_theme import extract_theme, read_theme, reset_theme, write_theme
from jobhunt.font_theme import resolve_typography
from jobhunt.assessment import apply_assessment
from jobhunt.config import COMPANIES_PATH, DB_PATH, ROOT, load_companies, write_companies
from jobhunt.database import connect, dedupe_key, fetch_scraper_health_rows, init_db, upsert_jobs
from jobhunt.gmail_integration import (
    apply_evidence,
    consume_auth_state,
    create_auth_url,
    disconnect_gmail,
    evidence_candidates,
    evidence_rows,
    exchange_code_for_token,
    gmail_status,
    gmail_metrics,
    gmail_sync_progress,
    load_gmail_config,
    reject_evidence,
    save_oauth_token,
    start_gmail_sync,
    update_evidence,
)
from jobhunt.integration_settings import (
    clear_firecrawl_settings,
    clear_gmail_settings,
    effective_firecrawl_key,
    integration_status,
    save_features,
    save_firecrawl_settings,
    scraper_enabled,
    save_gmail_settings,
    effective_ollama_settings,
    ollama_headers,
    save_ollama_settings,
    test_ollama_settings,
)
from jobhunt.job_scrape import scrape_job_listing
from jobhunt.style_defaults import (
    CV_VARIANTS,
    STYLE_FONTS,
    apply_default_variant,
    read_default_style,
    render_style_preview,
    save_default_style,
)
from jobhunt.models import Job
from jobhunt import profile as profile_module
from jobhunt.onboarding import (
    ProfileError,
    complete_onboarding,
    ensure_profile_file,
    get_goals,
    onboarding_state,
    read_profile_document,
    reset_onboarding,
    save_goals,
    set_onboarding_step,
    skip_onboarding,
    write_profile_document,
)
from jobhunt.profile import CandidateProfile, export_profile_for_typst, load_candidate_profile

STATIC_DIR = ROOT / "dashboard" / "static"
APPLICATIONS_DIR = ROOT / "Applications"


def _safe_profile() -> CandidateProfile:
    """Load the candidate profile, tolerating a hand-edited or malformed file."""
    try:
        return load_candidate_profile()
    except Exception as exc:
        print(f"warning: could not load profile: {exc}; using defaults", file=sys.stderr)
        return CandidateProfile(name="Candidate")


# The job hunt is over: scraping, LLM drafting and all other live actions are
# paused. Set to keep the dashboard itself up as a read-only browsable archive.
RETIRED = os.environ.get("JOBHUNT_RETIRED", "0") == "1"
RETIRED_BANNER = (
    b'<div style="background:#111;color:#f5c518;padding:10px 16px;'
    b'font:600 14px system-ui,sans-serif;text-align:center;position:sticky;'
    b'top:0;z-index:9999">'
    b"This dashboard is retired \xe2\x80\x94 the job hunt is over. "
    b"Browsing past applications and data is still available; scraping, "
    b"drafting and other live actions are paused."
    b"</div>"
)

TRACKED_STATUSES = ("new", "reviewed", "tailoring", "ready", "applied", "interviewing", "rejected", "offer", "skipped", "expired")
STATUS_LABELS = {
    "new": "New",
    "reviewed": "Reviewing",
    "tailoring": "Tailoring",
    "ready": "Ready to apply",
    "applied": "Applied",
    "interviewing": "Interviewing",
    "offer": "Offer",
    "rejected": "Rejected",
    "skipped": "Skipped",
    "expired": "Expired",
}
NEXT_STATUSES = {
    "new": ("reviewed", "tailoring", "skipped", "expired"),
    "reviewed": ("tailoring", "ready", "skipped", "expired"),
    "tailoring": ("ready", "reviewed", "skipped", "expired"),
    "ready": ("applied", "tailoring", "reviewed", "skipped"),
    "applied": ("interviewing", "rejected", "offer", "skipped"),
    "interviewing": ("offer", "rejected", "applied"),
    "offer": ("applied", "interviewing"),
    "rejected": ("applied", "interviewing"),
    "skipped": ("new", "reviewed"),
    "expired": ("new", "reviewed"),
}
OUTCOME_STATUSES = ("applied", "interviewing", "rejected", "offer")
KNOWN_OUTCOME_STATUSES = ("interviewing", "rejected", "offer")
MATURITY_DAYS = 30
GHOSTED_DAYS = 45
FOLLOW_UP_DAYS = 14

VALID_ENGINES = ("ollama", "gemini_cli", "openai_cli", "manual")
ROLE_FOCUSES = ("marketing", "campaign", "content", "brand", "community", "growth", "operations")
MARKETING_ROLE_FOCUSES = {"marketing", "campaign", "content", "brand", "community"}
CV_ALLOWED_KEYS = {
    "max_pages",
    "variant",
    "role_focus",
    "title",
    "tagline",
    "profile",
    "selected_highlights",
    "experience",
    "additional",
}
LETTER_ALLOWED_KEYS = {"max_pages", "subtitle", "paragraphs"}
ROLE_ALLOWED_KEYS = {"role", "company", "period", "location", "bullets", "include"}
CV_FIELD_LIMITS = {"tagline": 170, "profile": 600, "bullet": 165, "highlight": 135}
MAX_HIGHLIGHTS = 4
LETTER_BODY_LIMIT = 2050
DRAFT_META_FILENAME = "draft-meta.json"


def get_candidate_facts(profile: CandidateProfile | None = None) -> str:
    prof = profile or _safe_profile()
    return (
        f"{prof.name} is targeting roles in {prof.contact.location or 'their target area'}.\n"
        f"Use only these facts:\n{prof.career_facts}\n"
        f"Skills: {', '.join(prof.skills)}\n"
        "Do not invent any facts, employers, tools, degrees, languages, metrics, clients, or locations beyond this list."
    )


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _slug_text(value: str | None) -> str:
    # Drop apostrophes outright (don't turn them into a hyphen): "Peet's" and
    # "Peets" must slug identically, since folder names are typed by hand
    # (agents/skills) and inconsistently preserve the apostrophe-as-hyphen
    # convention. Treating it as a separator instead of stripping it makes
    # _match_artifact's startswith() check brittle to that one character
    # (e.g. "JDE Peet's" -> "jde-peet-s" failed to prefix-match a folder
    # slugged "jde-peets-...").
    text = (value or "").lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


MAX_BODY_BYTES = 256 * 1024  # POST payloads are tiny JSON; cap to avoid memory-blow DoS.


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    if length > MAX_BODY_BYTES:
        raise ValueError("Request body too large.")
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def _match_artifact(
    company_slug: str, title_slug: str, artifacts: dict[str, dict], job_id: int | None = None
) -> dict | None:
    """Pick the application folder that best matches a job.

    A folder must start with the company slug; among those, win on the most
    shared significant title words (>4 chars). The old logic was first-match
    on *any* shared word, so a common word like "manager" attached one folder
    to every "...Manager" role of that company (e.g. all Bynder sales roles got
    the Global-Partner-Marketing-Manager CV).

    Reposted/near-duplicate postings (e.g. Amazon's "AI Data Associate" roles,
    or "Technician II" vs "Technician III") share every word over 4 chars, so
    they tie on the primary signal. Break ties with two extra passes before
    falling back to alphabetical: (1) overlap over *all* words including short
    ones (catches distinguishing roman numerals/levels), (2) whether the DB
    job id appears as its own token in the folder name (catches folders we
    deliberately suffixed with an id to disambiguate true duplicates).
    """
    if not company_slug:
        return None
    title_parts = [part for part in title_slug.split("-") if len(part) > 4]
    all_parts = [part for part in title_slug.split("-") if part]
    id_token = str(job_id) if job_id is not None else None
    best = None
    best_key: tuple = (0,)
    for folder_slug, candidate in artifacts.items():
        if not folder_slug.startswith(company_slug):
            continue
        overlap = sum(1 for part in title_parts if part in folder_slug)
        if title_parts and overlap == 0:
            continue
        full_overlap = sum(1 for part in all_parts if part in folder_slug.split("-"))
        id_match = 1 if id_token and id_token in folder_slug.split("-") else 0
        key = (overlap, full_overlap, id_match, -len(folder_slug), folder_slug)
        if best is None or key > best_key:
            best, best_key = candidate, key
    return best


def _folder_component(value: str | None) -> str:
    # Keep folder minting aligned with _slug_text() matching. Apostrophes are
    # removed, not hyphenated, so "JDE Peet's" becomes "JDE-Peets".
    text = (value or "").strip().replace("'", "").replace("’", "")
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-") or "Unknown"


def _application_folder_name(company: str, title: str) -> str:
    return f"{_folder_component(company)}-{_folder_component(title)}"


def _resolve_application_folder(company: str, title: str) -> Path:
    """Folder for a (company, title) draft, reusing an existing folder that
    matches case-insensitively.

    Folder names historically preserved the source title's casing (see
    _folder_component), but lookups are case-insensitive (see _slug_text). So a
    role drafted from a lower-cased DB title and the same role from a Title-cased
    one produced two folders that collide on case-insensitive filesystems
    (Windows). Align creation with matching: reuse the existing folder instead of
    minting a case-variant sibling.
    """
    name = _application_folder_name(company, title)
    if APPLICATIONS_DIR.exists():
        key = _slug_text(name)
        for folder in APPLICATIONS_DIR.iterdir():
            if folder.is_dir() and _slug_text(folder.name) == key:
                return folder
    return _safe_application_dir(name)


def _safe_application_dir(folder_name: str) -> Path:
    folder_name = unquote(folder_name)
    candidate = (APPLICATIONS_DIR / folder_name).resolve()
    try:
        candidate.relative_to(APPLICATIONS_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Invalid application folder.") from exc
    return candidate


def _draft_meta_path(folder: Path) -> Path:
    return folder / DRAFT_META_FILENAME


@contextmanager
def db_session():
    # sqlite3.Connection's own `with conn:` only commits/rolls back the
    # transaction, it never closes the connection -- every request handler
    # using that pattern leaked a Connection (and its OS-level file lock)
    # until CPython's GC happened to collect it. A slow request (e.g. Gmail
    # sync, which can run for minutes) piling up alongside that meant other
    # requests' writes could block on a still-open, uncollected transaction
    # and fail with "database is locked". Close deterministically instead.
    conn = init_db(connect(DB_PATH))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")


def _lifecycle_bucket(days: int) -> str:
    if days < 7:
        return "fresh_0_6d"
    if days < 14:
        return "early_7_13d"
    if days < MATURITY_DAYS:
        return "aging_14_29d"
    if days < GHOSTED_DAYS:
        return "mature_30_44d"
    return "ghosted_45d_plus"


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * ((p * (1 - p) + z * z / (4 * total)) / total) ** 0.5
    return max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)


def read_draft_meta(folder: Path) -> dict:
    path = _draft_meta_path(folder)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _brand_theme_response(folder: Path) -> dict:
    theme = read_theme(folder)
    if not theme:
        return {"mode": "base", "enabled": False, "theme": None, "warnings": []}
    enabled = bool(theme.get("enabled")) and not theme.get("fallback")
    return {
        "mode": "chameleon" if enabled else "base",
        "enabled": enabled,
        "theme": theme,
        "warnings": list(theme.get("warnings") or []),
    }


def write_draft_meta(folder: Path, updates: dict) -> dict:
    meta = read_draft_meta(folder)
    meta.update(updates)
    meta.setdefault("updated_at", _now_iso())
    _draft_meta_path(folder).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _logo_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if re.match(r"^https?://", url) else f"https://{url}")
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _job_row(row: sqlite3.Row, artifacts: dict[str, dict], companies: dict[str, dict] | None = None) -> dict:
    company_slug = _slug_text(row["company"])
    title_slug = _slug_text(row["title"])
    artifact = _match_artifact(company_slug, title_slug, artifacts, job_id=row["id"])
    company = (companies or {}).get(row["company"], {})
    try:
        score_reasons = json.loads(row["score_reasons"] or "[]")
    except Exception:
        score_reasons = []
    score = row["score"]
    fit_band = row["fit_band"]
    priority = row["priority"]
    if not score and fit_band == "stretch":
        from jobhunt.assessment import assess_job

        assessment = assess_job(
            Job(
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
        )
        score = assessment.score
        fit_band = assessment.fit_band if assessment.included else "stretch"
        priority = assessment.priority
        score_reasons = assessment.reason_chips
    return {
        "id": row["id"],
        "company": row["company"],
        "company_logo_url": company.get("logo_url"),
        "company_logo_domain": company.get("logo_domain"),
        "title": row["title"],
        "location": row["location"],
        "country": row["country"],
        "remote_type": row["remote_type"],
        "department": row["department"],
        "employment_type": row["employment_type"],
        "date_posted": row["date_posted"],
        "apply_url": row["apply_url"],
        "source_url": row["source_url"],
        "source_platform": row["source_platform"],
        "source_job_id": row["source_job_id"],
        "scraper_type": row["scraper_type"],
        "discovered_at": row["discovered_at"],
        "last_seen_at": row["last_seen_at"],
        "expired_at": row["expired_at"],
        "status": row["status"],
        "last_error": row["last_error"],
        "priority": priority,
        "score": score,
        "fit_band": fit_band,
        "score_reasons": score_reasons,
        "notes": row["notes"],
        "artifact": artifact,
        # filled in by _tag_possible_duplicates after the full set is loaded.
        "possible_duplicate": False,
        "duplicate_of": [],
    }


def _tag_possible_duplicates(jobs: list[dict]) -> None:
    """Flag jobs that look like the same role harvested from more than one
    source (e.g. a dedicated Tesla scraper and the englishjobsearch.nl
    aggregator both surfacing one posting). Grouped by normalized
    company+title; only flagged when the group spans >=2 distinct
    source_platforms — two same-source rows are usually genuinely distinct
    concurrent reqs (Amazon posts many identically-titled openings), so those
    are left alone. Read-time only: never auto-merges, just surfaces."""
    from jobhunt.database import normalize_key

    groups: dict[tuple[str, str], list[dict]] = {}
    for job in jobs:
        key = (normalize_key(job["company"]), normalize_key(job["title"]))
        groups.setdefault(key, []).append(job)
    for members in groups.values():
        if len(members) < 2:
            continue
        if len({m.get("source_platform") for m in members}) < 2:
            continue
        for job in members:
            job["possible_duplicate"] = True
            job["duplicate_of"] = [
                {
                    "id": other["id"],
                    "source_platform": other.get("source_platform"),
                    "status": other["status"],
                }
                for other in members
                if other is not job
            ]


def application_artifacts() -> dict[str, dict]:
    artifacts: dict[str, dict] = {}
    if not APPLICATIONS_DIR.exists():
        return artifacts
    for folder in sorted(APPLICATIONS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not folder.is_dir():
            continue
        cv_paths = sorted(folder.glob("cv*.pdf"))
        letter_paths = sorted(folder.glob("motivation-letter*.pdf"))
        meta = read_draft_meta(folder)
        try:
            folder_label = str(folder.relative_to(ROOT))
            cv_label = str(cv_paths[0].relative_to(ROOT)) if cv_paths else None
            letter_label = str(letter_paths[0].relative_to(ROOT)) if letter_paths else None
        except ValueError:
            folder_label = str(folder)
            cv_label = str(cv_paths[0]) if cv_paths else None
            letter_label = str(letter_paths[0]) if letter_paths else None
        artifacts[_slug_text(folder.name)] = {
            "folder": folder_label,
            "folder_name": folder.name,
            "has_job_listing": (folder / "job-listing.md").exists(),
            "has_draft_data": (folder / "cv-data.yaml").exists() and (folder / "letter-data.yaml").exists(),
            "has_cv": bool(cv_paths),
            "has_letter": bool(letter_paths),
            "cv_path": cv_label,
            "letter_path": letter_label,
            "draft_origin": meta.get("origin"),
            "draft_model": meta.get("model"),
            "draft_state": meta.get("state"),
            "draft_review_label": meta.get("review_label"),
        }
    return artifacts


# ponytail: LIMIT truncates before status filtering, and the ORDER BY sorts
# 'interviewing'/'offer' after every open-pipeline status -- with ~558 rows
# today a 250 cap already clipped real interviewing jobs off the page.
# 5000 covers years of growth at current volume; revisit if the table nears it.
def fetch_jobs(conn: sqlite3.Connection, limit: int = 5000) -> list[dict]:
    artifacts = application_artifacts()
    companies = {
        company.company: {
            "logo_url": company.logo_url,
            "logo_domain": _logo_domain(company.careers_url),
        }
        for company in load_companies()
    }
    rows = conn.execute(
        """
        SELECT *
        FROM jobs
        WHERE title != '__scrape_failure__'
        ORDER BY
            CASE status
                WHEN 'new' THEN 0
                WHEN 'reviewed' THEN 1
                WHEN 'tailoring' THEN 2
                WHEN 'ready' THEN 3
                WHEN 'applied' THEN 4
                WHEN 'interviewing' THEN 5
                WHEN 'offer' THEN 6
                WHEN 'rejected' THEN 7
                WHEN 'skipped' THEN 8
                WHEN 'expired' THEN 9
                ELSE 10
            END,
            CASE fit_band
                WHEN 'core_fit' THEN 0
                WHEN 'adjacent_plausible' THEN 1
                WHEN 'stretch' THEN 2
                ELSE 3
            END,
            score DESC,
            discovered_at DESC,
            company ASC,
            title ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    jobs = [_job_row(row, artifacts, companies) for row in rows]
    _tag_possible_duplicates(jobs)
    applied_at_map: dict[int, str] = {}
    if jobs:
        placeholders = ",".join("?" * len(jobs))
        applied_rows = conn.execute(
            f"SELECT job_id, MIN(created_at) FROM status_events WHERE status = 'applied' AND job_id IN ({placeholders}) GROUP BY job_id",
            [j["id"] for j in jobs],
        ).fetchall()
        applied_at_map = {r[0]: r[1] for r in applied_rows}
    for j in jobs:
        j["applied_at"] = applied_at_map.get(j["id"])
    return jobs


def _artifact_response(folder_name: str) -> dict:
    folder = APPLICATIONS_DIR / folder_name
    meta = read_draft_meta(folder)
    try:
        folder_label = str(folder.relative_to(ROOT))
    except ValueError:
        folder_label = str(folder)
    return application_artifacts().get(_slug_text(folder_name), {
        "folder": folder_label,
        "folder_name": folder_name,
        "has_job_listing": (folder / "job-listing.md").exists(),
        "has_draft_data": (folder / "cv-data.yaml").exists() and (folder / "letter-data.yaml").exists(),
        "has_cv": False,
        "has_letter": False,
        "cv_path": None,
        "letter_path": None,
        "draft_origin": meta.get("origin"),
        "draft_model": meta.get("model"),
        "draft_state": meta.get("state"),
        "draft_review_label": meta.get("review_label"),
    })


def _job_listing_text(row: sqlite3.Row) -> str:
    sections = [
        f"# {row['title']} - {row['company']}",
        f"**Company:** {row['company']}",
        f"**Location:** {row['location'] or row['country'] or 'Unknown'}",
        f"**URL:** {row['apply_url'] or row['source_url'] or ''}",
    ]
    if row["department"]:
        sections.append(f"**Department:** {row['department']}")
    if row["employment_type"]:
        sections.append(f"**Employment type:** {row['employment_type']}")
    if row["description"]:
        sections.extend(["", "## Description", row["description"]])
    if row["requirements"]:
        sections.extend(["", "## Requirements", row["requirements"]])
    if not row["description"] and not row["requirements"]:
        sections.extend([
            "",
            "## Notes",
            "The scraper did not capture a full job description. Use the linked posting before final application review.",
        ])
    return "\n".join(str(item or "") for item in sections).strip() + "\n"


def _reference_application_text() -> str:
    # Deliberately NOT the full Base/reference CV/letter prose: an earlier
    # version embedded the complete finished YAML text here, and the local
    # drafting model (qwen2.5:7b, temperature 0.25) reliably copied it almost
    # verbatim instead of composing fresh, listing-specific content -- 11 of
    # 15 auto-drafted CVs in the 2026-07-08 batch were byte-identical to
    # Base/reference/cv-data.yaml. Keep this to targets a model can't
    # plagiarize; Base/reference itself stays the human-facing exemplar and
    # is still covered by its own density/quality gate test.
    return (
        "STYLE TARGETS (numbers and tone only -- do not copy wording from this note "
        "or from any earlier draft; every sentence must be freshly composed from the "
        "JOB LISTING and CANDIDATE FACTS below):\n"
        "- grotesk_one_page density: 5 roles, 14-18 bullets total, profile 450-600 chars, "
        "tagline <=170 chars.\n"
        "- Bullets land near the 165-char budget (120-165 chars), packed with concrete "
        "tools, channels, and metrics from the candidate facts.\n"
        "- Tone: specific and restrained, not generic enthusiasm; no cliches like "
        "'results-driven' or 'team player'.\n"
        "- Letter: 3-5 paragraphs, total <=2050 chars, opening paragraph names the role "
        "and company, closing paragraph invites a conversation."
    )


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Ollama did not return a JSON object.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON: {exc}") from exc


def _as_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def _validate_role_list(value: object, field: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list.")
    roles = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object.")
        extra = set(item) - ROLE_ALLOWED_KEYS
        if extra:
            raise ValueError(f"{field}[{index}] has unsupported fields: {', '.join(sorted(extra))}.")
        bullets = item.get("bullets", [])
        if not isinstance(bullets, list):
            raise ValueError(f"{field}[{index}].bullets must be a list.")
        if len(bullets) > 5:
            raise ValueError(f"{field}[{index}] has more than 5 bullets.")
        clean = {
            "role": str(item.get("role") or "").strip(),
            "company": str(item.get("company") or "").strip(),
            "period": str(item.get("period") or "").strip(),
            "location": str(item.get("location") or "").strip(),
            "bullets": [str(bullet or "").strip() for bullet in bullets if str(bullet or "").strip()],
            "include": _as_bool(item.get("include"), default=True),
        }
        roles.append(clean)
    return roles


def _validate_highlights(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("selected_highlights must be a list.")
    highlights = [str(item or "").strip() for item in value if str(item or "").strip()]
    if len(highlights) > MAX_HIGHLIGHTS:
        raise ValueError(f"selected_highlights has more than {MAX_HIGHLIGHTS} items.")
    return highlights


def _variant_default(cv: dict) -> str:
    if cv.get("variant"):
        return str(cv.get("variant")).strip()
    return "compact_one_page" if int(cv.get("max_pages") or 2) <= 1 else "classic_two_page"


def _normalize_grotesk_marketing_cv(cv_data: dict) -> list[str]:
    """Fold marketing-proof roles into the single Grotesk Experience section.

    The YAML schema stays backward-compatible: older drafts may still carry
    roles in `additional[]`. The Grotesk marketing CV renders one
    Experience section, so we normalize those records into `experience[]` on
    validate/save/read.
    """
    if cv_data.get("variant") != "grotesk_one_page":
        return []
    warnings: list[str] = []
    role_focus = cv_data.get("role_focus") or "marketing"
    if role_focus not in MARKETING_ROLE_FOCUSES:
        return warnings

    cv_data["selected_highlights"] = []
    seen = {
        (_slug_text(role.get("role")), _slug_text(role.get("company")))
        for role in cv_data["experience"]
    }
    for role in cv_data["additional"]:
        key = (_slug_text(role.get("role")), _slug_text(role.get("company")))
        if key not in seen:
            cv_data["experience"].append(role)
            seen.add(key)
    cv_data["additional"] = []
    return warnings


def validate_draft_payload(payload: dict) -> tuple[dict, dict, list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("Draft payload must be an object.")
    cv = payload.get("cv", payload.get("cv_data"))
    letter = payload.get("letter", payload.get("letter_data"))
    if not isinstance(cv, dict) or not isinstance(letter, dict):
        raise ValueError("Draft payload must contain cv and letter objects.")
    cv_extra = set(cv) - CV_ALLOWED_KEYS
    letter_extra = set(letter) - LETTER_ALLOWED_KEYS
    if cv_extra:
        raise ValueError(f"CV has unsupported fields: {', '.join(sorted(cv_extra))}.")
    if letter_extra:
        raise ValueError(f"Letter has unsupported fields: {', '.join(sorted(letter_extra))}.")

    variant = _variant_default(cv)
    if variant not in CV_VARIANTS:
        raise ValueError(f"CV variant must be one of: {', '.join(CV_VARIANTS)}.")
    role_focus = str(cv.get("role_focus") or "").strip()
    if role_focus and role_focus not in ROLE_FOCUSES:
        raise ValueError(f"CV role_focus must be one of: {', '.join(ROLE_FOCUSES)}.")
    max_pages = int(cv.get("max_pages") or (1 if variant in {"compact_one_page", "grotesk_one_page"} else 2))

    cv_data = {
        "max_pages": max_pages,
        "variant": variant,
        "role_focus": role_focus,
        "title": str(cv.get("title") or "").strip(),
        "tagline": str(cv.get("tagline") or "").strip(),
        "profile": str(cv.get("profile") or "").strip(),
        "selected_highlights": _validate_highlights(cv.get("selected_highlights")),
        "experience": _validate_role_list(cv.get("experience"), "experience"),
        "additional": _validate_role_list(cv.get("additional"), "additional"),
    }
    warnings = _normalize_grotesk_marketing_cv(cv_data)
    paragraphs = letter.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise ValueError("letter.paragraphs must be a list.")
    letter_data = {
        "max_pages": int(letter.get("max_pages") or 1),
        "subtitle": str(letter.get("subtitle") or "").strip(),
        "paragraphs": [str(paragraph or "").strip() for paragraph in paragraphs if str(paragraph or "").strip()],
    }

    if len(cv_data["tagline"]) > CV_FIELD_LIMITS["tagline"]:
        warnings.append("Tagline is over 170 characters.")
    if len(cv_data["profile"]) > CV_FIELD_LIMITS["profile"]:
        warnings.append("Profile is over 600 characters.")
    if cv_data["variant"] in {"compact_one_page", "grotesk_one_page"} and cv_data["max_pages"] != 1:
        warnings.append("One-page CV variants should use max_pages: 1.")
    if cv_data["variant"] not in {"compact_one_page", "grotesk_one_page"} and cv_data["max_pages"] < 2:
        warnings.append("Two-page CV variants should use max_pages: 2.")
    for highlight in cv_data["selected_highlights"]:
        if len(highlight) > CV_FIELD_LIMITS["highlight"]:
            warnings.append("A selected highlight is over 135 characters.")
            break
    for section in ("experience", "additional"):
        for role in cv_data[section]:
            for bullet in role["bullets"]:
                if len(bullet) > CV_FIELD_LIMITS["bullet"]:
                    warnings.append(f"Bullet over 165 characters in {role.get('company') or section}.")
                    break
    if not 3 <= len(letter_data["paragraphs"]) <= 5:
        warnings.append("Letter should have 3-5 paragraphs.")
    if sum(len(paragraph) for paragraph in letter_data["paragraphs"]) > LETTER_BODY_LIMIT:
        warnings.append("Letter body is over the template budget.")
    return cv_data, letter_data, warnings


def _draft_text(cv_data: dict) -> str:
    parts = [cv_data.get("title", ""), cv_data.get("tagline", ""), cv_data.get("profile", "")]
    parts.extend(cv_data.get("selected_highlights") or [])
    for section in ("experience", "additional"):
        for role in cv_data.get(section, []):
            if not role.get("include", True):
                continue
            parts.extend([role.get("role", ""), role.get("company", ""), " ".join(role.get("bullets") or [])])
    return " ".join(parts)


def review_cv_payload(cv_data: dict, listing: str = "") -> dict:
    """Deterministic CV scrutinizer feedback for the dashboard.

    This is deliberately heuristic: it catches common review risks before Typst
    compile, without pretending to score hiring-manager fit as a model would.
    """
    review_items: list[dict] = []
    included_experience = [r for r in cv_data.get("experience", []) if r.get("include", True)]
    included_additional = [r for r in cv_data.get("additional", []) if r.get("include", True)]
    bullets = [b for r in included_experience + included_additional for b in r.get("bullets", [])]
    proof_bullets = [b for b in bullets if re.search(r"(\d|%|~|\\+)", b)]
    text = _draft_text(cv_data).lower()
    listing_text = (listing or "").lower()

    if cv_data.get("variant") not in {"compact_one_page", "grotesk_one_page"} and len(included_additional) <= 1 and not cv_data.get("selected_highlights"):
        review_items.append(
            {
                "level": "warning",
                "title": "Sparse second page risk",
                "detail": "Classic two-page mode has little page-two content. Use compact mode or add selected impact highlights.",
            }
        )
    if cv_data.get("variant") == "grotesk_one_page":
        # Calibrated against a page-filling reference (Booking.com Lead Content
        # Strategy): 5 roles, 17 bullets, ~520-char summary end flush with the
        # sidebar. Under those counts the main column trails off into white space.
        if len(included_experience) + len(included_additional) < 4 or len(bullets) < 12:
            review_items.append(
                {
                    "level": "warning",
                    "title": "Under-filled one-page CV",
                    "detail": "A full Grotesk page holds 4-5 roles and 12-18 bullets; fewer leaves visible white space under Experience.",
                }
            )
        if len(bullets) > 18:
            review_items.append(
                {
                    "level": "warning",
                    "title": "One-page overflow risk",
                    "detail": "More than 18 bullets is likely to fail the one-page compile; trim the weakest evidence.",
                }
            )
        if len(cv_data.get("profile") or "") < 400:
            review_items.append(
                {
                    "level": "warning",
                    "title": "Summary shorter than the page budget",
                    "detail": "Aim for a 450-600 character summary; shorter reads thin and under-fills the main column.",
                }
            )
    elif cv_data.get("variant") == "compact_one_page":
        if len(included_experience) > 4:
            review_items.append(
                {
                    "level": "warning",
                    "title": "One-page density risk",
                    "detail": "More than four primary roles may overflow or dilute the strongest evidence.",
                }
            )
        if len(bullets) > 12:
            review_items.append(
                {
                    "level": "warning",
                    "title": "Too many bullets for compact mode",
                    "detail": "Aim for roughly 8-12 total bullets in the one-page CV.",
                }
            )
    if len(proof_bullets) < 3:
        review_items.append(
            {
                "level": "warning",
                "title": "Add more quantified proof",
                "detail": "Fewer than three bullets contain a metric, scale, or concrete count.",
            }
        )

    generic_phrases = (
        "detail-oriented",
        "results-driven",
        "team player",
        "fast-paced",
        "passionate",
        "excellent communication",
    )
    found_generic = [phrase for phrase in generic_phrases if phrase in text]
    if len(found_generic) >= 2:
        review_items.append(
            {
                "level": "note",
                "title": "Generic language cluster",
                "detail": "Replace repeated broad claims with role-specific evidence: " + ", ".join(found_generic[:3]) + ".",
            }
        )

    fallback_terms = (
        "marketing",
        "campaign",
        "content",
        "brand",
        "community",
        "social",
        "crm",
        "email",
        "cms",
        "stakeholder",
        "reporting",
    )
    _stop = {"and", "of", "the", "&", "for", "with"}
    _profile = _safe_profile()
    _words = {
        word
        for phrase in [*_profile.skills, *_profile.search.target_roles]
        for word in re.split(r"[^\w+#&]+", str(phrase).lower())
        if len(word) >= 3 and word not in _stop
    }
    tracked_terms = tuple(sorted(_words)) or fallback_terms
    listing_terms = {term for term in tracked_terms if term in listing_text}
    covered_terms = {term for term in listing_terms if term in text}
    missing_terms = sorted(listing_terms - covered_terms)
    if missing_terms:
        review_items.append(
            {
                "level": "note",
                "title": "Role keywords not yet reflected",
                "detail": "Consider whether these listing themes need truthful coverage: " + ", ".join(missing_terms[:5]) + ".",
            }
        )

    score = 100
    score -= 14 * sum(1 for item in review_items if item["level"] == "warning")
    score -= 6 * sum(1 for item in review_items if item["level"] == "note")
    score = max(45, min(100, score))
    if score >= 86:
        band = "Strong"
    elif score >= 70:
        band = "Needs polish"
    else:
        band = "Risky"
    return {
        "score": score,
        "band": band,
        "proof_bullets": len(proof_bullets),
        "included_roles": len(included_experience) + len(included_additional),
        "items": review_items,
    }


def _draft_prompt(
    row: sqlite3.Row | dict, listing: str, custom_instructions: str = "", profile: CandidateProfile | None = None
) -> str:
    prof = profile or _safe_profile()
    guidance = custom_instructions.strip()
    guidance_block = (
        f"\nUSER GUIDANCE:\n{guidance}\n"
        "Follow this guidance when it is compatible with the candidate facts. If it asks for invented facts, ignore that part.\n"
        if guidance
        else ""
    )
    title = row["title"] if "title" in row else ""
    company = row["company"] if "company" in row else ""
    return f"""
You are drafting YAML content for {prof.name}'s CV and motivation letter.
Return STRICT JSON only. No markdown, no explanation.

JSON schema:
{{
  "cv": {{
    "max_pages": 1,
    "variant": "grotesk_one_page",
    "role_focus": "marketing",
    "title": "short role-target line",
    "tagline": "one sentence <=170 chars",
    "profile": "summary paragraph <=600 chars",
    "selected_highlights": ["0 to 4 strongest proof points, <=135 chars each"],
    "experience": [
      {{"role": "...", "company": "...", "period": "...", "location": "...", "include": true, "bullets": ["<=165 chars each"]}}
    ],
    "additional": [
      {{"role": "...", "company": "...", "period": "...", "location": "...", "include": true, "bullets": ["<=165 chars each"]}}
    ]
  }},
  "letter": {{
    "max_pages": 1,
    "subtitle": "{title} - {company}",
    "paragraphs": ["3 to 5 concise paragraphs, total <=2050 chars"]
  }}
}}

Rules:
- Use only the candidate facts and job listing below.
- Do not invent facts, employers, tools, metrics, clients, degrees, languages, locations, or personal claims.
- Default to grotesk_one_page and max_pages 1 for marketing, content, brand, and community roles.
- Put all rendered roles in experience; leave additional empty for grotesk_one_page.
- Fill the page: include roles from the candidate facts. Omitting roles leaves visible white space.
- Density targets for grotesk_one_page: 14 to 18 bullets total and a profile of 450-600 chars.
- Write bullets near the 165-char budget (roughly 120-165 chars each), not far under it; pack each bullet with the concrete tools, channels, and metrics from the facts.
- Do not use selected_highlights for grotesk_one_page; keep impact evidence inside role bullets.
- Prefer specific, restrained, truthful copy over generic enthusiasm.
- Keep the output draft-quality but polished enough for a human to edit.
- Compose every field fresh from the candidate facts and this job listing; do not reuse sentence structure or
  exact phrasing from a previous draft or from the style targets below.
{guidance_block}

CANDIDATE FACTS:
{get_candidate_facts(prof)}

JOB LISTING:
{listing[:8000]}

STYLE TARGETS:
{_reference_application_text()}
""".strip()


def _ollama_runtime(function: str) -> tuple[str, str, dict[str, str]]:
    """Resolve (base_url, model, headers) for an Ollama function at call time."""
    with db_session() as conn:
        settings = effective_ollama_settings(conn)
    return (
        settings["base_url"].rstrip("/"),
        settings["models"].get(function) or settings["model"],
        ollama_headers(settings),
    )


def _ollama_post(payload: dict, timeout: int = 300, function: str = "draft") -> dict:
    """POST to Ollama /api/generate with up to 3 retries on connection errors."""
    base_url, _model, headers = _ollama_runtime(function)
    request = Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    last_exc: Exception | None = None
    for attempt in range(6):
        if attempt:
            time.sleep(15)
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            last_exc = exc
            continue  # retry on all network/connection errors
        except Exception as exc:
            raise ValueError(f"Ollama request failed: {exc}") from exc
    raise ValueError(f"Ollama unavailable after 6 attempts: {last_exc}") from last_exc


def _ollama_await_ready(max_wait: int = 120, function: str = "draft") -> bool:
    """Poll /api/tags until Ollama accepts connections or max_wait seconds pass."""
    base_url, _model, headers = _ollama_runtime(function)
    deadline = time.monotonic() + max_wait
    probe = 0
    while time.monotonic() < deadline:
        try:
            with urlopen(Request(f"{base_url}/api/tags", headers=headers), timeout=5) as resp:
                resp.read()
            if probe:
                print(f"[dashboard] Ollama ready after {probe} poll(s).")
            return True
        except Exception:
            probe += 1
            time.sleep(5)
    print(f"[dashboard] Ollama did not become available within {max_wait}s.")
    return False


def _ollama_warmup_background() -> None:
    """Load the model into Ollama memory on demand. Runs in a daemon thread; failures are non-fatal."""
    try:
        base_url, model, headers = _ollama_runtime("draft")
        payload = {
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_predict": 0},
        }
        request = Request(
            f"{base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urlopen(request, timeout=120) as resp:
            resp.read()
        print(f"[dashboard] Ollama model '{model}' warmed up and will stay loaded for 24h.")
    except Exception as exc:
        print(f"[dashboard] Ollama warmup failed (non-fatal): {exc}")


def _ollama_status() -> dict:
    model = ""
    try:
        base_url, model, headers = _ollama_runtime("draft")
        with urlopen(Request(f"{base_url}/api/tags", headers=headers), timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        model_names = {(m.get("name") or m.get("model") or "") for m in data.get("models", [])}
        model_present = any(model in name for name in model_names)
        return {"available": True, "model": model, "model_present": model_present}
    except Exception as exc:
        return {"available": False, "model": model, "error": str(exc)}


def generate_draft_with_ollama(
    row: sqlite3.Row | dict, listing: str, custom_instructions: str = "", profile: CandidateProfile | None = None
) -> tuple[dict, dict, list[str]]:
    if not _ollama_await_ready(function="draft"):
        raise ValueError("Ollama unavailable after 120s — model may still be loading. Retry in a moment.")
    _url, model, _headers = _ollama_runtime("draft")
    payload = {
        "model": model,
        "prompt": _draft_prompt(row, listing, custom_instructions, profile=profile),
        "stream": False,
        "options": {"temperature": 0.25, "num_ctx": 12000},
    }
    try:
        data = _ollama_post(payload, timeout=300, function="draft")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Ollama draft generation failed: {exc}") from exc
    raw = data.get("response")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Ollama returned an empty draft.")
    parsed = _extract_json_object(raw)
    if isinstance(parsed, dict):
        # A configured default style wins over whatever variant the model emitted.
        apply_default_variant(parsed.get("cv", parsed.get("cv_data")))
    return validate_draft_payload(parsed)


def _refine_prompt(
    current_yaml: str, listing: str, instructions: str, profile: CandidateProfile | None = None
) -> str:
    prof = profile or _safe_profile()
    guidance = instructions.strip()
    guidance_block = f"\nNEW INSTRUCTIONS:\n{guidance}\n" if guidance else ""
    return f"""
You are refining {prof.name}'s CV and motivation letter draft.
Return STRICT JSON only. No markdown, no explanation.

JSON schema (same structure as input):
{{
  "cv": {{
    "max_pages": 1,
    "variant": "grotesk_one_page",
    "role_focus": "marketing",
    "title": "short role-target line",
    "tagline": "one sentence <=170 chars",
    "profile": "summary paragraph <=600 chars",
    "selected_highlights": ["0 to 4 strongest proof points, <=135 chars each"],
    "experience": [{{"role": "...", "company": "...", "period": "...", "location": "...", "include": true, "bullets": ["<=165 chars each"]}}],
    "additional": [{{"role": "...", "company": "...", "period": "...", "location": "...", "include": true, "bullets": ["<=165 chars each"]}}]
  }},
  "letter": {{
    "max_pages": 1,
    "subtitle": "...",
    "paragraphs": ["3 to 5 concise paragraphs, total <=2050 chars"]
  }}
}}

Rules:
- Use only facts present in the CURRENT DRAFT or the CANDIDATE FACTS list below. You may restore roles, bullets, tools, and metrics from the CANDIDATE FACTS that the draft dropped; invent nothing beyond those two sources.
- Improve prose, tighten bullets to <=165 chars, apply the new instructions.
- Preserve or intentionally improve the CV variant. For marketing/content/brand/community roles prefer grotesk_one_page with max_pages 1.
- For grotesk_one_page, keep all rendered roles in experience, leave additional empty, and keep selected_highlights empty.
- Fill the page: a grotesk_one_page CV should carry the roles from the candidate facts and roughly 14 to 18 bullets total, with a 450-600 char profile; if the current draft is thinner, restore material from the CANDIDATE FACTS.
- Return valid JSON that is an improvement on the current draft.
{guidance_block}

CURRENT DRAFT (refine this):
{current_yaml}

JOB LISTING (context):
{listing[:4000]}

CANDIDATE FACTS (you may restore dropped roles/bullets from here; never go beyond it):
{get_candidate_facts(prof)}
""".strip()


def _refine_draft_with_ollama(
    current_draft_payload: dict, listing: str, instructions: str, profile: CandidateProfile | None = None
) -> tuple[dict, dict, list[str]]:
    if not _ollama_await_ready(function="refine"):
        raise ValueError("Ollama unavailable after 120s — model may still be loading. Retry in a moment.")
    _url, model, _headers = _ollama_runtime("refine")
    cv_data, letter_data, _ = validate_draft_payload(current_draft_payload)
    current_yaml = (
        "CV:\n"
        + yaml.safe_dump(cv_data, sort_keys=False, allow_unicode=True, width=110)
        + "\nLETTER:\n"
        + yaml.safe_dump(letter_data, sort_keys=False, allow_unicode=True, width=110)
    )
    payload = {
        "model": model,
        "prompt": _refine_prompt(current_yaml, listing, instructions, profile=profile),
        "stream": False,
        "options": {"temperature": 0.25, "num_ctx": 12000},
    }
    try:
        data = _ollama_post(payload, timeout=300, function="refine")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Ollama refinement failed: {exc}") from exc
    raw = data.get("response")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Ollama returned an empty response.")
    return validate_draft_payload(_extract_json_object(raw))


def reprompt_draft(
    folder_name: str,
    mode: str,
    instructions: str,
    current_draft_payload: dict,
    job_id: int | None,
    conn: sqlite3.Connection,
) -> dict:
    if mode not in ("fresh", "refine"):
        raise ValueError("mode must be 'fresh' or 'refine'.")
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    listing = (folder / "job-listing.md").read_text(encoding="utf-8") if (folder / "job-listing.md").exists() else ""

    if mode == "fresh":
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone() if job_id else None
        if not row:
            raise ValueError("job_id is required for fresh mode (could not find job row).")
        cv_data, letter_data, warnings = generate_draft_with_ollama(row, listing, instructions)
        used_model = _ollama_runtime("draft")[1]
    else:
        cv_data, letter_data, warnings = _refine_draft_with_ollama(current_draft_payload, listing, instructions)
        used_model = _ollama_runtime("refine")[1]

    _write_yaml(folder / "cv-data.yaml", cv_data, f"# Draft CV for: {folder_name}")
    _write_yaml(folder / "letter-data.yaml", letter_data, f"# Draft motivation letter for: {folder_name}")
    write_draft_meta(
        folder,
        {
            "origin": "ollama",
            "model": used_model,
            "state": "draft_generated",
            "updated_at": _now_iso(),
            "custom_instructions": instructions.strip(),
        },
    )
    return read_application_draft(folder.name) | {"warnings": warnings}


def delete_application(folder_name: str, job_id: int | None, conn: sqlite3.Connection) -> None:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    if job_id is not None:
        conn.execute(
            "UPDATE jobs SET status = 'reviewed' WHERE id = ? AND status IN ('tailoring', 'ready', 'draft_generated')",
            (job_id,),
        )
        conn.commit()
    shutil.rmtree(folder)


def _write_yaml(path: Path, data: dict, header: str) -> None:
    path.write_text(
        f"{header}\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110),
        encoding="utf-8",
    )


def read_application_draft(folder_name: str) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    cv_path = folder / "cv-data.yaml"
    letter_path = folder / "letter-data.yaml"
    if not cv_path.exists() or not letter_path.exists():
        raise ValueError("Draft YAML files are missing.")
    cv = yaml.safe_load(cv_path.read_text(encoding="utf-8")) or {}
    letter = yaml.safe_load(letter_path.read_text(encoding="utf-8")) or {}
    cv_data, letter_data, warnings = validate_draft_payload({"cv": cv, "letter": letter})
    meta = read_draft_meta(folder)
    listing = (folder / "job-listing.md").read_text(encoding="utf-8") if (folder / "job-listing.md").exists() else ""
    return {
        "folder_name": folder.name,
        "cv": cv_data,
        "letter": letter_data,
        "listing": listing,
        "artifact": _artifact_response(folder.name),
        "brand_theme": _brand_theme_response(folder),
        "brand_source": _brand_source_response(folder.name, None),
        "warnings": warnings,
        "cv_review": review_cv_payload(cv_data, listing),
        "limits": {
            "tagline": 170,
            "profile": 600,
            "bullet": 165,
            "highlight": CV_FIELD_LIMITS["highlight"],
            "letter_body": LETTER_BODY_LIMIT,
            "variants": list(CV_VARIANTS),
            "role_focuses": list(ROLE_FOCUSES),
        },
        "meta": meta,
    }


def save_application_draft(folder_name: str, payload: dict) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    cv_data, letter_data, warnings = validate_draft_payload(payload)
    _write_yaml(folder / "cv-data.yaml", cv_data, "# Draft CV data generated/edited from Job Application Hub.")
    _write_yaml(folder / "letter-data.yaml", letter_data, "# Draft motivation letter data generated/edited from Job Application Hub.")
    write_draft_meta(folder, {"updated_at": _now_iso()})
    return read_application_draft(folder.name) | {"warnings": warnings}


def _company_careers_url(company_name: str | None) -> str | None:
    company = _company_config(company_name)
    return company.careers_url if company else None


def _company_config(company_name: str | None):
    if not company_name:
        return None
    company_key = _slug_text(company_name)
    for company in load_companies():
        if _slug_text(company.company) == company_key:
            return company
    return None


def _company_brand_url(company_name: str | None) -> str | None:
    company = _company_config(company_name)
    return company.brand_url if company else None


def _normalize_url(value: str | None) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = f"https://{url}"
    return url


def _classify_brand_source_url(url: str | None) -> str:
    value = (url or "").lower()
    if not value:
        return "missing"
    careers_tokens = (
        "careers.",
        "jobs.",
        "/careers",
        "/jobs",
        "/job/",
        "/vacanc",
        "greenhouse.io",
        "lever.co",
        "workday",
        "smartrecruiters",
        "ashbyhq",
        "successfactors",
        "taleo",
        "paradox.ai",
        "attrax",
        "avature",
    )
    if any(token in value for token in careers_tokens):
        return "careers"
    return "company_site"


def _infer_brand_url_from_careers_url(careers_url: str | None) -> str:
    url = _normalize_url(careers_url)
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    for prefix in ("careers.", "jobs."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    if not host:
        return ""
    return f"{parsed.scheme or 'https'}://{host}"


def _brand_source_response(folder_name: str, job_id: int | None = None, conn: sqlite3.Connection | None = None) -> dict:
    folder = _safe_application_dir(folder_name)
    meta = read_draft_meta(folder) if folder.is_dir() else {}
    override = _normalize_url(meta.get("brand_url_override"))
    if override:
        return {
            "url": override,
            "kind": _classify_brand_source_url(override),
            "reason": "Draft-level brand URL override.",
            "override": True,
        }

    company_name = _folder_company_guess(folder_name)
    if conn is not None and job_id is not None:
        row = conn.execute(
            "SELECT company FROM jobs WHERE id = ? AND title != '__scrape_failure__'",
            (job_id,),
        ).fetchone()
        if row:
            company_name = row["company"]

    brand_url = _normalize_url(_company_brand_url(company_name))
    if brand_url:
        return {
            "url": brand_url,
            "kind": _classify_brand_source_url(brand_url),
            "reason": "Configured company brand_url.",
            "override": False,
        }

    inferred = _infer_brand_url_from_careers_url(_company_careers_url(company_name))
    if inferred and _classify_brand_source_url(inferred) == "company_site":
        return {
            "url": inferred,
            "kind": "company_site",
            "reason": "Inferred company homepage from careers URL.",
            "override": False,
        }

    careers_url = _normalize_url(_company_careers_url(company_name))
    if careers_url:
        return {
            "url": careers_url,
            "kind": "careers",
            "reason": "Careers page fallback; configure a brand URL for better brand extraction.",
            "override": False,
        }

    return {"url": "", "kind": "missing", "reason": "No company brand URL found.", "override": False}


def _folder_company_guess(folder_name: str) -> str:
    parts = folder_name.split("-")
    if not parts:
        return folder_name
    best = ""
    best_len = 0
    folder_slug = _slug_text(folder_name)
    for company in load_companies():
        slug = _slug_text(company.company)
        if folder_slug.startswith(slug) and len(slug) > best_len:
            best = company.company
            best_len = len(slug)
    return best or parts[0]


def _brand_source_url(conn: sqlite3.Connection, folder_name: str, job_id: int | None = None) -> str:
    return _brand_source_response(folder_name, job_id, conn)["url"]


def extract_application_brand_theme(
    conn: sqlite3.Connection,
    folder_name: str,
    job_id: int | None = None,
    source_url: str | None = None,
    provider: str = "auto",
) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    source = (
        {
            "url": _normalize_url(source_url),
            "kind": _classify_brand_source_url(source_url),
            "reason": "Explicit extraction URL.",
            "override": True,
        }
        if source_url
        else _brand_source_response(folder.name, job_id, conn)
    )
    url = source["url"]
    if not url:
        theme = write_theme(folder, {"enabled": False, "confidence": 0, "notes": ["No company source URL found."]})
    else:
        try:
            result = extract_theme(url, provider=provider, api_key=effective_firecrawl_key(conn) or None)
            font_resolution = resolve_typography(result.theme.get("typography"))
            font_tokens = font_resolution.as_theme_tokens()
            theme = write_theme(
                folder,
                result.theme
                | {
                    **font_tokens,
                    "typography_enabled": False,
                    "warnings": result.warnings,
                    "source_kind": source["kind"],
                    "source_reason": source["reason"],
                },
            )
        except Exception as exc:
            print(f"[chameleon] theme extraction failed for {folder.name} ({url}): {exc}", file=sys.stderr)
            theme = write_theme(
                folder,
                {
                    "enabled": False,
                    "confidence": 0,
                    "provider": provider,
                    "source_url": url,
                    "source_kind": source["kind"],
                    "source_reason": source["reason"],
                    "notes": [f"Theme extraction failed: {exc}"],
                },
            )
    write_draft_meta(folder, {"updated_at": _now_iso()})
    return {
        "ok": True,
        "folder_name": folder.name,
        "brand_theme": _brand_theme_response(folder),
        "brand_source": _brand_source_response(folder.name, job_id, conn),
        "theme": theme,
    }


def set_application_brand_url(folder_name: str, brand_url: str | None) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    url = _normalize_url(brand_url)
    if url and not re.match(r"^https?://[^/]+\S*$", url, re.I):
        raise ValueError("Brand URL must be a valid http(s) URL.")
    meta = read_draft_meta(folder)
    if url:
        meta["brand_url_override"] = url
    else:
        meta.pop("brand_url_override", None)
    meta["updated_at"] = _now_iso()
    _draft_meta_path(folder).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "folder_name": folder.name, "brand_source": _brand_source_response(folder.name)}


def reset_application_brand_theme(folder_name: str) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    theme = reset_theme(folder)
    write_draft_meta(folder, {"updated_at": _now_iso()})
    return {"ok": True, "folder_name": folder.name, "brand_theme": _brand_theme_response(folder), "theme": theme}


def set_application_brand_theme_mode(folder_name: str, mode: str) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    requested_mode = str(mode or "").strip().lower()
    if requested_mode not in {"light", "dark"}:
        raise ValueError("Theme mode must be light or dark.")
    path = folder / "brand-theme.yaml"
    if not path.exists():
        raise ValueError("Extract a Chameleon theme before choosing dark mode.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or not raw.get("enabled"):
        raise ValueError("Enable a Chameleon theme before choosing dark mode.")

    light_keys = ("accent_dark", "muted", "page_bg", "soft_bg", "rule", "link")
    if requested_mode == "dark":
        light_tokens = raw.get("light_tokens") if isinstance(raw.get("light_tokens"), dict) else {}
        for key in light_keys:
            if raw.get(key) and not light_tokens.get(key):
                light_tokens[key] = raw[key]
        raw["light_tokens"] = light_tokens
        raw["mode"] = "dark"
        raw["accent"] = raw.get("link") or raw.get("accent")
        raw["accent_dark"] = "#FFFFFF"
        raw["muted"] = "#B3B3B3"
        raw["page_bg"] = "#000000"
        raw["soft_bg"] = "#141414"
        raw["rule"] = "#333333"
        raw["link"] = raw.get("accent") or raw.get("link")
        notes = list(raw.get("notes") or [])
        if "Dark mode enabled by user." not in notes:
            notes.append("Dark mode enabled by user.")
        raw["notes"] = notes
    else:
        raw["mode"] = "light"
        light_tokens = raw.get("light_tokens") if isinstance(raw.get("light_tokens"), dict) else {}
        for key in light_keys:
            if light_tokens.get(key):
                raw[key] = light_tokens[key]
            elif key in {"muted", "page_bg"}:
                raw.pop(key, None)
        raw["notes"] = [note for note in list(raw.get("notes") or []) if note != "Dark mode enabled by user."]

    theme = write_theme(folder, raw)
    write_draft_meta(folder, {"updated_at": _now_iso()})
    return {"ok": True, "folder_name": folder.name, "brand_theme": _brand_theme_response(folder), "theme": theme}


def set_application_brand_typography(folder_name: str, enabled: bool) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    path = folder / "brand-theme.yaml"
    if not path.exists():
        raise ValueError("Extract a Chameleon theme before choosing typography.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or not raw.get("enabled"):
        raise ValueError("Enable a Chameleon theme before choosing typography.")
    if enabled and not raw.get("typography_available"):
        raise ValueError("No usable Chameleon font was resolved for this brand.")
    raw["typography_enabled"] = bool(enabled)
    notes = list(raw.get("notes") or [])
    if enabled and "Typography enabled by user." not in notes:
        notes.append("Typography enabled by user.")
    if not enabled:
        notes = [note for note in notes if note != "Typography enabled by user."]
    raw["notes"] = notes
    theme = write_theme(folder, raw)
    write_draft_meta(folder, {"updated_at": _now_iso()})
    return {"ok": True, "folder_name": folder.name, "brand_theme": _brand_theme_response(folder), "theme": theme}


def create_draft_pack(conn: sqlite3.Connection, job_id: int, custom_instructions: str = "") -> dict:
    row = conn.execute("SELECT * FROM jobs WHERE id = ? AND title != '__scrape_failure__'", (job_id,)).fetchone()
    if not row:
        raise ValueError(f"Job not found: {job_id}")
    folder = _resolve_application_folder(row["company"], row["title"])
    folder_name = folder.name
    artifact = _artifact_response(folder_name)
    if artifact.get("has_cv") or artifact.get("has_letter"):
        raise ValueError("This job already has generated application artifacts.")

    listing = _job_listing_text(row)
    instructions = custom_instructions.strip()
    cv_data, letter_data, warnings = generate_draft_with_ollama(row, listing, instructions)
    used_model = _ollama_runtime("draft")[1]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job-listing.md").write_text(listing, encoding="utf-8")
    _write_yaml(folder / "cv-data.yaml", cv_data, f"# Draft CV for: {row['company']} - {row['title']}")
    _write_yaml(folder / "letter-data.yaml", letter_data, f"# Draft motivation letter for: {row['company']} - {row['title']}")
    write_draft_meta(
        folder,
        {
            "origin": "ollama",
            "model": used_model,
            "state": "draft_generated",
            "review_label": "Draft pack ready for review",
            "generated_at": _now_iso(),
            "updated_at": _now_iso(),
            "custom_instructions": instructions,
        },
    )
    conn.execute("UPDATE jobs SET status = ? WHERE id = ? AND status = ?", ("tailoring", job_id, "new"))
    conn.commit()
    return read_application_draft(folder.name) | {"job_id": job_id, "warnings": warnings}


def build_application(folder_name: str) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    result = subprocess.run(
        [sys.executable, "-m", "jobhunt", "build", "--app", folder.name],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if result.returncode == 0:
        write_draft_meta(folder, {"state": "built", "updated_at": _now_iso()})
    artifact = _artifact_response(folder.name)
    ok = result.returncode == 0 and artifact.get("has_cv") and artifact.get("has_letter")
    return {
        "ok": ok,
        "folder_name": folder.name,
        "artifact": artifact,
        "output": output,
        "error": None if ok else output or f"Build failed with exit code {result.returncode}.",
    }


def mark_draft_ready_for_review(conn: sqlite3.Connection, folder_name: str, job_id: int | None = None) -> dict:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    meta = write_draft_meta(
        folder,
        {"state": "ready_for_review", "review_label": "Draft pack ready for review", "updated_at": _now_iso()},
    )
    if job_id is not None:
        update_job_status(conn, job_id, "ready")
    return read_application_draft(folder.name) | {"ok": True, "meta": meta}


def fetch_summary(conn: sqlite3.Connection) -> dict:
    status_counts = {
        row["status"]: row["count"]
        for row in conn.execute(
            "SELECT status, COUNT(*) AS count FROM jobs WHERE title != '__scrape_failure__' GROUP BY status"
        ).fetchall()
    }
    total_jobs = sum(status_counts.values())
    active_jobs = sum(count for status, count in status_counts.items() if status not in ("expired", "skipped", "rejected", "offer"))
    latest = conn.execute("SELECT MAX(last_seen_at) AS latest FROM jobs").fetchone()["latest"]
    artifacts = list(application_artifacts().values())
    generated = sum(1 for item in artifacts if item["has_cv"] or item["has_letter"])
    ready_artifacts = sum(1 for item in artifacts if item["has_cv"] and item["has_letter"])
    health_counts = {
        row["status"]: row["count"]
        for row in conn.execute("SELECT status, COUNT(*) AS count FROM scraper_health GROUP BY status").fetchall()
    }
    return {
        "status_counts": status_counts,
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "generated_applications": generated,
        "ready_artifacts": ready_artifacts,
        "last_seen_at": latest,
        "scraper_health_counts": health_counts,
        "unhealthy_scrapers": health_counts.get("failed", 0) + health_counts.get("warning", 0),
    }


def _streaks(days: set[str]) -> tuple[int, int]:
    """Return (current_streak, best_streak) from a set of YYYY-MM-DD apply days.

    Current streak counts consecutive days ending today; if nothing logged today
    yet, it still counts from yesterday so the streak isn't broken mid-day.
    """
    if not days:
        return 0, 0
    parsed = sorted(date.fromisoformat(d) for d in days)
    # Best streak: longest run of consecutive calendar days.
    best = run = 1
    for prev, cur in zip(parsed, parsed[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    # Current streak: walk back from today (grace: allow starting at yesterday).
    today = date.today()
    cursor = today if today.isoformat() in days else today - timedelta(days=1)
    current = 0
    while cursor.isoformat() in days:
        current += 1
        cursor -= timedelta(days=1)
    return current, best


def fetch_lifecycle_stats(conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    rows = conn.execute(
        f"""
        SELECT j.id, j.status, j.discovered_at,
               (SELECT MIN(created_at) FROM status_events se WHERE se.job_id = j.id AND se.status = 'applied') AS applied_at
        FROM jobs j
        WHERE j.title != '__scrape_failure__'
          AND j.status IN ({",".join("?" for _ in OUTCOME_STATUSES)})
        """,
        OUTCOME_STATUSES,
    ).fetchall()
    buckets = {
        "fresh_0_6d": 0,
        "early_7_13d": 0,
        "aging_14_29d": 0,
        "mature_30_44d": 0,
        "ghosted_45d_plus": 0,
    }
    pending = matured_pending = ghosted = follow_up_due = known_outcomes = interviews = rejections = 0
    submitted = len(rows)
    for row in rows:
        applied_at = _parse_dt(row["applied_at"]) or _parse_dt(row["discovered_at"])
        if applied_at is None:
            continue
        age_days = max(0, (today - applied_at.date()).days)
        buckets[_lifecycle_bucket(age_days)] += 1
        status = row["status"]
        if status == "applied":
            pending += 1
            if age_days >= MATURITY_DAYS:
                matured_pending += 1
            if age_days >= GHOSTED_DAYS:
                ghosted += 1
            if age_days >= FOLLOW_UP_DAYS and age_days < GHOSTED_DAYS:
                follow_up_due += 1
        elif status in KNOWN_OUTCOME_STATUSES:
            known_outcomes += 1
            if status in ("interviewing", "offer"):
                interviews += 1
            elif status == "rejected":
                rejections += 1

    matured_denominator = known_outcomes + matured_pending
    rate = interviews / matured_denominator if matured_denominator else 0.0
    low, high = _wilson_interval(interviews, matured_denominator)
    return {
        "submitted_total": submitted,
        "pending_total": pending,
        "known_outcomes": known_outcomes,
        "matured_denominator": matured_denominator,
        "matured_no_response": matured_pending,
        "immature_pending": max(0, pending - matured_pending),
        "ghosted": ghosted,
        "follow_up_due": follow_up_due,
        "interviews": interviews,
        "rejections": rejections,
        "response_rate_observed": round(rate, 4),
        "response_rate_low": round(low, 4),
        "response_rate_high": round(high, 4),
        "maturity_days": MATURITY_DAYS,
        "ghosted_days": GHOSTED_DAYS,
        "follow_up_days": FOLLOW_UP_DAYS,
        "buckets": buckets,
    }


def audit_status_event_hygiene(conn: sqlite3.Connection) -> dict:
    duplicate_applied = [
        dict(row)
        for row in conn.execute(
            """
            SELECT j.id AS job_id, j.company, j.title, COUNT(*) AS event_count,
                   MIN(se.created_at) AS first_event, MAX(se.created_at) AS last_event
            FROM status_events se
            JOIN jobs j ON j.id = se.job_id
            WHERE se.status = 'applied'
            GROUP BY se.job_id
            HAVING COUNT(*) > 1
            ORDER BY event_count DESC, first_event ASC
            """
        ).fetchall()
    ]
    missing_applied_event = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT j.id AS job_id, j.company, j.title, j.status, j.discovered_at
            FROM jobs j
            WHERE j.title != '__scrape_failure__'
              AND j.status IN ({",".join("?" for _ in OUTCOME_STATUSES)})
              AND NOT EXISTS (
                SELECT 1 FROM status_events se WHERE se.job_id = j.id AND se.status = 'applied'
              )
            ORDER BY j.discovered_at ASC
            """,
            OUTCOME_STATUSES,
        ).fetchall()
    ]
    rejected_without_rejected_event = [
        dict(row)
        for row in conn.execute(
            """
            SELECT j.id AS job_id, j.company, j.title, j.discovered_at
            FROM jobs j
            WHERE j.title != '__scrape_failure__'
              AND j.status = 'rejected'
              AND NOT EXISTS (
                SELECT 1 FROM status_events se WHERE se.job_id = j.id AND se.status = 'rejected'
              )
            ORDER BY j.discovered_at ASC
            """
        ).fetchall()
    ]
    orphan_events = [
        dict(row)
        for row in conn.execute(
            """
            SELECT se.id, se.job_id, se.status, se.created_at
            FROM status_events se
            LEFT JOIN jobs j ON j.id = se.job_id
            WHERE j.id IS NULL
            ORDER BY se.created_at ASC
            """
        ).fetchall()
    ]
    return {
        "duplicate_applied": duplicate_applied,
        "missing_applied_event": missing_applied_event,
        "rejected_without_rejected_event": rejected_without_rejected_event,
        "orphan_events": orphan_events,
        "counts": {
            "duplicate_applied": len(duplicate_applied),
            "missing_applied_event": len(missing_applied_event),
            "rejected_without_rejected_event": len(rejected_without_rejected_event),
            "orphan_events": len(orphan_events),
        },
    }


def fetch_stats(conn: sqlite3.Connection) -> dict:
    applications_sent = conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('applied', 'interviewing', 'rejected', 'offer')"
    ).fetchone()["n"]
    daily_rows = conn.execute(
        """
        SELECT date(created_at) AS day, COUNT(*) AS count
        FROM status_events
        WHERE status = 'applied' AND created_at >= date('now', '-90 days')
        GROUP BY day
        ORDER BY day
        """
    ).fetchall()
    daily = [{"date": row["day"], "count": row["count"]} for row in daily_rows]
    apply_days = {row["day"] for row in daily_rows}
    today_iso = date.today().isoformat()
    pulls_today = next((row["count"] for row in daily if row["date"] == today_iso), 0)
    cutoff_7d = (date.today() - timedelta(days=6)).isoformat()
    applied_7d = sum(row["count"] for row in daily if row["date"] >= cutoff_7d)
    current_streak, best_streak = _streaks(apply_days)
    return {
        "applications_sent": applications_sent,
        "pulls_today": pulls_today,
        "daily": daily,
        "current_streak": current_streak,
        "best_streak": best_streak,
        "actual_cadence_7d": round(applied_7d / 7, 2),
        "lifecycle": fetch_lifecycle_stats(conn),
    }


def company_rows(conn: sqlite3.Connection) -> list[dict]:
    companies = load_companies()
    job_counts = {
        row["company"]: row["count"]
        for row in conn.execute(
            "SELECT company, COUNT(*) AS count FROM jobs WHERE title != '__scrape_failure__' GROUP BY company"
        ).fetchall()
    }
    last_seen = {
        row["company"]: row["last_seen_at"]
        for row in conn.execute(
            "SELECT company, MAX(last_seen_at) AS last_seen_at FROM jobs GROUP BY company"
        ).fetchall()
    }
    health = {row["company"]: dict(row) for row in fetch_scraper_health_rows(conn)}
    return [
        {
            **asdict(company),
            "logo_domain": _logo_domain(company.careers_url),
            "job_count": job_counts.get(company.company, 0),
            "last_seen_at": last_seen.get(company.company),
            "health": health.get(company.company),
            "is_promoted": company.scraper_type == "dedicated",
        }
        for company in companies
    ]


def fetch_companies(conn: sqlite3.Connection) -> dict:
    rows = company_rows(conn)
    dedicated = [row for row in rows if row["scraper_type"] == "dedicated" and row["enabled"]]
    manual = [row for row in rows if row["scraper_type"] == "manual_review" and row["enabled"]]
    disabled = [row for row in rows if not row["enabled"]]
    return {
        "companies": rows,
        "coverage": {
            "total": len(rows),
            "dedicated": len(dedicated),
            "manual_review": len(manual),
            "disabled": len(disabled),
            "promoted_percent": round((len(dedicated) / len(rows)) * 100) if rows else 0,
        },
    }


def fetch_company_candidates(conn: sqlite3.Connection) -> dict:
    return {"active": [], "backlog": [], "counts": {}, "total": 0}


def fetch_raw_jobs(conn: sqlite3.Connection, limit: int = 500) -> dict:
    rows = conn.execute(
        """
        SELECT captured_at, company, title, location, country, remote_type, department,
               employment_type, date_posted, apply_url, source_url, source_platform,
               source_job_id, scraper_type, is_relevant, assessment_summary
        FROM raw_jobs
        ORDER BY company ASC, is_relevant DESC, title ASC, location ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    company_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT company, COUNT(*) AS raw_count, SUM(is_relevant) AS relevant_count
            FROM raw_jobs
            GROUP BY company
            ORDER BY raw_count DESC, company ASC
            """
        ).fetchall()
    ]
    total = conn.execute("SELECT COUNT(*) AS count FROM raw_jobs").fetchone()["count"]
    relevant = conn.execute("SELECT COUNT(*) AS count FROM raw_jobs WHERE is_relevant = 1").fetchone()["count"]
    latest = conn.execute("SELECT MAX(captured_at) AS latest FROM raw_jobs").fetchone()["latest"]
    return {
        "rows": [dict(row) for row in rows],
        "company_counts": company_counts,
        "summary": {
            "total": total,
            "relevant": relevant,
            "latest": latest,
            "returned": len(rows),
        },
    }


def add_company(payload: dict) -> dict:
    name = str(payload.get("company") or "").strip()
    careers_url = str(payload.get("careers_url") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    logo_url = str(payload.get("logo_url") or "").strip()
    if not name:
        raise ValueError("Company name is required.")
    if not careers_url:
        raise ValueError("Careers URL is required.")
    if not re.match(r"^https?://", careers_url):
        raise ValueError("Careers URL must start with http:// or https://.")

    raw = (yaml.safe_load(COMPANIES_PATH.read_text(encoding="utf-8")) or {}) if COMPANIES_PATH.exists() else {}
    companies = raw.get("companies", [])
    if any(str(item.get("company", "")).lower() == name.lower() for item in companies):
        raise ValueError(f"{name} is already in the company wishlist.")

    reason = "Added from dashboard wishlist."
    if notes:
        reason = f"{reason} Notes: {notes}"
    companies.append(
        {
            "company": name,
            "careers_url": careers_url,
            "scraper_type": "manual_review",
            "enabled": True,
            "manual_review_reason": reason,
            **({"logo_url": logo_url} if logo_url else {}),
        }
    )
    companies.sort(key=lambda item: str(item.get("company", "")).lower())
    write_companies(companies, COMPANIES_PATH)
    return {"ok": True, "company": name}


def update_company_candidate_decision(conn: sqlite3.Connection, candidate_id: int, payload: dict) -> dict:
    return {"ok": True}


def update_company_candidate_careers_url(conn: sqlite3.Connection, candidate_id: int, payload: dict) -> dict:
    return {"ok": True}


def suggest_company_candidate_careers_url(conn: sqlite3.Connection, candidate_id: int) -> dict:
    return {"ok": True, "suggestion": None}


def add_company_candidate_to_scrapers(conn: sqlite3.Connection, candidate_id: int) -> dict:
    return {"ok": True}


def create_manual_job(conn: sqlite3.Connection, payload: dict) -> dict:
    company = str(payload.get("company") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not company:
        raise ValueError("Company is required.")
    if not title:
        raise ValueError("Title is required.")
    status = str(payload.get("status") or "new").strip()
    if status not in TRACKED_STATUSES:
        raise ValueError(f"Unsupported status: {status}")

    job = Job(
        company=company,
        title=title,
        location=str(payload.get("location") or "").strip() or None,
        apply_url=str(payload.get("apply_url") or "").strip() or None,
        description=str(payload.get("notes") or "").strip() or None,
        source_platform="manual",
        scraper_type="manual",
        status=status,
    )
    apply_assessment(job)  # same plausibility/fit-band scoring scraped jobs get
    if job.fit_band == "excluded":
        # Deliberately tracked role; don't show a hard-fail label for a manual
        # entry just because it lacks the description text the filters expect.
        job.fit_band = "stretch"
        job.score = max(job.score, 40)
        reasons = [r for r in json.loads(job.score_reasons or "[]") if r != "Manually added"]
        job.score_reasons = json.dumps(["Manually added"] + reasons, ensure_ascii=False)
    upsert_jobs(conn, [job])

    row = conn.execute("SELECT id FROM jobs WHERE dedupe_key = ?", (dedupe_key(job),)).fetchone()
    if not row:
        raise ValueError("Failed to save job.")  # pragma: no cover - upsert_jobs always inserts/updates a row
    job_id = row["id"]

    applied_at = str(payload.get("applied_at") or "").strip()
    if status in ("applied", "interviewing") and applied_at:
        conn.execute(
            "INSERT INTO status_events (job_id, status, created_at) VALUES (?, ?, ?)",
            (job_id, status, f"{applied_at} 12:00:00"),
        )
    else:
        conn.execute("INSERT INTO status_events (job_id, status) VALUES (?, ?)", (job_id, status))
    conn.commit()
    return {"ok": True, "id": job_id, "status": status, "score": job.score, "fit_band": job.fit_band}


def create_feedback(conn: sqlite3.Connection, payload: dict) -> dict:
    message = str(payload.get("message") or "").strip()
    if not message:
        raise ValueError("Feedback message is required.")
    page = str(payload.get("page") or "").strip() or None
    conn.execute("INSERT INTO feedback (message, page) VALUES (?, ?)", (message, page))
    conn.commit()
    return {"ok": True}


def update_job_status(conn: sqlite3.Connection, job_id: int, status: str) -> dict:
    if status not in set(TRACKED_STATUSES) | {"scrape_failed"}:
        raise ValueError(f"Unsupported status: {status}")
    row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise ValueError(f"Job not found: {job_id}")
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.execute("INSERT INTO status_events (job_id, status) VALUES (?, ?)", (job_id, status))
    conn.commit()
    return {"ok": True, "id": job_id, "status": status}


def update_job_notes(conn: sqlite3.Connection, job_id: int, notes: str) -> dict:
    row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise ValueError(f"Job not found: {job_id}")
    conn.execute("UPDATE jobs SET notes = ? WHERE id = ?", (notes or None, job_id))
    conn.commit()
    return {"ok": True, "id": job_id, "notes": notes}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "JobArcade/1.0"

    def _send_json(self, payload: dict | list, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _send_png(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _blocked_if_retired(self) -> bool:
        """Reject any write/action request while the dashboard is retired (read-only archive)."""
        if not RETIRED:
            return False
        self._send_error_json(
            "This dashboard is retired — it's read-only now. No new scraping, drafting, or edits.",
            HTTPStatus.FORBIDDEN,
        )
        return True

    def _blocked_if_scraper_disabled(self, conn: sqlite3.Connection) -> bool:
        """Reject URL scraping and discovery requests when the scraper feature is disabled."""
        if scraper_enabled(conn):
            return False
        self._send_error_json(
            "URL scraping is disabled. Enable it under System → Features.",
            HTTPStatus.FORBIDDEN,
        )
        return True

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/onboarding":
                with db_session() as conn:
                    self._send_json(onboarding_state(conn, profile_module.DEFAULT_PROFILE_PATH))
                return
            if parsed.path == "/api/profile":
                self._send_json(read_profile_document(profile_module.DEFAULT_PROFILE_PATH))
                return
            if parsed.path == "/api/goals":
                with db_session() as conn:
                    self._send_json(get_goals(conn))
                return
            if parsed.path == "/api/style":
                self._send_json({**read_default_style(), "variants": list(CV_VARIANTS), "fonts": list(STYLE_FONTS)})
                return
            if parsed.path == "/api/summary":
                with db_session() as conn:
                    self._send_json(fetch_summary(conn))
                return
            if parsed.path == "/api/stats":
                with db_session() as conn:
                    self._send_json(fetch_stats(conn))
                return
            if parsed.path == "/api/jobs":
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["5000"])[0])
                with db_session() as conn:
                    self._send_json(fetch_jobs(conn, limit=limit))
                return
            if parsed.path == "/api/companies":
                with db_session() as conn:
                    self._send_json(fetch_companies(conn))
                return
            if parsed.path == "/api/company-candidates":
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                    self._send_json(fetch_company_candidates(conn))
                return
            if parsed.path == "/api/raw-jobs":
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["500"])[0])
                with db_session() as conn:
                    self._send_json(fetch_raw_jobs(conn, limit=limit))
                return
            if parsed.path == "/api/artifacts":
                self._send_json(list(application_artifacts().values()))
                return
            if parsed.path == "/api/ollama/status":
                self._send_json(_ollama_status())
                return
            if parsed.path == "/api/gmail/status":
                with db_session() as conn:
                    self._send_json(gmail_status(conn))
                return
            if parsed.path == "/api/gmail/sync/progress":
                self._send_json(gmail_sync_progress())
                return
            if parsed.path == "/api/integrations":
                forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
                scheme = forwarded_proto or "http"
                host = self.headers.get("Host") or "localhost:8765"
                suggested = f"{scheme}://{host}/api/gmail/oauth/callback"
                with db_session() as conn:
                    self._send_json(integration_status(conn, suggested))
                return
            if parsed.path == "/api/gmail/evidence":
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["50"])[0])
                with db_session() as conn:
                    self._send_json(evidence_rows(conn, limit=limit))
                return
            if parsed.path == "/api/gmail/metrics":
                with db_session() as conn:
                    self._send_json(gmail_metrics(conn))
                return
            evidence_candidates_match = re.match(r"^/api/gmail/evidence/([^/]+)/candidates$", parsed.path)
            if evidence_candidates_match:
                with db_session() as conn:
                    self._send_json(evidence_candidates(conn, unquote(evidence_candidates_match.group(1))))
                return
            if parsed.path == "/api/gmail/oauth/callback":
                query = parse_qs(parsed.query)
                if query.get("error"):
                    self._send_oauth_html(f"Gmail connection failed: {query['error'][0]}", ok=False)
                    return
                code = (query.get("code") or [""])[0]
                if not code:
                    self._send_oauth_html("Gmail connection failed: missing OAuth code.", ok=False)
                    return
                with db_session() as conn:
                    consume_auth_state(conn, (query.get("state") or [""])[0])
                    config = load_gmail_config(conn)
                    result = save_oauth_token(conn, exchange_code_for_token(code, config), config)
                self._send_oauth_html(f"Gmail connected for {result.get('email') or 'this account'}.")
                return
            draft_match = re.match(r"^/api/applications/([^/]+)/draft$", parsed.path)
            if draft_match:
                self._send_json(read_application_draft(draft_match.group(1)))
                return
            zip_match = re.match(r"^/applications/([^/]+)/bundle\.zip$", parsed.path)
            if zip_match:
                self._serve_application_zip(zip_match.group(1))
                return
            app_match = re.match(r"^/applications/([^/]+)/(.+\.pdf)$", parsed.path)
            if app_match:
                self._serve_application_file(app_match.group(1), app_match.group(2))
                return
            self._serve_static(parsed.path)
        except ProfileError as exc:
            self._send_error_json(str(exc), HTTPStatus.UNPROCESSABLE_ENTITY)
        except Exception as exc:  # pragma: no cover - keeps browser errors useful.
            self.log_message("unhandled GET error: %s", exc)
            self._send_error_json("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        if self._blocked_if_retired():
            return
        parsed = urlparse(self.path)
        try:
            payload = _read_json(self)
            if parsed.path == "/api/style/preview":
                self._send_png(render_style_preview(payload))
                return
            if parsed.path == "/api/demo/seed":
                from jobhunt.demo_seed import seed_demo

                with db_session() as conn:
                    self._send_json(seed_demo(conn, APPLICATIONS_DIR))
                return
            if parsed.path == "/api/onboarding/step":
                with db_session() as conn:
                    self._send_json(set_onboarding_step(conn, str(payload.get("step") or "")))
                return
            if parsed.path in ("/api/onboarding/complete", "/api/onboarding/skip", "/api/onboarding/reset"):
                action = {
                    "/api/onboarding/complete": complete_onboarding,
                    "/api/onboarding/skip": skip_onboarding,
                    "/api/onboarding/reset": reset_onboarding,
                }[parsed.path]
                with db_session() as conn:
                    self._send_json(action(conn))
                return
            if parsed.path == "/api/companies":
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                self._send_json(add_company(payload), HTTPStatus.CREATED)
                return
            candidate_decision_match = re.match(r"^/api/company-candidates/(\d+)/decision$", parsed.path)
            if candidate_decision_match:
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                    self._send_json(
                        update_company_candidate_decision(conn, int(candidate_decision_match.group(1)), payload)
                    )
                return
            candidate_url_match = re.match(r"^/api/company-candidates/(\d+)/careers-url$", parsed.path)
            if candidate_url_match:
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                    self._send_json(
                        update_company_candidate_careers_url(conn, int(candidate_url_match.group(1)), payload)
                    )
                return
            candidate_suggest_url_match = re.match(
                r"^/api/company-candidates/(\d+)/suggest-careers-url$", parsed.path
            )
            if candidate_suggest_url_match:
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                    self._send_json(suggest_company_candidate_careers_url(conn, int(candidate_suggest_url_match.group(1))))
                return
            candidate_add_match = re.match(r"^/api/company-candidates/(\d+)/add-to-scrapers$", parsed.path)
            if candidate_add_match:
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                    self._send_json(
                        add_company_candidate_to_scrapers(conn, int(candidate_add_match.group(1))),
                        HTTPStatus.CREATED,
                    )
                return
            if parsed.path == "/api/jobs/scrape":
                with db_session() as conn:
                    if self._blocked_if_scraper_disabled(conn):
                        return
                    key = effective_firecrawl_key(conn) or None
                self._send_json(scrape_job_listing(str(payload.get("url") or ""), api_key=key))
                return
            if parsed.path == "/api/integrations/firecrawl/test":
                url = str(payload.get("url") or "https://www.netflix.com")
                with db_session() as conn:
                    key = effective_firecrawl_key(conn)
                try:
                    if not key:
                        raise ValueError("No Firecrawl API key is configured.")
                    result = extract_theme(url, provider="firecrawl", api_key=key)
                    theme = result.theme
                    self._send_json(
                        {
                            "ok": True,
                            "accent": theme.get("accent"),
                            "mode": theme.get("mode"),
                            "dark_recommended": bool(theme.get("dark_recommended")),
                            "warnings": result.warnings,
                        }
                    )
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc).replace(key, "***")[:500] if key else str(exc)[:500]})
                return
            if parsed.path == "/api/jobs":
                with db_session() as conn:
                    self._send_json(create_manual_job(conn, payload), HTTPStatus.CREATED)
                return
            if parsed.path == "/api/ollama/warmup":
                threading.Thread(target=_ollama_warmup_background, daemon=True).start()
                self._send_json({"ok": True, "model": _ollama_runtime("draft")[1], "status": "warming"})
                return
            if parsed.path == "/api/gmail/oauth/start":
                with db_session() as conn:
                    self._send_json(create_auth_url(conn))
                return
            if parsed.path == "/api/integrations/ollama/test":
                with db_session() as conn:
                    self._send_json(test_ollama_settings(conn))
                return
            if parsed.path == "/api/gmail/sync":
                with db_session() as conn:
                    self._send_json(
                        start_gmail_sync(
                            conn,
                            max_results=int(payload.get("max_results") or 50),
                            after=str(payload.get("after") or "") or None,
                        )
                    )
                return
            evidence_apply_match = re.match(r"^/api/gmail/evidence/([^/]+)/apply$", parsed.path)
            if evidence_apply_match:
                with db_session() as conn:
                    self._send_json(apply_evidence(conn, unquote(evidence_apply_match.group(1))))
                return
            evidence_update_match = re.match(r"^/api/gmail/evidence/([^/]+)$", parsed.path)
            if evidence_update_match:
                job_id = payload.get("job_id")
                with db_session() as conn:
                    self._send_json(
                        update_evidence(
                            conn,
                            unquote(evidence_update_match.group(1)),
                            str(payload.get("evidence_type") or ""),
                            int(job_id) if job_id is not None else None,
                        )
                    )
                return
            evidence_ignore_match = re.match(r"^/api/gmail/evidence/([^/]+)/ignore$", parsed.path)
            if evidence_ignore_match:
                with db_session() as conn:
                    self._send_json(reject_evidence(conn, unquote(evidence_ignore_match.group(1))))
                return
            if parsed.path == "/api/feedback":
                with db_session() as conn:
                    self._send_json(create_feedback(conn, payload), HTTPStatus.CREATED)
                return
            draft_match = re.match(r"^/api/jobs/(\d+)/draft-pack$", parsed.path)
            if draft_match:
                with db_session() as conn:
                    self._send_json(
                        create_draft_pack(
                            conn,
                            int(draft_match.group(1)),
                            str(payload.get("custom_instructions") or ""),
                        ),
                        HTTPStatus.CREATED,
                    )
                return
            build_match = re.match(r"^/api/applications/([^/]+)/build$", parsed.path)
            if build_match:
                self._send_json(build_application(build_match.group(1)))
                return
            brand_url_match = re.match(r"^/api/applications/([^/]+)/brand-url$", parsed.path)
            if brand_url_match:
                self._send_json(set_application_brand_url(brand_url_match.group(1), payload.get("brand_url")))
                return
            theme_match = re.match(r"^/api/applications/([^/]+)/brand-theme$", parsed.path)
            if theme_match:
                job_id_val = payload.get("job_id")
                job_id = int(job_id_val) if job_id_val else None
                source_url = str(payload.get("source_url") or "") or None
                provider = str(payload.get("provider") or "auto")
                with db_session() as conn:
                    self._send_json(
                        extract_application_brand_theme(conn, theme_match.group(1), job_id, source_url, provider)
                    )
                return
            theme_reset_match = re.match(r"^/api/applications/([^/]+)/brand-theme/reset$", parsed.path)
            if theme_reset_match:
                self._send_json(reset_application_brand_theme(theme_reset_match.group(1)))
                return
            theme_mode_match = re.match(r"^/api/applications/([^/]+)/brand-theme/mode$", parsed.path)
            if theme_mode_match:
                self._send_json(set_application_brand_theme_mode(theme_mode_match.group(1), str(payload.get("mode") or "")))
                return

            theme_typography_match = re.match(r"^/api/applications/([^/]+)/brand-theme/typography$", parsed.path)
            if theme_typography_match:
                self._send_json(set_application_brand_typography(theme_typography_match.group(1), bool(payload.get("enabled"))))
                return
            ready_match = re.match(r"^/api/applications/([^/]+)/ready-for-review$", parsed.path)
            if ready_match:
                with db_session() as conn:
                    self._send_json(
                        mark_draft_ready_for_review(
                            conn, ready_match.group(1), int(payload.get("job_id")) if payload.get("job_id") else None
                        )
                    )
                return
            match = re.match(r"^/api/jobs/(\d+)/status$", parsed.path)
            if match:
                with db_session() as conn:
                    self._send_json(update_job_status(conn, int(match.group(1)), str(payload.get("status"))))
                return
            notes_match = re.match(r"^/api/jobs/(\d+)/notes$", parsed.path)
            if notes_match:
                with db_session() as conn:
                    self._send_json(update_job_notes(conn, int(notes_match.group(1)), str(payload.get("notes") or "")))
                return
            reprompt_match = re.match(r"^/api/applications/([^/]+)/reprompt$", parsed.path)
            if reprompt_match:
                mode = str(payload.get("mode") or "fresh")
                instructions = str(payload.get("instructions") or "")
                current_draft = payload.get("current_draft") or {}
                job_id_val = payload.get("job_id")
                job_id = int(job_id_val) if job_id_val else None
                with db_session() as conn:
                    self._send_json(reprompt_draft(reprompt_match.group(1), mode, instructions, current_draft, job_id, conn))
                return
            self._send_error_json("Not found", HTTPStatus.NOT_FOUND)
        except ProfileError as exc:
            self._send_error_json(str(exc), HTTPStatus.UNPROCESSABLE_ENTITY)
        except ValueError as exc:
            self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover
            self.log_message("unhandled POST error: %s", exc)
            self._send_error_json("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:  # noqa: N802
        if self._blocked_if_retired():
            return
        parsed = urlparse(self.path)
        try:
            payload = _read_json(self)
            if parsed.path == "/api/integrations/gmail":
                with db_session() as conn:
                    self._send_json(save_gmail_settings(conn, payload))
                return
            if parsed.path == "/api/integrations/ollama":
                with db_session() as conn:
                    self._send_json(save_ollama_settings(conn, payload))
                return
            if parsed.path == "/api/integrations/firecrawl":
                with db_session() as conn:
                    self._send_json(save_firecrawl_settings(conn, payload))
                return
            if parsed.path == "/api/features":
                with db_session() as conn:
                    self._send_json(save_features(conn, payload))
                return
            if parsed.path == "/api/profile":
                self._send_json(write_profile_document(payload, profile_module.DEFAULT_PROFILE_PATH))
                return
            if parsed.path == "/api/goals":
                with db_session() as conn:
                    self._send_json(save_goals(conn, payload))
                return
            if parsed.path == "/api/style":
                self._send_json(save_default_style(payload))
                return
            draft_match = re.match(r"^/api/applications/([^/]+)/draft$", parsed.path)
            if draft_match:
                self._send_json(save_application_draft(draft_match.group(1), payload))
                return
            self._send_error_json("Not found", HTTPStatus.NOT_FOUND)
        except ProfileError as exc:
            self._send_error_json(str(exc), HTTPStatus.UNPROCESSABLE_ENTITY)
        except ValueError as exc:
            self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover
            self.log_message("unhandled PUT error: %s", exc)
            self._send_error_json("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:  # noqa: N802
        if self._blocked_if_retired():
            return
        parsed = urlparse(self.path)
        try:
            app_match = re.match(r"^/api/applications/([^/]+)$", parsed.path)
            if app_match:
                qs = parse_qs(parsed.query)
                job_id_str = (qs.get("job_id") or [None])[0]
                job_id = int(job_id_str) if job_id_str and job_id_str.isdigit() else None
                with db_session() as conn:
                    delete_application(app_match.group(1), job_id, conn)
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            if parsed.path == "/api/demo":
                from jobhunt.demo_seed import clear_demo

                with db_session() as conn:
                    self._send_json(clear_demo(conn, APPLICATIONS_DIR))
                return
            if parsed.path == "/api/gmail/account":
                with db_session() as conn:
                    disconnect_gmail(conn)
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            if parsed.path == "/api/integrations/gmail":
                with db_session() as conn:
                    self._send_json(clear_gmail_settings(conn))
                return
            if parsed.path == "/api/integrations/firecrawl":
                with db_session() as conn:
                    self._send_json(clear_firecrawl_settings(conn))
                return
            self._send_error_json("Not found", HTTPStatus.NOT_FOUND)
        except ProfileError as exc:
            self._send_error_json(str(exc), HTTPStatus.UNPROCESSABLE_ENTITY)
        except ValueError as exc:
            self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover
            self.log_message("unhandled DELETE error: %s", exc)
            self._send_error_json("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_static(self, request_path: str) -> None:
        if request_path in ("", "/"):
            path = "index.html"
        elif request_path in ("/draft", "/draft/") or request_path.startswith("/draft/"):
            path = "index.html"
        else:
            path = request_path.lstrip("/")
        candidate = (STATIC_DIR / path).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
            is_valid = True
        except ValueError:
            is_valid = False
        if not is_valid or not candidate.exists() or candidate.is_dir():
            candidate = STATIC_DIR / "index.html"
        content = candidate.read_bytes()
        if RETIRED and candidate.suffix == ".html":
            content = content.replace(b"<body>", b"<body>" + RETIRED_BANNER, 1)
        mime_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        # Hashed build assets (dashboard/static/app/*) are immutable; the HTML
        # shells must revalidate so a rebuild never serves a stale bundle ref.
        if candidate.suffix == ".html":
            self.send_header("Cache-Control", "no-cache")
        elif candidate.parent.name == "app":
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(content)

    def _send_oauth_html(self, message: str, ok: bool = True) -> None:
        escaped = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Gmail OAuth</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 680px; margin: 64px auto; line-height: 1.5;">
  <h1>{'Connected' if ok else 'Connection failed'}</h1>
  <p>{escaped}</p>
  <p>You can close this tab and return to Job Hunt HQ.</p>
</body>
</html>""".encode("utf-8")
        self.send_response(HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_application_file(self, app_slug: str, filename: str) -> None:
        """Serve a PDF from Applications/<app_slug>/<filename> with traversal protection."""
        candidate = (APPLICATIONS_DIR / app_slug / filename).resolve()
        apps_resolved = APPLICATIONS_DIR.resolve()
        try:
            candidate.relative_to(apps_resolved)
            is_valid = True
        except ValueError:
            is_valid = False
        if not is_valid:
            self._send_error_json("Forbidden", HTTPStatus.FORBIDDEN)
            return
        if not candidate.exists() or candidate.is_dir():
            self._send_error_json("Not found", HTTPStatus.NOT_FOUND)
            return
        if candidate.suffix.lower() != ".pdf":
            self._send_error_json("Only PDF files are served", HTTPStatus.FORBIDDEN)
            return
        content = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'inline; filename="{candidate.name}"')
        self.end_headers()
        self.wfile.write(content)

    def _serve_application_zip(self, app_slug: str) -> None:
        """Bundle an application's CV + letter into a zip, named after the role."""
        folder = (APPLICATIONS_DIR / app_slug).resolve()
        try:
            folder.relative_to(APPLICATIONS_DIR.resolve())
            is_valid = folder.is_dir()
        except ValueError:
            is_valid = False
        cv_paths = sorted(folder.glob("cv*.pdf")) if is_valid else []
        letter_paths = sorted(folder.glob("motivation-letter*.pdf")) if is_valid else []
        if not (cv_paths and letter_paths):
            self._send_error_json("Not found", HTTPStatus.NOT_FOUND)
            return
        cand_name = _safe_profile().name or "Candidate"
        role_label = app_slug.replace("-", " ")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(cv_paths[0], f"{cand_name} - CV - {role_label}.pdf")
            zf.write(letter_paths[0], f"{cand_name} - Motivation Letter - {role_label}.pdf")
        content = buffer.getvalue()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(content)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="{cand_name} - {role_label}.zip"'
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[dashboard] {self.address_string()} - {format % args}")


def serve_dashboard(host: str = "127.0.0.1", port: int = 8765) -> None:
    ensure_profile_file()
    init_db(connect(DB_PATH)).close()
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Job Application Hub dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()
