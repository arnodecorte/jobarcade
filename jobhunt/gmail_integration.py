from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from jobhunt.database import connect, init_db, utc_now
from jobhunt.integration_settings import (
    effective_gmail_settings,
    effective_ollama_settings,
    load_or_create_master_key,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

REJECTION_TERMS = (
    "unfortunately",
    "not selected",
    "not be moving forward",
    "not moving forward",
    "decided to move forward with other candidates",
    "pursue other candidates",
    "will not proceed",
    "unsuccessful",
    "regret to inform",
    "after careful consideration",
)
RECEIPT_TERMS = (
    "thank you for applying",
    "thanks for applying",
    "received your application",
    "application has been received",
    "we have received your application",
    "application received",
)
INTERVIEW_TERMS = (
    "schedule an interview",
    "invite you to interview",
    "interview invitation",
    "next step",
    "speak with you",
    "meet with",
    "recruiter screen",
)
NOISE_TERMS = ("job alert", "new jobs", "saved search", "unsubscribe")
EVIDENCE_TYPES = (
    "application_receipt",
    "rejection",
    "interview_invite",
    "assessment_invite",
    "recruiter_outreach",
    "information_request",
    "offer",
    "withdrawal_confirmation",
    "administrative_update",
    "noise",
    "unknown",
)
EVIDENCE_STATUS_MAP = {
    "application_receipt": "applied",
    "rejection": "rejected",
    "interview_invite": "interviewing",
    "assessment_invite": "interviewing",
    "offer": "offer",
}
AUTO_THRESHOLD = 0.90
CLASSIFIER_VERSION = "email-intelligence-v1"


@dataclass
class GmailConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    encryption_key: str

    @property
    def ready(self) -> bool:
        return all((self.client_id, self.client_secret, self.redirect_uri, self.encryption_key))


@dataclass
class Classification:
    kind: str
    confidence: float
    reason: str
    inferred_company: str | None = None
    inferred_role: str | None = None
    supporting_excerpts: tuple[str, ...] = ()
    source: str = "rules"
    version: str = CLASSIFIER_VERSION
    error: str | None = None


@dataclass
class Match:
    job_id: int | None
    confidence: float
    reason: str
    candidates: tuple[dict[str, Any], ...] = ()


@dataclass
class OllamaConfig:
    base_url: str
    model: str
    timeout: float = 45.0


def load_ollama_config(conn=None) -> OllamaConfig:
    if conn is not None:
        settings = effective_ollama_settings(conn)
        return OllamaConfig(
            base_url=settings["base_url"],
            model=settings["model"],
            timeout=float(os.environ.get("OLLAMA_CLASSIFIER_TIMEOUT", "45")),
        )
    return OllamaConfig(
        base_url=(
            os.environ.get("OLLAMA_BASE_URL")
            or os.environ.get("JOBHUNT_OLLAMA_URL")
            or "http://host.docker.internal:11434"
        ).strip(),
        model=(
            os.environ.get("OLLAMA_MODEL")
            or os.environ.get("JOBHUNT_OLLAMA_MODEL")
            or "qwen2.5:7b"
        ).strip(),
        timeout=float(os.environ.get("OLLAMA_CLASSIFIER_TIMEOUT", "45")),
    )


def load_gmail_config(conn=None) -> GmailConfig:
    if conn is not None:
        settings = effective_gmail_settings(conn)
        return GmailConfig(
            client_id=settings["client_id"],
            client_secret=settings["client_secret"],
            redirect_uri=settings["redirect_uri"],
            encryption_key=load_or_create_master_key(),
        )
    return GmailConfig(
        client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        redirect_uri=os.environ.get("GMAIL_REDIRECT_URI", "").strip(),
        encryption_key=os.environ.get("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip(),
    )


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode("ascii")


def _fernet(key: str) -> Fernet:
    raw = key.strip().encode("ascii")
    return Fernet(raw)


def encrypt_token(token: str, key: str) -> str:
    return _fernet(key).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(token: str, key: str) -> str:
    try:
        return _fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored Gmail token could not be decrypted with GMAIL_TOKEN_ENCRYPTION_KEY.") from exc


def gmail_status(conn, config: GmailConfig | None = None) -> dict:
    config = config or load_gmail_config(conn)
    account = conn.execute(
        """
        SELECT email, scopes, connected_at, updated_at, last_sync_at, last_error
        FROM gmail_accounts
        ORDER BY updated_at DESC
        LIMIT 1
        """
    ).fetchone()
    pending = conn.execute("SELECT COUNT(*) AS n FROM email_evidence WHERE status = 'pending'").fetchone()["n"]
    matched = conn.execute("SELECT COUNT(*) AS n FROM email_evidence WHERE job_id IS NOT NULL").fetchone()["n"]
    messages = conn.execute("SELECT COUNT(*) AS n FROM gmail_messages").fetchone()["n"]
    return {
        "configured": config.ready,
        "missing_config": [
            name
            for name, value in {
                "GOOGLE_CLIENT_ID": config.client_id,
                "GOOGLE_CLIENT_SECRET": config.client_secret,
                "GMAIL_REDIRECT_URI": config.redirect_uri,
                "GMAIL_TOKEN_ENCRYPTION_KEY": config.encryption_key,
            }.items()
            if not value
        ],
        "connected": bool(account),
        "account": dict(account) if account else None,
        "evidence": {"pending": pending, "matched": matched, "messages": messages},
        "intelligence": {
            "base_url": load_ollama_config(conn).base_url,
            "model": load_ollama_config(conn).model,
            "auto_threshold": AUTO_THRESHOLD,
        },
        "metrics": gmail_metrics(conn),
    }


def build_auth_url(config: GmailConfig | None = None) -> dict:
    config = config or load_gmail_config()
    if not config.ready:
        raise ValueError("Gmail OAuth is not configured. Set Google client env vars first.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    return {"auth_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}", "state": state, "redirect_uri": config.redirect_uri}


def create_auth_url(conn, config: GmailConfig | None = None) -> dict:
    payload = build_auth_url(config or load_gmail_config(conn))
    conn.execute("INSERT INTO gmail_oauth_states (state, created_at) VALUES (?, ?)", (payload["state"], utc_now()))
    conn.commit()
    return payload


def consume_auth_state(conn, state: str) -> None:
    if not state:
        raise ValueError("Missing OAuth state.")
    row = conn.execute("SELECT state FROM gmail_oauth_states WHERE state = ?", (state,)).fetchone()
    if not row:
        raise ValueError("OAuth state was not recognized. Start Gmail connection again.")
    conn.execute("DELETE FROM gmail_oauth_states WHERE state = ?", (state,))
    conn.commit()


def exchange_code_for_token(code: str, config: GmailConfig | None = None) -> dict:
    config = config or load_gmail_config()
    if not config.ready:
        raise ValueError("Gmail OAuth is not configured. Set Google client env vars first.")
    with httpx.Client(timeout=30) as client:
        res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "redirect_uri": config.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        res.raise_for_status()
        payload = res.json()
    if not payload.get("refresh_token"):
        raise ValueError("Google did not return a refresh token. Reconnect with prompt=consent.")
    return payload


def refresh_access_token(refresh_token: str, config: GmailConfig | None = None) -> dict:
    config = config or load_gmail_config()
    with httpx.Client(timeout=30) as client:
        res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        res.raise_for_status()
        payload = res.json()
    return {
        "access_token": str(payload["access_token"]),
        "refresh_token": payload.get("refresh_token"),
    }


class GmailClient:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        with httpx.Client(timeout=30) as client:
            res = client.get(f"{GMAIL_API_BASE}{path}", headers=headers, params=params)
            res.raise_for_status()
            return res.json()

    def profile(self) -> dict:
        return self._get("/users/me/profile")

    def search(self, query: str, max_results: int = 50) -> list[str]:
        ids: list[str] = []
        page_token = None
        while len(ids) < max_results:
            params: dict[str, Any] = {"q": query, "maxResults": min(100, max_results - len(ids))}
            if page_token:
                params["pageToken"] = page_token
            payload = self._get("/users/me/messages", params)
            ids.extend(item["id"] for item in payload.get("messages", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return ids

    def message(self, message_id: str) -> dict:
        return self._get(f"/users/me/messages/{message_id}", {"format": "full"})


def save_oauth_token(conn, token_payload: dict, config: GmailConfig | None = None) -> dict:
    config = config or load_gmail_config(conn)
    refresh_token = str(token_payload["refresh_token"])
    access_token = str(token_payload.get("access_token") or "")
    account_email = None
    if access_token:
        try:
            account_email = GmailClient(access_token).profile().get("emailAddress")
        except Exception:
            account_email = None
    now = utc_now()
    encrypted = encrypt_token(refresh_token, config.encryption_key)
    scopes = token_payload.get("scope") or GMAIL_READONLY_SCOPE
    conn.execute("DELETE FROM gmail_accounts")
    conn.execute(
        """
        INSERT INTO gmail_accounts (email, encrypted_refresh_token, scopes, connected_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (account_email, encrypted, scopes, now, now),
    )
    conn.commit()
    return {"ok": True, "email": account_email, "scopes": scopes}


def disconnect_gmail(conn) -> dict:
    conn.execute("DELETE FROM gmail_accounts")
    conn.commit()
    return {"ok": True}


def gmail_query(after: str | None = None) -> str:
    terms = [
        '"application"',
        '"thank you for applying"',
        '"received your application"',
        '"unfortunately"',
        '"not selected"',
        '"interview"',
        '"assessment"',
        '"job offer"',
        '"recruiter"',
        '"sollicitatie"',
        '"candidature"',
        '"bewerbung"',
    ]
    query = " OR ".join(terms)
    if after:
        query = f"({query}) after:{after}"
    return query


def classify_email(subject: str | None, snippet: str | None, body: str | None = None) -> Classification:
    """Deterministic fallback classifier used when Ollama cannot answer."""
    text = " ".join(part for part in (subject, snippet, body) if part).lower()
    if any(term in text for term in NOISE_TERMS) and not any(term in text for term in REJECTION_TERMS):
        return Classification("noise", 0.75, "Looks like a job alert or mailing-list message.")
    if any(term in text for term in REJECTION_TERMS):
        return Classification("rejection", 0.9, "Matched common rejection language.")
    if any(term in text for term in INTERVIEW_TERMS):
        return Classification("interview_invite", 0.82, "Matched interview or recruiter next-step language.")
    if any(term in text for term in RECEIPT_TERMS):
        return Classification("application_receipt", 0.82, "Matched application receipt language.")
    if "application" in text or "candidate" in text:
        return Classification("unknown", 0.45, "Mentions application/candidate but no strong outcome phrase.")
    return Classification("unknown", 0.1, "No job-application signal found.")


def _obvious_noise(subject: str | None, snippet: str | None, body: str | None = None) -> Classification | None:
    text = " ".join(part for part in (subject, snippet, body) if part).lower()
    hits = sum(term in text for term in NOISE_TERMS)
    outcome_signal = any(term in text for term in REJECTION_TERMS + RECEIPT_TERMS + INTERVIEW_TERMS)
    if hits >= 2 and not outcome_signal:
        return Classification("noise", 0.98, "Deterministic job-alert or mailing-list signals.", source="rules")
    return None


def _classification_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(EVIDENCE_TYPES)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "inferred_company": {"type": ["string", "null"]},
            "inferred_role": {"type": ["string", "null"]},
            "reasoning": {"type": "string"},
            "supporting_excerpts": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3,
            },
        },
        "required": [
            "category",
            "confidence",
            "inferred_company",
            "inferred_role",
            "reasoning",
            "supporting_excerpts",
        ],
    }


def classify_email_with_ollama(
    email: dict,
    thread_context: list[dict] | None = None,
    config: OllamaConfig | None = None,
) -> Classification:
    obvious = _obvious_noise(email.get("subject"), email.get("snippet"), email.get("body"))
    if obvious:
        return obvious
    config = config or load_ollama_config()
    context = [
        {
            "sender": item.get("sender"),
            "subject": item.get("subject"),
            "snippet": item.get("snippet"),
            "received_at": item.get("received_at"),
        }
        for item in (thread_context or [])[-5:]
    ]
    prompt = {
        "task": (
            "Classify this email in the context of a job search. Distinguish an application receipt from "
            "a rejection, interview, assessment, recruiter outreach, request for information, offer, "
            "withdrawal confirmation, administrative update, noise, or unknown. Quoted older messages "
            "must not override the newest message. Confidence is the probability the category is correct, "
            "not confidence about which database application it belongs to."
        ),
        "email": {
            "sender": email.get("sender"),
            "subject": email.get("subject"),
            "received_at": email.get("received_at"),
            "body": (email.get("body") or email.get("snippet") or "")[:12000],
        },
        "earlier_thread_messages": context,
    }
    payload = {
        "model": config.model,
        "prompt": json.dumps(prompt, ensure_ascii=False),
        "stream": False,
        "format": _classification_schema(),
        "options": {"temperature": 0, "num_ctx": 16384},
        "keep_alive": "10m",
    }
    try:
        response = None
        last_exc: Exception | None = None
        with httpx.Client(timeout=config.timeout) as client:
            for attempt in range(3):
                if attempt:
                    time.sleep(2)
                try:
                    response = client.post(f"{config.base_url.rstrip('/')}/api/generate", json=payload)
                    response.raise_for_status()
                    break
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    response = None
                    continue
            if response is None:
                raise last_exc or RuntimeError("Ollama request failed with no response.")
            raw = response.json().get("response")
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, dict):
            raise ValueError("Ollama returned a non-object classification.")
        kind = str(parsed.get("category") or "unknown")
        if kind not in EVIDENCE_TYPES:
            raise ValueError(f"Ollama returned unsupported category: {kind}")
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0)))
        excerpts = tuple(str(value)[:240] for value in (parsed.get("supporting_excerpts") or [])[:3])
        return Classification(
            kind=kind,
            confidence=confidence,
            reason=str(parsed.get("reasoning") or "Ollama semantic classification.")[:1000],
            inferred_company=str(parsed["inferred_company"]).strip()[:200] if parsed.get("inferred_company") else None,
            inferred_role=str(parsed["inferred_role"]).strip()[:300] if parsed.get("inferred_role") else None,
            supporting_excerpts=excerpts,
            source="ollama",
            version=f"{CLASSIFIER_VERSION}:{config.model}",
        )
    except Exception as exc:
        fallback = classify_email(email.get("subject"), email.get("snippet"), email.get("body"))
        fallback.source = "rules_fallback"
        fallback.error = str(exc)[:1000]
        return fallback


def _headers(message: dict) -> dict[str, str]:
    headers = message.get("payload", {}).get("headers", [])
    return {item.get("name", "").lower(): item.get("value", "") for item in headers}


def _decode_body_part(data: str | None) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode((data + padding).encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _body_text(payload: dict) -> str:
    chunks: list[str] = []
    if payload.get("mimeType") == "text/plain":
        chunks.append(_decode_body_part(payload.get("body", {}).get("data")))
    elif payload.get("mimeType") == "text/html":
        raw = _decode_body_part(payload.get("body", {}).get("data"))
        raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
        chunks.append(re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))).strip())
    for part in payload.get("parts", []) or []:
        chunks.append(_body_text(part))
    return "\n".join(chunk for chunk in chunks if chunk)


def parse_gmail_message(message: dict) -> dict:
    headers = _headers(message)
    body = _body_text(message.get("payload", {}))
    received_at = None
    if headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            received_at = None
    if not received_at and message.get("internalDate"):
        dt = datetime.fromtimestamp(int(message["internalDate"]) / 1000, timezone.utc)
        received_at = dt.isoformat(timespec="seconds")
    return {
        "gmail_message_id": message["id"],
        "gmail_thread_id": message.get("threadId"),
        "sender": headers.get("from"),
        "subject": headers.get("subject"),
        "received_at": received_at,
        "snippet": message.get("snippet"),
        "body": body,
        "body_hash": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else None,
    }


def _tokens(value: str | None) -> set[str]:
    return {part for part in re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split() if len(part) >= 4}


def ranked_job_matches(
    conn,
    email: dict,
    classification: Classification | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    subject_tokens = _tokens(email.get("subject"))
    text_tokens = subject_tokens | _tokens(email.get("snippet")) | _tokens(
        classification.inferred_company if classification else None
    ) | _tokens(classification.inferred_role if classification else None)
    rows = conn.execute(
        """
        SELECT j.id, j.company, j.title, j.apply_url, j.source_platform, j.status,
               MAX(CASE WHEN se.status = 'applied' THEN se.created_at END) AS applied_at
        FROM jobs j
        LEFT JOIN status_events se ON se.job_id = j.id
        WHERE j.title != '__scrape_failure__'
          AND j.status IN ('applied', 'interviewing', 'rejected', 'offer')
        GROUP BY j.id
        """
    ).fetchall()
    sender = (email.get("sender") or "").lower()
    sender_domain = sender.rsplit("@", 1)[-1].split(">", 1)[0] if "@" in sender else ""
    received_at = _parse_iso(email.get("received_at"))
    candidates: list[dict[str, Any]] = []
    for row in rows:
        company_tokens = _tokens(row["company"])
        title_tokens = _tokens(row["title"])
        company_hit = bool(company_tokens & text_tokens) or any(token in sender for token in company_tokens)
        title_overlap = len(title_tokens & text_tokens)
        score = 0.0
        reasons: list[str] = []
        if company_hit:
            score += 0.5
            reasons.append("company")
        if title_tokens:
            title_ratio = title_overlap / len(title_tokens)
            score += min(0.38, title_ratio * 0.38)
            if title_overlap:
                reasons.append(f"{title_overlap} title terms")
        apply_domain = urlparse(row["apply_url"] or "").netloc.lower()
        if sender_domain and apply_domain and (
            sender_domain.endswith(apply_domain) or apply_domain.endswith(sender_domain)
        ):
            score += 0.08
            reasons.append("sender domain")
        applied_at = _parse_iso(row["applied_at"])
        if received_at and applied_at and received_at >= applied_at:
            days = (received_at - applied_at).days
            if days <= 90:
                score += 0.04
                reasons.append("application timing")
        candidates.append(
            {
                "job_id": row["id"],
                "company": row["company"],
                "title": row["title"],
                "status": row["status"],
                "applied_at": row["applied_at"],
                "confidence": round(min(score, 0.99), 3),
                "reason": ", ".join(reasons) or "weak textual overlap",
            }
        )
    candidates.sort(key=lambda item: (-item["confidence"], item["company"], item["title"]))
    return candidates[:limit]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # status_events.created_at is written both as SQLite's naive `datetime('now')`
    # default and as our own tz-aware UTC ISO strings (utc_now(), Gmail received_at).
    # Both are UTC in practice, so normalize naive values instead of leaving them
    # incomparable against aware ones (TypeError: offset-naive vs offset-aware).
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def match_email_to_job(conn, email: dict, classification: Classification | None = None) -> Match:
    candidates = ranked_job_matches(conn, email, classification)
    if not candidates or candidates[0]["confidence"] < 0.45:
        reason = candidates[0]["reason"] if candidates else "No submitted application matched."
        confidence = candidates[0]["confidence"] if candidates else 0.0
        return Match(None, confidence, reason, tuple(candidates))
    best = candidates[0]
    return Match(best["job_id"], best["confidence"], best["reason"], tuple(candidates))


def upsert_message_and_evidence(conn, account_email: str | None, email: dict) -> dict:
    thread_rows = conn.execute(
        """
        SELECT sender, subject, received_at, snippet
        FROM gmail_messages
        WHERE gmail_thread_id = ? AND gmail_message_id != ?
        ORDER BY received_at
        LIMIT 5
        """,
        (email.get("gmail_thread_id"), email["gmail_message_id"]),
    ).fetchall()
    classification = classify_email_with_ollama(
        email,
        [dict(row) for row in thread_rows],
        load_ollama_config(conn),
    )
    match = (
        match_email_to_job(conn, email, classification)
        if classification.kind != "noise"
        else Match(None, 0.0, "Noise message ignored.")
    )
    combined_confidence = round(classification.confidence * match.confidence, 3)
    conn.execute(
        """
        INSERT INTO gmail_messages (
            gmail_message_id, gmail_thread_id, account_email, sender, subject, received_at,
            snippet, body_hash, classification, confidence, matched_job_id, match_reason,
            classification_confidence, match_confidence, classifier_source, classifier_version,
            classification_reason, inferred_company, inferred_role, supporting_excerpts, classifier_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(gmail_message_id) DO UPDATE SET
            gmail_thread_id = excluded.gmail_thread_id,
            account_email = excluded.account_email,
            sender = excluded.sender,
            subject = excluded.subject,
            received_at = excluded.received_at,
            snippet = excluded.snippet,
            body_hash = excluded.body_hash,
            classification = excluded.classification,
            confidence = excluded.confidence,
            matched_job_id = excluded.matched_job_id,
            match_reason = excluded.match_reason,
            classification_confidence = excluded.classification_confidence,
            match_confidence = excluded.match_confidence,
            classifier_source = excluded.classifier_source,
            classifier_version = excluded.classifier_version,
            classification_reason = excluded.classification_reason,
            inferred_company = excluded.inferred_company,
            inferred_role = excluded.inferred_role,
            supporting_excerpts = excluded.supporting_excerpts,
            classifier_error = excluded.classifier_error
        """,
        (
            email["gmail_message_id"],
            email.get("gmail_thread_id"),
            account_email,
            email.get("sender"),
            email.get("subject"),
            email.get("received_at"),
            (email.get("snippet") or "")[:500],
            email.get("body_hash"),
            classification.kind,
            combined_confidence,
            match.job_id,
            match.reason,
            classification.confidence,
            match.confidence,
            classification.source,
            classification.version,
            classification.reason,
            classification.inferred_company,
            classification.inferred_role,
            json.dumps(classification.supporting_excerpts, ensure_ascii=False),
            classification.error,
        ),
    )
    if classification.kind not in ("noise",):
        existing = conn.execute(
            "SELECT status, corrected_by_user FROM email_evidence WHERE gmail_message_id = ?",
            (email["gmail_message_id"],),
        ).fetchone()
        preserve_review = bool(existing and (existing["status"] != "pending" or existing["corrected_by_user"]))
        target_status = EVIDENCE_STATUS_MAP.get(classification.kind)
        can_auto, automation_outcome = _automation_decision(
            conn, match.job_id, target_status, classification.confidence, match.confidence
        )
        if classification.source != "ollama":
            can_auto = False
            automation_outcome = (
                "review_classifier_error" if classification.error else "review_deterministic_classification"
            )
        evidence_status = "pending"
        if preserve_review:
            evidence_status = existing["status"]
            automation_outcome = "preserved_human_review"
        elif can_auto:
            evidence_status = "pending"
        conn.execute(
            """
            INSERT INTO email_evidence (
                gmail_message_id, job_id, evidence_type, confidence, reason, status, occurred_at,
                classification_confidence, match_confidence, original_evidence_type, original_job_id,
                automation_outcome, target_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gmail_message_id) DO UPDATE SET
                job_id = CASE WHEN email_evidence.corrected_by_user = 1 THEN email_evidence.job_id ELSE excluded.job_id END,
                evidence_type = CASE WHEN email_evidence.corrected_by_user = 1 THEN email_evidence.evidence_type ELSE excluded.evidence_type END,
                confidence = excluded.confidence,
                reason = excluded.reason,
                occurred_at = excluded.occurred_at,
                classification_confidence = CASE WHEN email_evidence.corrected_by_user = 1 THEN email_evidence.classification_confidence ELSE excluded.classification_confidence END,
                match_confidence = CASE WHEN email_evidence.corrected_by_user = 1 THEN email_evidence.match_confidence ELSE excluded.match_confidence END,
                original_evidence_type = COALESCE(email_evidence.original_evidence_type, excluded.original_evidence_type),
                original_job_id = COALESCE(email_evidence.original_job_id, excluded.original_job_id),
                automation_outcome = CASE WHEN email_evidence.corrected_by_user = 1 THEN email_evidence.automation_outcome ELSE excluded.automation_outcome END,
                target_status = CASE WHEN email_evidence.corrected_by_user = 1 THEN email_evidence.target_status ELSE excluded.target_status END
            """,
            (
                email["gmail_message_id"],
                match.job_id,
                classification.kind,
                combined_confidence,
                f"{classification.reason} Match: {match.reason}",
                evidence_status,
                email.get("received_at"),
                classification.confidence,
                match.confidence,
                classification.kind,
                match.job_id,
                automation_outcome,
                target_status,
            ),
        )
        if can_auto and not preserve_review:
            apply_evidence(conn, email["gmail_message_id"], automated=True)
    return {
        "classification": classification.kind,
        "classification_confidence": classification.confidence,
        "match_confidence": match.confidence,
        "matched_job_id": match.job_id,
        "classifier_source": classification.source,
        "classifier_error": classification.error,
    }


def _automation_decision(
    conn,
    job_id: int | None,
    target_status: str | None,
    classification_confidence: float,
    match_confidence: float,
) -> tuple[bool, str]:
    if classification_confidence < AUTO_THRESHOLD:
        return False, "review_low_classification_confidence"
    if not job_id or match_confidence < AUTO_THRESHOLD:
        return False, "review_low_match_confidence"
    if not target_status:
        return False, "informational_no_status_change"
    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return False, "review_job_missing"
    allowed = {
        "applied": {"ready", "tailoring", "applied"},
        "interviewing": {"applied", "interviewing"},
        "rejected": {"applied", "interviewing", "rejected"},
        "offer": {"applied", "interviewing", "offer"},
    }
    if row["status"] not in allowed[target_status]:
        return False, f"review_lifecycle_conflict_{row['status']}_to_{target_status}"
    return True, "auto_applied"


def update_evidence(conn, gmail_message_id: str, evidence_type: str, job_id: int | None) -> dict:
    if evidence_type not in EVIDENCE_TYPES or evidence_type == "noise":
        raise ValueError(f"Unsupported evidence type: {evidence_type}")
    if job_id is not None:
        job = conn.execute(
            """
            SELECT id FROM jobs
            WHERE id = ? AND status IN ('applied', 'interviewing', 'rejected', 'offer')
            """,
            (job_id,),
        ).fetchone()
        if not job:
            raise ValueError("Selected application was not found or has not been submitted.")
    target_status = EVIDENCE_STATUS_MAP.get(evidence_type)
    cursor = conn.execute(
        """
        UPDATE email_evidence
        SET evidence_type = ?, job_id = ?, target_status = ?, corrected_by_user = 1,
            match_confidence = CASE WHEN ? IS NULL THEN 0 ELSE 1 END,
            automation_outcome = 'human_corrected', status = 'pending', reviewed_at = NULL
        WHERE gmail_message_id = ?
        """,
        (evidence_type, job_id, target_status, job_id, gmail_message_id),
    )
    if not cursor.rowcount:
        raise ValueError(f"Email evidence not found: {gmail_message_id}")
    conn.commit()
    return {"ok": True, "evidence_type": evidence_type, "job_id": job_id, "target_status": target_status}


def apply_evidence(conn, gmail_message_id: str, automated: bool = False) -> dict:
    row = conn.execute("SELECT * FROM email_evidence WHERE gmail_message_id = ?", (gmail_message_id,)).fetchone()
    if not row:
        raise ValueError(f"Email evidence not found: {gmail_message_id}")
    target_status = EVIDENCE_STATUS_MAP.get(row["evidence_type"])
    if not target_status:
        if automated:
            raise ValueError(f"Informational evidence cannot be automatically applied: {row['evidence_type']}")
        now = utc_now()
        conn.execute(
            """
            UPDATE email_evidence
            SET status = 'applied', automation_outcome = ?, reviewed_at = ?
            WHERE gmail_message_id = ?
            """,
            ("human_corrected_applied" if row["corrected_by_user"] else "human_applied", now, gmail_message_id),
        )
        conn.execute(
            "UPDATE gmail_messages SET reviewed_at = ? WHERE gmail_message_id = ?",
            (now, gmail_message_id),
        )
        conn.commit()
        return {"ok": True, "job_id": row["job_id"], "status": None}
    if not row["job_id"]:
        raise ValueError("Evidence needs a matched job before it can update application status.")
    occurred_at = row["occurred_at"] or utc_now()
    existing_status = conn.execute("SELECT status FROM jobs WHERE id = ?", (row["job_id"],)).fetchone()
    if not existing_status:
        raise ValueError(f"Matched job not found: {row['job_id']}")
    if existing_status["status"] != target_status:
        if automated:
            can_auto, reason = _automation_decision(
                conn,
                row["job_id"],
                target_status,
                row["classification_confidence"],
                row["match_confidence"],
            )
            if not can_auto:
                raise ValueError(f"Evidence cannot be automatically applied: {reason}")
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (target_status, row["job_id"]))
        conn.execute(
            "INSERT INTO status_events (job_id, status, created_at) VALUES (?, ?, ?)",
            (row["job_id"], target_status, occurred_at),
        )
    now = utc_now()
    conn.execute(
        """
        UPDATE email_evidence
        SET status = ?, automation_outcome = ?, reviewed_at = ?
        WHERE gmail_message_id = ?
        """,
        (
            "auto_applied" if automated else "applied",
            "auto_applied" if automated else ("human_corrected_applied" if row["corrected_by_user"] else "human_applied"),
            now,
            gmail_message_id,
        ),
    )
    conn.execute(
        "UPDATE gmail_messages SET reviewed_at = ? WHERE gmail_message_id = ?",
        (now, gmail_message_id),
    )
    conn.commit()
    return {"ok": True, "job_id": row["job_id"], "status": target_status}


def reject_evidence(conn, gmail_message_id: str) -> dict:
    now = utc_now()
    conn.execute(
        "UPDATE email_evidence SET status = 'ignored', reviewed_at = ? WHERE gmail_message_id = ?",
        (now, gmail_message_id),
    )
    conn.execute(
        "UPDATE gmail_messages SET reviewed_at = ? WHERE gmail_message_id = ?",
        (now, gmail_message_id),
    )
    conn.commit()
    return {"ok": True}


def evidence_rows(conn, limit: int = 50) -> dict:
    rows = conn.execute(
        """
        SELECT ee.gmail_message_id, ee.job_id, ee.evidence_type, ee.confidence, ee.reason,
               ee.status, ee.occurred_at, ee.classification_confidence, ee.match_confidence,
               ee.original_evidence_type, ee.original_job_id, ee.corrected_by_user,
               ee.automation_outcome, ee.target_status,
               gm.sender, gm.subject, gm.snippet, gm.classifier_source, gm.classifier_version,
               gm.classification_reason, gm.inferred_company, gm.inferred_role,
               gm.supporting_excerpts, gm.classifier_error, j.company, j.title
        FROM email_evidence ee
        LEFT JOIN gmail_messages gm ON gm.gmail_message_id = ee.gmail_message_id
        LEFT JOIN jobs j ON j.id = ee.job_id
        ORDER BY
            CASE ee.status WHEN 'pending' THEN 0 WHEN 'auto_applied' THEN 1 ELSE 2 END,
            ee.occurred_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    evidence = []
    for row in rows:
        item = dict(row)
        try:
            item["supporting_excerpts"] = json.loads(item["supporting_excerpts"] or "[]")
        except json.JSONDecodeError:
            item["supporting_excerpts"] = []
        evidence.append(item)
    return {"evidence": evidence}


def evidence_candidates(conn, gmail_message_id: str, limit: int = 8) -> dict:
    row = conn.execute(
        """
        SELECT gm.sender, gm.subject, gm.snippet, gm.received_at, gm.inferred_company, gm.inferred_role
        FROM gmail_messages gm WHERE gm.gmail_message_id = ?
        """,
        (gmail_message_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Gmail message not found: {gmail_message_id}")
    classification = Classification(
        "unknown",
        0,
        "",
        inferred_company=row["inferred_company"],
        inferred_role=row["inferred_role"],
    )
    return {"candidates": ranked_job_matches(conn, dict(row), classification, limit=limit)}


def gmail_metrics(conn) -> dict:
    scalar = lambda query: conn.execute(query).fetchone()[0]
    categories = {
        row["evidence_type"]: row["count"]
        for row in conn.execute(
            "SELECT evidence_type, COUNT(*) AS count FROM email_evidence GROUP BY evidence_type"
        ).fetchall()
    }
    return {
        "scanned": scalar("SELECT COUNT(*) FROM gmail_messages"),
        "job_related": scalar("SELECT COUNT(*) FROM gmail_messages WHERE classification NOT IN ('noise', 'unknown')"),
        "auto_classified": scalar("SELECT COUNT(*) FROM gmail_messages WHERE classifier_source = 'ollama'"),
        "auto_matched": scalar("SELECT COUNT(*) FROM email_evidence WHERE job_id IS NOT NULL AND corrected_by_user = 0"),
        "auto_applied": scalar("SELECT COUNT(*) FROM email_evidence WHERE status = 'auto_applied'"),
        "pending_review": scalar("SELECT COUNT(*) FROM email_evidence WHERE status = 'pending'"),
        "corrected": scalar("SELECT COUNT(*) FROM email_evidence WHERE corrected_by_user = 1"),
        "unmatched": scalar("SELECT COUNT(*) FROM email_evidence WHERE job_id IS NULL"),
        "errors": scalar("SELECT COUNT(*) FROM gmail_messages WHERE classifier_error IS NOT NULL"),
        "categories": categories,
    }


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
    try:
        conn = init_db(connect(db_path))
    except Exception as exc:
        # No DB handle exists yet in this sub-case, so there's nowhere to
        # persist last_error -- but `running` must still be cleared, or every
        # future start_gmail_sync() call is permanently rejected as
        # already_running until the whole process restarts (the exact "stuck
        # sync blocks everything" failure mode this task exists to fix).
        with _sync_progress_lock:
            _sync_progress.error = str(exc)
            _sync_progress.running = False
        return
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
