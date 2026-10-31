from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = ROOT / "config" / "profile.yaml"
EXAMPLE_PROFILE_PATH = ROOT / "config" / "profile.example.yaml"


@dataclass
class CandidateContact:
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    linkedin_url: str = ""
    portfolio: str = ""
    portfolio_url: str = ""


@dataclass(frozen=True)
class SearchRules:
    target_roles: tuple[str, ...] = ()
    adjacent_roles: tuple[str, ...] = ()
    excluded_functions: tuple[str, ...] = ()
    max_years_experience: int | None = None
    exclude_senior_titles: bool = False
    exclude_internships: bool = False
    accepted_locations: tuple[str, ...] = ()
    preferred_cities: tuple[str, ...] = ()
    allow_remote: bool = True
    excluded_language_patterns: tuple[str, ...] = ()


def _str_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    return tuple(str(v).strip() for v in value if str(v).strip())


def _opt_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _search_rules_from_prefs(prefs: dict) -> SearchRules:
    allow_remote = prefs.get("allow_remote")
    return SearchRules(
        target_roles=_str_tuple(prefs.get("target_roles")),
        adjacent_roles=_str_tuple(prefs.get("adjacent_roles")),
        excluded_functions=_str_tuple(prefs.get("excluded_functions")),
        max_years_experience=_opt_int(prefs.get("max_years_experience")),
        exclude_senior_titles=bool(prefs.get("exclude_senior_titles", False)),
        exclude_internships=bool(prefs.get("exclude_internships", False)),
        accepted_locations=_str_tuple(prefs.get("target_locations")),
        preferred_cities=_str_tuple(prefs.get("preferred_cities")),
        allow_remote=True if allow_remote is None else bool(allow_remote),
        excluded_language_patterns=_str_tuple(prefs.get("excluded_language_patterns")),
    )


@dataclass
class CandidateProfile:
    name: str = "Candidate Name"
    tagline: str = ""
    contact: CandidateContact = field(default_factory=CandidateContact)
    career_facts: str = ""
    skills: list[str] = field(default_factory=list)
    languages: list[list[str]] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    target_roles: list[str] = field(default_factory=list)
    target_locations: list[str] = field(default_factory=list)
    search: SearchRules = field(default_factory=SearchRules)


def load_candidate_profile(path: Path | None = None) -> CandidateProfile:
    target = path or DEFAULT_PROFILE_PATH
    if not target.exists():
        target = EXAMPLE_PROFILE_PATH
    if not target.exists():
        return CandidateProfile()

    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    raw = raw if isinstance(raw, dict) else {}
    cand = raw.get("candidate")
    cand = cand if isinstance(cand, dict) else {}
    contact_data = cand.get("contact")
    contact_data = contact_data if isinstance(contact_data, dict) else {}
    target_prefs = raw.get("target_preferences")
    target_prefs = target_prefs if isinstance(target_prefs, dict) else {}

    contact = CandidateContact(
        email=str(contact_data.get("email") or "").strip(),
        phone=str(contact_data.get("phone") or "").strip(),
        location=str(contact_data.get("location") or "").strip(),
        linkedin=str(contact_data.get("linkedin") or "").strip(),
        linkedin_url=str(contact_data.get("linkedin_url") or "").strip(),
        portfolio=str(contact_data.get("portfolio") or "").strip(),
        portfolio_url=str(contact_data.get("portfolio_url") or "").strip(),
    )

    return CandidateProfile(
        name=str(cand.get("name") or "Candidate Name").strip(),
        tagline=str(cand.get("tagline") or "").strip(),
        contact=contact,
        career_facts=str(cand.get("career_facts") or "").strip(),
        skills=list(cand.get("skills") or []),
        languages=list(cand.get("languages") or []),
        education=list(cand.get("education") or []),
        certifications=list(cand.get("certifications") or []),
        target_roles=list(target_prefs.get("target_roles") or []),
        target_locations=list(target_prefs.get("target_locations") or []),
        search=_search_rules_from_prefs(target_prefs),
    )


_RULES_CACHE: dict[tuple[str, float | None], SearchRules] = {}


def load_search_rules(path: Path | None = None) -> SearchRules:
    """Load search rules from the profile, cached on (resolved path, mtime)."""
    target = path or DEFAULT_PROFILE_PATH
    if not target.exists():
        target = EXAMPLE_PROFILE_PATH
    try:
        key = (str(target.resolve()), target.stat().st_mtime)
    except OSError:
        return SearchRules()
    cached = _RULES_CACHE.get(key)
    if cached is None:
        try:
            cached = load_candidate_profile(target).search
        except (yaml.YAMLError, AttributeError, TypeError, ValueError, OSError) as exc:
            print(f"warning: could not read search rules from {target}: {exc}; using permissive defaults", file=sys.stderr)
            cached = SearchRules()
        _RULES_CACHE[key] = cached
    return cached


def export_profile_for_typst(profile: CandidateProfile) -> dict:
    contacts = []
    if profile.contact.email:
        contacts.append({"label": "Email", "value": profile.contact.email, "url": f"mailto:{profile.contact.email}"})
    if profile.contact.phone:
        contacts.append({"label": "Phone", "value": profile.contact.phone})
    if profile.contact.location:
        contacts.append({"label": "Location", "value": profile.contact.location})
    if profile.contact.linkedin:
        contacts.append({
            "label": "LinkedIn",
            "value": profile.contact.linkedin,
            "url": profile.contact.linkedin_url or f"https://{profile.contact.linkedin}",
        })
    if profile.contact.portfolio:
        contacts.append({
            "label": "Portfolio",
            "value": profile.contact.portfolio,
            "url": profile.contact.portfolio_url or f"https://{profile.contact.portfolio}",
        })

    return {
        "name": profile.name,
        "tagline": profile.tagline,
        "contact": contacts,
        "skills": profile.skills,
        "languages": profile.languages,
        "education": profile.education,
        "certifications": profile.certifications,
    }
