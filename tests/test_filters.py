import pytest

from jobhunt.assessment import assess_job
from jobhunt.filters import location_ok, title_ok, job_ok, calculate_priority
from jobhunt.models import Job
from jobhunt.profile import SearchRules

NL_MARKETING = SearchRules(
    target_roles=("marketing", "campaign", "content", "brand", "communications", "communication", "crm", "social media", "copywriter", "editor"),
    adjacent_roles=(
        "account manager", "account management", "partnership", "partnerships", "partner", "community",
        "customer success", "client success", "growth", "business development", "operations", "strategy",
        "analytics", "sales", "sales operations", "sales enablement", "field sales",
    ),
    excluded_functions=(
        "engineering", "engineer", "software", "backend", "frontend", "full stack", "infrastructure", "sap",
        "technical", "recruitment", "recruiter", "hr business", "human resources", "talent",
    ),
    max_years_experience=4,
    exclude_senior_titles=True,
    exclude_internships=True,
    accepted_locations=(
        "den haag", "the hague", "amsterdam", "rotterdam", "delft", "utrecht", "hilversum", "netherlands",
        "nederland", "nl", "remote nl", "remote - nl", "remote netherlands",
    ),
    preferred_cities=("delft", "den haag", "the hague", "amsterdam", "rotterdam"),
    excluded_language_patterns=(
        r"vloeiend nederlands", r"nederlands vereist", r"nederlands.*vereiste", r"nederlands als moedertaal",
        r"dutch fluency.*must", r"dutch fluency", r"fluent in dutch.*must", r"fluent in dutch",
        r"must be fluent in dutch", r"native dutch", r"vloeiende beheersing van.*nederlandse",
    ),
)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Content Coordinator", True),
        ("Assistant Content Producer - EA SPORTS FC", True),
        ("Brand Campaign Manager", True),
        ("CRM Marketing Specialist", True),
        ("Account Manager", True),
        ("Partnership Coordinator", True),
        ("Customer Success Specialist", True),
        ("Business Development Executive", True),
        ("Marketing", False),
        ("Brand", False),
        ("content", False),
        ("pcs-content-v1.pcs-media-cc-view1-option1.theme21-px", False),
        ("Senior Director, Brand", False),
        ("VP Marketing", False),
        ("Software Engineer", False),
        ("Marketing Intern", False),
        ("Stage Shopper Marketing", False),
    ],
)
def test_title_filter(title, expected):
    assert title_ok(title, rules=NL_MARKETING) is expected


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Amsterdam, Netherlands", True),
        ("Delft, NL", True),
        ("Den Haag", True),
        ("Remote Netherlands", True),
        ("Remote - Europe", False),
        ("London, UK", False),
        ("Stockholm, Sweden", False),
        (None, False),
    ],
)
def test_location_filter(location, expected):
    assert location_ok(location, rules=NL_MARKETING) is expected


def test_dutch_language_filter():
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Vloeiend Nederlands vereist", location="Amsterdam"), rules=NL_MARKETING) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Dutch fluency is a must", location="Amsterdam"), rules=NL_MARKETING) is False
    assert job_ok(Job("PepsiCo", "Marketing Specialist (Nederlands vereist)", description="Details...", location="Amsterdam"), rules=NL_MARKETING) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Bilingual Dutch / English. Dutch is a plus.", location="Amsterdam"), rules=NL_MARKETING) is True

    assert job_ok(Job("PepsiCo", "Marketing Manager", description="This role is in English. Speaking Dutch is a pre.", location="Amsterdam"), rules=NL_MARKETING) is True

def test_experience_filter():
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Requires 5+ years of experience", location="Amsterdam"), rules=NL_MARKETING) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Minimum 5-8 years of experience in content.", location="Amsterdam"), rules=NL_MARKETING) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Requires 2-4 years of experience", location="Amsterdam"), rules=NL_MARKETING) is True
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="No experience limits specified.", location="Amsterdam"), rules=NL_MARKETING) is True

def test_priority_calculation():
    job_high = Job("PepsiCo", "Marketing Manager", description="Own content campaigns and collaborate cross-functionally to launch growth programs.", location="Amsterdam")
    assert job_ok(job_high, rules=NL_MARKETING) is True
    full_text = " ".join(part for part in (job_high.title, job_high.description, job_high.requirements) if part)
    job_high.priority = calculate_priority(full_text, rules=NL_MARKETING)
    assert job_high.priority == "⭐ High"

    job_med = Job("PepsiCo", "Account Manager", description="Build client relationships and coordinate campaigns for retail partners.", location="Amsterdam")
    assert job_ok(job_med, rules=NL_MARKETING) is True
    assessment = assess_job(job_med, rules=NL_MARKETING)
    assert assessment.priority == "⭐ High"
    assert assessment.fit_band == "adjacent_plausible"

    job_low = Job("PepsiCo", "Marketing Manager", description="Requires 4 years of experience managing social campaigns.", location="Amsterdam")
    assert job_ok(job_low, rules=NL_MARKETING) is True
    assessment = assess_job(job_low, rules=NL_MARKETING)
    assert assessment.priority == "Low"
    assert assessment.fit_band == "stretch"


def test_seniority_hard_fail_blocks_unachievable_roles():
    assert assess_job(Job("Nike", "Senior Brand Manager", location="Hilversum"), rules=NL_MARKETING).included is False
    assert assess_job(Job("Nike", "Brand Manager", description="Requires 5+ years of experience.", location="Hilversum"), rules=NL_MARKETING).hard_fail_reason == "seniority"
    assert assess_job(Job("Nike", "Marketing Manager", description="Manage a team of campaign specialists.", location="Hilversum"), rules=NL_MARKETING).hard_fail_reason == "seniority"


def test_broad_adjacent_roles_can_survive_when_plausible():
    assessment = assess_job(
        Job(
            "Bynder",
            "Partnership Coordinator",
            description="Coordinate partner campaigns, build relationships, and support cross-functional launch plans.",
            location="Amsterdam",
        ), rules=NL_MARKETING)
    assert assessment.included is True
    assert assessment.fit_band == "adjacent_plausible"
    assert "Adjacent plausible" in assessment.reason_chips


def test_storefront_floor_hard_fail_blocks_retail_jobs():
    assert assess_job(Job("Foot Locker", "Sales Associate", location="Amsterdam"), rules=NL_MARKETING).included is False
    assert assess_job(Job("Foot Locker", "Sales Associate", location="Amsterdam"), rules=NL_MARKETING).hard_fail_reason == "storefront_floor"
    assert assess_job(Job("Nike", "Store Manager", location="Amsterdam"), rules=NL_MARKETING).included is False
    assert assess_job(Job("Adidas", "Sales Advisor", location="Amsterdam"), rules=NL_MARKETING).included is False
    assert assess_job(Job("Asics", "Retail Assistant", location="Amsterdam"), rules=NL_MARKETING).included is False



def test_empty_rules_accept_manual_entry_without_location():
    a = assess_job(Job("Acme", "Data Analyst"), rules=SearchRules())
    assert a.included is True


def test_target_roles_match_all_words_of_phrase():
    rules = SearchRules(target_roles=("product designer",))
    assert assess_job(Job("Acme", "Senior Product Designer", location="Berlin"), rules=rules).included is True
    assert assess_job(Job("Acme", "Product Manager", location="Berlin"), rules=rules).hard_fail_reason == "theme"


def test_excluded_functions_hard_fail():
    rules = SearchRules(excluded_functions=("recruiter",))
    assert assess_job(Job("Acme", "Technical Recruiter Lead"), rules=rules).hard_fail_reason == "wrong_function"


def test_language_patterns_are_configurable():
    rules = SearchRules(excluded_language_patterns=(r"fluent german",))
    job = Job("Acme", "Account Manager", description="Fluent German required", location="Berlin")
    assert assess_job(job, rules=rules).hard_fail_reason == "language_required"


def test_language_patterns_tolerate_inline_flags_and_invalid_regex():
    rules = SearchRules(excluded_language_patterns=(r"(?i)fluent german", r"[unclosed"))
    job = Job("Acme", "Account Manager", description="Fluent German required", location="Berlin")
    assert assess_job(job, rules=rules).hard_fail_reason == "language_required"
    job_unclosed = Job("Acme", "Account Manager", description="Needs [unclosed skill", location="Berlin")
    assert assess_job(job_unclosed, rules=rules).hard_fail_reason == "language_required"
    job_ok = Job("Acme", "Account Manager", description="English only", location="Berlin")
    assert assess_job(job_ok, rules=rules).included is True



def test_remote_role_allowed_only_when_allow_remote():
    job = Job("Acme", "Account Manager", location="Lisbon", remote_type="Remote")
    assert assess_job(job, rules=SearchRules(accepted_locations=("berlin",))).included is True
    assert assess_job(job, rules=SearchRules(accepted_locations=("berlin",), allow_remote=False)).hard_fail_reason == "geography"
