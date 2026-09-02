from __future__ import annotations

from dataclasses import dataclass, field
import json
import re

from jobhunt import config
from jobhunt.models import Job


CORE_TERMS = (
    "marketing",
    "campaign",
    "content",
    "brand",
    "communications",
    "communication",
    "crm",
    "social media",
    "copywriter",
    "editor",
)

ADJACENT_TERMS = (
    "account manager",
    "account management",
    "partnership",
    "partnerships",
    "partner",
    "community",
    "customer success",
    "client success",
    "growth",
    "business development",
    "operations",
    "strategy",
    "analytics",
    "sales",
    "sales operations",
    "sales enablement",
    "field sales",
)

ROLE_TERMS = config.ROLE_TITLE_KEYWORDS
EXCLUDED_FUNCTION_RE = re.compile(
    r"\b(?:platform|finance|fintech|treasury|cash|accounting|tax|legal|procurement|security|warehouse|chef|driver)\b",
    re.I,
)
HARD_EXCLUDED_FUNCTION_RE = re.compile(
    r"\b(?:engineering|engineer|software|backend|frontend|full stack|infrastructure|sap|technical|recruitment|recruiter|hr business|human resources|talent)\b",
    re.I,
)

DUTCH_REQUIRED_PATTERNS = [
    r"vloeiend nederlands",
    r"nederlands vereist",
    r"nederlands.*vereiste",
    r"nederlands als moedertaal",
    r"dutch fluency.*must",
    r"dutch fluency",
    r"fluent in dutch.*must",
    r"fluent in dutch",
    r"must be fluent in dutch",
    r"native dutch",
    r"vloeiende beheersing van.*nederlandse",
]
DUTCH_REQUIRED_RE = re.compile(r"\b(?:" + "|".join(DUTCH_REQUIRED_PATTERNS) + r")\b", re.I)

EXP_RANGE_PREFIX = re.compile(
    r"(?:require|need|minimum|at least|have|with|possess|demonstrate)\s+(\d+)\s*(?:-|to|tot)\s*(\d+)\s*(?:years?|yrs?|jaar|jr)",
    re.I,
)
EXP_RANGE_SUFFIX = re.compile(
    r"(\d+)\s*(?:-|to|tot)\s*(\d+)\s*(?:years?|yrs?|jaar|jr)\s*(?:of\s+)?(?:experience|ervaring|werkervaring|required|needed)",
    re.I,
)
EXP_SINGLE_PREFIX = re.compile(
    r"(?:require|need|minimum|at least|have|with|possess|demonstrate)\s+(\d+)\+?\s*(?:years?|yrs?|jaar|jr)",
    re.I,
)
EXP_SINGLE_SUFFIX = re.compile(
    r"(\d+)\+?\s*(?:years?|yrs?|jaar|jr)\s*(?:of\s+)?(?:experience|ervaring|werkervaring|required|needed)",
    re.I,
)

SENIOR_TITLE_RE = re.compile(
    r"\b(?:senior|sr\.?|director|head of|vp|vice president|chief|principal|leader|leadership|country manager|regional manager|national .*manager)\b",
    re.I,
)
INTERNSHIP_RE = re.compile(r"\b(?:intern|internship|stage|meewerkstage)\b", re.I)
# ponytail: exclude storefront/floor roles directly to avoid low-growth roles passing adjacent/sales filters
STOREFRONT_FLOOR_RE = re.compile(
    r"\b(?:sales associate|sales advisor|sales assistant|shop assistant|retail associate|store associate|floor staff|floor manager|cashier|clerk|stylist|store manager|assistant store manager|shop manager|boutique manager|retail assistant|retail specialist|retail representative|beauty advisor|beauty consultant|makeup artist|receptionist|front desk|night auditor|guest service|waiter|bartender|barista)\b",
    re.I,
)
MANAGEMENT_SCOPE_RE = re.compile(
    r"\b(?:manage|managing|lead|leading|hire|develop|coach)\s+(?:a\s+)?(?:team|people|managers|direct reports)\b",
    re.I,
)
REGIONAL_SCOPE_RE = re.compile(r"\b(?:regional|multi-market|multimarket|emea|global|benelux|northern europe|southern europe)\b", re.I)
OWNERSHIP_RE = re.compile(
    r"\b(?:own|ownership|execute|coordinate|build|launch|manage|optimi[sz]e|create|produce|calendar|campaign|content|community|partner)\b",
    re.I,
)
HEADROOM_RE = re.compile(
    r"\b(?:cross-functional|stakeholder|collaborat|learn|training|development|growth|mentor|ownership|launch|build|scale|new market)\b",
    re.I,
)


@dataclass(slots=True)
class JobAssessment:
    included: bool
    score: int = 0
    priority: str = "Low"
    fit_band: str = "excluded"
    reason_chips: list[str] = field(default_factory=list)
    hard_fail_reason: str | None = None
    score_breakdown: dict[str, int] = field(default_factory=dict)

    def summary_json(self) -> str:
        return json.dumps(
            {
                "included": self.included,
                "score": self.score,
                "fit_band": self.fit_band,
                "hard_fail_reason": self.hard_fail_reason,
                "reason_chips": self.reason_chips,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def full_text(job: Job) -> str:
    return " ".join(part for part in (job.title, job.department, job.description, job.requirements) if part)


def has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_token(text: str, token: str) -> bool:
    # word-boundary match so short tokens like "nl" don't substring-match
    # inside unrelated words (e.g. "Menlo Park" contains "nl").
    return re.search(r"\b" + re.escape(token) + r"\b", text) is not None


def location_ok(location: str | None, remote_type: str | None = None) -> bool:
    loc = clean(location)
    remote = clean(remote_type)
    # Fully-remote jobs are acceptable regardless of where the HQ is listed.
    # Hybrid is excluded here — a hybrid role based in Cologne or Gothenburg
    # is not viable from Delft and still needs to pass the geo filter.
    if any(token in remote for token in config.REMOTE_TOKENS) and "hybrid" not in remote:
        return True
    dutch_anchor = any(anchor in loc for anchor in ("netherlands", "nederland", "amsterdam", "rotterdam", "delft", "den haag", "the hague", "utrecht", "hilversum", "rijswijk", "schiphol", "almere"))
    foreign_anchor = any(anchor in loc for anchor in ("austria", "oostenrijk", "germany", "duitsland", "united kingdom", " uk", "france", "belgium", "sweden", "stockholm", "united states", "verenigde staten", "usa", "canada"))
    if foreign_anchor and not dutch_anchor:
        return False
    if not loc:
        return False
    if any(token in loc for token in config.REMOTE_TOKENS):
        return any(_has_token(loc, accepted) for accepted in config.ACCEPT_LOCATIONS)
    return any(_has_token(loc, accepted) for accepted in config.ACCEPT_LOCATIONS)


def language_ok(text: str) -> bool:
    return not bool(DUTCH_REQUIRED_RE.search(text))


def experience_floor(text: str) -> int | None:
    floors: list[int] = []
    for start, _ in EXP_RANGE_PREFIX.findall(text):
        floors.append(int(start))
    for start, _ in EXP_RANGE_SUFFIX.findall(text):
        floors.append(int(start))

    cleaned_text = EXP_RANGE_PREFIX.sub("", text)
    cleaned_text = EXP_RANGE_SUFFIX.sub("", cleaned_text)
    for num in EXP_SINGLE_PREFIX.findall(cleaned_text):
        floors.append(int(num))
    for num in EXP_SINGLE_SUFFIX.findall(cleaned_text):
        floors.append(int(num))
    return max(floors) if floors else None


def experience_ok(text: str) -> bool:
    floor = experience_floor(text)
    return floor is None or floor < 5


def title_has_role_shape(title: str | None) -> bool:
    text = clean(title)
    if not text:
        return False
    if len(text.split()) < 2 and "copywriter" not in text:
        return False
    if re.search(r"\b[a-z0-9]+-[a-z0-9]+-[a-z0-9]+", text):
        return False
    return has_any(text, ROLE_TERMS) or has_any(text, CORE_TERMS) or has_any(text, ADJACENT_TERMS)


def seniority_hard_fail(title: str, text: str) -> str | None:
    if INTERNSHIP_RE.search(title):
        return "internship"
    if SENIOR_TITLE_RE.search(title):
        return "seniority"
    floor = experience_floor(text)
    if floor is not None and floor >= 5:
        return "seniority"
    if MANAGEMENT_SCOPE_RE.search(text):
        return "seniority"
    if REGIONAL_SCOPE_RE.search(title) and ("manager" in title or "lead" in title or "executive" in title):
        return "seniority"
    return None


def classify_theme(title_context: str) -> str | None:
    if has_any(title_context, CORE_TERMS):
        return "core"
    if has_any(title_context, ADJACENT_TERMS):
        return "adjacent"
    return None


def _capped_reasons(reasons: list[str]) -> list[str]:
    deduped = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped[:3]


def assess_job(job: Job) -> JobAssessment:
    title = clean(job.title)
    text = clean(full_text(job))
    title_context = clean(" ".join(part for part in (job.title, job.department) if part))
    location_parts = [part for part in (job.location, job.country) if part]
    location = ", ".join(location_parts) or None

    if not title_has_role_shape(job.title):
        return JobAssessment(False, hard_fail_reason="role_shape")
    if STOREFRONT_FLOOR_RE.search(title):
        return JobAssessment(False, hard_fail_reason="storefront_floor")
    if HARD_EXCLUDED_FUNCTION_RE.search(title_context):
        return JobAssessment(False, hard_fail_reason="wrong_function")
    if EXCLUDED_FUNCTION_RE.search(title_context) and not has_any(title_context, CORE_TERMS):
        return JobAssessment(False, hard_fail_reason="wrong_function")
    if not location_ok(location, job.remote_type):
        return JobAssessment(False, hard_fail_reason="geography")
    if not language_ok(text):
        return JobAssessment(False, hard_fail_reason="dutch_required")

    seniority_fail = seniority_hard_fail(title, text)
    if seniority_fail:
        return JobAssessment(False, hard_fail_reason=seniority_fail)

    theme = classify_theme(title_context)
    if not theme:
        return JobAssessment(False, hard_fail_reason="theme")

    breakdown = {
        "thematic_fit": 25 if theme == "core" else 16,
        "pivot_plausibility": 18 if OWNERSHIP_RE.search(text) else 12 if theme == "adjacent" else 10,
        "seniority_attainability": 30,
        "environment_headroom": 15 if HEADROOM_RE.search(text) else 8,
        "freshness": 5 if job.date_posted else 3,
        "location_strength": 5 if location and any(city in clean(location) for city in ("delft", "den haag", "the hague", "amsterdam", "rotterdam")) else 3,
    }

    floor = experience_floor(text)
    if floor == 4:
        breakdown["seniority_attainability"] = 18
    elif floor == 3:
        breakdown["seniority_attainability"] = 23
    elif "manager" in title and theme == "adjacent":
        breakdown["seniority_attainability"] = 20

    score = max(0, min(100, sum(breakdown.values())))
    if floor == 4:
        score = min(score, 59)
    if score >= 75 and theme == "core":
        fit_band = "core_fit"
    elif score >= 60:
        fit_band = "adjacent_plausible"
    elif score >= 45:
        fit_band = "stretch"
    else:
        return JobAssessment(False, score=score, fit_band="excluded", hard_fail_reason="low_score", score_breakdown=breakdown)

    priority = "⭐ High" if score >= 75 else "Medium" if score >= 60 else "Low"
    reasons = ["Core fit" if fit_band == "core_fit" else "Adjacent plausible" if fit_band == "adjacent_plausible" else "Seniority stretch"]
    if theme == "adjacent":
        reasons.append("People-facing")
    if OWNERSHIP_RE.search(text):
        reasons.append("Marketing ownership" if theme == "core" else "Relationship ownership")
    if HEADROOM_RE.search(text):
        reasons.append("Strong growth headroom")
    if breakdown["location_strength"] == 5:
        reasons.append("Location strong")
    if job.date_posted:
        reasons.append("Fresh posting")

    return JobAssessment(True, score, priority, fit_band, _capped_reasons(reasons), None, breakdown)


def apply_assessment(job: Job, assessment: JobAssessment | None = None) -> Job:
    assessment = assessment or assess_job(job)
    job.priority = assessment.priority
    job.score = assessment.score
    job.fit_band = assessment.fit_band
    job.score_reasons = json.dumps(assessment.reason_chips, ensure_ascii=False)
    job.assessment_summary = assessment.summary_json()
    return job
