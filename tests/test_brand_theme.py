from __future__ import annotations

import httpx

from jobhunt import brand_theme
from jobhunt.brand_theme import extract_theme_from_html, extract_theme_with_firecrawl, read_theme, sanitize_theme, write_theme


def test_sanitize_theme_falls_back_for_low_confidence():
    result = sanitize_theme({"enabled": True, "accent": "#FF00FF", "confidence": 0.1})

    assert result.theme["fallback"] is True
    assert result.theme["accent"] == "#C41230"
    assert result.warnings


def test_sanitize_theme_darkens_light_accent_for_readability():
    result = sanitize_theme({"enabled": True, "accent": "#66CCFF", "confidence": 0.9})

    assert result.theme["fallback"] is False
    assert result.theme["accent"] != "#66CCFF"


def test_extract_theme_from_html_uses_meta_and_css_colors():
    html = """
    <html>
      <head><meta name="theme-color" content="#0057ff"></head>
      <style>:root { --brand-color: #0057ff; color: #111111; }</style>
    </html>
    """

    result = extract_theme_from_html(html, "https://example.com/careers")

    assert result.theme["enabled"] is True
    assert result.theme["fallback"] is False
    assert result.theme["source_url"] == "https://example.com/careers"
    assert result.theme["confidence"] >= 0.5


def test_write_and_read_theme_round_trip(tmp_path):
    write_theme(tmp_path, {"enabled": True, "accent": "#0057FF", "confidence": 0.8, "notes": ["ok"]})

    theme = read_theme(tmp_path)

    assert theme
    assert theme["enabled"] is True
    assert theme["fallback"] is False
    assert theme["notes"] == ["ok"]


def test_write_and_read_theme_preserves_dark_mode_tokens(tmp_path):
    write_theme(
        tmp_path,
        {
            "enabled": True,
            "mode": "dark",
            "accent": "#E50914",
            "accent_dark": "#FFFFFF",
            "muted": "#B3B3B3",
            "page_bg": "#000000",
            "soft_bg": "#141414",
            "rule": "#333333",
            "link": "#E50914",
            "confidence": 0.8,
            "light_tokens": {"soft_bg": "#F5EBEB", "rule": "#DEC4C6"},
        },
    )

    theme = read_theme(tmp_path)

    assert theme
    assert theme["mode"] == "dark"
    assert theme["page_bg"] == "#000000"
    assert theme["muted"] == "#B3B3B3"
    assert theme["accent_dark"] == "#FFFFFF"
    assert theme["light_tokens"]["soft_bg"] == "#F5EBEB"


def test_extract_theme_from_url_uses_browser_like_user_agent(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "<html></html>"
        url = "https://tesla.com"

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(brand_theme.httpx, "Client", FakeClient)

    brand_theme.extract_theme_from_url("https://tesla.com")

    user_agent = captured["headers"].get("User-Agent", "")
    assert "SomeBot" not in user_agent, "bot-labeled UA trips Akamai on sites like tesla.com"
    assert "Mozilla" in user_agent


def test_extract_theme_auto_surfaces_both_errors_when_local_fallback_also_fails(monkeypatch):
    def fake_firecrawl(url, *args, **kwargs):
        raise ValueError("firecrawl boom")

    def fake_local(url, *args, **kwargs):
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError(
            "Client error '403 Forbidden' for url 'https://tesla.com'",
            request=request,
            response=httpx.Response(403, request=request),
        )

    monkeypatch.setattr(brand_theme, "extract_theme_with_firecrawl", fake_firecrawl)
    monkeypatch.setattr(brand_theme, "extract_theme_from_url", fake_local)

    try:
        brand_theme.extract_theme("https://tesla.com", provider="auto")
        raised = None
    except Exception as exc:
        raised = exc

    assert raised is not None, "expected extract_theme to raise when both providers fail"
    message = str(raised)
    assert "firecrawl boom" in message, "original Firecrawl error must not be swallowed"
    assert "403" in message


def test_describe_error_includes_status_code_and_response_body():
    request = httpx.Request("POST", "https://api.firecrawl.dev/v2/scrape")
    response = httpx.Response(429, request=request, text='{"error":"Rate limit exceeded"}')
    exc = httpx.HTTPStatusError("429 rate limited", request=request, response=response)

    description = brand_theme._describe_error(exc)

    assert "429" in description
    assert "Rate limit exceeded" in description
    assert "api.firecrawl.dev" in description


def test_firecrawl_branding_maps_to_chameleon_tokens(monkeypatch):
    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.firecrawl.dev/v2/scrape"),
            json={
                "data": {
                    "metadata": {"sourceURL": "https://www.netflix.com"},
                    "branding": {
                        "colorScheme": "dark",
                        "colors": {
                            "primary": "#E50914",
                            "background": "#141414",
                            "textPrimary": "#FFFFFF",
                            "textSecondary": "#B3B3B3",
                        },
                        "typography": {
                            "fontFamilies": {"primary": "Netflix Sans", "heading": "Bebas Neue"},
                            "fontWeights": {"regular": 400, "medium": 500, "bold": 700},
                        },
                    },
                }
            },
        )

    monkeypatch.setattr(brand_theme.httpx, "post", fake_post)

    result = extract_theme_with_firecrawl("https://www.netflix.com", api_key="fc-test")

    assert result.theme["provider"] == "firecrawl"
    assert result.theme["accent"].startswith("#")
    assert result.theme["accent"] != "#C41230"
    assert result.theme["typography"]["primary"] == "Netflix Sans"
    assert result.theme["typography"]["heading"] == "Bebas Neue"
    assert result.theme["typography"]["primary"] != result.theme["typography"]["heading"]
    assert result.theme["typography"]["weights"] == {"regular": 400, "medium": 500, "bold": 700}
    assert result.theme["energy"] == "dark"
    assert result.theme["dark_recommended"] is True


def test_sanitize_theme_passes_through_weight_fields():
    result = sanitize_theme(
        {
            "enabled": True,
            "accent": "#0057FF",
            "confidence": 0.9,
            "body_weight": 350,
            "subheading_weight": 480,
            "heading_weight": 750,
        }
    )

    assert result.theme["fallback"] is False
    assert result.theme["body_weight"] == 350
    assert result.theme["subheading_weight"] == 480
    assert result.theme["heading_weight"] == 750


def test_sanitize_theme_defaults_weight_fields_when_missing():
    result = sanitize_theme({"enabled": True, "accent": "#0057FF", "confidence": 0.9})

    assert result.theme["body_weight"] == 400
    assert result.theme["subheading_weight"] == 500
    assert result.theme["heading_weight"] == 700


def test_sanitize_theme_defaults_weight_fields_in_fallback_branch():
    # Low confidence -> takes the fallback branch of sanitize_theme.
    result = sanitize_theme({"enabled": True, "accent": "#FF00FF", "confidence": 0.1})

    assert result.theme["fallback"] is True
    assert result.theme["body_weight"] == 400
    assert result.theme["subheading_weight"] == 500
    assert result.theme["heading_weight"] == 700


def test_sanitize_theme_preserves_nested_typography_resolution():
    nested = {
        "body": {"source": "local", "family": "Georgia", "font_path": ""},
        "heading": {"source": "google_fonts", "family": "Verdana", "font_path": "fonts/chameleon/verdana"},
    }
    result = sanitize_theme(
        {
            "enabled": True,
            "accent": "#0057FF",
            "confidence": 0.9,
            "typography_resolution": nested,
        }
    )

    assert result.theme["typography_resolution"] == nested
