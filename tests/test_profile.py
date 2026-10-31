from pathlib import Path
import pytest
from jobhunt.profile import SearchRules, load_candidate_profile, load_search_rules, CandidateProfile, CandidateContact, export_profile_for_typst


def test_load_candidate_profile_from_example(tmp_path: Path):
    yaml_content = """
candidate:
  name: "Alex Morgan"
  tagline: "Growth Marketer"
  contact:
    email: "alex@example.com"
    phone: "+31 6 12345678"
    location: "Amsterdam, Netherlands"
    linkedin: "linkedin.com/in/alex"
    linkedin_url: "https://linkedin.com/in/alex"
    portfolio: "alex.design"
    portfolio_url: "https://alex.design"
  career_facts: |
    - Marketer at Corp A (2023-Present): Scaled leads by 30%.
  skills:
    - "Lifecycle Marketing"
    - "SQL Analytics"
  languages:
    - ["English", "Native"]
  education:
    - deg: "BSc Business"
      school: "UvA"
      notes: ["Honors"]
  certifications:
    - "HubSpot Certified"
target_preferences:
  target_roles: ["Marketing Manager"]
  target_locations: ["Amsterdam"]
"""
    cfg_file = tmp_path / "profile.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    prof = load_candidate_profile(cfg_file)
    assert prof.name == "Alex Morgan"
    assert prof.tagline == "Growth Marketer"
    assert prof.contact.email == "alex@example.com"
    assert prof.contact.phone == "+31 6 12345678"
    assert prof.contact.location == "Amsterdam, Netherlands"
    assert prof.contact.linkedin == "linkedin.com/in/alex"
    assert prof.contact.linkedin_url == "https://linkedin.com/in/alex"
    assert prof.contact.portfolio == "alex.design"
    assert prof.contact.portfolio_url == "https://alex.design"
    assert len(prof.skills) == 2
    assert len(prof.languages) == 1
    assert len(prof.education) == 1
    assert len(prof.certifications) == 1
    assert prof.target_roles == ["Marketing Manager"]
    assert prof.target_locations == ["Amsterdam"]
    assert "Marketer at Corp A" in prof.career_facts

    typst_data = export_profile_for_typst(prof)
    assert typst_data["name"] == "Alex Morgan"
    assert typst_data["tagline"] == "Growth Marketer"
    assert len(typst_data["contact"]) == 5
    assert typst_data["contact"][0]["value"] == "alex@example.com"
    assert typst_data["contact"][0]["url"] == "mailto:alex@example.com"
    assert typst_data["contact"][1]["label"] == "Phone"
    assert typst_data["contact"][2]["label"] == "Location"
    assert typst_data["contact"][3]["url"] == "https://linkedin.com/in/alex"
    assert typst_data["contact"][4]["url"] == "https://alex.design"


def test_load_candidate_profile_fallback(tmp_path: Path):
    prof = load_candidate_profile(tmp_path / "non_existent_profile.yaml")
    assert isinstance(prof, CandidateProfile)


def test_load_candidate_profile_default_repo_config():
    prof = load_candidate_profile()
    assert isinstance(prof, CandidateProfile)
    assert prof.name != ""


def test_export_profile_for_typst_defaults_urls():
    prof = CandidateProfile(
        name="Test User",
        contact=CandidateContact(
            linkedin="linkedin.com/in/testuser",
            portfolio="testuser.com",
        ),
    )
    typst_data = export_profile_for_typst(prof)
    assert typst_data["contact"][0]["url"] == "https://linkedin.com/in/testuser"
    assert typst_data["contact"][1]["url"] == "https://testuser.com"


def test_load_candidate_profile_empty_yaml(tmp_path: Path):
    cfg_file = tmp_path / "empty.yaml"
    cfg_file.write_text("", encoding="utf-8")
    prof = load_candidate_profile(cfg_file)
    assert prof.name == "Candidate Name"
    assert prof.skills == []


def test_search_rules_loaded_from_target_preferences(tmp_path: Path):
    cfg = tmp_path / "profile.yaml"
    cfg.write_text(
        "target_preferences:\n  target_roles: [X]\n  target_locations: [Berlin]\n  max_years_experience: 3\n  allow_remote: false\n",
        encoding="utf-8",
    )
    rules = load_search_rules(cfg)
    assert rules.target_roles == ("X",)
    assert rules.accepted_locations == ("Berlin",)
    assert rules.max_years_experience == 3
    assert rules.allow_remote is False
    assert load_candidate_profile(cfg).search == rules


def test_missing_search_keys_give_permissive_defaults(tmp_path: Path):
    cfg = tmp_path / "profile.yaml"
    cfg.write_text("candidate:\n  name: Z\n", encoding="utf-8")
    assert load_search_rules(cfg) == SearchRules()
    assert SearchRules().allow_remote is True


def test_search_rules_cache_refreshes_on_change(tmp_path: Path):
    import os
    cfg = tmp_path / "profile.yaml"
    cfg.write_text("target_preferences:\n  target_roles: [A]\n", encoding="utf-8")
    assert load_search_rules(cfg).target_roles == ("A",)
    cfg.write_text("target_preferences:\n  target_roles: [B]\n", encoding="utf-8")
    st = cfg.stat()
    os.utime(cfg, (st.st_atime, st.st_mtime + 5))
    assert load_search_rules(cfg).target_roles == ("B",)
