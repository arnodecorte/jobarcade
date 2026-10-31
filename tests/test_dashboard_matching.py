"""Artifact-to-job matching: the dashboard must attach the *right* folder.

Regression guard for the bug where a common title word ("manager") routed one
folder to every same-company role.
"""
from jobhunt.dashboard import _match_artifact, _slug_text


def _artifacts(*folder_names):
    # Mirror application_artifacts(): keyed by slug, value carries folder_name.
    return {_slug_text(name): {"folder_name": name} for name in folder_names}


def _match(company, title, *folders):
    got = _match_artifact(_slug_text(company), _slug_text(title), _artifacts(*folders))
    return got["folder_name"] if got else None


def test_bynder_manager_collision_resolves_to_specific_role():
    folders = (
        "Bynder-Enterprise-Sales-Manager-EMEA",
        "Bynder-Global-Partner-Marketing-Manager",
        "Bynder-Strategic-Account-Manager",
    )
    assert _match("Bynder", "Strategic Account Manager", *folders) == "Bynder-Strategic-Account-Manager"
    assert _match("Bynder", "Enterprise Sales Manager, EMEA", *folders) == "Bynder-Enterprise-Sales-Manager-EMEA"
    assert _match("Bynder", "Global Partner Marketing Manager", *folders) == "Bynder-Global-Partner-Marketing-Manager"


def test_company_with_space_matches_hyphenated_folder():
    # "Red Bull" -> red-bull; folder must start with that slug.
    assert _match("Red Bull", "Communications Specialist Sports",
                  "Red-Bull-Communications-Specialist-Sports") == "Red-Bull-Communications-Specialist-Sports"
    # The buggy folder name (RedBull, no separator) must NOT match.
    assert _match("Red Bull", "Communications Specialist Sports",
                  "RedBull-Communications-Specialist-Sports") is None


def test_no_overlap_returns_none():
    assert _match("Uber", "Product Manager Attribution",
                  "Bynder-Strategic-Account-Manager") is None


def test_folder_component_strips_apostrophe_like_slug_text():
    from jobhunt.dashboard import _application_folder_name

    folder = _application_folder_name("JDE Peet's", "Global Communications Content Creator")
    assert folder == "JDE-Peets-Global-Communications-Content-Creator"
    assert _match("JDE Peet's", "Global Communications Content Creator", folder) == folder


if __name__ == "__main__":
    test_bynder_manager_collision_resolves_to_specific_role()
    test_company_with_space_matches_hyphenated_folder()
    test_no_overlap_returns_none()
    print("OK")


def _job(jid, company, title, source_platform, status="new"):
    # Minimal shape _tag_possible_duplicates reads.
    return {
        "id": jid,
        "company": company,
        "title": title,
        "source_platform": source_platform,
        "status": status,
        "possible_duplicate": False,
        "duplicate_of": [],
    }


def test_cross_source_same_role_flagged_as_possible_duplicate():
    from jobhunt.dashboard import _tag_possible_duplicates

    jobs = [
        _job(1, "Tesla", "Marketing Manager", "tesla_careers"),
        _job(2, "Tesla", "Marketing Manager", "englishjobsearch"),
    ]
    _tag_possible_duplicates(jobs)

    assert jobs[0]["possible_duplicate"] and jobs[1]["possible_duplicate"]
    assert jobs[0]["duplicate_of"][0]["id"] == 2
    assert jobs[1]["duplicate_of"][0]["source_platform"] == "tesla_careers"


def test_same_source_identical_titles_not_flagged():
    # Amazon posts many identically-titled but genuinely distinct reqs from the
    # same source — those must NOT be collapsed into a duplicate warning.
    from jobhunt.dashboard import _tag_possible_duplicates

    jobs = [
        _job(1, "Amazon", "AI Data Associate (NL)", "amazon_jobs"),
        _job(2, "Amazon", "AI Data Associate (NL)", "amazon_jobs"),
    ]
    _tag_possible_duplicates(jobs)

    assert not jobs[0]["possible_duplicate"]
    assert not jobs[1]["possible_duplicate"]


def test_distinct_roles_not_flagged():
    from jobhunt.dashboard import _tag_possible_duplicates

    jobs = [
        _job(1, "Tesla", "Marketing Manager", "tesla_careers"),
        _job(2, "Tesla", "Content Creator", "englishjobsearch"),
    ]
    _tag_possible_duplicates(jobs)

    assert not jobs[0]["possible_duplicate"]
    assert not jobs[1]["possible_duplicate"]
