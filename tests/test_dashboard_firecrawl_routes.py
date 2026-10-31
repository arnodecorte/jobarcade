from jobhunt import dashboard

KEY = "fc-super-secret-key-999"
DISABLED = "URL scraping is disabled. Enable it under System → Features."


def test_scrape_returns_403_when_flag_off(dashboard_server):
    status, body, _ = dashboard_server("POST", "/api/jobs/scrape", {"url": "https://example.com/job"})
    assert status == 403
    assert body == {"ok": False, "error": DISABLED}


def test_put_firecrawl_reports_configured_without_leaking_key(dashboard_server):
    status, body, text = dashboard_server("PUT", "/api/integrations/firecrawl", {"api_key": KEY})
    assert status == 200
    assert body["firecrawl"] == {"configured": True, "source": "vault"}
    assert KEY not in text
    status, body, text = dashboard_server("GET", "/api/integrations")
    assert body["firecrawl"] == {"configured": True, "source": "vault"}
    assert KEY not in text


def test_put_firecrawl_blank_key_is_400(dashboard_server):
    status, body, _ = dashboard_server("PUT", "/api/integrations/firecrawl", {"api_key": " "})
    assert status == 400


def test_firecrawl_test_route_scrubs_key_from_errors(dashboard_server, monkeypatch):
    dashboard_server("PUT", "/api/integrations/firecrawl", {"api_key": KEY})

    def boom(url, provider="auto", api_key=None):
        raise RuntimeError(f"401 Unauthorized for Bearer {api_key}")

    monkeypatch.setattr(dashboard, "extract_theme", boom)
    status, body, text = dashboard_server("POST", "/api/integrations/firecrawl/test", {})
    assert body["ok"] is False
    assert "Unauthorized" in body["error"]
    assert KEY not in text


def test_firecrawl_test_route_without_key(dashboard_server):
    _, body, _ = dashboard_server("POST", "/api/integrations/firecrawl/test", {})
    assert body["ok"] is False and "error" in body


def test_enabling_scraper_feature_unblocks_scrape(dashboard_server, monkeypatch):
    seen = {}

    def fake_scrape(url, api_key=None, **_):
        seen["api_key"] = api_key
        return {"title": "T", "url": url}

    monkeypatch.setattr(dashboard, "scrape_job_listing", fake_scrape)
    dashboard_server("PUT", "/api/integrations/firecrawl", {"api_key": KEY})
    status, body, _ = dashboard_server("PUT", "/api/features", {"scraper": True})
    assert status == 200 and body["features"] == {"scraper": True}
    status, body, _ = dashboard_server("POST", "/api/jobs/scrape", {"url": "https://example.com/job"})
    assert status == 200
    assert body["title"] == "T"
    assert seen["api_key"] == KEY


def test_delete_firecrawl_clears_key(dashboard_server):
    dashboard_server("PUT", "/api/integrations/firecrawl", {"api_key": KEY})
    status, body, text = dashboard_server("DELETE", "/api/integrations/firecrawl")
    assert status == 200
    assert body["firecrawl"] == {"configured": False, "source": "none"}
    assert KEY not in text
