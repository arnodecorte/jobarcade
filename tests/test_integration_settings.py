from __future__ import annotations

import os
import stat

import httpx
import pytest
from cryptography.fernet import Fernet

from jobhunt.database import init_db
from jobhunt.integration_settings import (
    clear_firecrawl_settings,
    clear_gmail_settings,
    decrypt_setting,
    effective_firecrawl_key,
    effective_gmail_settings,
    effective_ollama_settings,
    integration_status,
    load_or_create_master_key,
    ollama_headers,
    save_features,
    save_firecrawl_settings,
    save_gmail_settings,
    scraper_enabled,
    save_ollama_settings,
    test_ollama_settings as run_ollama_test,
    validate_ollama_url,
    validate_redirect_uri,
)


@pytest.fixture
def vault(tmp_path, monkeypatch):
    key_path = tmp_path / "config" / ".jobhunt-secrets.key"
    monkeypatch.setenv("JOBHUNT_SECRET_KEY_PATH", str(key_path))
    for name in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GMAIL_REDIRECT_URI",
        "GMAIL_TOKEN_ENCRYPTION_KEY",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "JOBHUNT_OLLAMA_URL",
        "JOBHUNT_OLLAMA_MODEL",
        "JOBHUNT_OLLAMA_API_KEY",
        "FIRECRAWL_API_KEY",
        "JOBHUNT_ENABLE_SCRAPER",
    ):
        monkeypatch.delenv(name, raising=False)
    return init_db(tmp_path / "jobs.sqlite"), key_path


def test_vault_generates_persistent_owner_only_key(vault):
    _conn, key_path = vault
    first = load_or_create_master_key()
    second = load_or_create_master_key()

    assert first == second
    assert key_path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_vault_adopts_existing_gmail_encryption_key(vault, monkeypatch):
    _conn, key_path = vault
    inherited = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("GMAIL_TOKEN_ENCRYPTION_KEY", inherited)

    assert load_or_create_master_key() == inherited
    assert key_path.read_text(encoding="ascii").strip() == inherited


def test_gmail_settings_are_encrypted_and_redacted(vault):
    conn, _key_path = vault
    status = save_gmail_settings(
        conn,
        {
            "client_id": "client-id",
            "client_secret": "super-secret",
            "redirect_uri": "https://infra.example.ts.net/api/gmail/oauth/callback",
        },
    )

    stored = conn.execute(
        "SELECT value, encrypted FROM integration_settings WHERE name = 'google_client_secret'"
    ).fetchone()
    assert stored["encrypted"] == 1
    assert stored["value"] != "super-secret"
    assert decrypt_setting(stored["value"]) == "super-secret"
    assert status["gmail"]["client_secret_set"] is True
    assert "super-secret" not in str(status)


def test_environment_credentials_can_be_imported_without_retyping_secret(vault, monkeypatch):
    conn, _key_path = vault
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "environment-secret")

    save_gmail_settings(
        conn,
        {
            "client_id": "client-id",
            "client_secret": "",
            "redirect_uri": "https://infra.example.ts.net/api/gmail/oauth/callback",
        },
    )

    assert effective_gmail_settings(conn)["source"] == "vault"
    assert effective_gmail_settings(conn)["client_secret"] == "environment-secret"


def test_clear_vault_credentials_disconnects_account(vault):
    conn, _key_path = vault
    save_gmail_settings(
        conn,
        {
            "client_id": "client-id",
            "client_secret": "secret",
            "redirect_uri": "https://infra.example.ts.net/api/gmail/oauth/callback",
        },
    )
    conn.execute(
        """
        INSERT INTO gmail_accounts (
            encrypted_refresh_token, scopes, connected_at, updated_at
        ) VALUES ('token', 'scope', 'now', 'now')
        """
    )
    conn.commit()

    clear_gmail_settings(conn)

    assert conn.execute("SELECT COUNT(*) FROM gmail_accounts").fetchone()[0] == 0
    assert integration_status(conn)["gmail"]["configured"] is False


def test_ollama_settings_persist(vault):
    conn, _key_path = vault
    save_ollama_settings(conn, {"base_url": "http://ollama-core:11434/", "model": "qwen2.5:7b"})

    status = integration_status(conn)
    assert status["ollama"]["base_url"] == "http://ollama-core:11434"
    assert status["ollama"]["model"] == "qwen2.5:7b"
    assert status["ollama"]["source"] == "vault"


@pytest.mark.parametrize(
    "value",
    [
        "http://infra.example.ts.net/api/gmail/oauth/callback",
        "https://infra.example.ts.net/wrong",
        "not-a-url",
    ],
)
def test_redirect_validation_rejects_unsafe_or_wrong_callbacks(value):
    with pytest.raises(ValueError):
        validate_redirect_uri(value)


def test_localhost_http_callback_remains_supported():
    assert (
        validate_redirect_uri("http://localhost:8765/api/gmail/oauth/callback")
        == "http://localhost:8765/api/gmail/oauth/callback"
    )


def test_ollama_url_rejects_embedded_credentials():
    with pytest.raises(ValueError):
        validate_ollama_url("http://user:password@ollama:11434")


def test_per_function_model_falls_back_to_default(vault):
    conn, _ = vault
    save_ollama_settings(conn, {"base_url": "http://ollama:11434", "model": "m1", "models": {"refine": "m2"}})
    s = effective_ollama_settings(conn)
    assert s["models"] == {"draft": "m1", "refine": "m2", "classify": "m1"}


def test_unknown_function_rejected(vault):
    conn, _ = vault
    with pytest.raises(ValueError):
        save_ollama_settings(conn, {"base_url": "http://o:1", "model": "m", "models": {"bogus": "x"}})


def test_api_key_encrypted_and_kept_when_blank(vault):
    conn, _ = vault
    save_ollama_settings(conn, {"base_url": "https://ollama.com", "model": "m", "api_key": "sk-1"})
    row = conn.execute("SELECT encrypted FROM integration_settings WHERE name='ollama_api_key'").fetchone()
    assert row["encrypted"] == 1
    save_ollama_settings(conn, {"base_url": "https://ollama.com", "model": "m", "api_key": ""})
    assert effective_ollama_settings(conn)["api_key"] == "sk-1"
    assert ollama_headers(effective_ollama_settings(conn))["Authorization"] == "Bearer sk-1"
    assert integration_status(conn)["ollama"]["api_key_set"] is True
    save_ollama_settings(conn, {"base_url": "https://ollama.com", "model": "m", "clear_api_key": True})
    assert effective_ollama_settings(conn)["api_key"] == ""
    assert "Authorization" not in ollama_headers(effective_ollama_settings(conn))


def test_api_key_cleared_when_url_moves_to_another_host(vault):
    conn, _ = vault
    status = save_ollama_settings(conn, {"base_url": "https://ollama.com", "model": "m", "api_key": "sk-1"})
    assert status["ollama"]["api_key_set"] is True
    # Same host and port (path/trailing slash changes) keeps the key.
    status = save_ollama_settings(conn, {"base_url": "https://ollama.com:443/", "model": "m2"})
    assert status["ollama"]["api_key_set"] is True
    status = save_ollama_settings(conn, {"base_url": "https://attacker.example", "model": "m"})
    assert status["ollama"]["api_key_set"] is False
    assert effective_ollama_settings(conn)["api_key"] == ""


def test_api_key_cleared_when_port_changes_but_kept_with_new_key(vault):
    conn, _ = vault
    save_ollama_settings(conn, {"base_url": "http://10.0.0.5:11434", "model": "m", "api_key": "sk-1"})
    assert save_ollama_settings(conn, {"base_url": "http://10.0.0.5:9999", "model": "m"})["ollama"]["api_key_set"] is False
    status = save_ollama_settings(conn, {"base_url": "http://10.0.0.6:11434", "model": "m", "api_key": "sk-2"})
    assert status["ollama"]["api_key_set"] is True
    assert effective_ollama_settings(conn)["api_key"] == "sk-2"


def test_save_ollama_settings_recovers_when_stored_api_key_undecryptable(vault):
    conn, key_path = vault
    save_ollama_settings(conn, {"base_url": "https://ollama.com", "model": "m", "api_key": "sk-old"})
    # Rotate vault key so the previously encrypted ollama_api_key cannot be decrypted.
    key_path.write_text(Fernet.generate_key().decode("ascii"), encoding="ascii")
    status = save_ollama_settings(conn, {"base_url": "https://ollama.com", "model": "m", "api_key": "sk-new"})
    assert status["ollama"]["api_key_set"] is True
    assert effective_ollama_settings(conn)["api_key"] == "sk-new"



def test_invalid_inherited_encryption_key_is_ignored(vault, monkeypatch, capsys):
    conn, key_path = vault
    monkeypatch.setenv("GMAIL_TOKEN_ENCRYPTION_KEY", "not-a-fernet-key")
    status = integration_status(conn)
    assert status["vault"]["ready"] is True
    key = key_path.read_text(encoding="ascii").strip()
    assert key != "not-a-fernet-key"
    Fernet(key.encode("ascii"))
    assert "GMAIL_TOKEN_ENCRYPTION_KEY" in capsys.readouterr().err


def test_invalid_inherited_key_does_not_break_integrations_route(dashboard_server, monkeypatch):
    monkeypatch.setenv("GMAIL_TOKEN_ENCRYPTION_KEY", "garbage")
    status, body, _ = dashboard_server("GET", "/api/integrations")
    assert status == 200 and body["vault"]["ready"] is True


def test_api_key_env_fallback(vault, monkeypatch):
    conn, _ = vault
    monkeypatch.setenv("JOBHUNT_OLLAMA_API_KEY", "env-key")
    assert effective_ollama_settings(conn)["api_key"] == "env-key"


def test_unreachable_ollama_returns_error_quickly(vault):
    conn, _ = vault
    save_ollama_settings(conn, {"base_url": "http://127.0.0.1:9", "model": "m"})
    result = run_ollama_test(conn)
    assert result["ok"] is False and result["models"] == [] and result["error"]


def test_defaults_point_at_host_docker_internal(vault):
    conn, _ = vault
    s = effective_ollama_settings(conn)
    assert s["base_url"] == "http://host.docker.internal:11434" and s["model"] == "qwen2.5:7b"


def test_test_call_lists_models(vault, monkeypatch):
    conn, _ = vault

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "b"}, {"name": "a"}]}

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: FakeResponse())
    result = run_ollama_test(conn)
    assert result["ok"] is True and result["models"] == ["a", "b"]


def test_firecrawl_key_vault_beats_env(vault, monkeypatch):
    conn, _ = vault
    monkeypatch.setenv("FIRECRAWL_API_KEY", "env")
    status = integration_status(conn)
    assert status["firecrawl"] == {"configured": True, "source": "environment"}
    assert effective_firecrawl_key(conn) == "env"

    status = save_firecrawl_settings(conn, {"api_key": "vault"})
    assert effective_firecrawl_key(conn) == "vault"
    assert status["firecrawl"] == {"configured": True, "source": "vault"}

    status = clear_firecrawl_settings(conn)
    assert effective_firecrawl_key(conn) == "env"
    assert status["firecrawl"]["source"] == "environment"


def test_firecrawl_key_none_when_unset_and_required(vault):
    conn, _ = vault
    assert integration_status(conn)["firecrawl"] == {"configured": False, "source": "none"}
    with pytest.raises(ValueError):
        save_firecrawl_settings(conn, {"api_key": "  "})


def test_firecrawl_key_stored_encrypted(vault):
    conn, _ = vault
    status = save_firecrawl_settings(conn, {"api_key": "fc-secret-123"})
    row = conn.execute(
        "SELECT value, encrypted FROM integration_settings WHERE name = 'firecrawl_api_key'"
    ).fetchone()
    assert row["encrypted"] == 1
    assert "fc-secret-123" not in row["value"]
    assert decrypt_setting(row["value"]) == "fc-secret-123"
    assert "fc-secret-123" not in str(status)


def test_scraper_disabled_by_default_and_toggleable(vault, monkeypatch):
    conn, _ = vault
    assert scraper_enabled(conn) is False
    assert integration_status(conn)["features"] == {"scraper": False}
    assert save_features(conn, {"scraper": True})["features"] == {"scraper": True}
    assert scraper_enabled(conn) is True
    assert save_features(conn, {"scraper": False})["features"] == {"scraper": False}
    monkeypatch.setenv("JOBHUNT_ENABLE_SCRAPER", "1")
    assert scraper_enabled(conn) is True
