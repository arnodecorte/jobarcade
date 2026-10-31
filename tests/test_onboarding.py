from __future__ import annotations

import pytest
import yaml

from jobhunt import profile as profile_module
from jobhunt.database import init_db
from jobhunt.onboarding import (
    ProfileError,
    ensure_profile_file,
    get_goals,
    onboarding_state,
    read_profile_document,
    reset_onboarding,
    save_goals,
    set_onboarding_step,
    skip_onboarding,
    write_profile_document,
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNT_SECRET_KEY_PATH", str(tmp_path / "config" / ".key"))
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    connection = init_db(tmp_path / "jobs.sqlite")
    yield connection
    connection.close()


def _example_name():
    return yaml.safe_load(profile_module.EXAMPLE_PROFILE_PATH.read_text())["candidate"]["name"]


def test_ensure_profile_creates_skeleton_once(tmp_path):
    target = tmp_path / "profile.yaml"
    assert ensure_profile_file(target) is True
    target.write_text("candidate:\n  name: Edited\n")
    assert ensure_profile_file(target) is False
    assert "Edited" in target.read_text()


def test_fresh_profile_is_a_blank_candidate(tmp_path):
    target = tmp_path / "profile.yaml"
    ensure_profile_file(target)
    raw = yaml.safe_load(target.read_text())
    cand = raw["candidate"]
    assert cand["name"] == "" and cand["tagline"] == "" and cand["career_facts"] == ""
    assert all(value == "" for value in cand["contact"].values())
    for key in ("skills", "education", "languages", "certifications"):
        assert cand[key] == []
    assert cand["signature"] == ""
    assert _example_name() not in target.read_text()
    # The permissive, commented target_preferences block is kept.
    assert raw["target_preferences"]["allow_remote"] is True
    assert raw["target_preferences"]["target_roles"] == []
    assert "# Job titles you are aiming for" in target.read_text()
    assert read_profile_document(target)["candidate"]["career_facts"] == ""
    assert profile_module.load_candidate_profile(target).search == profile_module.SearchRules()


def test_profile_check_requires_real_name(conn, tmp_path):
    path = tmp_path / "profile.yaml"
    ensure_profile_file(path)
    assert onboarding_state(conn, path)["checks"]["profile"] is False
    path.write_text(f"candidate:\n  name: {_example_name()}\n")
    assert onboarding_state(conn, path)["checks"]["profile"] is False
    write_profile_document({"candidate": {"name": "Sam Rivera"}}, path)
    assert onboarding_state(conn, path)["checks"]["profile"] is True


def test_profile_writes_keep_readable_mode(tmp_path):
    import stat

    path = tmp_path / "profile.yaml"
    ensure_profile_file(path)
    write_profile_document({"candidate": {"name": "Sam"}}, path)
    assert stat.S_IMODE(path.stat().st_mode) & 0o044 == 0o044  # group/other readable, not 0600
    path.chmod(0o640)
    write_profile_document({"candidate": {"name": "Sam R"}}, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    fresh = tmp_path / "new" / "profile.yaml"
    write_profile_document({"candidate": {"name": "Sam"}}, fresh)
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o644


def test_state_defaults_to_pending_with_checks_false(conn, tmp_path):
    state = onboarding_state(conn, tmp_path / "profile.yaml")
    assert state["status"] == "pending"
    assert state["step"] == "welcome"
    assert state["checks"] == {"ai": False, "profile": False, "style": False, "chameleon": False, "goal": False}
    assert state["profile_error"] is None


def test_skip_then_reset_round_trip(conn):
    assert skip_onboarding(conn)["status"] == "skipped"
    set_onboarding_step(conn, "goal")
    state = reset_onboarding(conn)
    assert state["status"] == "pending"
    assert state["step"] == "welcome"


def test_unknown_step_rejected(conn):
    with pytest.raises(ValueError):
        set_onboarding_step(conn, "bogus")


def test_write_profile_preserves_unknown_keys(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("candidate:\n  name: Old\n  education:\n    - deg: BSc\nextra: 1\n")
    result = write_profile_document({"candidate": {"name": "New Name"}}, path)
    raw = yaml.safe_load(path.read_text())
    assert raw["candidate"]["name"] == "New Name"
    assert raw["candidate"]["education"] == [{"deg": "BSc"}]
    assert raw["extra"] == 1
    assert result["candidate"]["name"] == "New Name"


def test_write_profile_validates_email_and_lists(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("candidate:\n  name: Old\n")
    before = path.read_bytes()
    bad_payloads = [
        {"candidate": {"contact": {"email": "nope"}}},
        {"candidate": {"skills": "python"}},
        {"candidate": {"skills": ["x" * 121]}},
        {"candidate": {"name": ""}},
        {"target_preferences": {"max_years_experience": 51}},
        {"target_preferences": {"allow_remote": "yes"}},
    ]
    for payload in bad_payloads:
        with pytest.raises(ValueError):
            write_profile_document(payload, path)
    assert path.read_bytes() == before


def test_broken_yaml_read_raises_profile_error_and_write_refuses(conn, tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("candidate: [unclosed")
    before = path.read_bytes()
    with pytest.raises(ProfileError):
        read_profile_document(path)
    with pytest.raises(ProfileError):
        write_profile_document({"candidate": {"name": "X"}}, path)
    assert path.read_bytes() == before
    assert onboarding_state(conn, path)["profile_error"]


def test_profile_check_flips_after_name_change(conn, tmp_path):
    path = tmp_path / "profile.yaml"
    ensure_profile_file(path)
    assert onboarding_state(conn, path)["checks"]["profile"] is False
    write_profile_document({"candidate": {"name": _example_name() + " Jr"}}, path)
    assert onboarding_state(conn, path)["checks"]["profile"] is True


def test_goals_defaults(conn):
    assert get_goals(conn) == {
        "daily_goal": 3,
        "odds_prior": 0.03,
        "odds_cadence": 3.0,
        "last_celebrated_date": "",
        "configured": False,
    }


def test_goals_validation_bounds(conn):
    with pytest.raises(ValueError):
        save_goals(conn, {"odds_prior": 0.2})
    with pytest.raises(ValueError):
        save_goals(conn, {"daily_goal": 0})
    with pytest.raises(ValueError):
        save_goals(conn, {"last_celebrated_date": "31/10/2026"})
    saved = save_goals(conn, {"daily_goal": 5, "last_celebrated_date": "2026-10-31"})
    assert saved["daily_goal"] == 5 and saved["configured"] is True
    assert saved["last_celebrated_date"] == "2026-10-31"
    assert save_goals(conn, {"odds_prior": 0.05})["daily_goal"] == 5


def test_existing_install_skip_keeps_jobs(conn):
    conn.execute("INSERT INTO jobs (company, title, discovered_at, last_seen_at, dedupe_key) VALUES ('Acme','Dev','t','t','k')")
    conn.commit()
    assert skip_onboarding(conn)["status"] == "skipped"
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1


def test_routes_onboarding_profile_and_goals(dashboard_server, tmp_path, monkeypatch):
    profile = tmp_path / "profile.yaml"
    monkeypatch.setattr(profile_module, "DEFAULT_PROFILE_PATH", profile)
    status, body, _ = dashboard_server("GET", "/api/onboarding")
    assert status == 200 and body["status"] == "pending"

    profile.write_text("candidate: [unclosed")
    status, body, _ = dashboard_server("GET", "/api/onboarding")
    assert status == 200 and body["profile_error"]
    status, body, _ = dashboard_server("GET", "/api/profile")
    assert status == 422 and "error" in body
    status, _, _ = dashboard_server("PUT", "/api/profile", {"candidate": {"name": "X"}})
    assert status == 422
    assert profile.read_text() == "candidate: [unclosed"

    profile.write_text("candidate:\n  name: Old\n")
    status, body, _ = dashboard_server("PUT", "/api/profile", {"candidate": {"name": "New"}})
    assert status == 200 and body["candidate"]["name"] == "New"
    status, _, _ = dashboard_server("PUT", "/api/profile", {"candidate": {"contact": {"email": "bad"}}})
    assert status == 400

    status, body, _ = dashboard_server("GET", "/api/goals")
    assert status == 200 and body["daily_goal"] == 3
    status, body, _ = dashboard_server("PUT", "/api/goals", {"daily_goal": 7})
    assert status == 200 and body["daily_goal"] == 7 and body["configured"] is True
    status, _, _ = dashboard_server("PUT", "/api/goals", {"daily_goal": 0})
    assert status == 400

    status, body, _ = dashboard_server("POST", "/api/onboarding/step", {"step": "ai"})
    assert status == 200 and body["step"] == "ai"
    status, _, _ = dashboard_server("POST", "/api/onboarding/step", {"step": "zzz"})
    assert status == 400
    status, body, _ = dashboard_server("POST", "/api/onboarding/skip", {})
    assert body["status"] == "skipped"
    status, body, _ = dashboard_server("POST", "/api/onboarding/complete", {})
    assert body["status"] == "complete"
    status, body, _ = dashboard_server("POST", "/api/onboarding/reset", {})
    assert body["status"] == "pending"


def test_server_tolerates_malformed_profile_on_request_paths(dashboard_server, tmp_path, monkeypatch):
    profile = tmp_path / "profile.yaml"
    profile.write_text("candidate: [unclosed")
    monkeypatch.setattr(profile_module, "DEFAULT_PROFILE_PATH", profile)
    status, _, _ = dashboard_server("GET", "/api/summary")
    assert status == 200
