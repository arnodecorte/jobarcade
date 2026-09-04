# GitHub Copilot Instructions for JobArcade

JobArcade is a local-first, privacy-focused job application tracker and AI-powered CV & cover letter tailoring studio.

## Core Rules for Copilot
- **Privacy & Grounding**: Never hardcode personal candidate details or career facts into code, tests, or Typst files. Ground-truth career facts live in `config/profile.yaml` and are parsed through `jobhunt.profile.load_candidate_profile()`.
- **Typst Formatting**: Maintain Typst template integrity in `Base/`. Enforce the character limits (≤165 chars per bullet, ≤600 chars summary, etc.) and page budgets (`grotesk_one_page` = 1 page).
- **Testing**: Whenever modifying backend logic or templates, write unit tests under `tests/` and ensure `pytest -v` and `python -m jobhunt validate` pass.
- **Dependencies**: Keep runtime and container footprints minimal. Do not introduce browser-automation frameworks (Playwright/Chrome).
