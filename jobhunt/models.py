from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Company:
    company: str
    careers_url: str
    scraper_type: str = "manual_review"
    enabled: bool = True
    adapter: str | None = None
    config: dict | None = None
    manual_review_reason: str | None = None
    brand_url: str | None = None
    logo_url: str | None = None
    ats: dict | None = None
    selectors: dict | None = None
    api: dict | None = None


@dataclass(slots=True)
class Job:
    company: str
    title: str
    location: str | None = None
    country: str | None = None
    remote_type: str | None = None
    department: str | None = None
    employment_type: str | None = None
    date_posted: str | None = None
    description: str | None = None
    requirements: str | None = None
    apply_url: str | None = None
    source_url: str | None = None
    source_platform: str | None = None
    source_job_id: str | None = None
    scraper_type: str | None = None
    status: str = "new"
    priority: str = "Low"
    score: int = 0
    fit_band: str = "stretch"
    score_reasons: str | None = None
    assessment_summary: str | None = None

