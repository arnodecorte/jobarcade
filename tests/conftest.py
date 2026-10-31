import pytest

from jobhunt import profile as profile_module


@pytest.fixture(autouse=True)
def _isolated_search_rules(tmp_path_factory, monkeypatch):
    """Keep tests independent of a local config/profile.yaml and of cached search rules."""
    missing = tmp_path_factory.mktemp("no-profile") / "profile.yaml"
    monkeypatch.setattr(profile_module, "DEFAULT_PROFILE_PATH", missing)
    profile_module._RULES_CACHE.clear()
    yield
    profile_module._RULES_CACHE.clear()


@pytest.fixture
def dashboard_server(tmp_path, monkeypatch):
    """Run the real dashboard handler on an ephemeral port with an isolated DB and vault.

    Returns ``request(method, path, body=None) -> (status, parsed_json, raw_text)``.
    """
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from jobhunt import dashboard

    monkeypatch.setattr(dashboard, "DB_PATH", tmp_path / "jobs.sqlite")
    monkeypatch.setenv("JOBHUNT_SECRET_KEY_PATH", str(tmp_path / "config" / ".jobhunt-secrets.key"))
    for name in ("FIRECRAWL_API_KEY", "JOBHUNT_ENABLE_SCRAPER", "GMAIL_TOKEN_ENCRYPTION_KEY"):
        monkeypatch.delenv(name, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def request(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status, text = resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            status, text = exc.code, exc.read().decode()
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = None
        return status, parsed, text

    yield request
    server.shutdown()
    server.server_close()
