import pytest

from jobhunt import profile as profile_module


@pytest.fixture(autouse=True)
def _isolated_search_rules(tmp_path_factory, monkeypatch):
    """Keep tests independent of a local config/profile.yaml and of cached search rules."""
    missing = tmp_path_factory.mktemp("no-profile") / "profile.yaml"
    monkeypatch.setattr(profile_module, "DEFAULT_PROFILE_PATH", missing)
    profile_module._RULES_CACHE.clear()
    yield
    profile_module._RULES_CACHE.clear()
