import pytest

from jobhunt.job_scrape import (
    ListingExtract,
    extract_from_firecrawl,
    extract_from_json_ld,
    extract_from_meta,
    looks_like_js_shell,
    scrape_job_listing,
)

LONG_BODY = " ".join(
    "We are looking for a marketing manager to own campaigns across the Benelux "
    "region, working with brand, content, and product teams.".split()
) * 5


def _no_firecrawl(url: str) -> dict:
    raise RuntimeError("firecrawl disabled in tests")


JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@type": "JobPosting",
  "title": "Content Coordinator",
  "hiringOrganization": {"@type": "Organization", "name": "Vitamin Well"},
  "description": "<p>Coordinate content across channels.</p>",
  "jobLocation": {"address": {"addressLocality": "Amsterdam", "addressCountry": "NL"}}
}
</script>
</head><body><h1>Join us</h1></body></html>
"""


def test_json_ld_jobposting_extracts_all_fields():
    extract = extract_from_json_ld(JSON_LD_HTML, "https://example.com/jobs/1")

    assert extract.title == "Content Coordinator"
    assert extract.company == "Vitamin Well"
    assert extract.location == "Amsterdam, NL"
    assert "Coordinate content" in extract.description
    assert extract.source == "json_ld"


def test_json_ld_graph_variant():
    html = """
    <script type="application/ld+json">
    {"@graph": [
      {"@type": "WebSite", "name": "Careers"},
      {"@type": "JobPosting", "title": "Brand Manager",
       "hiringOrganization": {"name": "Acme"},
       "description": "Run the brand."}
    ]}
    </script>
    """

    extract = extract_from_json_ld(html, "https://example.com/jobs/2")

    assert extract.title == "Brand Manager"
    assert extract.company == "Acme"


def test_og_only_page_extracts_title_company_description():
    html = f"""
    <html><head>
    <meta property="og:title" content="Marketing Manager - Acme | Careers" />
    <meta property="og:site_name" content="Acme" />
    </head><body><main><p>{LONG_BODY}</p></main></body></html>
    """

    result = scrape_job_listing(
        "https://careers.acme.com/jobs/3",
        fetcher=lambda url: html,
        firecrawl_fetcher=_no_firecrawl,
    )

    assert result["title"] == "Marketing Manager"
    assert result["company"] == "Acme"
    assert "marketing manager" in result["description"].lower()
    assert result["source"] == "meta"


def test_meta_description_fallback_adds_warning():
    html = """
    <html><head>
    <meta property="og:title" content="Campaign Manager" />
    <meta property="og:description" content="Short teaser about the role." />
    </head><body><p>tiny</p></body></html>
    """

    extract = extract_from_meta(html, "https://careers.acme.com/jobs/4")

    assert extract.description == "Short teaser about the role."
    assert any("summary" in w.lower() for w in extract.warnings)


def test_company_guessed_from_domain_adds_warning():
    html = f"""
    <html><head><title>Junior Digital Marketing Consultant</title></head>
    <body><article>{LONG_BODY}</article></body></html>
    """

    extract = extract_from_meta(html, "https://career.vitaminwell.com/jobs/5")

    assert extract.company == "Vitaminwell"
    assert any("domain" in w.lower() for w in extract.warnings)


def test_empty_page_raises_value_error():
    with pytest.raises(ValueError):
        scrape_job_listing(
            "https://example.com/empty",
            fetcher=lambda url: "<html></html>",
            firecrawl_fetcher=_no_firecrawl,
        )


def test_js_shell_detection():
    shell = '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
    content = f"<html><body><main>{LONG_BODY}</main></body></html>"

    assert looks_like_js_shell(shell) is True
    assert looks_like_js_shell(content) is False


def test_js_shell_escalates_to_firecrawl():
    calls = []

    def fake_firecrawl(url: str) -> dict:
        calls.append(url)
        return {
            "markdown": "# Channel Marketing Specialist\n\n" + LONG_BODY,
            "metadata": {"ogTitle": "Channel Marketing Specialist", "ogSiteName": "Sony"},
        }

    result = scrape_job_listing(
        "https://sony.example.com/job/6",
        fetcher=lambda url: '<div id="root"></div>',
        firecrawl_fetcher=fake_firecrawl,
    )

    assert calls == ["https://sony.example.com/job/6"]
    assert result["title"] == "Channel Marketing Specialist"
    assert result["company"] == "Sony"
    assert "marketing manager" in result["description"].lower()
    assert result["source"] == "firecrawl"


def test_fetch_error_falls_back_to_firecrawl():
    def failing_fetch(url: str) -> str:
        raise RuntimeError("HTTP 999 blocked")

    result = scrape_job_listing(
        "https://linkedin.example.com/jobs/7",
        fetcher=failing_fetch,
        firecrawl_fetcher=lambda url: {
            "markdown": LONG_BODY,
            "metadata": {"title": "B2B Marketeer at Firefly"},
        },
    )

    assert result["source"] == "firecrawl"
    assert result["description"]


def test_fetch_error_without_firecrawl_raises_readable_message():
    def failing_fetch(url: str) -> str:
        raise RuntimeError("HTTP 999 blocked")

    with pytest.raises(ValueError, match="999"):
        scrape_job_listing(
            "https://linkedin.example.com/jobs/8",
            fetcher=failing_fetch,
            firecrawl_fetcher=_no_firecrawl,
        )


@pytest.mark.parametrize("url", ["", "ftp://example.com/x", "javascript:alert(1)", "http://localhost/x", "http://127.0.0.1/x"])
def test_scrape_rejects_non_http_url(url):
    with pytest.raises(ValueError):
        scrape_job_listing(url, fetcher=lambda u: "<html></html>", firecrawl_fetcher=_no_firecrawl)


def test_merge_fills_gaps_only():
    first = ListingExtract(title="Brand Manager", source="json_ld")
    second = ListingExtract(title="SHOULD NOT WIN", description="Body text.", source="meta", warnings=["guessed"])

    merged = first.merge(second)

    assert merged.title == "Brand Manager"
    assert merged.description == "Body text."
    assert merged.source == "json_ld"
    assert merged.warnings == ["guessed"]


def test_double_escaped_json_ld_description_is_stripped():
    # Teamtailor (Vitamin Well) HTML-escapes the description inside JSON-LD, so
    # one strip pass yields literal "<p>" tags — the extractor must re-strip.
    html = """
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Content Coordinator",
     "description": "&lt;p&gt;&lt;em&gt;At Vitamin Well we make drinks.&lt;/em&gt;&lt;/p&gt;"}
    </script>
    """

    extract = extract_from_json_ld(html, "https://career.vitaminwell.com/jobs/1")

    assert "<p>" not in extract.description
    assert "At Vitamin Well we make drinks." in extract.description


def test_literal_backslash_n_normalized():
    # Sungrow's JSON-LD carries literal "\n" sequences in the description text.
    html = r"""
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Marketing Manager",
     "description": "Your duties\\nJoin us on our mission."}
    </script>
    """

    extract = extract_from_json_ld(html, "https://career-europe.sungrowpower.com/offer/x")

    assert "\\n" not in extract.description
    assert "Your duties\nJoin us" in extract.description


def test_http_404_fails_cleanly_without_firecrawl():
    import httpx

    calls = []

    def fetch_404(url: str) -> str:
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))

    def firecrawl(url: str) -> dict:
        calls.append(url)
        return {"markdown": "cookie banner", "metadata": {}}

    with pytest.raises(ValueError, match="404"):
        scrape_job_listing("https://example.com/gone", fetcher=fetch_404, firecrawl_fetcher=firecrawl)
    assert calls == []


def test_linkedin_hiring_title_fills_company_and_location():
    html = f"""
    <html><head>
    <meta property="og:title" content="Hunkemöller hiring Campaign Manager (6 months) in Hilversum, North Holland, Netherlands | LinkedIn" />
    </head><body><main>{LONG_BODY}</main></body></html>
    """

    extract = extract_from_meta(html, "https://www.linkedin.com/jobs/view/123/")

    assert extract.title == "Campaign Manager (6 months)"
    assert extract.company == "Hunkemöller"
    assert extract.location == "Hilversum, North Holland, Netherlands"
    assert not any("domain" in w.lower() for w in extract.warnings)


def test_description_prefers_specific_container_over_main():
    chrome = "Sign in to continue. " * 40
    jd = "At Hunkemöller we are looking for a concept-driven campaign manager. " * 10
    html = f"""
    <html><body><main>
    <nav>{chrome}</nav>
    <div class="description__text">{jd}</div>
    </main></body></html>
    """

    extract = extract_from_meta(html, "https://www.linkedin.com/jobs/view/124/")

    assert "concept-driven" in extract.description
    assert "Sign in to continue" not in extract.description


def test_generic_page_titles_are_dropped():
    data = {
        "markdown": "We use cookies to make the site better.\n\nDecline\n\nAccept Cookies\n\nThe page you are looking for doesn't exist.",
        "metadata": {"title": "Careers"},
    }

    extract = extract_from_firecrawl(data, "https://sonyglobal.wd1.myworkdayjobs.com/x")

    assert extract.is_empty()


def test_cookie_banner_description_is_dropped():
    data = {
        "markdown": "We value your privacy. We use cookies to enhance your browsing experience. CustomizeReject AllAccept All",
        "metadata": {"title": "Junior Consultant Vacancy"},
    }

    extract = extract_from_firecrawl(data, "https://example.com/jobs/1")

    assert extract.description is None
    assert extract.title == "Junior Consultant Vacancy"


def test_merge_drops_warnings_for_fields_that_lost():
    from jobhunt.job_scrape import DOMAIN_GUESS_WARNING, TEASER_WARNING

    json_ld = ListingExtract(company="Logitech Europe SA", description=LONG_BODY, source="json_ld")
    meta = ListingExtract(
        company="Logitech",
        description="Short teaser.",
        source="meta",
        warnings=[DOMAIN_GUESS_WARNING, TEASER_WARNING],
    )

    merged = json_ld.merge(meta)

    assert merged.company == "Logitech Europe SA"
    assert merged.warnings == []


def test_firecrawl_markdown_is_cleaned():
    data = {
        "markdown": "[Skip to content](#main)\n\n# Role\n\n![logo](https://x/logo.png)\n\nDo **great** [work](https://x/w).",
        "metadata": {"ogTitle": "Role | Acme"},
    }

    extract = extract_from_firecrawl(data, "https://careers.acme.com/jobs/9")

    assert "![" not in extract.description
    assert "](" not in extract.description
    assert "work" in extract.description
