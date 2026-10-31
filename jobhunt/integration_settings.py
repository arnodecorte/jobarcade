from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from jobhunt.database import utc_now

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY_PATH = ROOT / "config" / ".jobhunt-secrets.key"


def secret_key_path() -> Path:
    return Path(os.environ.get("JOBHUNT_SECRET_KEY_PATH", str(DEFAULT_KEY_PATH)))


def load_or_create_master_key() -> str:
    path = secret_key_path()
    if path.exists():
        return path.read_text(encoding="ascii").strip()
    inherited = os.environ.get("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip()
    key = inherited or Fernet.generate_key().decode("ascii")
    Fernet(key.encode("ascii"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding="ascii").strip()
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(key + "\n")
    return key


def encrypt_setting(value: str) -> str:
    cipher = Fernet(load_or_create_master_key().encode("ascii"))
    return cipher.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_setting(value: str) -> str:
    try:
        cipher = Fernet(load_or_create_master_key().encode("ascii"))
        return cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored integration secret cannot be decrypted with the current vault key.") from exc


def _row(conn, name: str):
    return conn.execute(
        "SELECT value, encrypted, updated_at FROM integration_settings WHERE name = ?",
        (name,),
    ).fetchone()


def get_setting(conn, name: str, default: str = "") -> str:
    row = _row(conn, name)
    if not row:
        return default
    return decrypt_setting(row["value"]) if row["encrypted"] else row["value"]


def has_setting(conn, name: str) -> bool:
    row = _row(conn, name)
    return bool(row and row["value"])


def set_setting(conn, name: str, value: str, *, encrypted: bool = False) -> None:
    stored = encrypt_setting(value) if encrypted else value
    conn.execute(
        """
        INSERT INTO integration_settings (name, value, encrypted, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            value = excluded.value,
            encrypted = excluded.encrypted,
            updated_at = excluded.updated_at
        """,
        (name, stored, int(encrypted), utc_now()),
    )


def delete_settings(conn, names: tuple[str, ...]) -> None:
    placeholders = ",".join("?" for _ in names)
    conn.execute(f"DELETE FROM integration_settings WHERE name IN ({placeholders})", names)


def effective_gmail_settings(conn) -> dict:
    saved_client_id = get_setting(conn, "google_client_id")
    saved_redirect = get_setting(conn, "gmail_redirect_uri")
    saved_secret = get_setting(conn, "google_client_secret") if has_setting(conn, "google_client_secret") else ""
    return {
        "client_id": saved_client_id or os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": saved_secret or os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "redirect_uri": saved_redirect or os.environ.get("GMAIL_REDIRECT_URI", "").strip(),
        "source": "vault" if saved_client_id or saved_secret or saved_redirect else "environment",
    }


OLLAMA_FUNCTIONS = ("draft", "refine", "classify")


def effective_ollama_settings(conn) -> dict:
    saved_url = get_setting(conn, "ollama_base_url")
    saved_model = get_setting(conn, "ollama_model")
    saved_key = get_setting(conn, "ollama_api_key") if has_setting(conn, "ollama_api_key") else ""
    model = (
        saved_model
        or os.environ.get("OLLAMA_MODEL", "").strip()
        or os.environ.get("JOBHUNT_OLLAMA_MODEL", "").strip()
        or "qwen2.5:7b"
    )
    models = {
        name: get_setting(conn, f"ollama_model_{name}").strip() or model for name in OLLAMA_FUNCTIONS
    }
    return {
        "base_url": saved_url
        or os.environ.get("OLLAMA_BASE_URL", "").strip()
        or os.environ.get("JOBHUNT_OLLAMA_URL", "").strip()
        or "http://host.docker.internal:11434",
        "model": model,
        "api_key": saved_key or os.environ.get("JOBHUNT_OLLAMA_API_KEY", "").strip(),
        "models": models,
        "source": "vault" if saved_url or saved_model else "environment",
    }


def ollama_headers(settings: dict) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    return headers


def validate_redirect_uri(value: str) -> str:
    parsed = urlparse(value.strip())
    localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    allowed_schemes = {"http", "https"} if localhost else {"https"}
    if parsed.scheme not in allowed_schemes:
        raise ValueError("OAuth callback must use HTTPS, except for localhost development.")
    if not parsed.netloc or parsed.path != "/api/gmail/oauth/callback":
        raise ValueError("OAuth callback must end with /api/gmail/oauth/callback.")
    return value.strip()


def validate_ollama_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Ollama URL must be a valid HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("Do not embed credentials in the Ollama URL.")
    return value.strip().rstrip("/")


def save_gmail_settings(conn, payload: dict) -> dict:
    current = effective_gmail_settings(conn)
    client_id = str(payload.get("client_id") or "").strip()
    redirect_uri = validate_redirect_uri(str(payload.get("redirect_uri") or ""))
    submitted_secret = str(payload.get("client_secret") or "")
    client_secret = submitted_secret or current["client_secret"]
    if not client_id:
        raise ValueError("Google client ID is required.")
    if not client_secret:
        raise ValueError("Google client secret is required.")
    set_setting(conn, "google_client_id", client_id)
    set_setting(conn, "gmail_redirect_uri", redirect_uri)
    if submitted_secret or not has_setting(conn, "google_client_secret"):
        set_setting(conn, "google_client_secret", client_secret, encrypted=True)
    conn.commit()
    return integration_status(conn)


def clear_gmail_settings(conn) -> dict:
    delete_settings(conn, ("google_client_id", "google_client_secret", "gmail_redirect_uri"))
    conn.execute("DELETE FROM gmail_accounts")
    conn.commit()
    return integration_status(conn)


def save_ollama_settings(conn, payload: dict) -> dict:
    base_url = validate_ollama_url(str(payload.get("base_url") or ""))
    model = str(payload.get("model") or "").strip()
    if not model:
        raise ValueError("Ollama model is required.")
    models = payload.get("models") or {}
    if not isinstance(models, dict):
        raise ValueError("models must be an object mapping function to model name.")
    unknown = sorted(set(models) - set(OLLAMA_FUNCTIONS))
    if unknown:
        raise ValueError(f"Unknown Ollama function: {', '.join(map(str, unknown))}.")
    set_setting(conn, "ollama_base_url", base_url)
    set_setting(conn, "ollama_model", model)
    for name in OLLAMA_FUNCTIONS:
        if name in models:
            value = str(models[name] or "").strip()
            if value:
                set_setting(conn, f"ollama_model_{name}", value)
            else:
                delete_settings(conn, (f"ollama_model_{name}",))
    api_key = str(payload.get("api_key") or "").strip()
    if payload.get("clear_api_key"):
        delete_settings(conn, ("ollama_api_key",))
    elif api_key:
        set_setting(conn, "ollama_api_key", api_key, encrypted=True)
    conn.commit()
    return integration_status(conn)


def test_ollama_settings(conn) -> dict:
    settings = effective_ollama_settings(conn)
    try:
        with httpx.Client(timeout=8) as client:
            response = client.get(f"{settings['base_url']}/api/tags", headers=ollama_headers(settings))
            response.raise_for_status()
            names = sorted(
                {
                    item.get("name") or item.get("model")
                    for item in response.json().get("models", [])
                    if item.get("name") or item.get("model")
                }
            )
        present = any(settings["model"] in name for name in names)
        return {"ok": True, "model": settings["model"], "model_present": present, "models": names}
    except Exception as exc:
        return {
            "ok": False,
            "model": settings["model"],
            "model_present": False,
            "models": [],
            "error": str(exc)[:500],
        }


def integration_status(conn, suggested_redirect_uri: str | None = None) -> dict:
    load_or_create_master_key()
    gmail = effective_gmail_settings(conn)
    ollama = effective_ollama_settings(conn)
    callback = gmail["redirect_uri"] or suggested_redirect_uri or ""
    path = secret_key_path()
    return {
        "gmail": {
            "configured": all((gmail["client_id"], gmail["client_secret"], callback)),
            "client_id": gmail["client_id"],
            "client_secret_set": bool(gmail["client_secret"]),
            "redirect_uri": callback,
            "source": gmail["source"],
        },
        "ollama": {
            "base_url": ollama["base_url"],
            "model": ollama["model"],
            "models": ollama["models"],
            "api_key_set": bool(ollama["api_key"]),
            "source": ollama["source"],
        },
        "vault": {
            "ready": True,
            "key_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else "external",
        },
    }
