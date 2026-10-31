from __future__ import annotations

from pathlib import Path

import yaml

from jobhunt.models import Company

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
COMPANIES_PATH = CONFIG_DIR / "companies.yaml"
DB_PATH = DATA_DIR / "jobs.sqlite"
CSV_PATH = DATA_DIR / "jobs.csv"
RAW_CSV_PATH = DATA_DIR / "raw-jobs.csv"
RAW_MARKDOWN_PATH = DATA_DIR / "raw-jobs.md"
DIRECTORY_PATH = ROOT / "careers-directory.md"


ROLE_TITLE_KEYWORDS = (
    "manager",
    "coordinator",
    "specialist",
    "creator",
    "producer",
    "executive",
    "associate",
    "assistant",
    "marketeer",
    "lead",
    "strategist",
    "editor",
    "planner",
    "copywriter",
    "consultant",
)


REMOTE_TOKENS = ("remote", "hybrid", "work from home", "wfh")


def load_companies(path: Path = COMPANIES_PATH) -> list[Company]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    companies = []
    for item in raw.get("companies", []):
        companies.append(
            Company(
                company=item["company"],
                careers_url=item["careers_url"],
                scraper_type=item.get("scraper_type", "manual_review"),
                enabled=bool(item.get("enabled", True)),
                adapter=item.get("adapter"),
                config=item.get("config"),
                manual_review_reason=item.get("manual_review_reason"),
                brand_url=item.get("brand_url"),
                logo_url=item.get("logo_url"),
                ats=item.get("ats"),
                selectors=item.get("selectors"),
                api=item.get("api"),
            )
        )
    return companies


def write_companies(companies: list[dict], path: Path = COMPANIES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"companies": companies}
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
