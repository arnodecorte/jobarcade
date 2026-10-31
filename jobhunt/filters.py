from __future__ import annotations

from jobhunt.assessment import assess_job
from jobhunt.assessment import experience_ok, language_ok, location_ok
from jobhunt.models import Job
from jobhunt.profile import SearchRules


def _filter_location(rules: SearchRules | None) -> str | None:
    # Placeholder location used for title-only checks: pick one the rules accept.
    from jobhunt.profile import load_search_rules

    resolved = rules if rules is not None else load_search_rules()
    return resolved.accepted_locations[0] if resolved.accepted_locations else None


def title_ok(title: str | None, rules: SearchRules | None = None) -> bool:
    return assess_job(Job(company="__filter__", title=title or "", location=_filter_location(rules)), rules).included


def calculate_priority(text: str, rules: SearchRules | None = None) -> str:
    job = Job(company="__priority__", title=text or "Marketing Specialist", location=_filter_location(rules), description=text)
    return assess_job(job, rules).priority


def job_ok(job: Job, rules: SearchRules | None = None) -> bool:
    return assess_job(job, rules).included
