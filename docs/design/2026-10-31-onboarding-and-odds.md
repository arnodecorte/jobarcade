# Onboarding flow and odds model

Design note for the public-release onboarding work. Contains no personal data.

## Setup flow

First launch shows a guided flow (`jobhunt/onboarding.py`, `ONBOARDING_STEPS`):

1. `welcome` - orientation, with a Skip option that keeps existing data.
2. `ai` - Ollama base URL, model and optional cloud API key; a test call
   returns `{"ok": false, "error": ...}` on failure and saving still works.
3. `profile` - writes `config/profile.yaml` (git-ignored). A malformed file
   yields a readable error rather than a 500, and is never overwritten blindly.
4. `style` - default accent written to `config/default-theme.yaml`
   (git-ignored). Low-contrast accents are rejected with a message.
5. `chameleon` - optional Firecrawl key for brand extraction.
6. `goal` - daily application goal.

Upgrading installs that stored goal/prior in `localStorage` have them migrated
to the server once.

## Settings keys

Stored in the `integration_settings` table (secrets encrypted with the vault key):

| Key | Purpose |
| :-- | :-- |
| `onboarding_status` / `onboarding_step` | `pending`, `complete` or `skipped`; current step |
| `ollama_base_url`, `ollama_model`, `ollama_api_key` | AI connection |
| `firecrawl_api_key` | Chameleon extraction (optional) |
| `daily_goal`, `last_celebrated_date` | Goal and celebration state |
| `odds_prior`, `odds_cadence` | Odds model inputs |
| `feature_scraper` | Scraper toggle (`1` = on) |

Environment overrides: `JOBHUNT_OLLAMA_URL`, `JOBHUNT_OLLAMA_MODEL`,
`JOBHUNT_OLLAMA_API_KEY`, `FIRECRAWL_API_KEY`, `JOBHUNT_ENABLE_SCRAPER`.

## Odds model

Chance of at least one interview after N applications: `1 - (1 - p)^N`.
`p` defaults to a 3% prior (slider 0.5%-8%) and is blended toward the user's
own matured data. Sources (`PRIOR_SOURCES` in `dashboard/web/src/lib/odds.ts`):

- CareerPlug 2024 Recruiting Metrics: about 3% of applicants reach an interview.
  https://www.careerplug.com/recruiting-metrics-and-kpis/
- Huntr 2025 Annual Job Search Trends: about 3.5% average, 2.7% (Jan) to 4.2% (Nov).
  https://huntr.co/research/2025-annual-job-search-trends-report

Celebrations show odds before/after a batch of applications and days saved on
the ETA at the current cadence. Copy stays encouraging; missing a goal is never
framed as failure.

## Scraper flag

URL scraping and discovery are experimental and hidden unless
`JOBHUNT_ENABLE_SCRAPER=1` or the `feature_scraper` setting is on. The
`scrape-listing` CLI command is deprecated. Manual entry is the primary path.
