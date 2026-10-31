import subprocess
import sys

import pytest

from jobhunt import dashboard
from jobhunt.dashboard import (
    build_application,
    create_draft_pack,
    extract_application_brand_theme,
    mark_draft_ready_for_review,
    read_application_draft,
    reset_application_brand_theme,
    review_cv_payload,
    save_application_draft,
    set_application_brand_url,
    set_application_brand_theme_mode,
    set_application_brand_typography,
    validate_draft_payload,
)
from jobhunt.database import init_db, upsert_jobs
from jobhunt.models import Company, Job


def valid_payload():
    return {
        "cv": {
            "max_pages": 2,
            "title": "Campaign Coordinator",
            "tagline": "Marketing coordinator who keeps campaign teams aligned and deliverables moving.",
            "profile": "Detail-driven marketing coordinator with experience across campaign delivery and reporting.",
            "experience": [
                {
                    "role": "Marketing Coordinator",
                    "company": "Northstar Cloud",
                    "period": "2026",
                    "location": "Amsterdam, NL",
                    "bullets": ["Coordinated campaign deliverables across web, social, email, CRM, and events."],
                }
            ],
            "additional": [],
        },
        "letter": {
            "max_pages": 1,
            "subtitle": "Campaign Coordinator - Example",
            "paragraphs": ["One.", "Two.", "Three."],
        },
    }


def test_validate_draft_payload_rejects_unknown_fields():
    payload = valid_payload()
    payload["cv"]["invented"] = "nope"

    with pytest.raises(ValueError, match="unsupported fields"):
        validate_draft_payload(payload)


def test_validate_draft_payload_defaults_existing_two_page_to_classic():
    cv_data, _, warnings = validate_draft_payload(valid_payload())

    assert cv_data["variant"] == "classic_two_page"
    assert cv_data["max_pages"] == 2
    assert cv_data["experience"][0]["include"] is True
    assert "Compact one-page CVs should use max_pages: 1." not in warnings


def test_validate_draft_payload_accepts_compact_builder_fields():
    payload = valid_payload()
    payload["cv"].update(
        {
            "max_pages": 1,
            "variant": "compact_one_page",
            "role_focus": "content",
            "selected_highlights": ["Cut listing errors by ~20% across 300+ weekly SKU audits."],
        }
    )
    payload["cv"]["experience"][0]["include"] = "false"

    cv_data, _, warnings = validate_draft_payload(payload)

    assert cv_data["variant"] == "compact_one_page"
    assert cv_data["role_focus"] == "content"
    assert cv_data["experience"][0]["include"] is False
    assert cv_data["selected_highlights"] == ["Cut listing errors by ~20% across 300+ weekly SKU audits."]
    assert warnings == []


def test_validate_draft_payload_normalizes_grotesk_marketing_experience():
    payload = valid_payload()
    payload["cv"].update(
        {
            "max_pages": 1,
            "variant": "grotesk_one_page",
            "role_focus": "marketing",
            "selected_highlights": ["This should remain data-only, not a rendered Grotesk section."],
            "additional": [
                {
                    "role": "Curatorial Assistant",
                    "company": "Studio Kinetix",
                    "period": "2022",
                    "location": "Rotterdam, NL",
                    "bullets": ["Produced 10+ marketing collateral pieces for artist and partner conversations."],
                }
            ],
        }
    )

    cv_data, _, warnings = validate_draft_payload(payload)

    assert cv_data["variant"] == "grotesk_one_page"
    assert cv_data["max_pages"] == 1
    assert cv_data["selected_highlights"] == []
    assert cv_data["additional"] == []
    assert cv_data["experience"][-1]["role"] == "Curatorial Assistant"
    assert cv_data["experience"][-1]["company"] == "Studio Kinetix"


def test_review_cv_payload_flags_sparse_two_page_risk():
    cv_data, _, _ = validate_draft_payload(valid_payload())

    review = review_cv_payload(cv_data, "Campaign marketing content role")

    assert review["band"] in {"Needs polish", "Risky"}
    assert any(item["title"] == "Sparse second page risk" for item in review["items"])


def grotesk_payload(role_specs):
    """Build a grotesk_one_page payload from (role, company, n_bullets) specs."""
    payload = valid_payload()
    payload["cv"].update({"max_pages": 1, "variant": "grotesk_one_page", "role_focus": "marketing"})
    payload["cv"]["profile"] = (
        "Content and digital marketing professional with hands-on experience managing multi-channel "
        "communications and turning data into strategy, from campaign coordination and CRM migrations "
        "to KPI dashboards, consumer insights, and retail engagement across NL and BE markets. "
        "Comfortable owning delivery end to end with cross-functional and external partners, "
        "and quick to fold new tools and AI-assisted workflows into day-to-day marketing operations."
    )
    payload["cv"]["experience"] = [
        {
            "role": role,
            "company": company,
            "period": "2026",
            "location": "Amsterdam, NL",
            "bullets": [
                f"Delivered measurable outcome number {i} across channels, partners, and reporting cadences."
                for i in range(n_bullets)
            ],
        }
        for role, company, n_bullets in role_specs
    ]
    payload["cv"]["additional"] = []
    return payload


FULL_GROTESK_ROLES = [
    ("Marketing Coordinator", "Northstar Cloud", 5),
    ("Data & Insights Analyst", "Veloce Mobility", 3),
    ("Sales Associate", "Veloce Mobility", 3),
    ("Curatorial & Marketing Assistant", "Studio Kinetix", 3),
    ("Marketing Operations Assistant", "Lumen Collective", 3),
]


def test_review_cv_payload_flags_underfilled_grotesk_page():
    payload = grotesk_payload(
        [
            ("Marketing Coordinator", "Northstar Cloud", 4),
            ("Data & Insights Analyst", "Veloce Mobility", 3),
            ("Sales Associate", "Veloce Mobility", 2),
            ("Curatorial & Marketing Assistant", "Studio Kinetix", 1),
        ]
    )
    cv_data, _, _ = validate_draft_payload(payload)

    review = review_cv_payload(cv_data, "Campaign marketing content role")

    assert any(item["title"] == "Under-filled one-page CV" for item in review["items"])


def test_review_cv_payload_flags_short_grotesk_profile():
    payload = grotesk_payload(FULL_GROTESK_ROLES)
    payload["cv"]["profile"] = "Marketing professional with a track record of aligning content strategy with business goals."
    cv_data, _, _ = validate_draft_payload(payload)

    review = review_cv_payload(cv_data, "Campaign marketing content role")

    assert any(item["title"] == "Summary shorter than the page budget" for item in review["items"])


def test_review_cv_payload_accepts_full_grotesk_page_without_density_warnings():
    cv_data, _, _ = validate_draft_payload(grotesk_payload(FULL_GROTESK_ROLES))

    review = review_cv_payload(cv_data, "Campaign marketing content role")

    titles = {item["title"] for item in review["items"]}
    assert "One-page density risk" not in titles
    assert "Too many bullets for compact mode" not in titles
    assert "Under-filled one-page CV" not in titles
    assert "Summary shorter than the page budget" not in titles


def test_review_cv_payload_still_flags_grotesk_overflow_risk():
    payload = grotesk_payload(
        [
            ("Marketing Coordinator", "Northstar Cloud", 5),
            ("Data & Insights Analyst", "Veloce Mobility", 5),
            ("Sales Associate", "Veloce Mobility", 4),
            ("Curatorial & Marketing Assistant", "Studio Kinetix", 3),
            ("Marketing Operations Assistant", "Lumen Collective", 3),
        ]
    )
    cv_data, _, _ = validate_draft_payload(payload)

    review = review_cv_payload(cv_data, "Campaign marketing content role")

    assert any(item["title"] == "One-page overflow risk" for item in review["items"])


def test_validate_draft_payload_full_grotesk_page_has_no_warnings():
    _, _, warnings = validate_draft_payload(grotesk_payload(FULL_GROTESK_ROLES))

    assert warnings == []


def test_draft_prompt_states_density_targets():
    prompt = dashboard._draft_prompt(
        {"title": "Content Manager", "company": "L'Oréal"},
        "Job listing text",
    )

    assert "14 to 18 bullets" in prompt or ("14" in prompt and "18" in prompt)
    assert "grotesk_one_page" in prompt
    assert "CANDIDATE FACTS" in prompt


def test_draft_prompt_injects_candidate_profile():
    from jobhunt.profile import CandidateContact, CandidateProfile

    custom_prof = CandidateProfile(
        name="Jordan Taylor",
        career_facts="- Growth Lead, Acme Corp, 2024: Built growth loops.\n- Marketer, Beta Inc, 2022: Managed paid ads.",
        skills=["Growth Hacking", "SQL"],
        contact=CandidateContact(location="Rotterdam, NL"),
    )
    prompt = dashboard._draft_prompt(
        {"title": "Growth Lead", "company": "Acme"},
        "Job listing text",
        profile=custom_prof,
    )
    assert "Jordan Taylor" in prompt
    assert "Acme Corp" in prompt
    assert "Growth Hacking, SQL" in prompt
    assert "Rotterdam, NL" in prompt


def test_get_candidate_facts_dynamic():
    from jobhunt.profile import CandidateContact, CandidateProfile

    prof = CandidateProfile(
        name="Sam Rivera",
        career_facts="- Marketing Specialist at Delta: Grew pipeline.",
        skills=["Copywriting", "SEO"],
        contact=CandidateContact(location="Utrecht, NL"),
    )
    facts = dashboard.get_candidate_facts(prof)
    assert "Sam Rivera is targeting roles in Utrecht, NL." in facts
    assert "Marketing Specialist at Delta: Grew pipeline." in facts
    assert "Skills: Copywriting, SEO" in facts


def test_reference_application_text_has_no_copyable_prose():
    """The style-targets note fed to the drafting model must stay numbers/tone
    only. An earlier version embedded the full Base/reference CV+letter YAML
    here, and the local model (qwen3:8b) reliably copied it almost verbatim
    instead of tailoring to the job listing -- 11 of 15 auto-drafted CVs in
    the 2026-07-08 batch were byte-identical to Base/reference/cv-data.yaml."""
    text = dashboard._reference_application_text()

    assert "do not copy" in text.lower()
    assert "14-18 bullets" in text or "14 to 18 bullets" in text
    # None of the sample CV/letter CV/letter prose should be reproducible from this note.
    assert "Northstar Cloud" not in text
    assert "Studio Kinetix" not in text


def test_draft_prompt_instructs_against_copying_previous_drafts():
    prompt = dashboard._draft_prompt(
        {"title": "Content Manager", "company": "L'Oréal"},
        "Job listing text",
    )

    assert "do not reuse" in prompt.lower()


def test_reference_application_is_canonical_and_full():
    """Base/reference stays the human-facing style/density exemplar and must
    itself pass every density/quality gate, even though its prose is no
    longer piped into the drafting prompt (see test above)."""
    import yaml

    cv_raw = yaml.safe_load((dashboard.ROOT / "Base" / "reference" / "cv-data.yaml").read_text(encoding="utf-8"))
    letter_raw = yaml.safe_load((dashboard.ROOT / "Base" / "reference" / "letter-data.yaml").read_text(encoding="utf-8"))
    cv_data, letter_data, warnings = validate_draft_payload({"cv": cv_raw, "letter": letter_raw})

    assert warnings == []
    review = review_cv_payload(cv_data, "")
    assert not any(item["level"] == "warning" for item in review["items"])
    forbidden = ("22%", "3x", "32%", "90% of", "tenure", "funding", "leaving")
    blob = (str(cv_data) + str(letter_data)).lower()
    assert not any(term.lower() in blob for term in forbidden)


def test_refine_prompt_allows_restoring_candidate_facts():
    prompt = dashboard._refine_prompt("CV:\n...", "Job listing text", "Add more bullets")

    assert "CANDIDATE FACTS" in prompt
    assert "reference only" not in prompt
    assert "restore" in prompt.lower() or "may add" in prompt.lower()


def test_create_draft_pack_refuses_missing_job(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", tmp_path / "Applications")

    with pytest.raises(ValueError, match="Job not found"):
        create_draft_pack(conn, 999)


def test_create_draft_pack_writes_expected_files_and_sets_tailoring(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(
        company="Red Bull",
        title="Brand Marketing Coordinator",
        location="Amsterdam",
        apply_url="https://example.com/job",
        description="Coordinate brand campaigns and content calendars.",
    )
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(
        dashboard,
        "generate_draft_with_ollama",
        lambda row, listing, custom_instructions="": (*validate_draft_payload(valid_payload()),),
    )

    result = create_draft_pack(conn, job_id)

    folder = apps / "Red-Bull-Brand-Marketing-Coordinator"
    assert result["folder_name"] == folder.name
    assert (folder / "job-listing.md").exists()
    assert (folder / "cv-data.yaml").exists()
    assert (folder / "letter-data.yaml").exists()
    assert conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"] == "tailoring"


def test_create_draft_pack_passes_and_records_custom_instructions(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(company="On", title="Trade Marketing Specialist", location="Netherlands", apply_url="https://example.com/job")
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    seen = {}
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)

    def fake_generate(row, listing, custom_instructions=""):
        seen["custom_instructions"] = custom_instructions
        return validate_draft_payload(valid_payload())

    monkeypatch.setattr(dashboard, "generate_draft_with_ollama", fake_generate)

    result = create_draft_pack(conn, job_id, "Put Lumen Collective Marketing Operations on page 1.")

    assert seen["custom_instructions"] == "Put Lumen Collective Marketing Operations on page 1."
    assert result["meta"]["custom_instructions"] == "Put Lumen Collective Marketing Operations on page 1."


def test_create_draft_pack_does_not_overwrite_existing_artifacts(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(company="Nike", title="Partner Marketing Specialist", location="Hilversum", apply_url="https://example.com/job")
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    folder = apps / "Nike-Partner-Marketing-Specialist"
    folder.mkdir(parents=True)
    (folder / "cv.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)

    with pytest.raises(ValueError, match="already has generated application artifacts"):
        create_draft_pack(conn, job_id)


def test_create_draft_pack_reuses_case_insensitive_existing_folder(tmp_path, monkeypatch):
    # Regression: the daily-sweep bot drafted a role from a lower-cased DB title
    # while a Title-cased folder for the same role already existed, minting a
    # case-variant sibling that collides on case-insensitive filesystems (Windows).
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(
        company="Cisco Systems",
        title="account executive portfolio",  # lower-cased, as the scraper stored it
        location="Amsterdam",
        apply_url="https://example.com/job",
    )
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    (apps / "Cisco-Systems-Account-Executive-Portfolio").mkdir(parents=True)  # existing Title-cased draft
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(
        dashboard,
        "generate_draft_with_ollama",
        lambda row, listing, custom_instructions="": validate_draft_payload(valid_payload()),
    )

    result = create_draft_pack(conn, job_id)

    assert result["folder_name"] == "Cisco-Systems-Account-Executive-Portfolio"


def test_invalid_ollama_result_does_not_create_folder(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(company="On", title="Trade Marketing Specialist", location="Netherlands", apply_url="https://example.com/job")
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(
        dashboard,
        "generate_draft_with_ollama",
        lambda row, listing, custom_instructions="": (_ for _ in ()).throw(ValueError("invalid model output")),
    )

    with pytest.raises(ValueError, match="invalid model output"):
        create_draft_pack(conn, job_id)

    assert not (apps / "On-Trade-Marketing-Specialist").exists()


def test_read_and_save_application_draft_round_trip(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    folder = apps / "Example-Role"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    save_application_draft(folder.name, valid_payload())

    draft = read_application_draft(folder.name)

    assert draft["folder_name"] == "Example-Role"
    assert draft["cv"]["title"] == "Campaign Coordinator"
    assert draft["letter"]["paragraphs"] == ["One.", "Two.", "Three."]
    assert draft["brand_theme"]["mode"] == "base"


def test_mark_draft_ready_for_review_returns_full_draft_doc(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(company="Nike", title="Partner Marketing Specialist", location="Hilversum", apply_url="https://example.com/job")
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    folder = apps / "Nike-Partner-Marketing-Specialist"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    save_application_draft(folder.name, valid_payload())

    result = mark_draft_ready_for_review(conn, folder.name, job_id)

    for key in ("cv", "letter", "listing", "warnings", "brand_theme", "brand_source", "cv_review", "limits"):
        assert key in result
    assert result["cv"]["title"] == "Campaign Coordinator"
    assert result["meta"]["state"] == "ready_for_review"
    assert conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"] == "ready"


def test_extract_and_reset_application_brand_theme(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    apps = tmp_path / "Applications"
    folder = apps / "Example-Role"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    save_application_draft(folder.name, valid_payload())

    def fake_extract(url, provider="auto"):
        from jobhunt.brand_theme import sanitize_theme

        return sanitize_theme(
            {
                "enabled": True,
                "provider": provider,
                "accent": "#0057FF",
                "confidence": 0.8,
                "source_url": url,
                "notes": ["fixture"],
            }
        )

    monkeypatch.setattr(dashboard, "extract_theme", fake_extract)

    extracted = extract_application_brand_theme(conn, folder.name, source_url="https://example.com/careers", provider="firecrawl")

    assert extracted["brand_theme"]["mode"] == "chameleon"
    assert extracted["brand_theme"]["theme"]["provider"] == "firecrawl"
    assert (folder / "brand-theme.yaml").exists()
    assert read_application_draft(folder.name)["brand_theme"]["enabled"] is True

    reset = reset_application_brand_theme(folder.name)

    assert reset["brand_theme"]["mode"] == "base"
    assert read_application_draft(folder.name)["brand_theme"]["enabled"] is False


def test_extract_application_brand_theme_prefers_company_brand_url(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "jobs.sqlite")
    job = Job(
        company="Accor",
        title="Commercial Manager",
        apply_url="https://careers.accor.com/global/en/job/commercial-manager",
        source_url="https://careers.accor.com/global/en/jobs?page=3",
    )
    upsert_jobs(conn, [job])
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    apps = tmp_path / "Applications"
    folder = apps / "Accor-commercial-manager"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(
        dashboard,
        "load_companies",
        lambda: [Company(company="Accor", careers_url="https://careers.accor.com", brand_url="https://group.accor.com/en")],
    )
    save_application_draft(folder.name, valid_payload())
    seen = {}

    def fake_extract(url, provider="auto"):
        seen["url"] = url
        from jobhunt.brand_theme import sanitize_theme

        return sanitize_theme(
            {
                "enabled": True,
                "provider": provider,
                "accent": "#9C6D36",
                "confidence": 0.8,
                "source_url": url,
            }
        )

    monkeypatch.setattr(dashboard, "extract_theme", fake_extract)

    result = extract_application_brand_theme(conn, folder.name, job_id=job_id, provider="local")

    assert seen["url"] == "https://group.accor.com/en"
    assert result["brand_source"]["kind"] == "company_site"
    assert result["brand_theme"]["theme"]["source_kind"] == "company_site"
    assert result["brand_theme"]["theme"]["source_reason"] == "Configured company brand_url."


def test_set_application_brand_url_overrides_configured_brand_source(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    folder = apps / "Accor-commercial-manager"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(
        dashboard,
        "load_companies",
        lambda: [Company(company="Accor", careers_url="https://careers.accor.com", brand_url="https://group.accor.com/en")],
    )
    save_application_draft(folder.name, valid_payload())

    saved = set_application_brand_url(folder.name, "https://all.accor.com")
    draft = read_application_draft(folder.name)

    assert saved["brand_source"]["url"] == "https://all.accor.com"
    assert saved["brand_source"]["override"] is True
    assert draft["brand_source"]["url"] == "https://all.accor.com"

    cleared = set_application_brand_url(folder.name, "")

    assert cleared["brand_source"]["url"] == "https://group.accor.com/en"
    assert cleared["brand_source"]["override"] is False


def test_application_brand_theme_dark_mode_is_opt_in_and_reversible(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    folder = apps / "Example-Role"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    save_application_draft(folder.name, valid_payload())
    dashboard.write_theme(
        folder,
        {
            "enabled": True,
            "provider": "firecrawl",
            "accent": "#E50914",
            "accent_dark": "#1A1A1A",
            "soft_bg": "#F5EBEB",
            "rule": "#DEC4C6",
            "link": "#E50914",
            "confidence": 0.88,
            "energy": "dark",
        },
    )

    dark = set_application_brand_theme_mode(folder.name, "dark")

    assert dark["brand_theme"]["enabled"] is True
    assert dark["brand_theme"]["theme"]["mode"] == "dark"
    assert dark["brand_theme"]["theme"]["page_bg"] == "#000000"
    assert dark["brand_theme"]["theme"]["light_tokens"]["soft_bg"] == "#F5EBEB"

    light = set_application_brand_theme_mode(folder.name, "light")

    assert light["brand_theme"]["theme"]["mode"] == "light"
    assert light["brand_theme"]["theme"]["soft_bg"] == "#F5EBEB"
    assert light["brand_theme"]["theme"]["rule"] == "#DEC4C6"


def test_application_brand_typography_is_opt_in_and_reversible(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    folder = apps / "Example-Role"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    save_application_draft(folder.name, valid_payload())
    dashboard.write_theme(
        folder,
        {
            "enabled": True,
            "provider": "firecrawl",
            "accent": "#E50914",
            "accent_dark": "#1A1A1A",
            "soft_bg": "#F5EBEB",
            "rule": "#DEC4C6",
            "link": "#E50914",
            "confidence": 0.88,
            "typography_available": True,
            "typography_enabled": False,
            "body_font": ["Inter", "Segoe UI", "Roboto"],
            "heading_font": ["Inter", "Segoe UI", "Roboto"],
            "typography_resolution": {"family": "Inter", "source": "google_fonts"},
        },
    )

    enabled = set_application_brand_typography(folder.name, True)

    assert enabled["brand_theme"]["theme"]["typography_enabled"] is True
    assert "Typography enabled by user." in enabled["brand_theme"]["theme"]["notes"]

    disabled = set_application_brand_typography(folder.name, False)

    assert disabled["brand_theme"]["theme"]["typography_enabled"] is False
    assert "Typography enabled by user." not in disabled["brand_theme"]["theme"]["notes"]


def test_build_application_returns_build_error(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    folder = apps / "Example-Role"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(dashboard, "ROOT", tmp_path)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="Typst assertion failed")

    monkeypatch.setattr(dashboard.subprocess, "run", fake_run)

    result = build_application(folder.name)

    assert result["ok"] is False
    assert "Typst assertion failed" in result["error"]


def test_build_application_invokes_cli(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    folder = apps / "Example-Role"
    folder.mkdir(parents=True)
    (folder / "cv.pdf").write_text("pdf", encoding="utf-8")
    (folder / "motivation-letter.pdf").write_text("pdf", encoding="utf-8")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", apps)
    monkeypatch.setattr(dashboard, "ROOT", tmp_path)

    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        return subprocess.CompletedProcess(args[0], 0, stdout="OK", stderr="")

    monkeypatch.setattr(dashboard.subprocess, "run", fake_run)

    result = build_application(folder.name)

    assert result["ok"] is True
    assert calls
    assert calls[0][:5] == [sys.executable, "-m", "jobhunt", "build", "--app"]
