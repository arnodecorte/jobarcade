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


def test_gmail_tables_are_created(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }

    assert "gmail_accounts" in tables
    assert "gmail_oauth_states" in tables
    assert "gmail_messages" in tables
    assert "email_evidence" in tables


def test_token_encryption_round_trips():
    key = generate_encryption_key()
    encrypted = encrypt_token("refresh-token", key)

    assert encrypted != "refresh-token"
    assert decrypt_token(encrypted, key) == "refresh-token"


def test_classifier_detects_rejection_receipt_and_interview():
    assert classify_email("Application update", "Unfortunately, we will not be moving forward.").kind == "rejection"
    assert classify_email("Thanks for applying", "We received your application.").kind == "application_receipt"
    assert classify_email("Next step", "We would like to schedule an interview.").kind == "interview_invite"


def test_match_email_to_submitted_job(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(
        company="Nike",
        title="Digital Content Specialist",
        apply_url="https://jobs.nike.com/1",
        status="applied",
    )
    upsert_jobs(conn, [job])

    match = match_email_to_job(
        conn,
        {
            "subject": "Nike Digital Content Specialist application update",
            "snippet": "Unfortunately, we will not be moving forward.",
            "sender": "careers@nike.com",
        },
    )

    assert match.job_id is not None
    assert match.confidence >= 0.45


def test_match_email_handles_naive_status_event_timestamp(tmp_path):
    # status_events.created_at can be SQLite's naive `datetime('now')` default
    # (e.g. from a manual dashboard status change), while Gmail's received_at is
    # always tz-aware. Matching must not crash comparing the two.
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(
        company="Nike",
        title="Digital Content Specialist",
        apply_url="https://jobs.nike.com/1",
        status="applied",
    )
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    conn.execute("INSERT INTO status_events (job_id, status) VALUES (?, ?)", (job_id, "applied"))
    conn.commit()

    match = match_email_to_job(
        conn,
        {
            "subject": "Nike Digital Content Specialist application update",
            "snippet": "Unfortunately, we will not be moving forward.",
            "sender": "careers@nike.com",
            "received_at": datetime(2026, 7, 5, tzinfo=timezone.utc).isoformat(timespec="seconds"),
        },
    )

    assert match.job_id == job_id


def test_upsert_evidence_and_apply_rejection_updates_status(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(
        conn,
        [Job(company="Nike", title="Digital Content Specialist", apply_url="https://jobs.nike.com/1", status="applied")],
    )
    email = {
        "gmail_message_id": "msg-1",
        "gmail_thread_id": "thread-1",
        "sender": "careers@nike.com",
        "subject": "Nike Digital Content Specialist application update",
        "snippet": "Unfortunately, after careful consideration, we are not moving forward.",
        "body": "",
        "body_hash": None,
        "received_at": datetime(2026, 7, 5, tzinfo=timezone.utc).isoformat(timespec="seconds"),
    }

    result = upsert_message_and_evidence(conn, "angelica@example.com", email)
    apply_evidence(conn, "msg-1")

    assert result["classification"] == "rejection"
    row = conn.execute("SELECT status FROM jobs").fetchone()
    assert row["status"] == "rejected"
    event = conn.execute("SELECT status FROM status_events ORDER BY id DESC LIMIT 1").fetchone()
    assert event["status"] == "rejected"


def test_ignore_evidence_marks_reviewed(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    conn.execute(
        """
        INSERT INTO email_evidence (gmail_message_id, evidence_type, confidence, status)
        VALUES ('msg-2', 'ambiguous', 0.4, 'pending')
        """
    )
    conn.commit()

    reject_evidence(conn, "msg-2")

    row = conn.execute("SELECT status, reviewed_at FROM email_evidence WHERE gmail_message_id = 'msg-2'").fetchone()
    assert row["status"] == "ignored"
    assert row["reviewed_at"]


def test_create_auth_url_persists_state(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GMAIL_REDIRECT_URI", "http://localhost:8765/api/gmail/oauth/callback")
    monkeypatch.setenv("GMAIL_TOKEN_ENCRYPTION_KEY", generate_encryption_key())
    conn = init_db(tmp_path / "jobs.sqlite")

    payload = create_auth_url(conn)

    row = conn.execute("SELECT state FROM gmail_oauth_states WHERE state = ?", (payload["state"],)).fetchone()
    assert row is not None
    assert "https://accounts.google.com" in payload["auth_url"]


def test_ollama_classifier_accepts_structured_semantic_rejection(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": """
                {
                  "category": "rejection",
                  "confidence": 0.97,
                  "inferred_company": "Nike",
                  "inferred_role": "Content Specialist",
                  "reasoning": "The newest message says the application will not proceed.",
                  "supporting_excerpts": ["we cannot proceed with your application"]
                }
                """
            }

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("jobhunt.gmail_integration.httpx.Client", Client)
    result = classify_email_with_ollama(
        {
            "sender": "careers@nike.com",
            "subject": "Your application",
            "body": "Thank you, but we cannot proceed with your application.",
        },
        config=OllamaConfig("http://ollama", "qwen2.5:7b"),
    )

    assert result.kind == "rejection"
    assert result.confidence == 0.97
    assert result.inferred_company == "Nike"
    assert result.source == "ollama"


def test_ollama_failure_falls_back_without_losing_message(monkeypatch):
    class Client:
        def __init__(self, **_kwargs):
            raise TimeoutError("offline")

    monkeypatch.setattr("jobhunt.gmail_integration.httpx.Client", Client)
    result = classify_email_with_ollama(
        {"subject": "Application update", "body": "Unfortunately, we are not moving forward."},
        config=OllamaConfig("http://ollama", "qwen2.5:7b"),
    )

    assert result.kind == "rejection"
    assert result.source == "rules_fallback"
    assert "offline" in (result.error or "")


def test_manual_correction_changes_category_and_match(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(conn, [Job(company="Nike", title="Brand Manager", apply_url="https://nike.com/1", status="applied")])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO email_evidence (
            gmail_message_id, evidence_type, confidence, status, original_evidence_type
        ) VALUES ('correct-me', 'unknown', 0.4, 'pending', 'unknown')
        """
    )
    conn.commit()

    update_evidence(conn, "correct-me", "interview_invite", job_id)

    row = conn.execute("SELECT * FROM email_evidence WHERE gmail_message_id = 'correct-me'").fetchone()
    assert row["evidence_type"] == "interview_invite"
    assert row["job_id"] == job_id
    assert row["corrected_by_user"] == 1
    assert row["target_status"] == "interviewing"


def test_apply_is_idempotent_when_job_already_has_target_status(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    upsert_jobs(conn, [Job(company="Nike", title="Brand Manager", apply_url="https://nike.com/1", status="rejected")])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO email_evidence (
            gmail_message_id, job_id, evidence_type, confidence, status, occurred_at
        ) VALUES ('same-status', ?, 'rejection', 0.95, 'pending', '2026-07-08T12:00:00+00:00')
        """,
        (job_id,),
    )
    conn.commit()

    apply_evidence(conn, "same-status")
    apply_evidence(conn, "same-status")

    assert conn.execute("SELECT COUNT(*) FROM status_events").fetchone()[0] == 0


def test_metrics_separate_automatic_and_manual_work(tmp_path):
    conn = init_db(tmp_path / "jobs.sqlite")
    conn.execute(
        """
        INSERT INTO gmail_messages (
            gmail_message_id, classification, confidence, classifier_source
        ) VALUES ('metric-1', 'rejection', 0.95, 'ollama')
        """
    )
    conn.execute(
        """
        INSERT INTO email_evidence (
            gmail_message_id, evidence_type, confidence, status, corrected_by_user
        ) VALUES ('metric-1', 'rejection', 0.95, 'pending', 1)
        """
    )
    conn.commit()

    metrics = gmail_metrics(conn)

    assert metrics["scanned"] == 1
    assert metrics["job_related"] == 1
    assert metrics["auto_classified"] == 1
    assert metrics["pending_review"] == 1
    assert metrics["corrected"] == 1


def test_html_only_gmail_body_is_available_to_classifier():
    encoded = base64.urlsafe_b64encode(
        b"<html><style>.x{display:none}</style><body>Unfortunately, we cannot proceed.</body></html>"
    ).decode("ascii")

    parsed = parse_gmail_message(
        {
            "id": "html-message",
            "internalDate": "1783512000000",
            "payload": {
                "mimeType": "text/html",
                "headers": [{"name": "Subject", "value": "Application update"}],
                "body": {"data": encoded},
            },
        }
    )

    assert parsed["body"] == "Unfortunately, we cannot proceed."


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
    def fake_profile(self):
        return {"emailAddress": "test@example.com"}
    monkeypatch.setattr(GmailClient, "profile", fake_profile)

    def fake_classify(email, thread_context=None, config=None):
        return Classification(
            kind="rejection",
            confidence=0.95,
            reason="Test classification",
            inferred_company="Nike",
            inferred_role="Content Specialist",
            supporting_excerpts=[],
            source="rules_fallback",
            version="test",
        )
    monkeypatch.setattr("jobhunt.gmail_integration.classify_email_with_ollama", fake_classify)


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


def test_run_sync_exception_mid_sync_resets_running_state(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    _setup_connected_account(conn, monkeypatch)

    def fake_search(self, query, max_results=50):
        raise RuntimeError("Gmail API exploded")

    monkeypatch.setattr(GmailClient, "search", fake_search)

    start = start_gmail_sync(conn, max_results=50)
    assert start == {"ok": True, "started": True}

    _wait_until(lambda: gmail_sync_progress()["running"] is False)

    progress = gmail_sync_progress()
    assert progress["error"]
    assert "Gmail API exploded" in progress["error"]

    # The lock/state must not be left stuck: a subsequent call must be able
    # to start a new sync, not get rejected as already_running forever.
    second = start_gmail_sync(conn, max_results=50)
    assert second == {"ok": True, "started": True}
    _wait_until(lambda: gmail_sync_progress()["running"] is False)


def test_run_sync_connect_failure_resets_running_state(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    _setup_connected_account(conn, monkeypatch)

    def fake_connect(path):
        raise RuntimeError("cannot open database")

    monkeypatch.setattr("jobhunt.gmail_integration.connect", fake_connect)

    start = start_gmail_sync(conn, max_results=50)
    assert start == {"ok": True, "started": True}

    _wait_until(lambda: gmail_sync_progress()["running"] is False)

    progress = gmail_sync_progress()
    assert progress["error"]
    assert "cannot open database" in progress["error"]
