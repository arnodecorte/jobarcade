# Design Spec: Async Gmail Sync with Progress Visibility

**Date**: 2026-07-11
**Status**: Approved

## Context

Today's debugging session traced three "prod is broken" symptoms back to one
root cause: `POST /api/gmail/sync` (`jobhunt/gmail_integration.py::sync_gmail`)
processes every fetched Gmail message **sequentially and synchronously** —
Gmail API fetch, then an Ollama classification call (up to
`OLLAMA_CLASSIFIER_TIMEOUT=45`s), then DB writes — for up to 75 messages, all
inside **one HTTP request and one open database transaction** that isn't
committed until the very end. A real run was measured at ~7 minutes.

This single design produced three distinct-looking bugs:

1. **"Unexpected token '<'... is not valid JSON"** — nginx's default 60s
   `proxy_read_timeout` on the `jobhunt.ana.hub` route cut the request off
   mid-flight and returned its own HTML 504 page, which the frontend's
   `api()` helper (`await res.json()` unconditionally) couldn't parse.
2. **"database is locked"** — every request handler opened a DB connection
   via `with init_db(connect(DB_PATH)) as conn:`, which only commits/rolls
   back and never calls `.close()`. Combined with `sync_gmail` holding one
   write transaction open for its entire multi-minute run, any other
   request (even a trivial `GET /api/summary`) could get stuck queued behind
   it and fail after SQLite's 10s `busy_timeout`. A `db_session()` context
   manager with a `finally: conn.close()` was added to fix the leak, but the
   fundamental one-giant-transaction-per-sync design is still there.
3. **"Failed to fetch"** — the same multi-minute single request, now
   correctly proxied through a bumped nginx timeout, still ties up one
   browser fetch, one HTTP connection, and one DB write-lock for minutes
   with zero feedback. Any hiccup anywhere in that chain (and there have
   been several today) presents to the user as an opaque failure with no
   way to tell what stage it died at.

Raising timeouts fixed symptom #1 but not the underlying fragility, and #2/#3
are architectural consequences of the same synchronous, single-transaction
design. The fix is to stop holding one giant request/transaction open at all.

## Goals

- `POST /api/gmail/sync` returns almost immediately; the actual work happens
  in a background thread.
- The dashboard shows live progress (X/Y messages processed) and a scrolling
  log of what's being classified, instead of a single opaque "Syncing..."
  message.
- The sync no longer holds one open DB write-transaction for its entire
  duration — it commits after each message, so other requests are never
  blocked for more than a fraction of a second.
- A second "Sync now" click (or a second browser tab) while a sync is
  running does not start a duplicate; it just observes the same progress.

## Non-goals

- Surviving a dashboard container restart mid-sync. If the container
  restarts, the in-progress sync dies with it (as it already does today) —
  only the *visibility* into a live sync is being added, not durability
  across restarts.
- Historical sync-run history/audit log. Only the current/most recent run's
  state is tracked.
- Queueing multiple sync requests. A second request while one is running is
  rejected, not deferred.
- Changing Gmail fetch pagination, Ollama classification logic, or matching
  logic — only the execution/commit/visibility model changes.

## Design

### Backend: `SyncProgress` state

A new module-level object in `jobhunt/gmail_integration.py`, guarded by a
`threading.Lock`, holding:

```python
@dataclass
class SyncProgress:
    running: bool = False
    total: int = 0
    processed: int = 0
    current_subject: str | None = None
    log: list[str] = field(default_factory=list)   # capped at last 50 entries
    error: str | None = None
    result: dict | None = None                      # final {"ok", "query", "seen", "saved", "classifications"} once done
```

A single shared instance (`_sync_progress`) plus a lock live at module scope.
This is intentionally in-memory only (per the approved design questions):
only one sync is meaningful at a time for a single-user tool, and a
container restart already kills any in-flight sync outright, so persisting
progress across restarts would just be tracking a lie.

### Backend: starting a sync

`start_gmail_sync(conn, max_results, after) -> dict`:

- Under the lock: if `_sync_progress.running` is already `True`, return
  `{"ok": False, "already_running": True}` immediately (no thread started).
- Otherwise, reset `_sync_progress` to a fresh running state and spawn a
  `threading.Thread(target=_run_sync, args=(...), daemon=True)`.
- Returns `{"ok": True, "started": True}` right away.

`_run_sync(...)` is today's `sync_gmail` body, modified to:
- Set `total = len(message_ids)` once the Gmail search resolves.
- After processing each message: commit, append a log line
  (`f"[{classification.kind}] {subject}"` truncated), increment `processed`,
  update `current_subject`, all under the lock.
- On any exception: set `error = str(exc)`, still write it to
  `gmail_accounts.last_error` as today.
- On completion (success or error): set `running = False` and `result` to
  the same summary dict `sync_gmail` returns today.

Existing `sync_gmail` callers (tests) get a thin synchronous wrapper for
compatibility where tests need the old blocking behavior; production code
path uses `start_gmail_sync`.

### Backend: commit-per-message

The core fix for symptom #2. Inside the per-message loop, replace the single
end-of-loop `conn.commit()` with a `conn.commit()` right after each message's
`upsert_message_and_evidence` call. This means the write lock is held for
roughly the duration of one message's DB writes (milliseconds), not the
whole sync. Combined with the already-shipped `db_session()` fix (which
guarantees the connection closes even on error), this removes the lock-pileup
failure mode independent of the async change.

### Backend: new endpoint

`GET /api/gmail/sync/progress` → returns the current `SyncProgress` as JSON
(`running`, `total`, `processed`, `current_subject`, `log`, `error`,
`result`). Cheap, read-only, no new DB writes.

`POST /api/gmail/sync` changes from calling `sync_gmail(...)` directly to
calling `start_gmail_sync(...)` and returning its `{"ok": ..., "started"|
"already_running": ...}` immediately.

### Frontend

- `syncGmail()` in `api.ts` still POSTs to `/api/gmail/sync`, but now expects
  the immediate `{"ok", "started"}` (or `"already_running"`) response.
- New `getGmailSyncProgress()` → `GET /api/gmail/sync/progress`.
- `GmailEvidencePanel`'s `sync()` handler: on start, begins polling
  `getGmailSyncProgress()` every 2s. While `running` is true: disable "Sync
  now", render a progress bar (`processed/total`) and the log lines
  (newest-first, scrollable, capped list from the backend). When `running`
  flips to false: stop polling, show the final result summary (`Processed N
  messages`) or the error, and call `reload()` once to refresh evidence/jobs.
- On mount (or when the panel is expanded), it also checks
  `getGmailSyncProgress()` once so that reopening the dashboard mid-sync (or
  a second tab) picks up the in-progress state instead of showing a blank
  "Sync now" button that would silently no-op.
- Browser-console logging: each poll tick logs
  `console.debug("[gmail-sync]", processed, "/", total, current_subject)` so
  the "more logging" ask is satisfied without cluttering the visible UI.

### Error handling

- Background thread exceptions are caught at the top of `_run_sync`, stored
  in `SyncProgress.error`, and also written to `gmail_accounts.last_error`
  (existing behavior). The frontend shows the error inline in the progress
  panel instead of a bare toast.
- `GET /api/gmail/sync/progress` itself cannot meaningfully fail (it's a
  read of an in-memory object) — no new failure mode introduced there.
- A second sync request while one is running gets a clear, distinct
  response (`already_running: true`) that the frontend renders as "Sync
  already in progress" rather than erroring.

### Testing

- `sync_gmail`/`_run_sync` commits after each message: a test that starts a
  sync (or calls the per-message step directly), and asserts that a
  **second, independent connection** can successfully write to the DB while
  the first message is mid-processing (this is the regression test for
  today's lock-contention bug).
- `start_gmail_sync` rejects a second call while `running` is `True`.
- `SyncProgress` updates (`processed`, `log`, `total`) reflect the number of
  messages actually processed, using the existing fixture pattern (mock
  Gmail client + Ollama).
- Existing `test_gmail_integration.py` tests that call `sync_gmail` directly
  get a synchronous test helper that drives `_run_sync` to completion
  in-thread (no need to poll) so they don't need timing-dependent waits.

## Open Questions

None — scope and behavior confirmed via the design-question exchange
(in-memory state, reject-not-queue for concurrent syncs).
