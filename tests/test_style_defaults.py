import shutil

import pytest

from jobhunt import style_defaults as sd


def test_default_style_unconfigured_returns_base(tmp_path):
    style = sd.read_default_style(tmp_path / "missing.yaml")
    assert style == {
        "cv_variant": "grotesk_one_page",
        "accent": sd.BASE_THEME["accent"],
        "font": "Default",
        "mode": "light",
        "configured": False,
    }


def test_default_theme_path_follows_patched_profile_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sd.profile_module, "DEFAULT_PROFILE_PATH", tmp_path / "profile.yaml")
    assert sd.default_theme_path() == tmp_path / "default-theme.yaml"


def test_build_default_theme_rejects_pale_accent(tmp_path):
    target = tmp_path / "default-theme.yaml"
    sd.save_default_style({"cv_variant": "classic_two_page", "accent": "#1F4E79"}, target)
    before = target.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="too light or low-contrast"):
        sd.build_default_theme({"cv_variant": "classic_two_page", "accent": "#F5F5F5"})
    with pytest.raises(ValueError, match="too light or low-contrast"):
        sd.save_default_style({"cv_variant": "grotesk_one_page", "accent": "#F5F5F5"}, target)
    assert target.read_text(encoding="utf-8") == before


def test_build_default_theme_rejects_unknown_variant_and_font():
    with pytest.raises(ValueError, match="variant"):
        sd.build_default_theme({"cv_variant": "nope", "accent": "#1F4E79"})
    with pytest.raises(ValueError, match="Font"):
        sd.build_default_theme({"cv_variant": "grotesk_one_page", "accent": "#1F4E79", "font": "Comic Sans"})


def test_save_then_read_round_trip(tmp_path):
    target = tmp_path / "default-theme.yaml"
    sd.save_default_style({"cv_variant": "classic_two_page", "accent": "#1F4E79"}, target)
    style = sd.read_default_style(target)
    assert style["cv_variant"] == "classic_two_page"
    assert style["accent"].startswith("#") and len(style["accent"]) == 7  # sanitize_theme may deepen it
    assert style["configured"] is True
    assert style["font"] == "Default" and style["mode"] == "light"


def test_font_failure_falls_back_to_default_with_warning(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(sd, "resolve_typography", boom)
    result = sd.save_default_style({"cv_variant": "grotesk_one_page", "accent": "#1F4E79", "font": "Inter"}, tmp_path / "t.yaml")
    assert result["font"] == "Default"
    assert result["warnings"]


@pytest.mark.skipif(not shutil.which("typst"), reason="typst not installed")
def test_render_preview_returns_png():
    png = sd.render_style_preview({"cv_variant": "classic_two_page", "accent": "#1F4E79", "font": "Default"})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_style_routes(dashboard_server, tmp_path, monkeypatch):
    monkeypatch.setattr(sd.profile_module, "DEFAULT_PROFILE_PATH", tmp_path / "profile.yaml")
    status, body, _ = dashboard_server("GET", "/api/style")
    assert status == 200 and body["configured"] is False
    assert "classic_two_page" in body["variants"] and "Inter" in body["fonts"]
    status, body, _ = dashboard_server("PUT", "/api/style", {"cv_variant": "classic_two_page", "accent": "#1F4E79"})
    assert status == 200 and body["configured"] is True
    before = (tmp_path / "default-theme.yaml").read_text(encoding="utf-8")
    status, body, _ = dashboard_server("PUT", "/api/style", {"cv_variant": "classic_two_page", "accent": "#F5F5F5"})
    assert status == 400 and "low-contrast" in body["error"]
    assert (tmp_path / "default-theme.yaml").read_text(encoding="utf-8") == before
    status, body, _ = dashboard_server("POST", "/api/style/preview", {"cv_variant": "nope"})
    assert status == 400


@pytest.mark.skipif(not shutil.which("typst"), reason="typst not installed")
def test_preview_route_returns_png(dashboard_server):
    status, _body, _text = dashboard_server("POST", "/api/style/preview", {"cv_variant": "grotesk_one_page", "accent": "#1F4E79"})
    assert status == 200
    assert dashboard_server.last_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert dashboard_server.last_content_type == "image/png"
