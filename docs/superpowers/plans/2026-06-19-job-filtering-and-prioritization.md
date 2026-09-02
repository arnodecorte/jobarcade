# Job Filtering and Prioritization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement regex-based filters for Dutch fluency and experience level, expand matching target keywords to include Sales/Account Management/Partnerships/Customer Success, and add a persistent `priority` column to the SQLite database and CSV/Markdown exports based on team/learning keywords.

**Architecture:** 
1. Expand keywords in `jobhunt/config.py`.
2. Add language, experience, and priority functions to `jobhunt/filters.py` and modify `job_ok()` to apply them.
3. Update `Job` model dataclass to store the `priority` string.
4. Update `jobhunt/database.py` with automatic schema migrations for `priority` and updates to insert/update queries.
5. Update `jobhunt/export.py` to write the priority column in exports.

**Tech Stack:** Python 3.11, SQLite, pytest.

---

### Task 1: Expand Target Keywords (`jobhunt/config.py`)

**Files:**
- Modify: [config.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/config.py)
- Test: [test_filters.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_filters.py)

- [ ] **Step 1: Write tests for title expansion**
  Open [test_filters.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_filters.py) and add test cases to `test_title_filter` parameters verifying the new roles match.
  ```python
  # Add to test_title_filter parameterized list:
  ("Account Manager", True),
  ("Partnership Coordinator", True),
  ("Customer Success Specialist", True),
  ("Business Development Executive", True),
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_filters.py -v`
  Expected: Failures on the new parameterized test cases (e.g. Account Manager returning False).

- [ ] **Step 3: Modify config.py to add target keywords**
  Open [config.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/config.py) and update `TARGET_TITLE_KEYWORDS`:
  ```python
  TARGET_TITLE_KEYWORDS = (
      "marketing",
      "campaign",
      "content",
      "brand",
      "crm",
      "social media",
      "communications",
      "communication",
      "digital marketing",
      "marketing operations",
      "community",
      "copywriter",
      "sales",
      "account manager",
      "account management",
      "customer success",
      "client success",
      "partnership",
      "partnerships",
      "business development",
      "growth",
  )
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_filters.py -v`
  Expected: PASS

- [ ] **Step 5: Commit changes**
  Run:
  ```bash
  git add jobhunt/config.py tests/test_filters.py
  git commit -m "feat: expand target title keywords to Sales, Account Management, Partnerships, and Customer Success"
  ```

---

### Task 2: Implement Language, Experience, and Priority Filters (`jobhunt/filters.py`)

**Files:**
- Modify: [filters.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/filters.py)
- Modify: [models.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/models.py)
- Test: [test_filters.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_filters.py)

- [ ] **Step 1: Update Job Model**
  Open [models.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/models.py) and update the `Job` class by adding the `priority` attribute at the end:
  ```python
  @dataclass(slots=True)
  class Job:
      # ... existing fields ...
      scraper_type: str | None = None
      status: str = "new"
      priority: str = "Low"
  ```

- [ ] **Step 2: Write tests for language, experience, and priority**
  Open [test_filters.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_filters.py) and append the following tests:
  ```python
  from jobhunt.models import Job
  from jobhunt.filters import job_ok

  def test_dutch_language_filter():
      # Fluent Dutch required should fail
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="Vloeiend Nederlands vereist", location="Amsterdam")) is False
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="Dutch fluency is a must", location="Amsterdam")) is False
      assert job_ok(Job("PepsiCo", "Marketing Manager", title="Marketing Specialist (Nederlands vereist)", description="Details...", location="Amsterdam")) is False
      
      # Dutch / English bilingual or Dutch is a plus should pass
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="Bilingual Dutch / English. Dutch is a plus.", location="Amsterdam")) is True
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="This role is in English. Speaking Dutch is a pre.", location="Amsterdam")) is True

  def test_experience_filter():
      # 5+ years should fail
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="Requires 5+ years of experience", location="Amsterdam")) is False
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="Minimum 5-8 years of experience in content.", location="Amsterdam")) is False
      
      # Under 5 years or unspecified should pass
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="Requires 2-4 years of experience", location="Amsterdam")) is True
      assert job_ok(Job("PepsiCo", "Marketing Manager", description="No experience limits specified.", location="Amsterdam")) is True

  def test_priority_calculation():
      # High: both team & learning
      job_high = Job("PepsiCo", "Marketing Manager", description="Work in a collaborative team and learn new skills with professional mentorship.", location="Amsterdam")
      assert job_ok(job_high) is True
      assert job_high.priority == "⭐ High"

      # Medium: team only
      job_med = Job("PepsiCo", "Marketing Manager", description="Join our friendly team working together.", location="Amsterdam")
      assert job_ok(job_med) is True
      assert job_med.priority == "Medium"

      # Low: none
      job_low = Job("PepsiCo", "Marketing Manager", description="Manage social campaigns.", location="Amsterdam")
      assert job_ok(job_low) is True
      assert job_low.priority == "Low"
  ```

- [ ] **Step 3: Run tests to verify they fail**
  Run: `pytest tests/test_filters.py -v`
  Expected: Failures on `test_dutch_language_filter`, `test_experience_filter`, and `test_priority_calculation`.

- [ ] **Step 4: Implement filters and priority assignment in filters.py**
  Open [filters.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/filters.py) and update it:
  ```python
  from __future__ import annotations

  import re

  from jobhunt import config
  from jobhunt.models import Job

  DUTCH_REQUIRED_PATTERNS = [
      r"vloeiend nederlands",
      r"nederlands vereist",
      r"nederlands.*vereiste",
      r"nederlands als moedertaal",
      r"dutch fluency.*must",
      r"fluent in dutch.*must",
      r"must be fluent in dutch",
      r"native dutch",
      r"vloeiende beheersing van.*nederlandse",
  ]

  TEAM_KEYWORDS = ("team", "collaborate", "collaboration", "collaborative", "cross-functional", "peer", "together")
  LEARNING_KEYWORDS = ("learn", "training", "growth", "mentor", "mentorship", "development", "coach", "coaching", "upskill")


  def _clean(value: str | None) -> str:
      return re.sub(r"\s+", " ", value or "").strip().lower()


  def title_ok(title: str | None) -> bool:
      text = _clean(title)
      if not text:
          return False
      if len(text.split()) < 2 and "copywriter" not in text:
          return False
      if re.search(r"\b[a-z0-9]+-[a-z0-9]+-[a-z0-9]+", text):
          return False
      if any(word in text for word in config.EXCLUDED_TITLE_KEYWORDS):
          return False
      has_target = any(word in text for word in config.TARGET_TITLE_KEYWORDS)
      has_role = any(word in text for word in config.ROLE_TITLE_KEYWORDS)
      return has_target and has_role


  def location_ok(location: str | None, remote_type: str | None = None) -> bool:
      loc = _clean(location)
      remote = _clean(remote_type)
      if not loc:
          return bool(remote) and any(accepted in remote for accepted in config.ACCEPT_LOCATIONS)
      if any(token in loc for token in config.REMOTE_TOKENS):
          return any(accepted in loc for accepted in config.ACCEPT_LOCATIONS)
      if any(token in remote for token in config.REMOTE_TOKENS):
          return True
      return any(accepted in loc for accepted in config.ACCEPT_LOCATIONS)


  def language_ok(text: str) -> bool:
      for pattern in DUTCH_REQUIRED_PATTERNS:
          if re.search(pattern, text, re.I):
              return False
      return True


  def experience_ok(text: str) -> bool:
      # Find ranges first like "5-8 years", "5 to 8 years", "5 tot 8 jaar"
      ranges = re.findall(r"\b(\d+)\s*(?:-|to|tot)\s*(\d+)\s*(?:years?|yrs?|jaar|jr)\b", text, re.I)
      for start, end in ranges:
          if int(start) >= 5:
              return False

      # Remove range text so we don't double-match single numbers in "3-5 years"
      cleaned = re.sub(r"\b(\d+)\s*(?:-|to|tot)\s*(\d+)\s*(?:years?|yrs?|jaar|jr)\b", "", text, flags=re.I)

      # Check single numbers with optional plus (e.g. "5+ years", "at least 5 years")
      singles = re.findall(r"\b(\d+)\+?\s*(?:years?|yrs?|jaar|jr)\b", cleaned, re.I)
      for num in singles:
          if int(num) >= 5:
              return False
      return True


  def calculate_priority(text: str) -> str:
      text_lower = text.lower()
      has_team = any(word in text_lower for word in TEAM_KEYWORDS)
      has_learning = any(word in text_lower for word in LEARNING_KEYWORDS)
      if has_team and has_learning:
          return "⭐ High"
      if has_team or has_learning:
          return "Medium"
      return "Low"


  def job_ok(job: Job) -> bool:
      location_parts = [part for part in (job.location, job.country) if part]
      location = ", ".join(location_parts) or None
      if not (title_ok(job.title) and location_ok(location, job.remote_type)):
          return False

      # Combine title, description, and requirements to scan for language and experience
      full_text = " ".join(part for part in (job.title, job.description, job.requirements) if part)
      if not language_ok(full_text):
          return False
      if not experience_ok(full_text):
          return False

      # Set priority on the job object dynamically
      job.priority = calculate_priority(full_text)
      return True
  ```

- [ ] **Step 5: Run tests to verify they pass**
  Run: `pytest tests/test_filters.py -v`
  Expected: PASS

- [ ] **Step 6: Commit changes**
  Run:
  ```bash
  git add jobhunt/filters.py jobhunt/models.py tests/test_filters.py
  git commit -m "feat: implement Dutch fluency, experience filters, and team/learning priority classification"
  ```

---

### Task 3: Implement Database Migration & Priority Persistence (`jobhunt/database.py`)

**Files:**
- Modify: [database.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/database.py)
- Test: [test_database.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_database.py)

- [ ] **Step 1: Write test for schema migration and column insertion**
  Open [test_database.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_database.py) and add tests for migrating priority and saving it:
  ```python
  def test_init_db_adds_priority_column_if_missing(tmp_path):
      db_file = tmp_path / "jobs.sqlite"
      
      # 1. Create a legacy database without the priority column
      import sqlite3
      conn = sqlite3.connect(db_file)
      conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, company TEXT NOT NULL, title TEXT NOT NULL, discovered_at TEXT, last_seen_at TEXT, status TEXT DEFAULT 'new', dedupe_key TEXT UNIQUE)")
      conn.commit()
      conn.close()
      
      # 2. Run init_db which should execute the migration
      from jobhunt.database import init_db
      conn = init_db(db_file)
      
      # 3. Check if priority column exists and has default value 'Low'
      cursor = conn.execute("PRAGMA table_info(jobs)")
      columns = [row["name"] for row in cursor.fetchall()]
      assert "priority" in columns
      
      # Clean up
      conn.close()

  def test_upsert_saves_and_updates_priority(tmp_path):
      conn = init_db(tmp_path / "jobs.sqlite")
      job = Job(company="Paramount", title="Content Coordinator", location="Amsterdam", apply_url="https://x/jobs/1", priority="⭐ High")
      
      upsert_jobs(conn, [job])
      row = conn.execute("SELECT priority FROM jobs WHERE apply_url = ?", (job.apply_url,)).fetchone()
      assert row["priority"] == "⭐ High"
      
      job.priority = "Medium"
      upsert_jobs(conn, [job])
      row = conn.execute("SELECT priority FROM jobs WHERE apply_url = ?", (job.apply_url,)).fetchone()
      assert row["priority"] == "Medium"
      
      conn.close()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_database.py -v`
  Expected: Failures due to `priority` not being defined/mapped, column missing, etc.

- [ ] **Step 3: Modify database.py to handle priority column**
  Open [database.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/database.py) and update:
  - Inside `init_db()`, check if `priority` column exists. If not, alter the table.
  - In `init_db()` SQL table creation, include `priority TEXT NOT NULL DEFAULT 'Low'`.
  - In `upsert_jobs()`, include `priority` in the `INSERT` and `UPDATE` statements.
  - In `fetch_export_rows()`, select `priority`.
  
  ```python
  # Modifying init_db():
  def init_db(conn: sqlite3.Connection | Path | str | None = None) -> sqlite3.Connection:
      if conn is None:
          conn = connect()
      elif not isinstance(conn, sqlite3.Connection):
          conn = connect(conn)
      conn.execute(
          """
          CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              company TEXT NOT NULL,
              title TEXT NOT NULL,
              location TEXT,
              country TEXT,
              remote_type TEXT,
              department TEXT,
              employment_type TEXT,
              date_posted TEXT,
              description TEXT,
              requirements TEXT,
              apply_url TEXT,
              source_url TEXT,
              source_platform TEXT,
              source_job_id TEXT,
              scraper_type TEXT,
              discovered_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              expired_at TEXT,
              status TEXT NOT NULL DEFAULT 'new',
              dedupe_key TEXT NOT NULL UNIQUE,
              miss_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              priority TEXT NOT NULL DEFAULT 'Low'
          )
          """
      )
      
      # Migration check for existing databases
      cursor = conn.execute("PRAGMA table_info(jobs)")
      columns = [row["name"] for row in cursor.fetchall()]
      if "priority" not in columns:
          conn.execute("ALTER TABLE jobs ADD COLUMN priority TEXT NOT NULL DEFAULT 'Low'")
          
      conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
      conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
      conn.commit()
      return conn
  ```
  
  And update `upsert_jobs()` insert & update queries:
  ```python
  # In UPDATE query inside upsert_jobs():
  UPDATE jobs
  SET last_seen_at = ?,
      expired_at = NULL,
      miss_count = 0,
      location = COALESCE(?, location),
      description = COALESCE(?, description),
      apply_url = COALESCE(?, apply_url),
      source_job_id = COALESCE(?, source_job_id),
      last_error = NULL,
      priority = ?
  WHERE id = ?
  # Bindings: (now, job.location, job.description, job.apply_url, job.source_job_id, job.priority, row["id"])

  # In INSERT query inside upsert_jobs():
  INSERT INTO jobs (
      company, title, location, country, remote_type, department, employment_type,
      date_posted, description, requirements, apply_url, source_url, source_platform,
      source_job_id, scraper_type, discovered_at, last_seen_at, expired_at, status,
      dedupe_key, miss_count, last_error, priority
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 0, NULL, ?)
  # Bindings: (..., job.priority)
  ```
  
  And `fetch_export_rows()`:
  ```python
  def fetch_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
      return conn.execute(
          """
          SELECT date(discovered_at) AS date, company, title AS role, location, apply_url AS url, status,
                 source_platform, source_job_id, date_posted, last_seen_at, priority
          FROM jobs
          WHERE title != '__scrape_failure__'
          ORDER BY discovered_at DESC, company ASC, title ASC
          """
      ).fetchall()
  ```

- [ ] **Step 4: Run database tests**
  Run: `pytest tests/test_database.py -v`
  Expected: PASS

- [ ] **Step 5: Run all test suites**
  Run: `pytest -v`
  Expected: ALL PASS

- [ ] **Step 6: Commit changes**
  Run:
  ```bash
  git add jobhunt/database.py tests/test_database.py
  git commit -m "feat: add priority column to jobs table, write migrations, and persist priority on upsert"
  ```

---

### Task 4: Implement Priority Field in CSV and Markdown Export (`jobhunt/export.py`)

**Files:**
- Modify: [export.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/export.py)
- Test: Write a small export test in a new file `tests/test_export.py` or within `test_database.py`.

- [ ] **Step 1: Write tests for export fields**
  Open [test_database.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/tests/test_database.py) and append:
  ```python
  from jobhunt.export import export_csv, export_markdown

  def test_export_includes_priority(tmp_path):
      conn = init_db(tmp_path / "jobs.sqlite")
      job = Job(company="Paramount", title="Content Coordinator", location="Amsterdam", apply_url="https://x/jobs/1", priority="⭐ High")
      upsert_jobs(conn, [job])
      
      csv_path = tmp_path / "jobs.csv"
      md_path = tmp_path / "careers-directory.md"
      
      export_csv(conn, csv_path)
      export_markdown(conn, md_path)
      
      # Check CSV contents
      csv_text = csv_path.read_text(encoding="utf-8")
      assert "priority" in csv_text
      assert "⭐ High" in csv_text
      
      # Check Markdown contents
      md_text = md_path.read_text(encoding="utf-8")
      assert "| date | company | role | location | url | status | priority |" in md_text
      assert "| 2026-06-19 | Paramount | Content Coordinator | Amsterdam | https://x/jobs/1 | new | ⭐ High |" in md_text or "Paramount" in md_text
      
      conn.close()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_database.py -v`
  Expected: Failure in `test_export_includes_priority`.

- [ ] **Step 3: Modify export.py to add priority column**
  Open [export.py](file:///c:/Users/junti/source/working-directories/Angelica-Job-Hunt/jobhunt/export.py) and update:
  - `fields` in `export_csv` to contain `"priority"`.
  - Headers list in `export_markdown` to include `priority` column and notes.
  
  ```python
  # Modifying export_csv:
  def export_csv(conn, path=CSV_PATH) -> int:
      rows = fetch_export_rows(conn)
      path.parent.mkdir(parents=True, exist_ok=True)
      fields = ["date", "company", "role", "location", "url", "status", "priority", "source_platform", "source_job_id", "date_posted", "last_seen_at"]
      with path.open("w", encoding="utf-8", newline="") as f:
          writer = csv.DictWriter(f, fieldnames=fields)
          writer.writeheader()
          for row in rows:
              writer.writerow({field: row[field] for field in fields})
      return len(rows)

  # Modifying export_markdown:
  def export_markdown(conn, path=DIRECTORY_PATH) -> int:
      rows = fetch_export_rows(conn)
      lines = [
          "# Careers Directory",
          "",
          "Human-readable export from `data/jobs.sqlite`. Run `python -m jobhunt export` to refresh.",
          "",
          "## Schema",
          "",
          "| Field | Notes |",
          "|---|---|",
          "| `date` | ISO date the role was first found (YYYY-MM-DD) |",
          "| `company` | Company name |",
          "| `role` | Job title as listed |",
          "| `location` | City / country |",
          "| `url` | Direct link to the posting |",
          "| `status` | `new` · `reviewed` · `tailoring` · `ready` · `applied` · `interviewing` · `skipped` · `expired` · `scrape_failed` |",
          "| `priority` | `⭐ High` · `Medium` · `Low` (team and learning fit level) |",
          "",
          "---",
          "",
          "## Log",
          "",
          "| date | company | role | location | url | status | priority |",
          "|---|---|---|---|---|---|---|",
      ]
      for row in rows:
          lines.append(
              "| {date} | {company} | {role} | {location} | {url} | {status} | {priority} |".format(
                  date=_escape_md(row["date"]),
                  company=_escape_md(row["company"]),
                  role=_escape_md(row["role"]),
                  location=_escape_md(row["location"]),
                  url=_escape_md(row["url"]),
                  status=_escape_md(row["status"]),
                  priority=_escape_md(row["priority"]),
              )
          )
      path.write_text("\n".join(lines) + "\n", encoding="utf-8")
      return len(rows)
  ```

- [ ] **Step 4: Run tests to verify they pass**
  Run: `pytest tests/test_database.py -v`
  Expected: PASS

- [ ] **Step 5: Run all project tests**
  Run: `pytest -v`
  Expected: ALL PASS

- [ ] **Step 6: Commit changes**
  Run:
  ```bash
  git add jobhunt/export.py tests/test_database.py
  git commit -m "feat: export priority column to jobs.csv and careers-directory.md"
  ```

---

### Verification and Regression Runs

- [ ] **Step 1: Run complete validation sweep**
  Run: `python -m jobhunt validate`
  Expected: Success output indicating no schema or configuration failures.
  
- [ ] **Step 2: Run a targeted smoke test**
  Run: `python -m jobhunt sweep --company "Paramount" --db data/company-smoke.sqlite --delay 0 --export`
  Expected: Success. Check that `data/company-smoke.sqlite` has a migrated schema with `priority` column, and exported `careers-directory.md` contains the `priority` column.
