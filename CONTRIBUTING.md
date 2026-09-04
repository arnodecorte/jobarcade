# Contributing to JobArcade

Welcome! Whether you are a human developer or an AI coding agent (Claude Code, Cursor, Copilot, Codex, Aider, Windsurf, etc.), these guidelines ensure our collaboration stays smooth, fast, and high-quality.

---

## 🎯 Core Principles

1. **Strict Candidate Decoupling (Privacy First)**:
   - Never commit candidate-specific names, emails, phone numbers, or private career history to code or Typst templates.
   - All candidate facts live in `config/profile.yaml` (which is git-ignored) and are dynamically injected via `jobhunt.profile`.
   - Never commit `data/*.sqlite`, `data/*.csv`, or `.env`.

2. **Verification Before Assertion**:
   - Run verification commands before committing or opening a PR:
     ```bash
     python -m jobhunt validate
     pytest -v
     ```
   - Confirm all tests pass with zero errors. Evidence before assertions always.

3. **Lean Footprint**:
   - Do not reintroduce heavy browser dependencies (Playwright, Selenium, Chrome) or external crawler fleets.
   - Keep Typst compilation sub-second and vector-clean.

---

## 🌿 Branching & Git Etiquette

- **Branch Naming**:
  - `feat/<feature-name>` for new capabilities (e.g. `feat/gemini-tailoring-adapter`).
  - `fix/<bug-name>` for fixes (e.g. `fix/typst-margin-overflow`).
  - `docs/<topic>` for documentation improvements.
- **Conventional Commits**:
  - Format: `<type>(<scope>): <short summary>`
  - Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.
  - Example: `feat(ai): add streaming response support for Ollama drafts`
- **Avoid Monolithic Diffs**:
  - Keep commits focused and atomic.

---

## 🛠️ Local Development Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install package in editable mode with dev dependencies
pip install -e . pytest

# 3. Setup candidate profile
cp config/profile.example.yaml config/profile.yaml

# 4. Verify environment
python -m jobhunt validate
pytest -v
```

---

## 🤖 For AI Coding Agents

If you are an AI assistant:
- Review [`AGENTS.md`](AGENTS.md) or [`CLAUDE.md`](CLAUDE.md) for architectural constraints and template guard-rails.
- Use the pull request template in `.github/pull_request_template.md` when proposing changes.
