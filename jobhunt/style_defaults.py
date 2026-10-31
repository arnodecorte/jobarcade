"""Default CV style (variant, accent, font, light/dark) and live Typst preview."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from jobhunt import profile as profile_module
from jobhunt.brand_theme import BASE_THEME, sanitize_theme
from jobhunt.config import ROOT
from jobhunt.font_theme import font_paths_for_theme, resolve_typography

CV_VARIANTS = ("grotesk_one_page", "compact_one_page", "classic_two_page", "enriched_two_page")
DEFAULT_THEME_PATH = ROOT / "config" / "default-theme.yaml"
STYLE_FONTS = ("Default", "Roboto", "Inter", "IBM Plex Sans", "Source Serif 4", "Lora")
CONTRAST_MESSAGE = "That colour is too light or low-contrast to read on a CV — pick a deeper shade."
DEFAULT_VARIANT = "grotesk_one_page"


def default_theme_path() -> Path:
    """Default theme sits next to the active profile; resolved at call time."""
    return profile_module.DEFAULT_PROFILE_PATH.parent / "default-theme.yaml"


def _resolve(path: Path | None) -> Path:
    return Path(path) if path is not None else default_theme_path()


def _unconfigured() -> dict:
    return {
        "cv_variant": DEFAULT_VARIANT,
        "accent": BASE_THEME["accent"],
        "font": "Default",
        "mode": "light",
        "configured": False,
    }


def read_default_style(path: Path | None = None) -> dict:
    target = _resolve(path)
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return _unconfigured()
    if not isinstance(raw, dict):
        return _unconfigured()
    style = _unconfigured()
    if raw.get("cv_variant") in CV_VARIANTS:
        style["cv_variant"] = raw["cv_variant"]
    if isinstance(raw.get("accent"), str) and raw["accent"]:
        style["accent"] = raw["accent"]
    style["mode"] = "dark" if raw.get("mode") == "dark" else "light"
    style["font"] = raw["style_font"] if raw.get("style_font") in STYLE_FONTS else "Default"
    style["configured"] = True
    return style


def build_default_theme(style: dict) -> dict:
    """Pure: validate a style request and return the theme dict plus ``cv_variant``."""
    style = style if isinstance(style, dict) else {}
    variant = style.get("cv_variant") or DEFAULT_VARIANT
    if variant not in CV_VARIANTS:
        raise ValueError(f"CV variant must be one of: {', '.join(CV_VARIANTS)}.")
    font = style.get("font") or "Default"
    if font not in STYLE_FONTS:
        raise ValueError(f"Font must be one of: {', '.join(STYLE_FONTS)}.")
    mode = style.get("mode") or "light"
    if mode not in ("light", "dark"):
        raise ValueError("Mode must be light or dark.")
    accent = style.get("accent") or BASE_THEME["accent"]
    result = sanitize_theme(
        {
            "accent": accent,
            "confidence": 1.0,
            "enabled": True,
            "provider": "default",
            "mode": mode,
            "typography_enabled": font != "Default",
            "body_font": [font],
            "heading_font": [font],
        }
    )
    if result.theme.get("fallback") or any("contrast" in w.lower() for w in result.warnings):
        raise ValueError(CONTRAST_MESSAGE)
    theme = dict(result.theme)
    theme["cv_variant"] = variant
    theme["style_font"] = font
    return theme


def _write_atomic(path: Path, theme: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".default-theme-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(theme, handle, sort_keys=False, allow_unicode=True)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _with_typography(theme: dict) -> tuple[dict, list[str]]:
    """Resolve a non-default font; any failure falls back to the template font."""
    warnings: list[str] = []
    font = theme.get("style_font", "Default")
    if font == "Default":
        return theme, warnings
    try:
        resolution = resolve_typography({"primary": font, "heading": font})
        if not (resolution.body.enabled or resolution.heading.enabled):
            raise RuntimeError("font could not be resolved")
        theme.update(resolution.as_theme_tokens())
    except Exception as exc:
        warnings.append(f"Could not load font '{font}' ({exc}); using the template's default font.")
        theme.update(
            typography_available=False, typography_enabled=False, body_font=[], heading_font=[],
            typography_resolution={}, style_font="Default",
        )
    return theme, warnings


def save_default_style(style: dict, path: Path | None = None) -> dict:
    target = _resolve(path)
    theme = build_default_theme(style)  # raises before anything is written
    theme, warnings = _with_typography(theme)
    _write_atomic(target, theme)
    saved = read_default_style(target)
    saved["warnings"] = warnings
    return saved


def render_style_preview(style: dict) -> bytes:
    """Return a PNG of page 1 of the reference CV rendered with ``style``."""
    typst = shutil.which("typst")
    if typst is None:
        raise ValueError("Typst is not installed, so a preview can't be drawn.")
    theme = build_default_theme(style)
    theme, _warnings = _with_typography(theme)

    preview_dir = ROOT / "data" / ".preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=preview_dir, prefix="p-"))
    try:
        dump = lambda data: yaml.safe_dump(data, sort_keys=False, allow_unicode=True)  # noqa: E731
        (work / "theme.yaml").write_text(dump(theme), encoding="utf-8")
        cv = yaml.safe_load((ROOT / "Base" / "reference" / "cv-data.yaml").read_text(encoding="utf-8")) or {}
        cv["variant"] = theme["cv_variant"]
        cv["max_pages"] = 1 if theme["cv_variant"] in ("grotesk_one_page", "compact_one_page") else 2
        (work / "cv-data.yaml").write_text(dump(cv), encoding="utf-8")
        profile = profile_module.load_candidate_profile()
        (work / "profile.yaml").write_text(dump(profile_module.export_profile_for_typst(profile)), encoding="utf-8")

        def rel(name: str) -> str:
            return "/" + (work / name).relative_to(ROOT).as_posix()

        out = work / "preview.png"
        cmd = [
            typst, "compile", "--root", str(ROOT), str(ROOT / "Base" / "cv.typ"), str(out),
            "--format", "png", "--pages", "1", "--ppi", "110",
            "--input", f"data={rel('cv-data.yaml')}",
            "--input", f"profile={rel('profile.yaml')}",
            "--input", f"theme={rel('theme.yaml')}",
        ]
        for font_path in font_paths_for_theme(theme):
            cmd.extend(["--font-path", str(font_path)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not out.is_file():
            raise ValueError((result.stderr or "Typst failed to render the preview.").strip()[:800])
        return out.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)
