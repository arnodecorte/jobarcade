// Thin typed wrappers over the existing Python dashboard endpoints.

export type Role = {
  role: string;
  company: string;
  period: string;
  location: string;
  include?: boolean;
  bullets: string[];
};

export type CvData = {
  max_pages: number;
  variant?: "grotesk_one_page" | "compact_one_page" | "classic_two_page" | "enriched_two_page";
  role_focus?: "marketing" | "content" | "brand" | "community" | "commercial_ops" | "";
  title: string;
  tagline: string;
  profile: string;
  selected_highlights?: string[];
  experience: Role[];
  additional: Role[];
};

export type LetterData = {
  max_pages: number;
  subtitle: string;
  paragraphs: string[];
};

export type DraftLimits = {
  tagline: number;
  profile: number;
  bullet: number;
  highlight: number;
  letter_body: number;
  variants?: string[];
  role_focuses?: string[];
};

export type CvReview = {
  score: number;
  band: string;
  proof_bullets: number;
  included_roles: number;
  items: Array<{ level: "warning" | "note" | string; title: string; detail: string }>;
};

export type BrandTheme = {
  enabled: boolean;
  provider?: "auto" | "firecrawl" | "local" | string;
  mode?: "light" | "dark" | string;
  accent: string;
  accent_dark: string;
  muted?: string;
  page_bg?: string;
  soft_bg: string;
  rule: string;
  link: string;
  source_url: string;
  source_kind?: string;
  source_reason?: string;
  confidence: number;
  notes: string[];
  typography?: { primary?: string; heading?: string; code?: string; weights?: { regular?: number; medium?: number; bold?: number } };
  typography_available?: boolean;
  typography_enabled?: boolean;
  body_font?: string[];
  heading_font?: string[];
  body_weight?: number;
  subheading_weight?: number;
  heading_weight?: number;
  typography_resolution?: {
    // Legacy flat shape (pre-dual-font themes) — still present on themes
    // extracted before body/heading fonts were resolved independently.
    source?: string;
    requested?: string;
    family?: string;
    font_path?: string;
    notes?: string[];
    warnings?: string[];
    // Current nested shape.
    body?: { source?: string; requested?: string; family?: string; font_path?: string; notes?: string[]; warnings?: string[] };
    heading?: { source?: string; requested?: string; family?: string; font_path?: string; notes?: string[]; warnings?: string[] };
  };
  energy?: string;
  tone?: string;
  dark_recommended?: boolean;
  light_tokens?: Record<string, string>;
  fallback?: boolean;
  warnings?: string[];
};

export type BrandThemeState = {
  mode: "base" | "chameleon";
  enabled: boolean;
  theme: BrandTheme | null;
  warnings: string[];
};

export type BrandSource = {
  url: string;
  kind: "company_site" | "careers" | "missing" | string;
  reason: string;
  override: boolean;
};

export type DraftDoc = {
  folder_name: string;
  cv: CvData;
  letter: LetterData;
  listing: string;
  artifact: Artifact;
  brand_theme: BrandThemeState;
  brand_source: BrandSource;
  warnings: string[];
  cv_review: CvReview;
  limits: DraftLimits;
  meta: Record<string, unknown>;
};

export type RepromptBody = {
  mode: "fresh" | "refine";
  instructions: string;
  job_id?: number;
  current_draft?: { cv: CvData; letter: LetterData };
};

export type Artifact = {
  folder: string;
  folder_name: string;
  has_job_listing: boolean;
  has_draft_data: boolean;
  has_cv: boolean;
  has_letter: boolean;
  draft_origin: string | null;
  draft_model: string | null;
  draft_state: string | null;
  draft_review_label: string | null;
};

export type Job = {
  id: number;
  company: string;
  company_logo_url: string | null;
  company_logo_domain: string | null;
  title: string;
  location: string | null;
  country: string | null;
  department: string | null;
  apply_url: string | null;
  source_platform: string | null;
  scraper_type: string | null;
  discovered_at: string;
  status: string;
  notes: string | null;
  score: number | null;
  fit_band: "core_fit" | "adjacent_plausible" | "stretch" | string;
  score_reasons: string[];
  artifact: Artifact | null;
  possible_duplicate?: boolean;
  duplicate_of?: Array<{ id: number; source_platform: string | null; status: string }>;
  applied_at?: string | null;
};

export type Summary = {
  status_counts: Record<string, number>;
  total_jobs: number;
  active_jobs: number;
  generated_applications: number;
  ready_artifacts: number;
  last_seen_at: string | null;
  scraper_health_counts: Record<string, number>;
  unhealthy_scrapers: number;
};

export type Stats = {
  applications_sent: number;
  pulls_today: number;
  daily: Array<{ date: string; count: number }>;
  current_streak: number;
  best_streak: number;
  actual_cadence_7d: number;
  lifecycle: {
    submitted_total: number;
    pending_total: number;
    known_outcomes: number;
    matured_denominator: number;
    matured_no_response: number;
    immature_pending: number;
    ghosted: number;
    follow_up_due: number;
    interviews: number;
    rejections: number;
    response_rate_observed: number;
    response_rate_low: number;
    response_rate_high: number;
    maturity_days: number;
    ghosted_days: number;
    follow_up_days: number;
    buckets: Record<string, number>;
  };
};

export type Company = {
  company: string;
  careers_url: string;
  brand_url?: string | null;
  scraper_type: string;
  enabled: boolean;
  logo_url: string | null;
  logo_domain: string | null;
  job_count: number;
  last_seen_at: string | null;
  is_promoted: boolean;
  health: {
    status: string;
    strategy: string | null;
    checked_at: string | null;
    error: string | null;
    message: string | null;
  } | null;
};

export type Coverage = {
  total: number;
  dedicated: number;
  manual_review: number;
  disabled: number;
  promoted_percent: number;
};

export type CompanyCandidate = {
  id: number;
  company: string;
  website_url: string | null;
  careers_url: string | null;
  needs_careers_url: boolean;
  suggested_careers_url: string | null;
  suggested_careers_url_reason: string | null;
  logo_url: string | null;
  logo_domain: string | null;
  location_hint: string | null;
  industry_tags: string[];
  aspiration_tags: string[];
  role_signals: string[];
  source_names: string[];
  source_type: string;
  score: number;
  score_reasons: string[];
  status: "new" | "maybe" | "rejected" | "hidden" | "added" | string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  last_checked_at: string | null;
  added_at: string | null;
  is_tracked: boolean;
};

export type CompanyCandidateStats = {
  new: number;
  maybe: number;
  added: number;
  rejected: number;
  hidden: number;
  active: number;
};

export type CareersUrlAttempt = {
  url: string;
  final_url: string;
  status: number;
  score: number;
  reason: string;
};

export type CareersUrlSuggestion = {
  url: string;
  final_url: string;
  status: number;
  score: number;
  reason: string;
};

export type GmailStatus = {
  configured: boolean;
  missing_config: string[];
  connected: boolean;
  account: {
    email: string | null;
    scopes: string;
    connected_at: string;
    updated_at: string;
    last_sync_at: string | null;
    last_error: string | null;
  } | null;
  evidence: { pending: number; matched: number; messages: number };
  intelligence: { base_url: string; model: string; auto_threshold: number };
  metrics: GmailMetrics;
};

export type GmailSyncProgress = {
  running: boolean;
  total: number;
  processed: number;
  current_subject: string | null;
  log: string[];
  error: string | null;
  result: {
    ok: boolean;
    query: string;
    seen: number;
    saved: number;
    classifications: Record<string, number>;
  } | null;
};

export type GmailMetrics = {
  scanned: number;
  job_related: number;
  auto_classified: number;
  auto_matched: number;
  auto_applied: number;
  pending_review: number;
  corrected: number;
  unmatched: number;
  errors: number;
  categories: Record<string, number>;
};

export type GmailMatchCandidate = {
  job_id: number;
  company: string;
  title: string;
  status: string;
  applied_at: string | null;
  confidence: number;
  reason: string;
};

export type IntegrationStatus = {
  gmail: {
    configured: boolean;
    client_id: string;
    client_secret_set: boolean;
    redirect_uri: string;
    source: "vault" | "environment" | string;
  };
  ollama: {
    base_url: string;
    model: string;
    source: "vault" | "environment" | string;
    api_key_set?: boolean;
    models?: { draft: string; refine: string; classify: string };
  };
  firecrawl?: { configured: boolean; source: string };
  features?: { scraper: boolean };
  vault: { ready: boolean; key_path: string };
};

export type GmailEvidence = {
  gmail_message_id: string;
  job_id: number | null;
  evidence_type: string;
  confidence: number;
  classification_confidence: number;
  match_confidence: number;
  reason: string | null;
  status: string;
  occurred_at: string | null;
  sender: string | null;
  subject: string | null;
  snippet: string | null;
  company: string | null;
  title: string | null;
  target_status: string | null;
  original_evidence_type: string | null;
  original_job_id: number | null;
  corrected_by_user: number;
  automation_outcome: string | null;
  classifier_source: string;
  classifier_version: string | null;
  classification_reason: string | null;
  inferred_company: string | null;
  inferred_role: string | null;
  supporting_excerpts: string[];
  classifier_error: string | null;
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(payload?.error || `Request failed: ${res.status}`);
  return payload as T;
}

export const getSummary = () => api<Summary>("/api/summary");
export const getStats = () => api<Stats>("/api/stats");
export const getJobs = () => api<Job[]>("/api/jobs");
export const getCompanies = () =>
  api<{ companies: Company[]; coverage: Coverage }>("/api/companies");

export const getCompanyCandidates = () =>
  api<{ candidates: CompanyCandidate[]; stats: CompanyCandidateStats }>("/api/company-candidates");

export const setJobStatus = (jobId: number, status: string) =>
  api<{ ok: boolean }>(`/api/jobs/${jobId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const setJobNotes = (jobId: number, notes: string) =>
  api<{ ok: boolean }>(`/api/jobs/${jobId}/notes`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  });

export const createDraftPack = (jobId: number, customInstructions: string) =>
  api<{ folder_name: string }>(`/api/jobs/${jobId}/draft-pack`, {
    method: "POST",
    body: JSON.stringify({ custom_instructions: customInstructions }),
  });

export const addJob = (body: {
  company: string;
  title: string;
  location?: string;
  apply_url?: string;
  notes?: string;
  status?: string;
  applied_at?: string;
}) =>
  api<{ ok: boolean; id: number; status: string; score: number; fit_band: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const scrapeJobUrl = (url: string) =>
  api<{
    ok: boolean;
    title: string | null;
    company: string | null;
    location: string | null;
    description: string | null;
    source: string;
    warnings: string[];
  }>("/api/jobs/scrape", {
    method: "POST",
    body: JSON.stringify({ url }),
  });

export const sendFeedback = (message: string, page: string) =>
  api<{ ok: boolean }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify({ message, page }),
  });

export const addCompany = (body: {
  company: string;
  careers_url: string;
  notes?: string;
  logo_url?: string;
}) =>
  api<{ ok: boolean }>("/api/companies", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const decideCompanyCandidate = (
  id: number,
  status: "new" | "maybe" | "rejected" | "hidden",
  notes?: string
) =>
  api<{ ok: boolean; id: number; status: string }>(`/api/company-candidates/${id}/decision`, {
    method: "POST",
    body: JSON.stringify({ status, notes: notes || "" }),
  });

export const addCompanyCandidateToScrapers = (id: number) =>
  api<{ ok: boolean; candidate_id: number; company: string }>(`/api/company-candidates/${id}/add-to-scrapers`, {
    method: "POST",
    body: "{}",
  });

export const resolveCompanyCandidateCareersUrl = (id: number, careersUrl: string) =>
  api<{ ok: boolean; id: number; careers_url: string; needs_careers_url: boolean }>(
    `/api/company-candidates/${id}/careers-url`,
    {
      method: "POST",
      body: JSON.stringify({ careers_url: careersUrl }),
    }
  );

export const suggestCompanyCandidateCareersUrl = (id: number) =>
  api<{ ok: boolean; id: number; suggestion: CareersUrlSuggestion | null; attempts: CareersUrlAttempt[] }>(
    `/api/company-candidates/${id}/suggest-careers-url`,
    {
      method: "POST",
      body: "{}",
    }
  );

export const getDraft = (folder: string) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/draft`);

export const saveDraft = (folder: string, payload: { cv: CvData; letter: LetterData }) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/draft`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });

export const buildApplication = (folder: string) =>
  api<{ ok: boolean; folder_name: string; artifact: Artifact; output: string; error: string | null }>(
    `/api/applications/${encodeURIComponent(folder)}/build`,
    { method: "POST", body: JSON.stringify({}) }
  );

export const extractBrandTheme = (folder: string, body: { job_id?: number; source_url?: string; provider?: string }) =>
  api<{ ok: boolean; folder_name: string; brand_theme: BrandThemeState; brand_source: BrandSource }>(
    `/api/applications/${encodeURIComponent(folder)}/brand-theme`,
    { method: "POST", body: JSON.stringify(body) }
  );

export const setBrandUrl = (folder: string, brandUrl: string) =>
  api<{ ok: boolean; folder_name: string; brand_source: BrandSource }>(
    `/api/applications/${encodeURIComponent(folder)}/brand-url`,
    { method: "POST", body: JSON.stringify({ brand_url: brandUrl }) }
  );

export const resetBrandTheme = (folder: string) =>
  api<{ ok: boolean; folder_name: string; brand_theme: BrandThemeState }>(
    `/api/applications/${encodeURIComponent(folder)}/brand-theme/reset`,
    { method: "POST", body: "{}" }
  );

export const setBrandThemeMode = (folder: string, mode: "light" | "dark") =>
  api<{ ok: boolean; folder_name: string; brand_theme: BrandThemeState }>(
    `/api/applications/${encodeURIComponent(folder)}/brand-theme/mode`,
    { method: "POST", body: JSON.stringify({ mode }) }
  );

export const setBrandTypography = (folder: string, enabled: boolean) =>
  api<{ ok: boolean; folder_name: string; brand_theme: BrandThemeState }>(
    `/api/applications/${encodeURIComponent(folder)}/brand-theme/typography`,
    { method: "POST", body: JSON.stringify({ enabled }) }
  );

export const markDraftReady = (folder: string, jobId?: number) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/ready-for-review`, {
    method: "POST",
    body: JSON.stringify(jobId ? { job_id: jobId } : {}),
  });

export const repromptDraft = (folder: string, body: RepromptBody) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/reprompt`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getOllamaStatus = () =>
  api<{ available: boolean; model: string; model_present?: boolean; error?: string }>("/api/ollama/status");

export const warmupOllama = () =>
  api<{ ok: boolean; model: string; status: string }>("/api/ollama/warmup", { method: "POST", body: "{}" });

export const getGmailStatus = () => api<GmailStatus>("/api/gmail/status");
export const getIntegrationStatus = () => api<IntegrationStatus>("/api/integrations");
export const setScraperFeature = (scraper: boolean) =>
  api<IntegrationStatus>("/api/features", { method: "PUT", body: JSON.stringify({ scraper }) });

export const saveGmailIntegration = (body: {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
}) => api<IntegrationStatus>("/api/integrations/gmail", {
  method: "PUT",
  body: JSON.stringify(body),
});

export const clearGmailIntegration = () =>
  api<IntegrationStatus>("/api/integrations/gmail", { method: "DELETE" });

export const saveOllamaIntegration = (body: {
  base_url: string;
  model: string;
  api_key?: string;
  clear_api_key?: boolean;
  models?: { draft: string; refine: string; classify: string };
}) =>
  api<IntegrationStatus>("/api/integrations/ollama", {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const testOllamaIntegration = () =>
  api<{ ok: boolean; model: string; model_present: boolean; models?: string[]; error?: string }>(
    "/api/integrations/ollama/test",
    { method: "POST", body: "{}" },
  );

export const startGmailOAuth = () =>
  api<{ auth_url: string; state: string; redirect_uri: string }>("/api/gmail/oauth/start", {
    method: "POST",
    body: "{}",
  });

export const syncGmail = (body: { max_results?: number; after?: string } = {}) =>
  api<{ ok: boolean; started?: boolean; already_running?: boolean }>("/api/gmail/sync", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getGmailSyncProgress = () => api<GmailSyncProgress>("/api/gmail/sync/progress");

export const getGmailEvidence = () => api<{ evidence: GmailEvidence[] }>("/api/gmail/evidence");

export const getGmailEvidenceCandidates = (messageId: string) =>
  api<{ candidates: GmailMatchCandidate[] }>(
    `/api/gmail/evidence/${encodeURIComponent(messageId)}/candidates`,
  );

export const updateGmailEvidence = (
  messageId: string,
  body: { evidence_type: string; job_id: number | null },
) =>
  api<{ ok: boolean; evidence_type: string; job_id: number | null; target_status: string | null }>(
    `/api/gmail/evidence/${encodeURIComponent(messageId)}`,
    { method: "POST", body: JSON.stringify(body) },
  );

export const applyGmailEvidence = (messageId: string) =>
  api<{ ok: boolean; job_id: number; status: string }>(`/api/gmail/evidence/${encodeURIComponent(messageId)}/apply`, {
    method: "POST",
    body: "{}",
  });

export const ignoreGmailEvidence = (messageId: string) =>
  api<{ ok: boolean }>(`/api/gmail/evidence/${encodeURIComponent(messageId)}/ignore`, {
    method: "POST",
    body: "{}",
  });

export const disconnectGmail = async (): Promise<void> => {
  const res = await fetch("/api/gmail/account", { method: "DELETE" });
  if (res.status === 204) return;
  const payload = await res.json().catch(() => ({}));
  throw new Error((payload as { error?: string }).error || `Disconnect failed: ${res.status}`);
};

export const deleteDraft = async (folder: string, jobId?: number): Promise<void> => {
  const qs = jobId ? `?job_id=${jobId}` : "";
  const res = await fetch(`/api/applications/${encodeURIComponent(folder)}${qs}`, {
    method: "DELETE",
  });
  if (res.status === 204) return;
  const payload = await res.json().catch(() => ({}));
  throw new Error((payload as { error?: string }).error || `Delete failed: ${res.status}`);
};

export type Goals = {
  daily_goal: number;
  odds_prior: number;
  odds_cadence: number;
  last_celebrated_date: string;
  configured: boolean;
};

export const getGoals = () => api<Goals>("/api/goals");

export const saveGoals = (body: Partial<Goals>) =>
  api<Goals>("/api/goals", {
    method: "PUT",
    body: JSON.stringify(body),
  });

// ---- onboarding ----

export type OnboardingChecks = { ai: boolean; profile: boolean; style: boolean; chameleon: boolean; goal: boolean };
export type OnboardingState = {
  status: "pending" | "skipped" | "complete";
  step: string;
  checks: OnboardingChecks;
  profile_error?: string | null;
  demo_jobs?: number;
};

export const getOnboarding = () => api<OnboardingState>("/api/onboarding");
const post = <T>(path: string, body: unknown = {}) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const setOnboardingStep = (step: string) => post<OnboardingState>("/api/onboarding/step", { step });
export const completeOnboarding = () => post<OnboardingState>("/api/onboarding/complete");
export const skipOnboarding = () => post<OnboardingState>("/api/onboarding/skip");
export const resetOnboarding = () => post<OnboardingState>("/api/onboarding/reset");
export const seedDemo = () => post<{ jobs: number; draft_folder: string }>("/api/demo/seed");
export const clearDemo = () => api<{ removed: number }>("/api/demo", { method: "DELETE" });

export type ProfileDoc = {
  candidate?: {
    name?: string;
    tagline?: string;
    contact?: {
      email?: string;
      phone?: string;
      location?: string;
      linkedin?: string;
      linkedin_url?: string;
      portfolio?: string;
      portfolio_url?: string;
    };
    career_facts?: string;
    skills?: string[];
  };
  target_preferences?: {
    target_roles?: string[];
    adjacent_roles?: string[];
    excluded_functions?: string[];
    target_locations?: string[];
    preferred_cities?: string[];
    allow_remote?: boolean;
    max_years_experience?: number | null;
    exclude_senior_titles?: boolean;
    exclude_internships?: boolean;
    excluded_language_patterns?: string[];
  };
};

export const getProfile = () => api<ProfileDoc>("/api/profile");
export const saveProfile = (body: ProfileDoc) =>
  api<ProfileDoc>("/api/profile", { method: "PUT", body: JSON.stringify(body) });

export type StyleDoc = {
  cv_variant: string;
  accent: string;
  font: string;
  mode: "light" | "dark" | string;
  configured?: boolean;
  warnings?: string[];
};
export type StyleState = StyleDoc & { variants: string[]; fonts: string[] };

export const getStyle = () => api<StyleState>("/api/style");
export const saveStyle = (body: Pick<StyleDoc, "cv_variant" | "accent" | "font" | "mode">) =>
  api<StyleDoc>("/api/style", { method: "PUT", body: JSON.stringify(body) });

/** Renders the CV preview server-side; resolves to a PNG blob. */
export async function previewStyle(body: Pick<StyleDoc, "cv_variant" | "accent" | "font" | "mode">, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch("/api/style/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error((payload as { error?: string }).error || `Preview failed: ${res.status}`);
  }
  return res.blob();
}

export const saveFirecrawlKey = (api_key: string) =>
  api<unknown>("/api/integrations/firecrawl", { method: "PUT", body: JSON.stringify({ api_key }) });
export const testFirecrawl = (url?: string) =>
  post<{ ok: boolean; accent?: string; mode?: string; dark_recommended?: boolean; warnings?: string[]; error?: string }>(
    "/api/integrations/firecrawl/test",
    url ? { url } : {},
  );
