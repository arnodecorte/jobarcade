from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from jobhunt.config import ROOT

FONTS_DIR = ROOT / "fonts" / "chameleon"
GOOGLE_FONTS_METADATA_URL = "https://fonts.google.com/metadata/fonts"
GOOGLE_FONTS_CONTENTS_URL = "https://api.github.com/repos/google/fonts/contents"

DEFAULT_STACK = ["Segoe UI", "Roboto"]
LOCAL_SAFE_FONTS = {
    "arial": "Arial",
    "calibri": "Calibri",
    "georgia": "Georgia",
    "roboto": "Roboto",
    "segoe ui": "Segoe UI",
    "times new roman": "Times New Roman",
    "verdana": "Verdana",
}

CURATED_GOOGLE_ALTERNATIVES = {
    "netflix sans": "Inter",
    "helvetica neue": "Inter",
    "helvetica": "Inter",
    "sf pro": "Inter",
    "san francisco": "Inter",
    "circular": "Nunito Sans",
    "circular std": "Nunito Sans",
    "gotham": "Montserrat",
    "proxima nova": "Montserrat",
    "avenir": "Nunito Sans",
    "brandon grotesque": "Montserrat",
    "graphik": "Inter",
    "sohne": "Inter",
    "founders grotesk": "Inter",
}


@dataclass(frozen=True)
class FontResolution:
    enabled: bool
    source: str
    requested: str
    family: str
    stack: list[str]
    font_path: str
    notes: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class TypographyResolution:
    body: FontResolution
    heading: FontResolution
    body_weight: int
    subheading_weight: int
    heading_weight: int

    @staticmethod
    def _resolution_tokens(res: FontResolution) -> dict:
        return {
            "source": res.source,
            "requested": res.requested,
            "family": res.family,
            "font_path": res.font_path,
            "notes": res.notes,
            "warnings": res.warnings,
        }

    def as_theme_tokens(self) -> dict:
        body_stack = self.body.stack if self.body.enabled else DEFAULT_STACK
        heading_stack = self.heading.stack if self.heading.enabled else (
            body_stack if self.body.enabled else DEFAULT_STACK
        )
        return {
            "typography_available": self.body.enabled or self.heading.enabled,
            "body_font": body_stack,
            "heading_font": heading_stack,
            "body_weight": self.body_weight,
            "subheading_weight": self.subheading_weight,
            "heading_weight": self.heading_weight,
            "typography_resolution": {
                "body": self._resolution_tokens(self.body),
                "heading": self._resolution_tokens(self.heading),
            },
        }


def _normalize_family(value: str | None) -> str:
    raw = re.sub(r"['\"]", "", str(value or "")).strip()
    raw = raw.split(",")[0].strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]", "", family.lower())


def _installed_or_vendored_family(family: str) -> str | None:
    normalized = _key(family)
    if normalized in LOCAL_SAFE_FONTS:
        return LOCAL_SAFE_FONTS[normalized]
    vendored = FONTS_DIR / _slug(family)
    if vendored.exists() and any(vendored.glob("*.ttf")):
        return family
    return None


def _google_families(timeout: float = 12.0) -> dict[str, str]:
    response = httpx.get(GOOGLE_FONTS_METADATA_URL, timeout=timeout)
    response.raise_for_status()
    text = response.text.lstrip()
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1]
    data = response.json() if text == response.text else json.loads(text)
    families = data.get("familyMetadataList") or []
    return {_key(item.get("family", "")): item.get("family", "") for item in families if item.get("family")}


def _google_match(requested: str, timeout: float = 12.0) -> tuple[str | None, str]:
    requested_key = _key(requested)
    if not requested_key:
        return None, "No typography label found."
    try:
        families = _google_families(timeout=timeout)
    except Exception as exc:
        curated = CURATED_GOOGLE_ALTERNATIVES.get(requested_key)
        if curated:
            return curated, f"Google Fonts metadata unavailable; using curated alternative for {requested}."
        return None, f"Google Fonts metadata unavailable: {exc}"
    if requested_key in families:
        return families[requested_key], "Exact Google Fonts family match."
    curated = CURATED_GOOGLE_ALTERNATIVES.get(requested_key)
    if curated:
        return curated, f"Font not found on Google Fonts; using vetted alternative for {requested}."
    compact = requested_key.replace(" ", "")
    for key, family in families.items():
        if key.replace(" ", "") == compact:
            return family, "Close Google Fonts family match."
    return None, f"No vetted Google Fonts match for {requested}."


def _download_google_ttf(family: str, timeout: float = 20.0) -> Path:
    family_dir = FONTS_DIR / _slug(family)
    family_dir.mkdir(parents=True, exist_ok=True)
    if any(family_dir.glob("*.ttf")):
        return family_dir
    for bucket in ("ofl", "apache", "ufl"):
        url = f"{GOOGLE_FONTS_CONTENTS_URL}/{bucket}/{_slug(family)}"
        response = httpx.get(url, timeout=timeout)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        files = response.json()
        ttf_files = [
            item for item in files
            if isinstance(item, dict)
            and str(item.get("name", "")).lower().endswith(".ttf")
            and item.get("download_url")
        ]
        if not ttf_files:
            continue
        preferred = sorted(
            ttf_files,
            key=lambda item: (
                "regular" not in item["name"].lower() and "[wght]" not in item["name"].lower(),
                "bold" in item["name"].lower(),
                item["name"],
            ),
        )
        for item in preferred[:4]:
            out = family_dir / item["name"]
            font_response = httpx.get(item["download_url"], timeout=timeout)
            font_response.raise_for_status()
            out.write_bytes(font_response.content)
        if any(family_dir.glob("*.ttf")):
            return family_dir
    raise ValueError(f"Could not download TTF files for Google Font '{family}'.")


def _resolve_family(requested: str, timeout: float = 20.0) -> FontResolution:
    requested = _normalize_family(requested)
    if not requested:
        return FontResolution(False, "fallback", "", "", DEFAULT_STACK, "", [], ["No font family found in branding data."])

    local = _installed_or_vendored_family(requested)
    if local:
        return FontResolution(True, "local", requested, local, [local, *DEFAULT_STACK], "", [f"Exact local font hit: {local}."], [])

    family, note = _google_match(requested, timeout=min(timeout, 12.0))
    if not family:
        return FontResolution(False, "fallback", requested, "", DEFAULT_STACK, "", [], [note])

    try:
        font_dir = _download_google_ttf(family, timeout=timeout)
    except Exception as exc:
        return FontResolution(False, "fallback", requested, family, DEFAULT_STACK, "", [note], [f"Google Fonts download failed: {exc}"])

    return FontResolution(
        True,
        "google_fonts",
        requested,
        family,
        [family, *DEFAULT_STACK],
        str(font_dir.relative_to(ROOT)).replace("\\", "/"),
        [note, f"Cached Google Font '{family}'."],
        [],
    )


def resolve_typography(typography: dict | None, timeout: float = 20.0) -> TypographyResolution:
    typography = typography or {}
    body_requested = _normalize_family(
        typography.get("primary") or typography.get("body") or typography.get("heading") or ""
    )
    heading_requested = _normalize_family(
        typography.get("heading") or typography.get("primary") or typography.get("body") or ""
    )

    body_res = _resolve_family(body_requested, timeout)
    heading_res = body_res if heading_requested == body_requested else _resolve_family(heading_requested, timeout)

    weights = typography.get("weights") if isinstance(typography.get("weights"), dict) else {}

    def _w(key: str, default: int) -> int:
        try:
            return max(100, min(900, int(weights.get(key))))
        except (TypeError, ValueError):
            return default

    return TypographyResolution(
        body_res,
        heading_res,
        _w("regular", 400),
        _w("medium", 500),
        _w("bold", 700),
    )


def font_paths_for_theme(theme: dict | None) -> list[Path]:
    if not theme or not theme.get("typography_enabled") or theme.get("fallback"):
        return []
    resolution = theme.get("typography_resolution") if isinstance(theme.get("typography_resolution"), dict) else {}
    if "body" in resolution or "heading" in resolution:
        entries = [resolution.get("body"), resolution.get("heading")]
    else:
        entries = [resolution]  # legacy flat shape from pre-dual-font themes

    paths: list[Path] = []
    seen: set[Path] = set()
    for entry in entries:
        entry = entry if isinstance(entry, dict) else {}
        rel = str(entry.get("font_path") or "")
        if not rel:
            continue
        path = (ROOT / rel).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            continue
        if path.is_dir() and any(path.glob("*.ttf")) and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths
