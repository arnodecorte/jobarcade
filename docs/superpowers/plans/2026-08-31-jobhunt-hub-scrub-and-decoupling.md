# Job Application Hub Scrubbing & Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the repository from a personal job-hunt scraper into a clean, standalone, open-source-ready Job Application & AI Tailoring Hub with turnkey Docker deployment.

**Architecture:** Candidate facts, contact info, and role preferences are decoupled into `config/profile.yaml`. The fragile 98-company scraper fleet and bulk discovery backlogs are deleted, isolating the single-job URL extractor, Ollama AI CV/letter tailor, Typst PDF compiler, and Kanban/probabilistic analytics dashboard. Private applications and databases are scrubbed and replaced with clean starter assets.

**Tech Stack:** Python 3.11, Typst CLI, SQLite, Ollama, HTML5 / Vanilla JS Frontend, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-31-jobhunt-hub-scrub-and-decoupling-design.md`

## Global Constraints
- No hardcoded personal names, emails, phone numbers, or candidate history in code or Typst files.
- Python code must pass `pytest` cleanly.
- `typst compile` must succeed for all CV variants (`grotesk_one_page`, `compact_one_page`, `classic_two_page`, `enriched_two_page`) with dynamic profile data.
- Docker image must build without heavy browser/Playwright/Akamai bypass packages.

---

### Task 1: Candidate Profile Configuration & Loader

**Files:**
- Create: `config/profile.example.yaml`
- Create: `jobhunt/profile.py`
- Create: `tests/test_profile.py`

**Interfaces:**
- Consumes: YAML file from `config/profile.yaml` (falling back to `config/profile.example.yaml`).
- Produces: `CandidateProfile` dataclass, `load_candidate_profile(path: Path | None = None) -> CandidateProfile`, and `export_profile_for_typst(profile: CandidateProfile) -> dict`.

- [ ] **Step 1: Write the failing tests for profile loader**

```python
# tests/test_profile.py
from pathlib import Path
import pytest
from jobhunt.profile import load_candidate_profile, CandidateProfile, export_profile_for_typst


def test_load_candidate_profile_from_example(tmp_path: Path):
    yaml_content = """
candidate:
  name: "Alex Morgan"
  tagline: "Growth Marketer"
  contact:
    email: "alex@example.com"
    phone: "+31 6 12345678"
    location: "Amsterdam, Netherlands"
    linkedin: "linkedin.com/in/alex"
    linkedin_url: "https://linkedin.com/in/alex"
    portfolio: "alex.design"
    portfolio_url: "https://alex.design"
  career_facts: |
    - Marketer at Corp A (2023-Present): Scaled leads by 30%.
  skills:
    - "Lifecycle Marketing"
    - "SQL Analytics"
  languages:
    - ["English", "Native"]
  education:
    - deg: "BSc Business"
      school: "UvA"
      notes: ["Honors"]
  certifications:
    - "HubSpot Certified"
target_preferences:
  target_roles: ["Marketing Manager"]
  target_locations: ["Amsterdam"]
"""
    cfg_file = tmp_path / "profile.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    prof = load_candidate_profile(cfg_file)
    assert prof.name == "Alex Morgan"
    assert prof.tagline == "Growth Marketer"
    assert prof.contact.email == "alex@example.com"
    assert len(prof.skills) == 2
    assert "Marketer at Corp A" in prof.career_facts

    typst_data = export_profile_for_typst(prof)
    assert typst_data["name"] == "Alex Morgan"
    assert typst_data["contact"][0]["value"] == "alex@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'jobhunt.profile'`

- [ ] **Step 3: Create `config/profile.example.yaml` and implement `jobhunt/profile.py`**

```yaml
# config/profile.example.yaml
candidate:
  name: "Alex Morgan"
  tagline: "Product Marketing & Growth Strategist"
  contact:
    email: "alex.morgan@example.com"
    phone: "+31 6 12345678"
    location: "Amsterdam, Netherlands"
    linkedin: "linkedin.com/in/alex-morgan"
    linkedin_url: "https://www.linkedin.com/in/alex-morgan/"
    portfolio: "alexmorgan.design"
    portfolio_url: "https://alexmorgan.design"
  
  career_facts: |
    - Senior Marketing Specialist, TechCorp (SaaS), Amsterdam, 2023-Present: Owned B2B demand gen, ran paid acquisition campaigns, managed content calendars, increased inbound leads by 35%.
    - Growth Marketing Coordinator, StartupX, 2021-2023: Built lifecycle email automations in HubSpot, executed A/B tests on landing pages, boosted trial-to-paid conversion by 18%.
    - Marketing Assistant, Agency Y, 2019-2021: Produced social media assets, drafted blog posts, and reported campaign analytics.

  skills:
    - "Brand Strategy & Multichannel Consistency"
    - "Lifecycle Marketing & CRM Automation"
    - "Paid & Organic Acquisition (LinkedIn, Meta)"
    - "KPI Dashboards & Performance Reporting (SQL, Power BI)"
    - "Creative Asset Production (Figma, Canva, Copywriting)"

  languages:
    - ["English", "Native speaker"]
    - ["Dutch", "Professional working proficiency"]

  education:
    - deg: "BSc International Business Administration"
      school: "University of Amsterdam"
      notes:
        - "Specialization in Digital Marketing & Consumer Behavior"

  certifications:
    - "HubSpot Inbound Marketing Certified, 2023"
    - "Google Analytics Individual Qualification, 2022"

target_preferences:
  target_roles:
    - "Marketing Manager"
    - "Product Marketing Manager"
    - "Growth Marketing Specialist"
    - "Content Strategist"
  target_locations:
    - "Amsterdam"
    - "Rotterdam"
    - "Utrecht"
    - "Remote"
```

```python
# jobhunt/profile.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile.py -v`  
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add config/profile.example.yaml jobhunt/profile.py tests/test_profile.py
git commit -m "feat: add candidate profile schema, example, and loader"
```

---

### Task 2: Typst Template Decoupling & Dynamic Profile Ingestion

**Files:**
- Modify: `Base/cv.typ`
- Modify: `Base/letter.typ`
- Modify: `Base/reference/cv-data.yaml`
- Modify: `Base/reference/letter-data.yaml`
- Modify: `Base/assets/signature.png` (replace with generic signature sample)
- Test: `tests/test_typst_compile.py`

**Interfaces:**
- Consumes: `export_profile_for_typst` output passed as input or loaded from profile YAML in `Base/cv.typ` and `Base/letter.typ`.
- Produces: Compiled PDFs matching any candidate profile without hardcoded personal strings.

- [ ] **Step 1: Write test for Typst PDF compilation with dynamic profile**

```python
# tests/test_typst_compile.py
import subprocess
import shutil
from pathlib import Path
import pytest
import yaml
from jobhunt.profile import load_candidate_profile, export_profile_for_typst

TYPST_AVAILABLE = shutil.which("typst") is not None


@pytest.mark.skipif(not TYPST_AVAILABLE, reason="typst CLI is not installed")
def test_typst_cv_compile_with_profile(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    cv_typ = root / "Base" / "cv.typ"
    profile = load_candidate_profile(root / "config" / "profile.example.yaml")
    profile_data = export_profile_for_typst(profile)

    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(yaml.safe_dump(profile_data), encoding="utf-8")

    cv_data = {
        "title": "Marketing Manager",
        "tagline": "Specialist in B2B growth",
        "profile": "Experienced marketer with a track record of driving revenue.",
        "max_pages": 1,
        "variant": "grotesk_one_page",
        "experience": [
            {
                "company": "Tech Corp",
                "role": "Marketing Lead",
                "dates": "2023 - Present",
                "location": "Amsterdam",
                "bullets": ["Led GTM for flagship platform."],
            }
        ],
    }
    cv_data_file = tmp_path / "cv-data.yaml"
    cv_data_file.write_text(yaml.safe_dump(cv_data), encoding="utf-8")

    out_pdf = tmp_path / "cv.pdf"
    cmd = [
        "typst",
        "compile",
        "--root",
        str(root),
        str(cv_typ),
        str(out_pdf),
        "--input",
        f"data={cv_data_file}",
        "--input",
        f"profile={profile_file}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Typst compile failed: {res.stderr}"
    assert out_pdf.exists()
```

- [ ] **Step 2: Update `Base/cv.typ` and `Base/letter.typ` to read profile facts dynamically**

In `Base/cv.typ`:
```typst
#let profile-path = sys.inputs.at("profile", default: "config/profile.yaml")
#let profile-data = if profile-path != none and profile-path != "" {
  // If provided path is relative or absolute, load yaml
  yaml(profile-path)
} else {
  (:)
}

#let NAME = profile-data.at("name", default: "Candidate Name")
#let CONTACT = profile-data.at("contact", default: (
  (label: "Email", value: "candidate@example.com"),
  (label: "Location", value: "Amsterdam, Netherlands"),
))
#let SKILLS = profile-data.at("skills", default: ())
#let LANGUAGES = profile-data.at("languages", default: ())
#let EDUCATION = profile-data.at("education", default: ())
#let CERTS = profile-data.at("certifications", default: ())
```

And similar in `Base/letter.typ` for candidate name, contact, and signature rendering.

- [ ] **Step 3: Run test to verify Typst compilation passes**

Run: `pytest tests/test_typst_compile.py -v`  
Expected: PASS

- [ ] **Step 4: Commit Task 2**

```bash
git add Base/ tests/test_typst_compile.py
git commit -m "feat: decouple Typst CV and letter templates with dynamic profile data"
```

---

### Task 3: Ollama AI Tailoring & Candidate Facts Dynamic Injection

**Files:**
- Modify: `jobhunt/dashboard.py`
- Modify: `jobhunt/cli.py`
- Test: `tests/test_draft_pack.py`

**Interfaces:**
- Consumes: `load_candidate_profile()` from `jobhunt/profile.py`.
- Produces: AI prompt generation dynamically injected with `profile.career_facts` and `profile.name`, removing all hardcoded `ANGELICA_FACTS`.

- [ ] **Step 1: Update `tests/test_draft_pack.py` to assert dynamic candidate facts in prompts**

Verify that `create_draft_pack` queries the profile loader and formats the prompt using the loaded profile's `career_facts`.

- [ ] **Step 2: Refactor `dashboard.py` and `cli.py` to remove `ANGELICA_FACTS`**

Replace static `ANGELICA_FACTS` with:
```python
def get_candidate_facts() -> str:
    prof = load_candidate_profile()
    return (
        f"{prof.name} is targeting roles in {prof.contact.location or 'their target area'}.\n"
        f"Use only these facts:\n{prof.career_facts}\n"
        f"Skills: {', '.join(prof.skills)}\n"
        "Do not invent any facts, employers, tools, degrees, languages, metrics, clients, or locations beyond this list."
    )
```

- [ ] **Step 3: Run test suite to verify draft pack tests pass**

Run: `pytest tests/test_draft_pack.py -v`  
Expected: PASS

- [ ] **Step 4: Commit Task 3**

```bash
git add jobhunt/dashboard.py jobhunt/cli.py tests/test_draft_pack.py
git commit -m "feat: inject dynamic candidate career facts into Ollama AI prompt"
```

---

### Task 4: Scraper Fleet Removal & Single-Job Extractor Isolation

**Files:**
- Delete: `jobhunt/adapters.py`
- Delete: `jobhunt/ats.py`
- Delete: `jobhunt/scrape.py`
- Delete: `jobhunt/company_candidates.py`
- Delete: `jobhunt/company_sources.py`
- Delete: `jobhunt/applypilot_import.py`
- Modify: `jobhunt/job_scrape.py` (make fully standalone for single URL parsing)
- Delete obsolete tests: `tests/test_dedicated_adapters.py`, `tests/test_applypilot_import.py`, `tests/test_cli_import_applypilot.py`, `tests/test_company_candidates.py`, `tests/test_scrape_mapping.py`, `tests/test_scraper_health.py`
- Test: `tests/test_job_scrape.py`

**Interfaces:**
- Consumes: Single job URL string.
- Produces: `ListingExtract(title, company, location, description)` without calling any fleet scraper modules.

- [ ] **Step 1: Refactor `jobhunt/job_scrape.py` to be self-contained**

Move lightweight HTML stripping / JSON-LD helper into `job_scrape.py` directly, removing imports of `jobhunt.ats` and `jobhunt.scrape`.

- [ ] **Step 2: Delete scraper fleet modules and obsolete scraper tests**

Remove:
```bash
rm jobhunt/adapters.py jobhunt/ats.py jobhunt/scrape.py jobhunt/company_candidates.py jobhunt/company_sources.py jobhunt/applypilot_import.py config/companies.yaml
rm tests/test_dedicated_adapters.py tests/test_applypilot_import.py tests/test_cli_import_applypilot.py tests/test_company_candidates.py tests/test_scrape_mapping.py tests/test_scraper_health.py
```

- [ ] **Step 3: Run `tests/test_job_scrape.py`**

Run: `pytest tests/test_job_scrape.py -v`  
Expected: PASS

- [ ] **Step 4: Commit Task 4**

```bash
git add -u
git add jobhunt/job_scrape.py tests/test_job_scrape.py
git commit -m "refactor: remove scraper fleet and isolate single-job URL extractor"
```

---

### Task 5: CLI & Core Clean-up

**Files:**
- Modify: `jobhunt/cli.py`
- Modify: `jobhunt/models.py`
- Modify: `jobhunt/database.py`
- Modify: `jobhunt/assessment.py` / `jobhunt/filters.py`
- Delete: `batch1.py`, `batch2.py`, `batch3.py`, `batch4.py`, `daily-jobhunt*.sh`

**Interfaces:**
- Consumes: CLI commands `dashboard`, `validate`, `tailor-drafts`, `scrape-listing`.
- Produces: Clean CLI and database schema without discovery/scraper tables.

- [ ] **Step 1: Clean up `jobhunt/cli.py`**

Remove arguments and subcommands: `sweep`, `audit`, `discover-sites`, `resolve-candidate-urls`, `import-applypilot`. Keep `dashboard`, `validate`, `tailor-drafts`, `scrape-listing`.

- [ ] **Step 2: Clean up obsolete batch and shell scripts**

Remove `batch1.py`, `batch2.py`, `batch3.py`, `batch4.py`, `daily-jobhunt*.sh`.

- [ ] **Step 3: Run all remaining unit tests**

Run: `pytest -v`  
Expected: All tests pass.

- [ ] **Step 4: Commit Task 5**

```bash
git add -u
git commit -m "cleanup: remove scraper CLI commands and obsolete batch scripts"
```

---

### Task 6: Private Data & Database Scrubbing

**Files:**
- Delete: `Applications/*`
- Delete: `Reference/*`
- Delete: `data/*.sqlite`, `data/*.csv`, `data/*.md`, `data/company-source-packs/`
- Modify: `.gitignore` (ensure `data/jobs.sqlite`, `Applications/*`, `config/profile.yaml` are ignored or kept clean)

- [ ] **Step 1: Remove private applicant data and database artifacts**

```bash
rm -rf Applications/* Reference/* data/*.sqlite data/*.csv data/*.md data/company-source-packs data/html data/*.py
mkdir -p Applications data
touch Applications/.gitkeep data/.gitkeep
```

- [ ] **Step 2: Update `.gitignore`**

Ensure `config/profile.yaml` and `data/jobs.sqlite` and `Applications/**/cv.pdf` are ignored, while `config/profile.example.yaml` is tracked.

- [ ] **Step 3: Commit Task 6**

```bash
git add -u
git add Applications/.gitkeep data/.gitkeep .gitignore
git commit -m "chore: scrub private application data, databases, and history"
```

---

### Task 7: Dockerfile, Docker Compose & Documentation

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `CLAUDE.md` / `AGENTS.md`

- [ ] **Step 1: Simplify `Dockerfile`**

Remove Playwright, Google Chrome, Xvfb, and unnecessary GUI libraries. Keep Python 3.11, Typst, and lightweight runtime dependencies.

- [ ] **Step 2: Update `docker-compose.yml`**

Provide clean port mapping (`8765`), volume mounts (`./config`, `./data`, `./Applications`), and environment variable defaults.

- [ ] **Step 3: Write comprehensive `README.md`**

Include:
- Features overview (Kanban tracker, probabilistic goals calculator, AI CV tailoring, Typst PDF generator).
- Quickstart with Docker Compose (`cp config/profile.example.yaml config/profile.yaml && docker compose up -d`).
- Ollama configuration instructions.
- Typst CV variant customization guide.

- [ ] **Step 4: Update `AGENTS.md` and `CLAUDE.md` to reflect new architecture**

Sync instructions for future coding agents.

- [ ] **Step 5: Commit Task 7**

```bash
git add Dockerfile docker-compose.yml README.md CLAUDE.md AGENTS.md
git commit -m "docs: add Docker compose setup and open source README"
```

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Run complete unit test suite**

Run: `pytest -v`  
Expected: 100% tests passing.

- [ ] **Step 2: Test CLI startup and database initialization**

Run: `python -m jobhunt validate`  
Expected: Validates config, profile, and database schema cleanly.

- [ ] **Step 3: Final sanity commit and tag**

```bash
git status
```
