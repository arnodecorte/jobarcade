# 🕹️ JobArcade

> **Turnkey, local-first job application tracker and AI-powered CV & cover letter tailoring studio.**

JobArcade gives you a fast, deterministic, private workspace to manage your job application pipeline, tailor role-specific CVs and motivation letters with **zero hallucination** using local LLMs (Ollama), and compile pixel-perfect vector PDFs in milliseconds with **Typst**.

---

## ✨ Features

### 📋 Kanban Pipeline & Motivation Tracker
- **Visual Funnel**: Track opportunities across `New`, `Drafting`, `Ready`, `Applied`, `Interviewing`, `Offer`, and `Rejected`.
- **Activity & Streaks**: Keep momentum with daily submission tracking and milestone cadence counters.
- **Audit Trails & Rejection Forensics**: Log status changes, interview notes, and feedback to spot pipeline trends.

### 🎲 Probabilistic Pipeline Odds & Analytics
- **Monte Carlo & Binomial Forecasting**: Calculates real-time odds of landing at least one interview and offer based on your active pipeline volume and conversion rates.
- **Velocity Targets**: Computes the weekly application pace needed to reach your target timeline.

### 🤖 Zero-Hallucination AI Tailoring (Ollama)
- **Strictly Grounded Prompts**: Automatically tailors CV experience bullets and motivation letters strictly from your verified facts in `config/profile.yaml`.
- **Zero Invention Guarantee**: Constrained prompt engineering prevents LLMs from inventing employers, metrics, credentials, or technologies.
- **Pluggable Models**: Works out-of-the-box with `qwen2.5:7b`, `qwen3:8b`, `llama3.1:8b`, `mistral`, or any Ollama model.

### 📄 Typst PDF Typesetting Engine
- **Sub-Second Compilation**: Fast, ATS-optimized vector PDF generation using [Typst](https://typst.app/).
- **4 Built-In Layout Variants**:
  - `grotesk_one_page` *(default)*: Ultra-clean modern single-page format.
  - `compact_one_page`: High-density single-page layout with structured sidebar.
  - `classic_two_page`: Traditional multi-column two-page layout.
  - `enriched_two_page`: Expanded two-page format showcasing key project impact.
- **Compile-Time Guard Rails**: Enforces character budgets, bullet limits, and page boundaries at build time.

### 🔗 Single-Job URL Scraper & Manual Entry
- **Instant Extraction**: Scrapes title, company, location, and description from any job posting URL using JSON-LD, OpenGraph heuristics, or optional Firecrawl fallback.
- **Manual Input**: Paste descriptions and edit metadata directly in the browser.

### 🔒 100% Local & Private
- **Zero Cloud Lock-in**: All application data, candidate facts, and generated PDFs live locally on your filesystem and SQLite database (`data/jobs.sqlite`).
- **Encrypted Local Vault**: Optional integrations (e.g. Gmail status tracker) use encrypted local Fernet keys.

---

## 🚀 Quickstart (Docker Compose)

The easiest way to run JobArcade is with Docker Compose.

### 1. Clone Repository & Setup Profile
```bash
git clone https://github.com/arnodecorte/jobarcade.git
cd jobarcade

# Copy and edit your candidate profile
cp config/profile.example.yaml config/profile.yaml
```

### 2. Configure Environment (Optional)
Create a `.env` file if you want to customize your Ollama host or model:
```bash
# .env
JOBHUNT_OLLAMA_URL=http://host.docker.internal:11434
JOBHUNT_OLLAMA_MODEL=qwen2.5:7b
FIRECRAWL_API_KEY=  # Optional: for brand color extraction & complex web scrapes
```

### 3. Start the Container
```bash
docker compose up -d
```

### 4. Open the Arcade
Navigate to **[http://localhost:8765](http://localhost:8765)** in your browser.

---

## 🛠️ Local Development (Without Docker)

### Prerequisites
- **Python 3.11+**
- **Typst CLI** (`v0.11+`): `brew install typst` (macOS) or `cargo install --locked typst-cli` / binary download.
- **Ollama**: Running locally or on your network with a model pulled (e.g. `ollama pull qwen2.5:7b`).

### Setup
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies in editable mode
pip install -e .

# 3. Create your profile
cp config/profile.example.yaml config/profile.yaml

# 4. Validate setup
python -m jobhunt validate

# 5. Start web dashboard
python -m jobhunt dashboard --host 127.0.0.1 --port 8765
```

---

## 🧠 How the AI Tailoring Architecture Works

JobArcade separates candidate truth from document formatting:

```
config/profile.yaml ───┐
                       ├──► jobhunt/dashboard.py (Ollama Prompt Injection)
Job Listing Text ──────┘             │
                                     ▼
                      Applications/<Company-Role>/
                       ├── cv-data.yaml
                       ├── letter-data.yaml
                                     │
                                     ▼
Base/cv.typ + Base/letter.typ ───────┴──► Typst Compiler ──► cv.pdf & motivation-letter.pdf
```

1. **Candidate Facts Ingestion**: Your verified experience statements in `config/profile.yaml` are loaded into `jobhunt/profile.py`.
2. **Zero-Hallucination Prompting**: When generating a draft for a role, JobArcade sends a structured prompt to Ollama injecting your candidate facts and the target job description. The model selects and emphasizes relevant proof points without inventing new facts.
3. **Structured YAML Output**: Ollama outputs role-specific `cv-data.yaml` and `letter-data.yaml` files inside `Applications/<Company>-<Role-Slug>/`.
4. **Typst Rendering**: Typst compiles the YAML data against the templates in `Base/` to produce the final vector PDFs.

---

## 📁 Directory Structure

```
jobarcade/
├── Base/                     # Parameterized Typst templates
│   ├── cv.typ                # CV layout & page structure
│   ├── letter.typ            # Motivation letter layout
│   ├── lib.typ               # Design tokens, fonts, colors & guard-rails
│   └── reference/            # Generic reference YAML examples
├── config/
│   ├── profile.example.yaml  # Starter profile template
│   └── profile.yaml          # Active candidate profile (git-ignored)
├── dashboard/                # Web dashboard frontend (HTML5/CSS/JS)
│   ├── static/               # Production assets, icons & layouts
│   └── web/                  # React/Vite source components
├── data/                     # Local SQLite database & exports (git-ignored)
├── jobhunt/                  # Python backend & CLI engine
│   ├── dashboard.py          # HTTP server, API endpoints & Ollama orchestration
│   ├── profile.py            # Profile schema loader & Typst exporter
│   ├── job_scrape.py         # Single-job URL parser (JSON-LD / OpenGraph)
│   ├── assessment.py         # Job scoring & fit heuristics
│   └── database.py           # SQLite persistence layer
├── tests/                    # Comprehensive Pytest test suite
├── Dockerfile                # Lean Python + Typst container
├── docker-compose.yml        # Turnkey container orchestrator
└── README.md
```

---

## ⌨️ CLI Commands

JobArcade includes a command-line interface:

- `python -m jobhunt validate` — Verify profile configuration, SQLite schema, and Typst compiler.
- `python -m jobhunt dashboard` — Launch the web dashboard server.
- `python -m jobhunt scrape-listing "<URL>"` — Extract role details from a job listing URL into JSON.
- `python -m jobhunt tailor-drafts` — Run batch AI tailoring across unbuilt applications.
- `python -m jobhunt build --company <Company> --role <Role>` — Manually compile Typst PDFs from CLI.

---

## 🤝 Contributing & Customization

Feel free to fork this repository, adapt the Typst templates in `Base/` to match your personal style, or connect other LLM backends (OpenAI / Claude / vLLM) in `jobhunt/dashboard.py`.
