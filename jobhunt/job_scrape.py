"""Extract title/company/location/description from a single job-posting URL.

Backs the dashboard's Add Job "Scrape" button (POST /api/jobs/scrape) and the
`python -m jobhunt scrape-listing` CLI. Tiered: plain HTTP + JSON-LD JobPosting,
then meta/OG heuristics on the same HTML, then a Firecrawl markdown scrape for
JS-rendered or bot-blocked pages. Partial results are fine — the form is
reviewed by a human before submitting.
"""

import html
import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from jobhunt.brand_theme import FIRECRAWL_API_URL, _describe_error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_DESCRIPTION_CHARS = 20_000
MIN_BODY_CHARS = 300

TITLE_SEPARATORS = (" | ", " – ", " — ", " - ")
DOMAIN_GUESS_WARNING = "Company guessed from the site domain — double-check it."
TEASER_WARNING = "Only a short page summary was available — paste the full description if you have it."
# Navigation-label titles a JS shell or error page serves instead of the role name.
GENERIC_TITLE_RE = re.compile(r"^(careers?|jobs?|job search|vacatures?|page not found|404|home|welcome)$", re.IGNORECASE)
# LinkedIn (and imitators) pack everything into og:title: "<company> hiring <title> in <location>".
HIRING_TITLE_RE = re.compile(r"^(?P<company>.+?) hiring (?P<title>.+) in (?P<location>[^|]+?)(?:\s*\|\s*LinkedIn)?$")
DEAD_PAGE_RE = re.compile(
    r"(page|job|posting)[^.\n]{0,40}(doesn'?t|does not|no longer) exist|page not found|posting[^.\n]{0,30}(closed|expired|removed)",
    re.IGNORECASE,
)
# Specific job-description containers first; whole-page containers only as a
# fallback — on chrome-heavy pages (LinkedIn login wall) `main` is the longest
# match but mostly navigation noise.
DESCRIPTION_SELECTOR_TIERS = (
    ('[class*="job-description" i]', '[class*="description" i]', '[id*="description" i]', ".entry-content"),
    ("article", "main"),
)


@dataclass
class ListingExtract:
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    source: str = "none"
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "ListingExtract") -> "ListingExtract":
        """Fill-empty-only: keep this extract's fields, take other's for gaps.
        Warnings about a field the other extract lost are dropped with it."""
        other_warnings = [
            warning
            for warning in other.warnings
            if not (warning == DOMAIN_GUESS_WARNING and self.company)
            and not (warning == TEASER_WARNING and self.description)
        ]
        return ListingExtract(
            title=self.title or other.title,
            company=self.company or other.company,
            location=self.location or other.location,
            description=self.description or other.description,
            source=self.source if self.source != "none" else other.source,
            warnings=self.warnings + other_warnings,
        )

    def is_empty(self) -> bool:
        return not (self.title or self.company or self.location or self.description)

    def to_payload(self) -> dict:
        return {
            "ok": True,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
            "source": self.source,
            "warnings": list(dict.fromkeys(self.warnings)),
        }


def _clean_title(raw: str | None) -> str | None:
    """Trim site/company suffixes like "Role - Acme | Careers" down to "Role"."""
    text = re.sub(r"\s+", " ", raw or "").strip()
    for sep in TITLE_SEPARATORS:
        if sep in text:
            head = text.split(sep)[0].strip()
            if len(head) >= 4:
                text = head
    if GENERIC_TITLE_RE.match(text):
        return None
    return text or None


def _apply_page_title(extract: ListingExtract, raw_title: str | None) -> None:
    """Fill title (and company/location on LinkedIn-style "X hiring Y in Z"
    titles) from a page/OG title, without clobbering already-set fields."""
    hiring = HIRING_TITLE_RE.match(re.sub(r"\s+", " ", raw_title or "").strip())
    if hiring:
        extract.title = extract.title or hiring["title"].strip()
        extract.company = extract.company or hiring["company"].strip()
        extract.location = extract.location or hiring["location"].strip()
        return
    extract.title = extract.title or _clean_title(raw_title)


def _company_from_domain(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    labels = [label for label in host.split(".") if label]
    while labels and re.match(r"^(www|apply|recruit\w*|werkenbij\w*|careers?|jobs?)([-.].*)?$", labels[0]):
        labels.pop(0)
    if len(labels) >= 2:
        return labels[0].capitalize()
    return None


def _guess_company(extract: ListingExtract, url: str) -> None:
    """Fill company from the domain, but only when the page yielded a real job
    signal — a bare domain guess on an otherwise empty page is worthless."""
    if extract.company or not (extract.title or extract.description):
        return
    guess = _company_from_domain(url)
    if guess:
        extract.company = guess
        extract.warnings.append(DOMAIN_GUESS_WARNING)


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value).strip() or None
    if isinstance(value, dict):
        for key in ("name", "text", "label", "value", "city", "country"):
            if value.get(key):
                return _as_text(value[key])
    if isinstance(value, list):
        parts = [_as_text(item) for item in value[:4]]
        return ", ".join(part for part in parts if part) or None
    return None


def _cap(text: str | None) -> str | None:
    """Normalize a description: undo double-escaped newlines/HTML (some sites
    ship "\\n" and "&lt;p&gt;" inside their JSON-LD) and cap the length."""
    if not text:
        return None
    text = text.replace("\\n", "\n")
    if re.search(r"</?(p|div|ul|ol|li|br|strong|em|b|i|span|h[1-6])\b", text, re.IGNORECASE):
        text = strip_html(text) or ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_DESCRIPTION_CHARS].strip() or None


def looks_like_js_shell(html_content: str) -> bool:
    text = strip_html(html_content) or ""
    if re.search(r"(enable|requires?)\s+javascript", html_content, re.IGNORECASE):
        return True
    if len(text) < 500:
        return True
    return len(html_content) > 40_000 and len(text) < 0.01 * len(html_content)


def extract_from_json_ld(html_content: str, url: str) -> ListingExtract:
    soup = BeautifulSoup(html_content, "html.parser")
    candidates: list[ListingExtract] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if isinstance(entry, dict) and entry.get("@graph"):
                entries.extend(entry["@graph"])
            if not isinstance(entry, dict) or entry.get("@type") != "JobPosting":
                continue
            org = entry.get("hiringOrganization") or {}
            location = entry.get("jobLocation") or {}
            if isinstance(location, list):
                location = location[0] if location else {}
            address = location.get("address") if isinstance(location, dict) else {}
            loc_str = ", ".join(
                part
                for part in [
                    _as_text(address.get("addressLocality")) if isinstance(address, dict) else None,
                    _as_text(address.get("addressCountry")) if isinstance(address, dict) else None,
                ]
                if part
            ) or _as_text(location)

            raw_desc = _as_text(entry.get("description"))
            clean_desc = _cap(strip_html(raw_desc)) if raw_desc else None

            extract = ListingExtract(
                title=_clean_title(_as_text(entry.get("title"))),
                company=_as_text(org) or None,
                location=loc_str or None,
                description=clean_desc,
                source="json_ld",
            )
            if not extract.is_empty():
                candidates.append(extract)

    if not candidates:
        return ListingExtract()
    return next((c for c in candidates if c.description), candidates[0])


def _meta_content(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        content = (node.get("content") or "").strip() if node else ""
        if content:
            return content
    return None


def extract_from_meta(html: str, url: str) -> ListingExtract:
    soup = BeautifulSoup(html, "html.parser")
    extract = ListingExtract()

    raw_title = _meta_content(soup, "og:title")
    if not raw_title and soup.title:
        raw_title = soup.title.get_text(strip=True)
    if not raw_title:
        h1 = soup.find("h1")
        raw_title = h1.get_text(" ", strip=True) if h1 else None
    _apply_page_title(extract, raw_title)

    extract.company = extract.company or _meta_content(soup, "og:site_name")
    extract.location = extract.location or _meta_content(soup, "og:locality", "job:location")

    candidates: list[str] = []
    for tier in DESCRIPTION_SELECTOR_TIERS:
        for selector in tier:
            for node in soup.select(selector):
                text = strip_html(str(node))
                if text and len(text) >= MIN_BODY_CHARS:
                    candidates.append(text)
        if candidates:
            break
    if candidates:
        extract.description = _cap(max(candidates, key=len))
    else:
        teaser = _meta_content(soup, "og:description", "description")
        if teaser:
            extract.description = teaser
            extract.warnings.append(TEASER_WARNING)

    _guess_company(extract, url)
    if not extract.is_empty():
        extract.source = "meta"
    return extract


def _clean_markdown(markdown: str) -> str | None:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _cap(text)


def _drop_garbage_description(text: str | None) -> str | None:
    """Reject dead-page and cookie-consent boilerplate that a rendered scrape
    of an expired posting or an undismissed cookie wall produces."""
    if not text:
        return None
    if DEAD_PAGE_RE.search(text):
        return None
    if len(text) < 800 and re.search(r"\b(cookies?|consent)\b", text, re.IGNORECASE):
        return None
    return text


def extract_from_firecrawl(data: dict, url: str) -> ListingExtract:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    extract = ListingExtract(
        company=(str(metadata.get("ogSiteName") or "").strip() or None),
        description=_drop_garbage_description(_clean_markdown(str(data.get("markdown") or ""))),
    )
    _apply_page_title(extract, str(metadata.get("ogTitle") or metadata.get("title") or ""))
    _guess_company(extract, url)
    if not extract.is_empty():
        extract.source = "firecrawl"
    return extract


def fetch_html(url: str, timeout: float = 12.0) -> str:
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def fetch_firecrawl_markdown(url: str, timeout: float = 20.0, api_key: str | None = None) -> dict:
    key = api_key or os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise ValueError("FIRECRAWL_API_KEY is not set, so JS-rendered pages can't be scraped.")
    response = httpx.post(
        FIRECRAWL_API_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict) or not (data.get("markdown") or data.get("metadata")):
        raise ValueError("Firecrawl response did not include page content.")
    return data


def _validate_url(url: str) -> str:
    target = (url or "").strip()
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A valid http(s) URL is required.")
    host = parsed.hostname
    try:
        addr = ip_address(host)
    except ValueError:
        addr = None
    if host == "localhost" or host.endswith(".local") or (addr and not addr.is_global):
        raise ValueError("URLs pointing at local or private addresses aren't allowed.")
    return target


def scrape_job_listing(
    url: str,
    fetcher: Callable[[str], str] | None = None,
    firecrawl_fetcher: Callable[[str], dict] | None = None,
    api_key: str | None = None,
) -> dict:
    target = _validate_url(url)
    fetch = fetcher or fetch_html
    firecrawl = firecrawl_fetcher or (lambda target_url: fetch_firecrawl_markdown(target_url, api_key=api_key))

    html: str | None = None
    fetch_error: str | None = None
    firecrawl_error: str | None = None
    try:
        html = fetch(target)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 410):
            raise ValueError(
                f"The page returned HTTP {exc.response.status_code} — the posting may have been removed. "
                "Check the URL, or fill the fields in manually."
            ) from exc
        fetch_error = _describe_error(exc)
    except Exception as exc:
        fetch_error = _describe_error(exc)

    result = ListingExtract()
    if html:
        result = extract_from_json_ld(html, target).merge(extract_from_meta(html, target))

    if html is None or looks_like_js_shell(html) or not result.description:
        try:
            result = result.merge(extract_from_firecrawl(firecrawl(target), target))
        except Exception as exc:
            firecrawl_error = _describe_error(exc)
            if not result.is_empty():
                result.warnings.append(f"JS-rendering fallback failed: {firecrawl_error}")

    if fetch_error and not result.is_empty():
        result.warnings.append(f"Direct fetch failed ({fetch_error}); used the Firecrawl fallback instead.")

    if result.is_empty():
        parts = ["Couldn't extract anything from that page."]
        if fetch_error:
            parts.append(f"Fetch failed: {fetch_error}.")
        if firecrawl_error:
            parts.append(f"Firecrawl fallback: {firecrawl_error}.")
        parts.append("Fill the fields in manually.")
        raise ValueError(" ".join(parts))
    return result.to_payload()
