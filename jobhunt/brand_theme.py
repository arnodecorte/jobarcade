from __future__ import annotations

import colorsys
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import httpx
import yaml
from bs4 import BeautifulSoup

BASE_THEME = {
    "accent": "#C41230",
    "accent_dark": "#1A1A1A",
    "muted": "#6B6B6B",
    "page_bg": "#FFFFFF",
    "soft_bg": "#F1ECE2",
    "rule": "#D9D4CC",
    "link": "#2A6F8E",
}

DARK_THEME_DEFAULTS = {
    "accent_dark": "#FFFFFF",
    "muted": "#B3B3B3",
    "page_bg": "#000000",
    "soft_bg": "#141414",
    "rule": "#333333",
}

FIRECRAWL_API_URL = os.environ.get("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v2/scrape")

# A bot-labeled UA (e.g. "SomeBot/0.1") trips Akamai/bot-manager style
# protection on sites like tesla.com; match the browser UA already used by
# jobhunt/adapters.py for the same reason.
LOCAL_FETCH_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
CSS_COLOR_RE = re.compile(r"\b(?:color|background(?:-color)?|border-color|--[\w-]*color[\w-]*)\s*:\s*(#[0-9a-fA-F]{3,6})")
NOISY_COLORS = {"#000000", "#111111", "#1A1A1A", "#222222", "#333333", "#FFFFFF", "#FDFDFD", "#FAFAFA"}


@dataclass(frozen=True)
class ThemeResult:
    theme: dict
    warnings: list[str]


def _normalize_hex(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    match = HEX_RE.fullmatch(value.strip())
    if not match:
        return None
    raw = value.strip().upper()
    if len(raw) == 4:
        raw = "#" + "".join(ch * 2 for ch in raw[1:])
    return raw


def _rgb(hex_color: str) -> tuple[int, int, int]:
    color = _normalize_hex(hex_color) or "#000000"
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, channel)):02X}" for channel in rgb)


def _relative_luminance(hex_color: str) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (_rgb(hex_color))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    low, high = sorted((_relative_luminance(a), _relative_luminance(b)))
    return (high + 0.05) / (low + 0.05)


def _hls(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (channel / 255 for channel in _rgb(hex_color))
    return colorsys.rgb_to_hls(r, g, b)


def _from_hls(h: float, l: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return _hex_from_rgb((round(r * 255), round(g * 255), round(b * 255)))


def _adjust_for_text(hex_color: str) -> str:
    h, l, s = _hls(hex_color)
    color = hex_color
    for target_l in (0.32, 0.28, 0.24, 0.2):
        color = _from_hls(h, target_l, max(s, 0.34))
        if contrast_ratio(color, "#FFFFFF") >= 4.5:
            return color
    return color


def _adjust_for_dark_surface(hex_color: str, background: str = "#000000") -> str:
    h, l, s = _hls(hex_color)
    color = hex_color
    for target_l in (max(l, 0.48), 0.54, 0.6, 0.66):
        color = _from_hls(h, target_l, max(s, 0.5))
        if contrast_ratio(color, background) >= 4.5:
            return color
    return color


def _soft_background(hex_color: str) -> str:
    h, _l, s = _hls(hex_color)
    return _from_hls(h, 0.94, min(max(s, 0.12), 0.32))


def _rule_color(hex_color: str) -> str:
    h, _l, s = _hls(hex_color)
    return _from_hls(h, 0.82, min(max(s, 0.12), 0.28))


def _is_usable_accent(hex_color: str) -> bool:
    if hex_color.upper() in NOISY_COLORS:
        return False
    h, l, s = _hls(hex_color)
    return 0.16 <= l <= 0.74 and s >= 0.16


def _weight(value, default: int) -> int:
    try:
        return max(100, min(900, int(value)))
    except (TypeError, ValueError):
        return default


def sanitize_theme(raw: dict | None) -> ThemeResult:
    raw = raw or {}
    warnings: list[str] = []
    accent = _normalize_hex(str(raw.get("accent") or "")) if raw.get("accent") else None
    confidence = float(raw.get("confidence") or 0)
    mode = str(raw.get("mode") or "light").strip().lower()
    if mode not in {"light", "dark"}:
        warnings.append("Unsupported theme mode; using light mode.")
        mode = "light"
    page_bg = _normalize_hex(str(raw.get("page_bg") or "")) or (
        DARK_THEME_DEFAULTS["page_bg"] if mode == "dark" else BASE_THEME["page_bg"]
    )
    dark_recommended = bool(raw.get("dark_recommended")) or "dark" in str(raw.get("energy") or "").lower()

    if not accent or not _is_usable_accent(accent) or confidence < 0.35:
        warnings.append("Brand colors were too weak or low-confidence; using the base theme.")
        theme = dict(BASE_THEME)
        if mode == "dark":
            theme.update(DARK_THEME_DEFAULTS)
        theme.update(
            {
                "enabled": bool(raw.get("enabled", False)),
                "provider": raw.get("provider") or "local",
                "mode": mode,
                "source_url": raw.get("source_url") or "",
                "source_kind": raw.get("source_kind") or "",
                "source_reason": raw.get("source_reason") or "",
                "confidence": round(confidence, 2),
                "notes": list(raw.get("notes") or []),
                "typography": dict(raw.get("typography") or {}),
                "typography_available": bool(raw.get("typography_available")),
                "typography_enabled": bool(raw.get("typography_enabled")),
                "body_font": list(raw.get("body_font") or []),
                "heading_font": list(raw.get("heading_font") or []),
                "body_weight": _weight(raw.get("body_weight"), 400),
                "subheading_weight": _weight(raw.get("subheading_weight"), 500),
                "heading_weight": _weight(raw.get("heading_weight"), 700),
                "typography_resolution": dict(raw.get("typography_resolution") or {}),
                "energy": raw.get("energy") or "",
                "tone": raw.get("tone") or "",
                "dark_recommended": dark_recommended,
                "light_tokens": dict(raw.get("light_tokens") or {}),
                "fallback": True,
            }
        )
        return ThemeResult(theme, warnings)

    accent = _adjust_for_dark_surface(accent, page_bg) if mode == "dark" else _adjust_for_text(accent)
    theme = {
        "enabled": bool(raw.get("enabled", True)),
        "provider": raw.get("provider") or "local",
        "mode": mode,
        "accent": accent,
        "accent_dark": _normalize_hex(str(raw.get("accent_dark") or ""))
        or (DARK_THEME_DEFAULTS["accent_dark"] if mode == "dark" else BASE_THEME["accent_dark"]),
        "muted": _normalize_hex(str(raw.get("muted") or ""))
        or (DARK_THEME_DEFAULTS["muted"] if mode == "dark" else BASE_THEME["muted"]),
        "page_bg": page_bg,
        "soft_bg": _normalize_hex(str(raw.get("soft_bg") or ""))
        or (DARK_THEME_DEFAULTS["soft_bg"] if mode == "dark" else _soft_background(accent)),
        "rule": _normalize_hex(str(raw.get("rule") or ""))
        or (DARK_THEME_DEFAULTS["rule"] if mode == "dark" else _rule_color(accent)),
        "link": _normalize_hex(str(raw.get("link") or "")) or accent,
        "source_url": raw.get("source_url") or "",
        "source_kind": raw.get("source_kind") or "",
        "source_reason": raw.get("source_reason") or "",
        "confidence": round(confidence, 2),
        "notes": list(raw.get("notes") or []),
        "typography": dict(raw.get("typography") or {}),
        "typography_available": bool(raw.get("typography_available")),
        "typography_enabled": bool(raw.get("typography_enabled")),
        "body_font": list(raw.get("body_font") or []),
        "heading_font": list(raw.get("heading_font") or []),
        "body_weight": _weight(raw.get("body_weight"), 400),
        "subheading_weight": _weight(raw.get("subheading_weight"), 500),
        "heading_weight": _weight(raw.get("heading_weight"), 700),
        "typography_resolution": dict(raw.get("typography_resolution") or {}),
        "energy": raw.get("energy") or "",
        "tone": raw.get("tone") or "",
        "dark_recommended": dark_recommended,
        "light_tokens": dict(raw.get("light_tokens") or {}),
        "fallback": False,
    }
    contrast_bg = theme["page_bg"] if mode == "dark" else "#FFFFFF"
    if contrast_ratio(theme["accent"], contrast_bg) < 4.5:
        warnings.append("Accent color was darkened for contrast.")
        theme["accent"] = BASE_THEME["accent"]
    return ThemeResult(theme, warnings)


def _colors_from_html(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[tuple[str, str]] = []
    for meta_name in ("theme-color", "msapplication-TileColor"):
        node = soup.find("meta", attrs={"name": meta_name})
        color = _normalize_hex(node.get("content") if node else None)
        if color:
            found.append((color, f"meta {meta_name}"))
    for tag in soup.find_all("style"):
        text = tag.get_text(" ", strip=True)
        for color in CSS_COLOR_RE.findall(text):
            normalized = _normalize_hex(color)
            if normalized:
                found.append((normalized, "inline CSS"))
    for tag in soup.find_all(attrs={"style": True}):
        for color in HEX_RE.findall(tag.get("style") or ""):
            normalized = _normalize_hex(color)
            if normalized:
                found.append((normalized, "inline style"))
    for selector in ("link[rel~='icon']", "link[rel='mask-icon']", "meta[property='og:image']"):
        for node in soup.select(selector):
            color = _normalize_hex(node.get("color"))
            if color:
                found.append((color, "icon metadata"))
    return found


def _colors_from_css(css: str, source: str = "linked CSS") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for color in CSS_COLOR_RE.findall(css):
        normalized = _normalize_hex(color)
        if normalized:
            found.append((normalized, source))
    return found


def _best_color(candidates: list[tuple[str, str]]) -> tuple[str | None, float, list[str]]:
    usable = [(color, source) for color, source in candidates if _is_usable_accent(color)]
    if not usable:
        return None, 0.0, ["No usable brand accent color found."]
    counts = Counter(color for color, _source in usable)
    color, count = counts.most_common(1)[0]
    sources = sorted({source for candidate, source in usable if candidate == color})
    confidence = min(0.95, 0.42 + (count * 0.08) + (len(sources) * 0.08))
    notes = [f"Selected {color} from {', '.join(sources)}."]
    return color, confidence, notes


def extract_theme_from_html(html: str, source_url: str) -> ThemeResult:
    accent, confidence, notes = _best_color(_colors_from_html(html))
    return sanitize_theme(
        {
            "enabled": True,
            "accent": accent,
            "confidence": confidence,
            "source_url": source_url,
            "provider": "local",
            "notes": notes,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def extract_theme_from_url(url: str, timeout: float = 12.0) -> ThemeResult:
    if not url:
        return sanitize_theme({"enabled": False, "confidence": 0, "notes": ["No source URL available."]})
    target = url if re.match(r"^https?://", url) else f"https://{url}"
    with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": LOCAL_FETCH_USER_AGENT}) as client:
        response = client.get(target)
        response.raise_for_status()
        final_url = str(response.url)
        candidates = _colors_from_html(response.text)
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("link[rel~='stylesheet'][href]")[:4]:
            css_url = urljoin(final_url, node.get("href") or "")
            try:
                css_response = client.get(css_url)
                if css_response.status_code < 400:
                    candidates.extend(_colors_from_css(css_response.text))
            except Exception:
                continue
    accent, confidence, notes = _best_color(candidates)
    result = sanitize_theme(
        {
            "enabled": True,
            "accent": accent,
            "confidence": confidence,
            "source_url": final_url,
            "provider": "local",
            "notes": notes,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    result.theme["source_url"] = final_url
    return result


def _first_hex(value) -> str | None:
    if isinstance(value, str):
        return _normalize_hex(value)
    if isinstance(value, dict):
        for key in ("primary", "accent", "secondary", "textPrimary", "background", "color", "hex", "value"):
            color = _first_hex(value.get(key))
            if color:
                return color
        for child in value.values():
            color = _first_hex(child)
            if color:
                return color
    if isinstance(value, list):
        for child in value:
            color = _first_hex(child)
            if color:
                return color
    return None


def _color_value(branding: dict, *keys: str) -> str | None:
    colors = branding.get("colors") if isinstance(branding.get("colors"), dict) else {}
    for key in keys:
        color = _first_hex(colors.get(key))
        if color:
            return color
    return None


def _firecrawl_branding_to_theme(branding: dict, source_url: str) -> ThemeResult:
    colors = branding.get("colors") if isinstance(branding.get("colors"), dict) else {}
    accent = (
        _color_value(branding, "primary", "accent", "secondary")
        or _first_hex(colors)
        or _first_hex(branding.get("logo"))
    )
    typography = branding.get("typography") if isinstance(branding.get("typography"), dict) else {}
    font_families = typography.get("fontFamilies") if isinstance(typography.get("fontFamilies"), dict) else {}
    font_weights = typography.get("fontWeights") if isinstance(typography.get("fontWeights"), dict) else {}
    notes = ["Firecrawl branding profile extracted colors and typography."]
    if font_families:
        labels = [str(value) for value in font_families.values() if value]
        if labels:
            notes.append("Typography: " + ", ".join(dict.fromkeys(labels)))
    raw = {
        "enabled": True,
        "provider": "firecrawl",
        "accent": accent,
        "accent_dark": "#1A1A1A",
        "soft_bg": None,
        "rule": _color_value(branding, "border", "muted", "textSecondary"),
        "link": _color_value(branding, "accent", "primary", "secondary"),
        "source_url": source_url,
        "confidence": 0.88 if accent else 0.2,
        "notes": notes,
        "typography": {
            "primary": font_families.get("primary") or font_families.get("body") or "",
            "heading": font_families.get("heading") or "",
            "code": font_families.get("code") or "",
            "weights": {
                "regular": font_weights.get("regular"),
                "medium": font_weights.get("medium"),
                "bold": font_weights.get("bold"),
            } if font_weights else {},
        },
        "energy": str(branding.get("colorScheme") or ""),
        "tone": str(branding.get("theme") or branding.get("brandPersonality") or ""),
        "dark_recommended": "dark" in str(branding.get("colorScheme") or "").lower()
        or (_first_hex(colors.get("background")) or "").upper() in {"#000000", "#111111", "#141414"},
        "raw_branding_keys": sorted(str(key) for key in branding.keys()),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    return sanitize_theme(raw)


def _describe_error(exc: Exception) -> str:
    """Verbose, single-line description of an extraction failure, including
    HTTP status + response body when available — the raw exception text alone
    (e.g. from httpx) is often just a generic status line with no body, which
    isn't enough to tell a Firecrawl auth/rate-limit/quota error apart from a
    genuine site block."""
    if isinstance(exc, httpx.HTTPStatusError):
        body = (exc.response.text or "").strip().replace("\n", " ")
        if len(body) > 300:
            body = body[:300] + "…"
        return f"{type(exc).__name__} {exc.response.status_code} for {exc.request.url} — {body or '(empty body)'}"
    if isinstance(exc, httpx.RequestError):
        target = exc.request.url if exc.request else "unknown URL"
        return f"{type(exc).__name__} requesting {target}: {exc}"
    return f"{type(exc).__name__}: {exc}"


def extract_theme_with_firecrawl(url: str, api_key: str | None = None, timeout: float = 45.0) -> ThemeResult:
    key = api_key or os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise ValueError("FIRECRAWL_API_KEY is not set.")
    target = url if re.match(r"^https?://", url or "") else f"https://{url}"
    response = httpx.post(
        FIRECRAWL_API_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"url": target, "formats": ["branding"], "onlyMainContent": False},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    branding = data.get("branding") if isinstance(data, dict) else None
    if not isinstance(branding, dict):
        raise ValueError("Firecrawl response did not include a branding profile.")
    return _firecrawl_branding_to_theme(branding, data.get("metadata", {}).get("sourceURL") or target)


def extract_theme(url: str, provider: str = "auto", api_key: str | None = None) -> ThemeResult:
    if provider not in {"auto", "firecrawl", "local"}:
        raise ValueError("Theme provider must be auto, firecrawl, or local.")
    if provider in {"auto", "firecrawl"}:
        try:
            return extract_theme_with_firecrawl(url, api_key=api_key)
        except Exception as exc:
            if provider == "firecrawl":
                raise
            try:
                local = extract_theme_from_url(url)
            except Exception as local_exc:
                raise RuntimeError(
                    f"Firecrawl failed — {_describe_error(exc)}; "
                    f"local fallback also failed — {_describe_error(local_exc)}."
                ) from local_exc
            local.theme["notes"] = [f"Firecrawl unavailable; local fallback used: {_describe_error(exc)}"] + list(local.theme.get("notes") or [])
            local.theme["provider"] = "local"
            return local
    return extract_theme_from_url(url)


def theme_path(folder: Path) -> Path:
    return folder / "brand-theme.yaml"


def read_theme(folder: Path) -> dict | None:
    path = theme_path(folder)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {
            "enabled": False,
            "fallback": True,
            "warnings": ["brand-theme.yaml could not be parsed; using the base theme."],
        }
    if not isinstance(data, dict):
        return None
    result = sanitize_theme(data)
    theme = result.theme
    theme["warnings"] = result.warnings + list(data.get("warnings") or [])
    return theme


def write_theme(folder: Path, theme: dict) -> dict:
    result = sanitize_theme(theme)
    data = result.theme
    data["warnings"] = result.warnings + list(theme.get("warnings") or [])
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    theme_path(folder).write_text(yaml.safe_dump(data, sort_keys=False, width=100), encoding="utf-8")
    return data


def reset_theme(folder: Path) -> dict:
    return write_theme(folder, {"enabled": False, "confidence": 0, "notes": ["Chameleon theme disabled."]})


def candidate_source_url(job_url: str | None, company_url: str | None) -> str:
    return job_url or company_url or ""
