# CLAUDE.md — Agent & Collaborator Guidelines

Guidance for coding agents (Codex, Claude Code, Cursor, Copilot, Antigravity, Aider, etc.) working in this repository.
**This file mirrors [AGENTS.md](AGENTS.md)** — keep the two in sync when either changes.

---

## 🤝 Collaborative Agent Rules

When contributing to JobArcade, agents must follow these guidelines:

1. **Privacy & Candidate Decoupling (Strict)**:
   - Never commit candidate-specific names, emails, phone numbers, or private work histories in code, tests, or Typst templates.
   - All personal data must be loaded dynamically from `config/profile.yaml` via `jobhunt.profile.load_candidate_profile()`.
   - Never stage or commit `config/profile.yaml`, `data/*.sqlite`, `data/*.csv`, or `.env`.

2. **Verification Before Assertions**:
   - Always run verification before declaring work done or submitting a PR:
     ```bash
     python -m jobhunt validate
     pytest -v
     ```
   - Evidence before assertions always: do not claim tests pass without running them and checking output.

3. **Git Hygiene**:
   - Work on feature branches: `feat/<feature>`, `fix/<bug>`, `docs/<topic>`.
   - Use conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
   - Keep commits atomic and focused.

4. **Template & Engine Restraint**:
   - Keep dependencies lean. Do not add headless browser automation frameworks (Playwright/Selenium) or heavy scraping fleets.
   - Respect Typst compile guard-rails (page budgets and character budgets).

---

## Purpose

**JobArcade** is a standalone, local-first workspace for managing job applications, tailoring CVs and motivation letters using Ollama LLMs, and compiling pixel-perfect PDFs with Typst.

The workflow is:
1. Maintain candidate profile and verified career facts in `config/profile.yaml` (starter at `config/profile.example.yaml`).
2. Capture jobs via URL scraper, manual entry, or API in the web dashboard.
3. For each matching role, tailor a CV and motivation letter from the **Typst** templates in `Base/` using zero-hallucination Ollama AI prompts or manual editing.
4. Compile PDFs with Typst into `Applications/<Company>-<Role-Slug>/`.

## Candidate Profile & Facts

Candidate information is decoupled from the codebase:
- Profile configuration lives in `config/profile.yaml` (loaded via `jobhunt.profile.load_candidate_profile()`).
- If `config/profile.yaml` is absent, it falls back to `config/profile.example.yaml`.
- Ground-truth career facts live in `profile.career_facts` and are injected dynamically into AI tailoring prompts.
- Typst templates consume profile facts dynamically via `--input profile=<path>` or default `config/profile.yaml`.

## Directory Structure

```
Base/                        # Parameterized Typst templates — see Base/README.md
  lib.typ cv.typ letter.typ  # Layout components + guard-rails + dynamic profile ingestion
  reference/                 # Sample reference YAML data
Applications/                # Application workspaces (git-ignored)
  <Company>-<Role-Slug>/     # One folder per application
    job-listing.md           # Copy of the original job posting
    cv-data.yaml             # Tailored CV content for this role
    letter-data.yaml         # Tailored motivation letter content
    cv.pdf                   # Compiled output
    motivation-letter.pdf    # Compiled output
config/
  profile.example.yaml       # Starter profile template
  profile.yaml               # Active candidate profile (git-ignored)
dashboard/                   # Web dashboard frontend (HTML/JS/CSS)
data/                        # SQLite database & runtime data (git-ignored)
jobhunt/                     # Python backend & CLI
```

## CLI Commands

1. `python -m jobhunt validate` — check config, profile schema, and database connectivity.
2. `python -m jobhunt dashboard [--host 0.0.0.0] [--port 8765]` — launch the web dashboard and REST API.
3. `python -m jobhunt scrape-listing "<URL>"` — extract role details from a job listing URL.
4. `python -m jobhunt tailor-drafts` — run batch AI tailoring on draft applications.
5. `python -m jobhunt build --company <Company> --role <Role>` — compile Typst PDFs from CLI.

## CV & Letter Tailoring (Typst)

The CV and letter are compiled from parameterized Typst templates in `Base/`. An agent or user edits **only plain text** in two per-role YAML files (`cv-data.yaml` and `letter-data.yaml`). Layout, fonts, margins, spacing, contact/education/skills are rendered from the candidate profile and template layout.

**Per-role steps:**
1. Create `Applications/<Company>-<Role-Slug>/`.
2. Generate or edit `cv-data.yaml` + `letter-data.yaml` (or use the Dashboard CV Builder / Ollama tailoring).
3. Compile with Typst:
   ```bash
   typst compile --root . Base/cv.typ Applications/<Company>-<Role-Slug>/cv.pdf --input data=Applications/<Company>-<Role-Slug>/cv-data.yaml --input profile=config/profile.yaml
   typst compile --root . Base/letter.typ Applications/<Company>-<Role-Slug>/motivation-letter.pdf --input data=Applications/<Company>-<Role-Slug>/letter-data.yaml --input profile=config/profile.yaml
   ```
4. If compilation fails, check guard-rail assertions (character budget, max bullets, page limit) and adjust content.

**CV Variants**:
- `grotesk_one_page` *(default)* — Compact single-page layout with Summary, Experience, Education, Skills, Languages, and Certifications.
- `compact_one_page` — Dense single-page layout with structured sidebar.
- `classic_two_page` — Traditional two-page layout for comprehensive backgrounds.
- `enriched_two_page` — Two-page layout featuring expanded impact achievements.

**Guard-rails** (in `lib.typ` / `cv.typ`, enforced at compile time):
- ≤5 bullets per role, ≤~165 chars per bullet.
- Selected highlights ≤4 and ≤~135 chars each.
- Profile summary ≤600 chars, tagline ≤170 chars.
- Letter: 3–5 paragraphs, ≤~2050 chars total.
- Hard page budget: `grotesk_one_page` / `compact_one_page` = 1 page; two-page variants = 2 pages; letter = 1 page.
