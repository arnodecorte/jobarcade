from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
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


def load_candidate_profile(path: Path | None = None) -> CandidateProfile:
    target = path or DEFAULT_PROFILE_PATH
    if not target.exists():
        target = EXAMPLE_PROFILE_PATH
    if not target.exists():
        return CandidateProfile()

    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    cand = raw.get("candidate", {})
    contact_data = cand.get("contact", {})
    target_prefs = raw.get("target_preferences", {})

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
    )


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
