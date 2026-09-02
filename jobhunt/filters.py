from __future__ import annotations

from jobhunt.assessment import assess_job
from jobhunt.assessment import experience_ok, language_ok, location_ok
from jobhunt.models import Job


def title_ok(title: str | None) -> bool:
    return assess_job(Job(company="__filter__", title=title or "", location="Amsterdam")).included


def calculate_priority(text: str) -> str:
    job = Job(company="__priority__", title=text or "Marketing Specialist", location="Amsterdam", description=text)
    return assess_job(job).priority


def job_ok(job: Job) -> bool:
    return assess_job(job).included
