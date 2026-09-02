# Async Gmail Sync with Progress Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /api/gmail/sync` return immediately and run in a background thread that commits to the database after every message, and give the dashboard a live progress bar + log instead of one opaque multi-minute request.

**Architecture:** `jobhunt/gmail_integration.py` gets a module-level, lock-guarded `SyncProgress` object plus `start_gmail_sync()` (spawns a background thread, returns instantly) and `_run_sync()` (the actual loop, committing after each message instead of once at the end). `sync_gmail()` becomes a thin synchronous wrapper (starts the sync, joins the thread) so the CLI (`jobhunt/cli.py::cmd_gmail_sync`) keeps working unchanged. `dashboard.py` gets a new `GET /api/gmail/sync/progress` endpoint. The frontend polls that endpoint every 2s while a sync is running and renders a progress bar + scrolling log.

**Tech Stack:** Python 3.11 stdlib `threading`, SQLite (existing `jobhunt.database.connect`/`init_db`), React + TypeScript (Vite), existing `jobhunt/gmail_integration.py` Gmail/Ollama classification pipeline.

## Global Constraints

- In-memory progress state only — no new DB table, no durability across a
  dashboard restart (per approved design spec).
- A second sync request while one is running must be rejected
  (`already_running: true`), not queued.
- `jobhunt/cli.py::cmd_gmail_sync` must keep working via `sync_gmail(conn, ...)`
  with no changes to `cli.py` itself.
- No new frontend testing framework — this codebase has no component-test
  harness for React (only `dashboard/web/src/lib/odds.test.ts`, a plain
  logic unit test via vitest); verify the UI manually, don't introduce one.
- Follow existing code style: no comments explaining *what* code does, only
  non-obvious *why* (matches the rest of this file).

---

### Task 1: Async sync core in `jobhunt/gmail_integration.py`

**Files:**
- Modify: `jobhunt/gmail_integration.py:11` (imports), `jobhunt/gmail_integration.py:21` (imports), `jobhunt/gmail_integration.py:1028-1068` (replaces `sync_gmail`)
- Test: `tests/test_gmail_integration.py`

**Interfaces:**
- Produces: `gmail_sync_progress() -> dict` (keys: `running: bool`, `total: int`,
  `processed: int`, `current_subject: str | None`, `log: list[str]`,
  `error: str | None`, `result: dict | None`), `start_gmail_sync(conn,
  max_results: int = 50, after: str | None = None) -> dict` (returns
  `{"ok": True, "started": True}` or `{"ok": False, "already_running": True}`),
  `sync_gmail(conn, max_results: int = 50, after: str | None = None) -> dict`
  (unchanged signature/behavior for callers — blocks until done, returns the
  same `{"ok", "query", "seen", "saved", "classifications"}` summary or
  raises).
- Consumes (all already exist in this file, no changes): `load_gmail_config`,
  `decrypt_token`, `refresh_access_token`, `encrypt_token`, `GmailClient`,
  `gmail_query`, `parse_gmail_message`, `upsert_message_and_evidence`,
  `utc_now` (from `jobhunt.database`).

- [ ] **Step 1: Write the failing tests**

Open `tests/test_gmail_integration.py`. Update the import block at the top
(lines 1-24) to match exactly:

```python
from __future__ import annotations

from datetime import datetime, timezone
import base64
import threading
import time

import pytest

from jobhunt.database import connect, init_db, upsert_jobs
from jobhunt.gmail_integration import (
    Classification,
    GmailClient,
    OllamaConfig,
    apply_evidence,
    classify_email,
    classify_email_with_ollama,
    create_auth_url,
    decrypt_token,
    encrypt_token,
    generate_encryption_key,
    gmail_metrics,
    gmail_sync_progress,
    load_gmail_config,
    match_email_to_job,
    parse_gmail_message,
    reject_evidence,
    save_oauth_token,
    start_gmail_sync,
    sync_gmail,
    update_evidence,
    upsert_message_and_evidence,
)
from jobhunt.models import Job
```

Add these helpers and tests at the end of the file:

```python
def _setup_connected_account(conn, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GMAIL_REDIRECT_URI", "http://localhost:8765/api/gmail/oauth/callback")
    monkeypatch.setenv("GMAIL_TOKEN_ENCRYPTION_KEY", generate_encryption_key())
    config = load_gmail_config(conn)
    save_oauth_token(conn, {"refresh_token": "fake-refresh-token", "access_token": ""}, config)
    monkeypatch.setattr(
        "jobhunt.gmail_integration.refresh_access_token",
        lambda refresh_token, config: {"access_token": "fake-access-token"},
    )


def _fake_gmail_message(message_id: str, subject: str, body: str) -> dict:
    encoded = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "internalDate": "1751500800000",
        "snippet": body[:100],
        "payload": {
            "headers": [
                {"name": "From", "value": "careers@nike.com"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Wed, 1 Jul 2026 00:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        },
    }


def _wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    pytest.fail(f"Condition not met within {timeout}s")


def test_sync_commits_after_each_message_not_at_the_end(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    _setup_connected_account(conn, monkeypatch)

    release_second_message = threading.Event()
    calls: list[str] = []

    def fake_search(self, query, max_results=50):
        return ["msg-1", "msg-2"]

    def fake_message(self, message_id):
        calls.append(message_id)
        if message_id == "msg-2":
            release_second_message.wait(timeout=5)
        return _fake_gmail_message(
            message_id,
            "Nike application update",
            "Unfortunately, we will not be moving forward.",
        )

    monkeypatch.setattr(GmailClient, "search", fake_search)
    monkeypatch.setattr(GmailClient, "message", fake_message)

    start = start_gmail_sync(conn, max_results=50)
    assert start == {"ok": True, "started": True}

    _wait_until(lambda: gmail_sync_progress()["processed"] >= 1)

    # The sync thread is now paused inside client.message("msg-2"), holding no
    # SQL transaction at all -- message 1 must already be committed and
    # visible to, and writable around by, a brand-new connection. Before the
    # per-message commit fix, sync_gmail held one open transaction for the
    # whole run and this BEGIN IMMEDIATE would hang for busy_timeout (10s)
    # then raise "database is locked".
    other_conn = connect(tmp_path / "jobs.sqlite")
    row = other_conn.execute(
        "SELECT gmail_message_id FROM gmail_messages WHERE gmail_message_id = 'msg-1'"
    ).fetchone()
    assert row is not None
    other_conn.execute("BEGIN IMMEDIATE")
    other_conn.rollback()
    other_conn.close()

    release_second_message.set()
    _wait_until(lambda: gmail_sync_progress()["running"] is False)

    progress = gmail_sync_progress()
    assert progress["processed"] == 2
    assert progress["result"]["saved"] == 2
    assert progress["error"] is None
    assert calls == ["msg-1", "msg-2"]


def test_start_gmail_sync_rejects_concurrent_call(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    _setup_connected_account(conn, monkeypatch)

    release = threading.Event()

    def fake_search(self, query, max_results=50):
        return ["msg-1"]

    def fake_message(self, message_id):
        release.wait(timeout=5)
        return _fake_gmail_message(message_id, "Nike application update", "Thanks for applying.")

    monkeypatch.setattr(GmailClient, "search", fake_search)
    monkeypatch.setattr(GmailClient, "message", fake_message)

    first = start_gmail_sync(conn, max_results=50)
    assert first == {"ok": True, "started": True}

    _wait_until(lambda: gmail_sync_progress()["running"] is True)

    second = start_gmail_sync(conn, max_results=50)
    assert second == {"ok": False, "already_running": True}

    release.set()
    _wait_until(lambda: gmail_sync_progress()["running"] is False)


def test_sync_gmail_blocking_wrapper_returns_summary(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    _setup_connected_account(conn, monkeypatch)

    def fake_search(self, query, max_results=50):
        return ["msg-1"]

    def fake_message(self, message_id):
        return _fake_gmail_message(message_id, "Nike application update", "Thanks for applying.")

    monkeypatch.setattr(GmailClient, "search", fake_search)
    monkeypatch.setattr(GmailClient, "message", fake_message)

    result = sync_gmail(conn, max_results=50)

    assert result["ok"] is True
    assert result["seen"] == 1
    assert result["saved"] == 1
    assert "classifications" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gmail_integration.py -k "sync_commits_after_each_message or rejects_concurrent_call or sync_gmail_blocking_wrapper" -v`

Expected: FAIL/ERROR — `ImportError: cannot import name 'GmailClient'` (or
`'gmail_sync_progress'`/`'start_gmail_sync'`) since none of these are
importable from `jobhunt.gmail_integration` yet (`GmailClient` exists but
isn't currently exported by name in the test file's import list — the import
itself will fail as soon as any one name is missing).

- [ ] **Step 3: Update imports at the top of `jobhunt/gmail_integration.py`**

Change line 11 from:

```python
from dataclasses import dataclass
```

to:

```python
import threading
from dataclasses import dataclass, field
```

Change line 21 from:

```python
from jobhunt.database import utc_now
```

to:

```python
from jobhunt.database import connect, init_db, utc_now
```

- [ ] **Step 4: Replace `sync_gmail` with the async core**

Replace lines 1028-1068 (the entire current `sync_gmail` function) with:

```python
@dataclass
class SyncProgress:
    running: bool = False
    total: int = 0
    processed: int = 0
    current_subject: str | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None


_sync_progress = SyncProgress()
_sync_progress_lock = threading.Lock()
_sync_thread: threading.Thread | None = None


def gmail_sync_progress() -> dict:
    with _sync_progress_lock:
        return {
            "running": _sync_progress.running,
            "total": _sync_progress.total,
            "processed": _sync_progress.processed,
            "current_subject": _sync_progress.current_subject,
            "log": list(_sync_progress.log),
            "error": _sync_progress.error,
            "result": _sync_progress.result,
        }


def start_gmail_sync(conn, max_results: int = 50, after: str | None = None) -> dict:
    global _sync_thread
    with _sync_progress_lock:
        if _sync_progress.running:
            return {"ok": False, "already_running": True}
        account = conn.execute(
            "SELECT * FROM gmail_accounts ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if not account:
            raise ValueError("Gmail is not connected.")
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        _sync_progress.running = True
        _sync_progress.total = 0
        _sync_progress.processed = 0
        _sync_progress.current_subject = None
        _sync_progress.log = []
        _sync_progress.error = None
        _sync_progress.result = None
    _sync_thread = threading.Thread(target=_run_sync, args=(db_path, max_results, after), daemon=True)
    _sync_thread.start()
    return {"ok": True, "started": True}


def _run_sync(db_path: str, max_results: int, after: str | None) -> None:
    # Opens its own connection because it runs in a background thread, on its
    # own timeline, well after the request that spawned it has already
    # returned (and closed its own connection).
    conn = init_db(connect(db_path))
    account = None
    try:
        config = load_gmail_config(conn)
        account = conn.execute(
            "SELECT * FROM gmail_accounts ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if not account:
            raise ValueError("Gmail is not connected.")
        refresh_token = decrypt_token(account["encrypted_refresh_token"], config.encryption_key)
        token_payload = refresh_access_token(refresh_token, config)
        access_token = token_payload["access_token"]
        rotated_refresh_token = token_payload.get("refresh_token")
        if rotated_refresh_token and rotated_refresh_token != refresh_token:
            conn.execute(
                "UPDATE gmail_accounts SET encrypted_refresh_token = ? WHERE id = ?",
                (encrypt_token(rotated_refresh_token, config.encryption_key), account["id"]),
            )
            conn.commit()
        client = GmailClient(access_token)
        account_email = account["email"] or client.profile().get("emailAddress")
        query = gmail_query(after)
        message_ids = client.search(query, max_results=max_results)
        with _sync_progress_lock:
            _sync_progress.total = len(message_ids)
        seen = inserted = 0
        classifications: dict[str, int] = {}
        for message_id in message_ids:
            seen += 1
            parsed = parse_gmail_message(client.message(message_id))
            with _sync_progress_lock:
                _sync_progress.current_subject = parsed.get("subject")
            result = upsert_message_and_evidence(conn, account_email, parsed)
            # Commit per message (not once at the end): this is the fix for
            # today's "database is locked" incident, where a single
            # multi-minute sync held one write transaction open long enough
            # to lock out every other request on the dashboard.
            conn.commit()
            classifications[result["classification"]] = classifications.get(result["classification"], 0) + 1
            inserted += 1
            with _sync_progress_lock:
                _sync_progress.processed = seen
                subject = (parsed.get("subject") or "(no subject)")[:120]
                _sync_progress.log.append(f"[{result['classification']}] {subject}")
                _sync_progress.log = _sync_progress.log[-50:]
        now = utc_now()
        conn.execute(
            "UPDATE gmail_accounts SET email = ?, last_sync_at = ?, last_error = NULL, updated_at = ? WHERE id = ?",
            (account_email, now, now, account["id"]),
        )
        conn.commit()
        summary = {"ok": True, "query": query, "seen": seen, "saved": inserted, "classifications": classifications}
        with _sync_progress_lock:
            _sync_progress.result = summary
    except Exception as exc:
        if account is not None:
            conn.execute(
                "UPDATE gmail_accounts SET last_error = ?, updated_at = ? WHERE id = ?",
                (str(exc)[:1000], utc_now(), account["id"]),
            )
            conn.commit()
        with _sync_progress_lock:
            _sync_progress.error = str(exc)
    finally:
        with _sync_progress_lock:
            _sync_progress.running = False
        conn.close()


def sync_gmail(conn, max_results: int = 50, after: str | None = None) -> dict:
    """Blocking wrapper around start_gmail_sync/_run_sync, used by the CLI
    (jobhunt/cli.py::cmd_gmail_sync) and tests that want the old
    call-and-get-the-result-back behavior."""
    start = start_gmail_sync(conn, max_results=max_results, after=after)
    if not start.get("started"):
        raise RuntimeError("Gmail sync already running.")
    _sync_thread.join()
    with _sync_progress_lock:
        error = _sync_progress.error
        summary = _sync_progress.result
    if error:
        raise RuntimeError(error)
    return summary
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gmail_integration.py -v`

Expected: all tests in the file PASS, including the 3 new ones.

- [ ] **Step 6: Commit**

```bash
git add jobhunt/gmail_integration.py tests/test_gmail_integration.py
git commit -m "$(cat <<'EOF'
feat(gmail): make sync async with per-message commits and progress state

sync_gmail held one HTTP request and one open DB write-transaction for
its entire multi-minute run, which is what caused today's nginx 504,
"database is locked", and "Failed to fetch" incidents. Split it into
start_gmail_sync() (spawns a background thread, returns immediately)
and _run_sync() (commits after every message instead of once at the
end), tracked in a module-level SyncProgress. sync_gmail() becomes a
blocking wrapper so jobhunt/cli.py and existing callers are unaffected.
EOF
)"
```

---

### Task 2: Wire the dashboard's HTTP routes

**Files:**
- Modify: `jobhunt/dashboard.py:40-55` (imports), `jobhunt/dashboard.py:2218-2221` (add progress route), `jobhunt/dashboard.py:2332-2341` (change sync route)

**Interfaces:**
- Consumes: `start_gmail_sync(conn, max_results, after) -> dict`,
  `gmail_sync_progress() -> dict` (both from Task 1).
- Produces: `GET /api/gmail/sync/progress` (JSON, no request body), `POST
  /api/gmail/sync` now returns `{"ok": true, "started": true}` or `{"ok":
  false, "already_running": true}` instead of the old `{"ok", "query",
  "seen", "saved", "classifications"}` summary (that summary is now only
  reachable via polling `/api/gmail/sync/progress`'s `result` field once
  `running` is `false`).

- [ ] **Step 1: Update the `gmail_integration` import block**

In `jobhunt/dashboard.py`, change lines 40-55 from:

```python
from jobhunt.gmail_integration import (
    apply_evidence,
    consume_auth_state,
    create_auth_url,
    disconnect_gmail,
    evidence_candidates,
    evidence_rows,
    exchange_code_for_token,
    gmail_status,
    gmail_metrics,
    load_gmail_config,
    reject_evidence,
    save_oauth_token,
    sync_gmail,
    update_evidence,
)
```

to:

```python
from jobhunt.gmail_integration import (
    apply_evidence,
    consume_auth_state,
    create_auth_url,
    disconnect_gmail,
    evidence_candidates,
    evidence_rows,
    exchange_code_for_token,
    gmail_status,
    gmail_metrics,
    gmail_sync_progress,
    load_gmail_config,
    reject_evidence,
    save_oauth_token,
    start_gmail_sync,
    update_evidence,
)
```

(`sync_gmail` is no longer used by `dashboard.py` — only `jobhunt/cli.py`
uses it now, and that import is separate and untouched.)

- [ ] **Step 2: Add the progress GET route**

In `jobhunt/dashboard.py`, find this block (currently at lines 2218-2221):

```python
            if parsed.path == "/api/gmail/status":
                with db_session() as conn:
                    self._send_json(gmail_status(conn))
                return
```

Add a new route immediately after it:

```python
            if parsed.path == "/api/gmail/status":
                with db_session() as conn:
                    self._send_json(gmail_status(conn))
                return
            if parsed.path == "/api/gmail/sync/progress":
                self._send_json(gmail_sync_progress())
                return
```

- [ ] **Step 3: Change the sync POST route**

Find this block (currently at lines 2332-2341):

```python
            if parsed.path == "/api/gmail/sync":
                with db_session() as conn:
                    self._send_json(
                        sync_gmail(
                            conn,
                            max_results=int(payload.get("max_results") or 50),
                            after=str(payload.get("after") or "") or None,
                        )
                    )
                return
```

Replace with:

```python
            if parsed.path == "/api/gmail/sync":
                with db_session() as conn:
                    self._send_json(
                        start_gmail_sync(
                            conn,
                            max_results=int(payload.get("max_results") or 50),
                            after=str(payload.get("after") or "") or None,
                        )
                    )
                return
```

- [ ] **Step 4: Verify syntax and run the full test suite**

Run: `.venv/bin/python -c "import ast; ast.parse(open('jobhunt/dashboard.py').read())" && echo "syntax OK"`
Expected: `syntax OK`

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all tests pass (this repo has no HTTP-level test harness for
`DashboardHandler`, so route wiring is verified manually in Task 5, not by
an automated test here).

- [ ] **Step 5: Commit**

```bash
git add jobhunt/dashboard.py
git commit -m "$(cat <<'EOF'
feat(dashboard): wire /api/gmail/sync to the async sync + add progress endpoint

POST /api/gmail/sync now starts the background sync and returns
immediately; GET /api/gmail/sync/progress exposes live processed/total
counts, the current message subject, and a rolling log for the
frontend to poll.
EOF
)"
```

---

### Task 3: Frontend API client

**Files:**
- Modify: `dashboard/web/src/lib/api.ts:284-299` (near `GmailStatus`), `dashboard/web/src/lib/api.ts:581-588` (`syncGmail`)

**Interfaces:**
- Produces: `GmailSyncProgress` type, `getGmailSyncProgress(): Promise<GmailSyncProgress>`.
- Modifies: `syncGmail()`'s return type (was `{ ok, query, seen, saved,
  classifications }`, now `{ ok: boolean; started?: boolean;
  already_running?: boolean }`).

- [ ] **Step 1: Add the `GmailSyncProgress` type**

In `dashboard/web/src/lib/api.ts`, immediately after the `GmailStatus` type
(currently ending at line 299 with the closing `};` before `export type
GmailMetrics = {`), add:

```typescript
export type GmailSyncProgress = {
  running: boolean;
  total: number;
  processed: number;
  current_subject: string | null;
  log: string[];
  error: string | null;
  result: {
    ok: boolean;
    query: string;
    seen: number;
    saved: number;
    classifications: Record<string, number>;
  } | null;
};
```

- [ ] **Step 2: Update `syncGmail` and add `getGmailSyncProgress`**

Find (currently lines 581-588):

```typescript
export const syncGmail = (body: { max_results?: number; after?: string } = {}) =>
  api<{ ok: boolean; query: string; seen: number; saved: number; classifications: Record<string, number> }>("/api/gmail/sync", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getGmailEvidence = () => api<{ evidence: GmailEvidence[] }>("/api/gmail/evidence");
```

Replace with:

```typescript
export const syncGmail = (body: { max_results?: number; after?: string } = {}) =>
  api<{ ok: boolean; started?: boolean; already_running?: boolean }>("/api/gmail/sync", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getGmailSyncProgress = () => api<GmailSyncProgress>("/api/gmail/sync/progress");

export const getGmailEvidence = () => api<{ evidence: GmailEvidence[] }>("/api/gmail/evidence");
```

- [ ] **Step 3: Type-check**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: no new errors mentioning `api.ts` (pre-existing unrelated errors,
if any, are out of scope — compare against a run on `main` first if unsure).

- [ ] **Step 4: Commit**

```bash
git add dashboard/web/src/lib/api.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add GmailSyncProgress type and getGmailSyncProgress client

syncGmail() now returns the async start-acknowledgement shape instead
of the final summary; the summary is reached via polling
getGmailSyncProgress() until running is false.
EOF
)"
```

---

### Task 4: Progress bar + log UI in `GmailEvidencePanel`

**Files:**
- Modify: `dashboard/web/src/components/GmailEvidencePanel.tsx` (imports, state, `sync()`, JSX), `dashboard/web/src/styles/app.css` (near line 803, after the existing `.gmail-evidence` rules)

**Interfaces:**
- Consumes: `GmailSyncProgress`, `getGmailSyncProgress()` (Task 3).

- [ ] **Step 1: Update imports and add polling state**

In `dashboard/web/src/components/GmailEvidencePanel.tsx`, change the top of
the file from:

```typescript
import { useMemo, useState } from "react";
import type { GmailEvidence, GmailMatchCandidate, GmailStatus, Job } from "../lib/api";
import {
  applyGmailEvidence,
  disconnectGmail,
  getGmailEvidenceCandidates,
  ignoreGmailEvidence,
  startGmailOAuth,
  syncGmail,
  updateGmailEvidence,
} from "../lib/api";
```

to:

```typescript
import { useEffect, useMemo, useRef, useState } from "react";
import type { GmailEvidence, GmailMatchCandidate, GmailStatus, GmailSyncProgress, Job } from "../lib/api";
import {
  applyGmailEvidence,
  disconnectGmail,
  getGmailEvidenceCandidates,
  getGmailSyncProgress,
  ignoreGmailEvidence,
  startGmailOAuth,
  syncGmail,
  updateGmailEvidence,
} from "../lib/api";
```

In the component body, change:

```typescript
  const [message, setMessage] = useState("");
  const [drafts, setDrafts] = useState<Record<string, EvidenceDraft>>({});
  const [candidateMatches, setCandidateMatches] = useState<Record<string, GmailMatchCandidate[]>>({});
```

to:

```typescript
  const [message, setMessage] = useState("");
  const [drafts, setDrafts] = useState<Record<string, EvidenceDraft>>({});
  const [candidateMatches, setCandidateMatches] = useState<Record<string, GmailMatchCandidate[]>>({});
  const [syncProgress, setSyncProgress] = useState<GmailSyncProgress | null>(null);
  const pollingRef = useRef(false);
```

- [ ] **Step 2: Add the polling loop and mount effect**

Immediately before the existing `async function sync() {` definition, add:

```typescript
  async function pollSyncProgress() {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      for (;;) {
        const progress = await getGmailSyncProgress();
        setSyncProgress(progress);
        console.debug("[gmail-sync]", progress.processed, "/", progress.total, progress.current_subject);
        if (!progress.running) {
          if (progress.error) {
            setMessage(progress.error);
          } else if (progress.result) {
            setMessage(`Processed ${progress.result.saved} messages.`);
          }
          reload();
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    } catch {
      // Progress polling is best-effort; the rest of the dashboard still works.
    } finally {
      pollingRef.current = false;
    }
  }

  useEffect(() => {
    pollSyncProgress();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

- [ ] **Step 3: Update `sync()` to kick off polling**

Change:

```typescript
  async function sync() {
    setMessage("Syncing and classifying Gmail...");
    try {
      const result = await syncGmail({ max_results: 75 });
      setMessage(`Processed ${result.saved} messages.`);
      reload();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
```

to:

```typescript
  async function sync() {
    try {
      const result = await syncGmail({ max_results: 75 });
      setMessage(result.already_running ? "Sync already in progress." : "Syncing and classifying Gmail...");
      pollSyncProgress();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
```

- [ ] **Step 4: Disable "Sync now" while running and add the progress panel**

Change:

```typescript
        <div>
          {gmail.connected ? (
            <>
              <button className="btn rose sm" type="button" onClick={sync}>Sync now</button>
              <button className="btn ghost sm" type="button" onClick={disconnect}>Disconnect</button>
            </>
          ) : (
            <button className="btn rose sm" type="button" onClick={connect} disabled={!gmail.configured}>
              Connect Gmail
            </button>
          )}
        </div>
      </div>
      {gmail.account?.last_error ? <div className="banner-error">{gmail.account.last_error}</div> : null}
      {message ? <p className="muted gmail-message">{message}</p> : null}
```

to:

```typescript
        <div>
          {gmail.connected ? (
            <>
              <button className="btn rose sm" type="button" onClick={sync} disabled={Boolean(syncProgress?.running)}>
                {syncProgress?.running ? "Syncing…" : "Sync now"}
              </button>
              <button className="btn ghost sm" type="button" onClick={disconnect} disabled={Boolean(syncProgress?.running)}>
                Disconnect
              </button>
            </>
          ) : (
            <button className="btn rose sm" type="button" onClick={connect} disabled={!gmail.configured}>
              Connect Gmail
            </button>
          )}
        </div>
      </div>
      {gmail.account?.last_error ? <div className="banner-error">{gmail.account.last_error}</div> : null}
      {message ? <p className="muted gmail-message">{message}</p> : null}

      {syncProgress?.running ? (
        <div className="gmail-sync-progress">
          <div className="gmail-sync-progress-bar">
            <span
              style={{
                width: syncProgress.total > 0
                  ? `${Math.round((syncProgress.processed / syncProgress.total) * 100)}%`
                  : "4%",
              }}
            />
          </div>
          <p className="muted">
            {syncProgress.total > 0
              ? `${syncProgress.processed} / ${syncProgress.total} messages`
              : "Starting sync…"}
            {syncProgress.current_subject ? ` · ${syncProgress.current_subject}` : ""}
          </p>
          {syncProgress.log.length ? (
            <ul className="gmail-sync-log">
              {syncProgress.log.slice().reverse().map((line) => <li key={line}>{line}</li>)}
            </ul>
          ) : null}
        </div>
      ) : null}
```

- [ ] **Step 5: Add CSS for the progress bar and log**

In `dashboard/web/src/styles/app.css`, immediately after the existing rule
`.gmail-evidence blockquote { margin: 6px 0; padding-left: 9px; border-left: 2px solid var(--berry); }`
(around line 803), add:

```css
.gmail-sync-progress { margin: 10px 0; }
.gmail-sync-progress-bar { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.gmail-sync-progress-bar span { display: block; height: 100%; background: var(--berry); transition: width 300ms ease; }
.gmail-sync-progress p { font-size: 11px; margin: 6px 0; }
.gmail-sync-log { list-style: none; margin: 0; padding: 0; max-height: 140px; overflow-y: auto; font-size: 10.5px; color: var(--ink-soft); display: grid; gap: 3px; }
.gmail-sync-log li { border-bottom: 1px solid var(--border); padding-bottom: 3px; }
```

- [ ] **Step 6: Type-check and lint**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: no new errors mentioning `GmailEvidencePanel.tsx`.

- [ ] **Step 7: Commit**

```bash
git add dashboard/web/src/components/GmailEvidencePanel.tsx dashboard/web/src/styles/app.css
git commit -m "$(cat <<'EOF'
feat(frontend): show live progress bar and log while Gmail sync runs

Polls /api/gmail/sync/progress every 2s while a sync is running,
disables Sync now, and renders processed/total plus a scrolling log
of classified messages instead of one static "Syncing..." string.
Each poll also logs to the browser console for deeper visibility.
EOF
)"
```

---

### Task 5: Build, deploy, and verify end-to-end

**Files:** none (build/deploy/verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 2: Build the frontend**

Run: `cd dashboard/web && npm run build`
Expected: build succeeds, `dashboard/static/app/` contains new hashed JS/CSS
filenames.

- [ ] **Step 3: Rebuild and redeploy the container**

Run:
```bash
cd /opt/angelica-jobhunt
docker compose build dashboard
docker compose up -d dashboard
```
Expected: `Container angelica-jobhunt Started`.

- [ ] **Step 4: Verify the new endpoint responds**

Run: `curl -s http://127.0.0.1:8765/api/gmail/sync/progress`
Expected: `{"running": false, "total": 0, "processed": 0, "current_subject": null, "log": [], "error": null, "result": null}`
(or a populated `result` if a sync ran previously in this container's
lifetime — either is fine, the key check is that it responds instantly
with valid JSON rather than 404 or hanging).

- [ ] **Step 5: Verify the sync endpoint returns immediately**

Run: `time curl -s -X POST http://127.0.0.1:8765/api/gmail/sync -H "Content-Type: application/json" -d '{"max_results": 5}'`
Expected: completes in well under 1 second (not minutes), with body
`{"ok": true, "started": true}` (or `{"ok": false, "already_running": true}`
if a sync happened to already be running).

- [ ] **Step 6: Verify the dashboard stays responsive while that sync runs**

Immediately after Step 5, run:
`curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://127.0.0.1:8765/api/summary`
Expected: `200` and well under 1 second — proving a concurrent request is no
longer blocked behind the sync's write lock.

- [ ] **Step 7: Watch it finish**

Run: `while curl -s http://127.0.0.1:8765/api/gmail/sync/progress | grep -q '"running": true'; do sleep 2; echo -n .; done; echo done`
Expected: prints dots while running, then `done`, then a final check —
`curl -s http://127.0.0.1:8765/api/gmail/sync/progress` shows
`"running": false` and a populated `"result"` with `"ok": true`.

- [ ] **Step 8: Manual UI check**

Open the dashboard in a browser (or ask the user to), expand "Gmail
intelligence", click "Sync now", and confirm: the button becomes disabled
and shows "Syncing…", a progress bar appears and advances, log lines appear
listing classified subjects, and the panel returns to normal with a
"Processed N messages" line once done. Open the browser devtools console
and confirm `[gmail-sync]` lines are being logged each poll.
