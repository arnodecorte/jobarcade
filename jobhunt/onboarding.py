from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

import yaml

from jobhunt import profile as profile_module
from jobhunt.integration_settings import effective_firecrawl_key, get_setting, has_setting, set_setting
from jobhunt.profile import EXAMPLE_PROFILE_PATH

ONBOARDING_STEPS = ("welcome", "ai", "profile", "style", "chameleon", "goal")

PROFILE_FIELDS = (
    "candidate.name",
    "candidate.tagline",
    "candidate.contact.email",
    "candidate.contact.phone",
    "candidate.contact.location",
    "candidate.contact.linkedin",
    "candidate.contact.linkedin_url",
    "candidate.contact.portfolio",
    "candidate.contact.portfolio_url",
    "candidate.career_facts",
    "candidate.skills",
    "target_preferences.target_roles",
    "target_preferences.adjacent_roles",
    "target_preferences.excluded_functions",
    "target_preferences.target_locations",
    "target_preferences.preferred_cities",
    "target_preferences.allow_remote",
    "target_preferences.max_years_experience",
    "target_preferences.exclude_senior_titles",
    "target_preferences.exclude_internships",
    "target_preferences.excluded_language_patterns",
)

_LIST_FIELDS = {
    "candidate.skills",
    "target_preferences.target_roles",
    "target_preferences.adjacent_roles",
    "target_preferences.excluded_functions",
    "target_preferences.target_locations",
    "target_preferences.preferred_cities",
    "target_preferences.excluded_language_patterns",
}
_BOOL_FIELDS = {
    "target_preferences.allow_remote",
    "target_preferences.exclude_senior_titles",
    "target_preferences.exclude_internships",
}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfileError(ValueError):
    """The profile file exists but cannot be parsed."""


def _resolve(path: Path | None) -> Path:
    # Resolved at call time so a patched module-level path is honoured.
    return path if path is not None else profile_module.DEFAULT_PROFILE_PATH


def ensure_profile_file(path: Path | None = None, example: Path | None = None) -> bool:
    target = _resolve(path)
    source = example if example is not None else EXAMPLE_PROFILE_PATH
    if target.exists() or not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def _example_name() -> str:
    try:
        raw = yaml.safe_load(EXAMPLE_PROFILE_PATH.read_text(encoding="utf-8")) or {}
        return str((raw.get("candidate") or {}).get("name") or "").strip()
    except (OSError, yaml.YAMLError, AttributeError):
        return ""


def _load_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"Profile YAML could not be parsed: {exc}") from exc
    except OSError as exc:
        raise ProfileError(f"Profile could not be read: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ProfileError("Profile YAML must be a mapping at the top level.")
    return raw


def _get_path(doc: dict, dotted: str):
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def read_profile_document(path: Path | None = None) -> dict:
    raw = _load_raw(_resolve(path))
    out: dict = {}
    for dotted in PROFILE_FIELDS:
        value, found = _get_path(raw, dotted)
        if not found:
            continue
        node = out
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def _validate_field(dotted: str, value):
    label = dotted.split(".")[-1]
    if dotted == "candidate.name":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Name is required.")
        if len(value.strip()) > 120:
            raise ValueError("Name must be at most 120 characters.")
        return value.strip()
    if dotted == "candidate.career_facts":
        if not isinstance(value, str):
            raise ValueError("career_facts must be text.")
        if len(value) > 6000:
            raise ValueError("career_facts must be at most 6000 characters.")
        return value
    if dotted == "candidate.contact.email":
        if not isinstance(value, str):
            raise ValueError("Email must be text.")
        value = value.strip()
        if value and not _EMAIL_RE.match(value):
            raise ValueError("Email address is not valid.")
        return value
    if dotted in _LIST_FIELDS:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{label} must be a list of strings.")
        if any(len(item) > 120 for item in value):
            raise ValueError(f"Each {label} item must be at most 120 characters.")
        return [item.strip() for item in value]
    if dotted in _BOOL_FIELDS:
        if not isinstance(value, bool):
            raise ValueError(f"{label} must be true or false.")
        return value
    if dotted == "target_preferences.max_years_experience":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 50:
            raise ValueError("max_years_experience must be empty or a whole number from 0 to 50.")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    if len(value) > 500:
        raise ValueError(f"{label} must be at most 500 characters.")
    return value.strip()


def write_profile_document(payload: dict, path: Path | None = None) -> dict:
    target = _resolve(path)
    if not isinstance(payload, dict):
        raise ValueError("Profile payload must be an object.")
    raw = _load_raw(target)  # raises ProfileError before anything is written
    updates: list[tuple[str, object]] = []
    for dotted in PROFILE_FIELDS:
        value, found = _get_path(payload, dotted)
        if found:
            updates.append((dotted, _validate_field(dotted, value)))
    for dotted, value in updates:
        node = raw
        parts = dotted.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".profile-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return read_profile_document(target)


def _profile_name(path: Path) -> tuple[str, str | None]:
    source = path if path.exists() else EXAMPLE_PROFILE_PATH
    try:
        raw = _load_raw(source)
    except ProfileError as exc:
        return "", str(exc)
    cand = raw.get("candidate")
    return str((cand or {}).get("name") or "").strip() if isinstance(cand, dict) else "", None


def onboarding_state(conn, profile_path: Path | None = None) -> dict:
    path = _resolve(profile_path)
    status = get_setting(conn, "onboarding_status", "pending")
    if status not in ("pending", "skipped", "complete"):
        status = "pending"
    step = get_setting(conn, "onboarding_step", "welcome")
    if step not in ONBOARDING_STEPS:
        step = "welcome"
    name, profile_error = _profile_name(path)
    return {
        "status": status,
        "step": step,
        "checks": {
            "ai": has_setting(conn, "ollama_base_url"),
            "profile": bool(name) and name != _example_name(),
            "style": (path.parent / "default-theme.yaml").exists(),
            "chameleon": bool(effective_firecrawl_key(conn)),
            "goal": has_setting(conn, "daily_goal"),
        },
        "profile_error": profile_error,
    }


def set_onboarding_step(conn, step: str) -> dict:
    if step not in ONBOARDING_STEPS:
        raise ValueError(f"Unknown onboarding step: {step}")
    set_setting(conn, "onboarding_step", step)
    return onboarding_state(conn)


def complete_onboarding(conn) -> dict:
    set_setting(conn, "onboarding_status", "complete")
    return onboarding_state(conn)


def skip_onboarding(conn) -> dict:
    set_setting(conn, "onboarding_status", "skipped")
    return onboarding_state(conn)


def reset_onboarding(conn) -> dict:
    set_setting(conn, "onboarding_status", "pending")
    set_setting(conn, "onboarding_step", "welcome")
    return onboarding_state(conn)


def get_goals(conn) -> dict:
    def number(name, default, cast):
        try:
            return cast(get_setting(conn, name, "") or default)
        except ValueError:
            return default

    return {
        "daily_goal": number("daily_goal", 3, int),
        "odds_prior": number("odds_prior", 0.03, float),
        "odds_cadence": number("odds_cadence", 3.0, float),
        "last_celebrated_date": get_setting(conn, "last_celebrated_date", ""),
        "configured": has_setting(conn, "daily_goal"),
    }


def save_goals(conn, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Goals payload must be an object.")
    pending: dict[str, str] = {}
    if "daily_goal" in payload:
        value = payload["daily_goal"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
            raise ValueError("daily_goal must be a whole number from 1 to 50.")
        pending["daily_goal"] = str(value)
    for name, low, high in (("odds_prior", 0.005, 0.08), ("odds_cadence", 0.5, 50)):
        if name in payload:
            value = payload[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f"{name} must be a number from {low} to {high}.")
            pending[name] = repr(float(value))
    if "last_celebrated_date" in payload:
        value = payload["last_celebrated_date"]
        if value != "":
            try:
                date.fromisoformat(str(value))
            except ValueError as exc:
                raise ValueError("last_celebrated_date must be YYYY-MM-DD.") from exc
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
                raise ValueError("last_celebrated_date must be YYYY-MM-DD.")
        pending["last_celebrated_date"] = str(value)
    for name, value in pending.items():
        if value == "" and name == "last_celebrated_date":
            conn.execute("DELETE FROM integration_settings WHERE name = ?", (name,))
        else:
            set_setting(conn, name, value)
    return get_goals(conn)
