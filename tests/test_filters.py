import pytest

from jobhunt.assessment import assess_job
from jobhunt.filters import location_ok, title_ok, job_ok, calculate_priority
from jobhunt.models import Job


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
        ("Meewerkstage Social media Marketing", False),
    ],
)
def test_title_filter(title, expected):
    assert title_ok(title) is expected


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
    assert location_ok(location) is expected


def test_dutch_language_filter():
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Vloeiend Nederlands vereist", location="Amsterdam")) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Dutch fluency is a must", location="Amsterdam")) is False
    assert job_ok(Job("PepsiCo", "Marketing Specialist (Nederlands vereist)", description="Details...", location="Amsterdam")) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Bilingual Dutch / English. Dutch is a plus.", location="Amsterdam")) is True

    assert job_ok(Job("PepsiCo", "Marketing Manager", description="This role is in English. Speaking Dutch is a pre.", location="Amsterdam")) is True

def test_experience_filter():
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Requires 5+ years of experience", location="Amsterdam")) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Minimum 5-8 years of experience in content.", location="Amsterdam")) is False
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="Requires 2-4 years of experience", location="Amsterdam")) is True
    assert job_ok(Job("PepsiCo", "Marketing Manager", description="No experience limits specified.", location="Amsterdam")) is True

def test_priority_calculation():
    job_high = Job("PepsiCo", "Marketing Manager", description="Own content campaigns and collaborate cross-functionally to launch growth programs.", location="Amsterdam")
    assert job_ok(job_high) is True
    full_text = " ".join(part for part in (job_high.title, job_high.description, job_high.requirements) if part)
    job_high.priority = calculate_priority(full_text)
    assert job_high.priority == "⭐ High"

    job_med = Job("PepsiCo", "Account Manager", description="Build client relationships and coordinate campaigns for retail partners.", location="Amsterdam")
    assert job_ok(job_med) is True
    assessment = assess_job(job_med)
    assert assessment.priority == "⭐ High"
    assert assessment.fit_band == "adjacent_plausible"

    job_low = Job("PepsiCo", "Marketing Manager", description="Requires 4 years of experience managing social campaigns.", location="Amsterdam")
    assert job_ok(job_low) is True
    assessment = assess_job(job_low)
    assert assessment.priority == "Low"
    assert assessment.fit_band == "stretch"


def test_seniority_hard_fail_blocks_unachievable_roles():
    assert assess_job(Job("Nike", "Senior Brand Manager", location="Hilversum")).included is False
    assert assess_job(Job("Nike", "Brand Manager", description="Requires 5+ years of experience.", location="Hilversum")).hard_fail_reason == "seniority"
    assert assess_job(Job("Nike", "Marketing Manager", description="Manage a team of campaign specialists.", location="Hilversum")).hard_fail_reason == "seniority"


def test_broad_adjacent_roles_can_survive_when_plausible():
    assessment = assess_job(
        Job(
            "Bynder",
            "Partnership Coordinator",
            description="Coordinate partner campaigns, build relationships, and support cross-functional launch plans.",
            location="Amsterdam",
        )
    )
    assert assessment.included is True
    assert assessment.fit_band == "adjacent_plausible"
    assert "Adjacent plausible" in assessment.reason_chips


def test_storefront_floor_hard_fail_blocks_retail_jobs():
    assert assess_job(Job("Foot Locker", "Sales Associate", location="Amsterdam")).included is False
    assert assess_job(Job("Foot Locker", "Sales Associate", location="Amsterdam")).hard_fail_reason == "storefront_floor"
    assert assess_job(Job("Nike", "Store Manager", location="Amsterdam")).included is False
    assert assess_job(Job("Adidas", "Sales Advisor", location="Amsterdam")).included is False
    assert assess_job(Job("Asics", "Retail Assistant", location="Amsterdam")).included is False

