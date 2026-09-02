from __future__ import annotations

import httpx

from jobhunt import font_theme
from jobhunt.font_theme import font_paths_for_theme, resolve_typography


def test_resolve_typography_uses_local_safe_font():
    result = resolve_typography({"primary": "Georgia"})

    assert result.body.enabled is True
    assert result.body.source == "local"
    assert result.body.stack[0] == "Georgia"
    # No distinct heading label given -> heading mirrors body's resolution.
    assert result.heading is result.body


def test_resolve_typography_downloads_curated_google_alternative(tmp_path, monkeypatch):
    monkeypatch.setattr(font_theme, "ROOT", tmp_path)
    monkeypatch.setattr(font_theme, "FONTS_DIR", tmp_path / "fonts" / "chameleon")

    def fake_get(url, **kwargs):
      if url == font_theme.GOOGLE_FONTS_METADATA_URL:
          return httpx.Response(503, request=httpx.Request("GET", url))
      if url.endswith("/ofl/inter"):
          return httpx.Response(
              200,
              request=httpx.Request("GET", url),
              json=[
                  {
                      "name": "Inter-Regular.ttf",
                      "download_url": "https://example.com/Inter-Regular.ttf",
                  }
              ],
          )
      if url == "https://example.com/Inter-Regular.ttf":
          return httpx.Response(200, request=httpx.Request("GET", url), content=b"fake-font")
      return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(font_theme.httpx, "get", fake_get)

    result = resolve_typography({"primary": "Netflix Sans"})

    assert result.body.enabled is True
    assert result.body.source == "google_fonts"
    assert result.body.family == "Inter"
    assert result.body.stack[0] == "Inter"
    assert (tmp_path / "fonts" / "chameleon" / "inter" / "Inter-Regular.ttf").exists()


def test_resolve_typography_falls_back_when_no_match(monkeypatch):
    def fake_get(url, **kwargs):
        if url == font_theme.GOOGLE_FONTS_METADATA_URL:
            return httpx.Response(200, json={"familyMetadataList": [{"family": "Inter"}]})
        return httpx.Response(404)

    monkeypatch.setattr(font_theme.httpx, "get", fake_get)

    result = resolve_typography({"primary": "Mystery Corporate Sans"})

    assert result.body.enabled is False
    assert result.body.source == "fallback"
    assert result.body.stack == font_theme.DEFAULT_STACK


def test_resolve_typography_resolves_distinct_heading_and_body_families():
    result = resolve_typography({"primary": "Georgia", "heading": "Verdana"})

    assert result.body.family == "Georgia"
    assert result.heading.family == "Verdana"
    assert result.body.enabled is True
    assert result.heading.enabled is True


def test_resolve_typography_reads_font_weights():
    result = resolve_typography({"primary": "Georgia", "weights": {"regular": 350, "medium": 480, "bold": 750}})

    assert result.body_weight == 350
    assert result.subheading_weight == 480
    assert result.heading_weight == 750


def test_resolve_typography_defaults_weights_when_missing():
    result = resolve_typography({"primary": "Georgia"})

    assert result.body_weight == 400
    assert result.subheading_weight == 500
    assert result.heading_weight == 700


def test_resolve_typography_clamps_out_of_range_weights():
    result = resolve_typography({"primary": "Georgia", "weights": {"regular": 50, "medium": "nonsense", "bold": 1200}})

    assert result.body_weight == 100
    assert result.subheading_weight == 500  # invalid -> default
    assert result.heading_weight == 900


def test_as_theme_tokens_nests_resolution_and_includes_weights():
    result = resolve_typography({"primary": "Georgia", "heading": "Verdana", "weights": {"regular": 400, "medium": 500, "bold": 700}})
    tokens = result.as_theme_tokens()

    assert tokens["body_font"][0] == "Georgia"
    assert tokens["heading_font"][0] == "Verdana"
    assert tokens["body_weight"] == 400
    assert tokens["subheading_weight"] == 500
    assert tokens["heading_weight"] == 700
    assert tokens["typography_resolution"]["body"]["family"] == "Georgia"
    assert tokens["typography_resolution"]["heading"]["family"] == "Verdana"


def test_as_theme_tokens_heading_falls_back_to_resolved_body_stack(monkeypatch):
    # heading family can't be resolved (no local/Google match), body can.
    def fake_get(url, **kwargs):
        if url == font_theme.GOOGLE_FONTS_METADATA_URL:
            return httpx.Response(200, json={"familyMetadataList": []})
        return httpx.Response(404)

    monkeypatch.setattr(font_theme.httpx, "get", fake_get)

    result = resolve_typography({"primary": "Georgia", "heading": "Totally Unknown Face"})
    tokens = result.as_theme_tokens()

    assert result.heading.enabled is False
    # Heading inherits the body's *resolved* stack, not the generic default.
    assert tokens["heading_font"] == tokens["body_font"]
    assert tokens["heading_font"][0] == "Georgia"


def test_font_paths_for_theme_returns_two_distinct_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(font_theme, "ROOT", tmp_path)
    body_dir = tmp_path / "fonts" / "chameleon" / "georgia"
    heading_dir = tmp_path / "fonts" / "chameleon" / "verdana"
    body_dir.mkdir(parents=True)
    heading_dir.mkdir(parents=True)
    (body_dir / "Georgia-Regular.ttf").write_text("fake", encoding="utf-8")
    (heading_dir / "Verdana-Regular.ttf").write_text("fake", encoding="utf-8")

    theme = {
        "typography_enabled": True,
        "fallback": False,
        "typography_resolution": {
            "body": {"font_path": "fonts/chameleon/georgia"},
            "heading": {"font_path": "fonts/chameleon/verdana"},
        },
    }

    paths = font_paths_for_theme(theme)

    assert len(paths) == 2
    assert body_dir.resolve() in paths
    assert heading_dir.resolve() in paths


def test_font_paths_for_theme_dedupes_same_family(tmp_path, monkeypatch):
    monkeypatch.setattr(font_theme, "ROOT", tmp_path)
    font_dir = tmp_path / "fonts" / "chameleon" / "inter"
    font_dir.mkdir(parents=True)
    (font_dir / "Inter-Regular.ttf").write_text("fake", encoding="utf-8")

    theme = {
        "typography_enabled": True,
        "fallback": False,
        "typography_resolution": {
            "body": {"font_path": "fonts/chameleon/inter"},
            "heading": {"font_path": "fonts/chameleon/inter"},
        },
    }

    paths = font_paths_for_theme(theme)

    assert len(paths) == 1
    assert paths[0] == font_dir.resolve()


def test_font_paths_for_theme_supports_legacy_flat_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(font_theme, "ROOT", tmp_path)
    font_dir = tmp_path / "fonts" / "chameleon" / "inter"
    font_dir.mkdir(parents=True)
    (font_dir / "Inter-Regular.ttf").write_text("fake", encoding="utf-8")

    # Real shape from Applications/Netflix-Art-Print-Producer/brand-theme.yaml
    theme = {
        "typography_enabled": True,
        "fallback": False,
        "typography_resolution": {
            "source": "google_fonts",
            "requested": "Netflix Sans",
            "family": "Inter",
            "font_path": "fonts/chameleon/inter",
            "notes": ["Font not found on Google Fonts; using vetted alternative for Netflix Sans."],
            "warnings": [],
        },
    }

    paths = font_paths_for_theme(theme)

    assert len(paths) == 1
    assert paths[0] == font_dir.resolve()
