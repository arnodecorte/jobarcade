const statusLabels = {
  new: "New",
  reviewed: "Reviewing",
  tailoring: "Tailoring",
  ready: "Ready",
  applied: "Applied",
  interviewing: "Interviewing",
  skipped: "Skipped",
  expired: "Expired",
  scrape_failed: "Scrape Failed",
};

const pipelineStatuses = ["new", "reviewed", "tailoring", "ready", "applied"];
const editableStatuses = ["new", "reviewed", "tailoring", "ready", "applied", "interviewing", "skipped", "expired"];
const healthLabels = {
  ok: "Healthy",
  warning: "Needs Check",
  failed: "Broken",
  manual_review: "Manual",
  unknown: "Unknown",
};
const fitBandLabels = {
  core_fit: "Core fit",
  adjacent_plausible: "Adjacent plausible",
  stretch: "Stretch",
};
const fitBandRank = {
  core_fit: 0,
  adjacent_plausible: 1,
  stretch: 2,
};

let state = {
  summary: null,
  jobs: [],
  companies: [],
  coverage: null,
  query: "",
  status: "",
  showStretch: false,
  selectedJobId: null,
  draftModalJobId: null,
  draftGeneratingJobId: null,
  draftGenerationMinimized: false,
  draftGenerationReady: null,
  draftGenerationError: "",
};

const $ = (selector) => document.querySelector(selector);

function formatDate(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { year: "numeric", month: "short", day: "numeric" });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function domainFromUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value.startsWith("http") ? value : `https://${value}`);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function faviconUrl(domain) {
  return domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64` : "";
}

function initialsLogo(company) {
  return String(company || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function companyLogo(company, domain, logoUrl, size = "md") {
  const fallback = initialsLogo(company);
  const src = logoUrl || faviconUrl(domain);
  if (!src) {
    return `<span class="company-logo ${size} fallback" aria-hidden="true">${escapeHtml(fallback)}</span>`;
  }
  return `
    <span class="company-logo ${size}" aria-hidden="true">
      <img src="${escapeHtml(src)}" alt="" loading="lazy" data-fallback="${escapeHtml(fallback)}" />
    </span>
  `;
}

function wireLogoFallbacks(root = document) {
  root.querySelectorAll(".company-logo img:not([data-wired])").forEach((img) => {
    img.dataset.wired = "true";
    img.addEventListener("load", () => {
      img.closest(".company-logo")?.classList.add("logo-found");
    });
    img.addEventListener("error", () => {
      const logo = img.closest(".company-logo");
      if (!logo) return;
      logo.classList.add("fallback");
      logo.textContent = img.dataset.fallback || "?";
    });
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function loadData() {
  const [summary, jobs, companies] = await Promise.all([
    api("/api/summary"),
    api("/api/jobs"),
    api("/api/companies"),
  ]);
  state.summary = summary;
  state.jobs = jobs;
  state.companies = companies.companies;
  state.coverage = companies.coverage;
  syncSelectedFromHash();
  render();
}

function filteredJobs() {
  const query = state.query.trim().toLowerCase();
  return state.jobs
    .filter((job) => {
      const matchesStatus = !state.status || job.status === state.status;
      const isProtected = ["ready", "applied", "interviewing"].includes(job.status);
      const matchesFit = isProtected || state.showStretch || job.fit_band !== "stretch";
      const haystack = [job.company, job.title, job.location, job.department, job.source_platform].join(" ").toLowerCase();
      return matchesStatus && matchesFit && (!query || haystack.includes(query));
    })
    .sort((a, b) => {
      const bandDelta = (fitBandRank[a.fit_band] ?? 9) - (fitBandRank[b.fit_band] ?? 9);
      if (bandDelta) return bandDelta;
      const scoreDelta = Number(b.score || 0) - Number(a.score || 0);
      if (scoreDelta) return scoreDelta;
      return String(b.discovered_at || "").localeCompare(String(a.discovered_at || ""));
    });
}

function renderMetrics() {
  const summary = state.summary || {};
  const counts = summary.status_counts || {};
  const metrics = [
    ["Discovered", summary.total_jobs || 0, "Total roles found", "blue"],
    ["Active", summary.active_jobs || 0, "Not expired or skipped", "blue"],
    ["Ready", counts.ready || 0, "Ready to apply", "amber"],
    ["Applied", counts.applied || 0, "Applications submitted", "green"],
    ["Scraper Issues", summary.unhealthy_scrapers || 0, "Needs attention", "coral"],
  ];
  $("#overview").innerHTML = metrics
    .map(
      ([label, value, caption, tone]) => `
        <article class="metric ${tone}">
          <span>${label}</span>
          <strong>${value}</strong>
          <small>${caption}</small>
        </article>
      `,
    )
    .join("");
  $("#last-sync").textContent = `Last sync: ${formatDate(summary.last_seen_at)} · ${summary.generated_applications || 0} generated application folders`;
}

function renderStatusFilter() {
  const select = $("#status-filter");
  const current = select.value;
  select.innerHTML = `<option value="">All statuses</option>${editableStatuses
    .map((status) => `<option value="${status}">${statusLabels[status]}</option>`)
    .join("")}`;
  select.value = current;
}

function pipelineCard(job) {
  return `
    <button class="pipeline-job" type="button" data-job-id="${job.id}" aria-label="View ${escapeHtml(job.title)} in database">
      ${companyLogo(job.company, job.company_logo_domain, job.company_logo_url, "sm")}
      <span>
        <strong>${escapeHtml(job.title)}</strong>
        <small>${escapeHtml(job.company)} · ${escapeHtml(job.location || "Location unknown")}</small>
      </span>
      <b aria-hidden="true">›</b>
    </button>
  `;
}

function renderPipeline() {
  const jobs = filteredJobs();
  $("#pipeline").innerHTML = pipelineStatuses
    .map((status) => {
      const statusJobs = jobs.filter((job) => job.status === status);
      const cards = statusJobs.length
        ? statusJobs.slice(0, 3).map(pipelineCard).join("")
        : `<p class="empty compact-empty">No roles yet</p>`;
      const overflow = statusJobs.length > 3 ? `<span class="pipeline-more">+${statusJobs.length - 3} more</span>` : "";
      return `
        <section class="pipeline-column ${status}">
          <header>
            <h3>${statusLabels[status]}</h3>
            <span class="count-pill">${statusJobs.length}</span>
          </header>
          <div class="pipeline-items">${cards}${overflow}</div>
        </section>
      `;
    })
    .join("");
  wireLogoFallbacks($("#pipeline"));
}

function draftBadge(job) {
  if (job.artifact?.draft_state === "ready_for_review") {
    return `<span class="artifact-pill draft-review">Draft Ready for Review</span>`;
  }
  if (job.artifact?.draft_origin === "ollama") {
    return `<span class="artifact-pill draft-ai">AI Draft (${escapeHtml(job.artifact.draft_model || "ollama")})</span>`;
  }
  return "";
}

function artifactHtml(job) {
  const items = [];
  if (!job.artifact) {
    items.push(`<span class="artifact-pill muted">No folder</span>`);
    return `<div class="artifact-stack">${items.join("")}</div>`;
  }
  if (job.artifact.has_cv) {
    items.push(`<a href="/applications/${encodeURIComponent(job.artifact.folder_name)}/cv.pdf" target="_blank" rel="noreferrer" class="artifact-pill ready">CV</a>`);
  }
  if (job.artifact.has_letter) {
    items.push(`<a href="/applications/${encodeURIComponent(job.artifact.folder_name)}/motivation-letter.pdf" target="_blank" rel="noreferrer" class="artifact-pill ready">Letter</a>`);
  }
  if (job.artifact.has_cv && job.artifact.has_letter) {
    items.push(`<a href="/applications/${encodeURIComponent(job.artifact.folder_name)}/bundle.zip" class="artifact-pill ready">Bundle</a>`);
  }
  if (job.artifact.has_job_listing) {
    items.push(`<span class="artifact-pill">Listing</span>`);
  }
  const badge = draftBadge(job);
  return `<div class="artifact-stack">${badge}${items.length ? `<div class="artifact-list">${items.join("")}</div>` : ""}</div>`;
}

function draftActionHtml(job) {
  if (!job.artifact) {
    return `<button type="button" class="job-draft-button" data-open-draft-modal="${job.id}">Create Draft</button>`;
  }
  if (job.artifact.has_draft_data || job.artifact.draft_origin === "ollama") {
    const href = job.artifact.folder_name
      ? `/draft?folder=${encodeURIComponent(job.artifact.folder_name)}&jobId=${job.id}`
      : `/draft?jobId=${job.id}`;
    return `<a class="button secondary job-draft-link" href="${href}">Open Draft</a>`;
  }
  return "";
}

function draftModalJob() {
  return state.jobs.find((job) => String(job.id) === String(state.draftModalJobId)) || null;
}

function renderDraftModal() {
  const existing = document.querySelector("#draft-modal-root");
  if (existing) existing.remove();
  const job = draftModalJob();
  const generatingJob = state.jobs.find((item) => String(item.id) === String(state.draftGeneratingJobId));
  if (!job && (!generatingJob || state.draftGenerationMinimized)) return;

  const root = document.createElement("div");
  root.id = "draft-modal-root";
  if (generatingJob) {
    root.innerHTML = `
      <div class="modal-backdrop is-busy" role="status" aria-live="polite">
        <section class="draft-loading-card">
          <button type="button" class="draft-minimize-button" data-minimize-draft>Minimize</button>
          <div class="angie-draft-sprite" aria-hidden="true"></div>
          <div>
            <h2>Generating draft pack</h2>
            <p>${escapeHtml(generatingJob.title)} · ${escapeHtml(generatingJob.company)}</p>
          </div>
          <div class="draft-thinking-line" aria-label="Draft generation status">
            <span>Reading the job listing</span>
            <span>Applying your guidance</span>
            <span>Preparing editable CV and letter YAML</span>
            <span>Checking guardrails</span>
          </div>
          <p class="draft-loading-note">You can minimize this and keep browsing jobs.</p>
        </section>
      </div>
    `;
  } else {
    root.innerHTML = `
      <div class="modal-backdrop" role="presentation" data-modal-close>
        <section class="draft-create-modal" role="dialog" aria-modal="true" aria-labelledby="draft-modal-title">
          <div class="draft-modal-heading">
            ${companyLogo(job.company, job.company_logo_domain, job.company_logo_url, "sm")}
            <div>
              <h2 id="draft-modal-title">Create Draft Pack</h2>
              <p>${escapeHtml(job.title)} · ${escapeHtml(job.company)}</p>
            </div>
          </div>
          <label class="draft-field">
            Optional guidance for the local draft model
            <textarea id="draft-custom-instructions" rows="7" placeholder="Example: Put Belkin Marketing Operations on page 1 and emphasize trade marketing execution."></textarea>
          </label>
          <p class="draft-helper-copy">Use this for role-specific priorities. The draft will still need human review.</p>
          <div class="draft-modal-actions">
            <button type="button" class="secondary" data-modal-close>Cancel</button>
            <button type="button" data-generate-draft="${job.id}">Generate Draft</button>
          </div>
        </section>
      </div>
    `;
  }
  document.body.appendChild(root);
  wireLogoFallbacks(root);
}

function renderDraftStatusChip() {
  const existing = document.querySelector("#draft-status-root");
  if (existing) existing.remove();
  const generatingJob = state.jobs.find((item) => String(item.id) === String(state.draftGeneratingJobId));
  const ready = state.draftGenerationReady;
  const shouldShow = (generatingJob && state.draftGenerationMinimized) || ready || state.draftGenerationError;
  if (!shouldShow) return;
  const root = document.createElement("div");
  root.id = "draft-status-root";
  if (ready) {
    root.innerHTML = `
      <aside class="draft-status-chip is-ready" aria-live="polite">
        <div class="angie-draft-sprite mini" aria-hidden="true"></div>
        <div>
          <strong>Draft pack ready</strong>
          <span>${escapeHtml(ready.title)} · ${escapeHtml(ready.company)}</span>
        </div>
        <a class="button" href="/draft?folder=${encodeURIComponent(ready.folderName)}&jobId=${encodeURIComponent(ready.jobId)}">Open</a>
        <button type="button" class="draft-chip-close" data-dismiss-draft-status aria-label="Dismiss draft status">&times;</button>
      </aside>
    `;
  } else if (state.draftGenerationError) {
    root.innerHTML = `
      <aside class="draft-status-chip is-error" aria-live="polite">
        <div class="angie-draft-sprite mini" aria-hidden="true"></div>
        <div>
          <strong>Draft generation failed</strong>
          <span>${escapeHtml(state.draftGenerationError)}</span>
        </div>
        <button type="button" class="draft-chip-close" data-dismiss-draft-status aria-label="Dismiss draft status">&times;</button>
      </aside>
    `;
  } else {
    root.innerHTML = `
      <aside class="draft-status-chip" role="status" aria-live="polite">
        <button type="button" class="draft-chip-main" data-restore-draft-modal aria-label="Restore draft generation status">
          <div class="angie-draft-sprite mini" aria-hidden="true"></div>
          <div>
            <strong>Generating draft pack</strong>
            <span>${escapeHtml(generatingJob.title)} · ${escapeHtml(generatingJob.company)}</span>
            <span class="draft-thinking-line mini">
              <span>Reading the job listing</span>
              <span>Applying your guidance</span>
              <span>Preparing editable YAML</span>
              <span>Checking guardrails</span>
            </span>
          </div>
        </button>
      </aside>
    `;
  }
  document.body.appendChild(root);
}

function jobTile(job) {
  const title = job.apply_url
    ? `<a class="role-link" href="${escapeHtml(job.apply_url)}" target="_blank" rel="noreferrer">${escapeHtml(job.title)}</a>`
    : `<span class="role-link">${escapeHtml(job.title)}</span>`;
  const reasons = Array.isArray(job.score_reasons) ? job.score_reasons : [];
  const reasonChips = reasons
    .slice(0, 3)
    .map((reason) => `<span class="reason-chip">${escapeHtml(reason)}</span>`)
    .join("");
  const whyDetails = reasons.length
    ? `<details class="why-details"><summary>Why?</summary><span>${escapeHtml(reasons.join(" · "))}</span></details>`
    : "";
  return `
    <article class="job-tile ${String(state.selectedJobId) === String(job.id) ? "is-selected" : ""}" id="job-${job.id}" data-job-id="${job.id}">
      <div class="job-identity">
        ${companyLogo(job.company, job.company_logo_domain, job.company_logo_url)}
        <div>
          ${title}
          <small>${escapeHtml(job.company)} · ${escapeHtml(job.location || job.country || "Unknown")}</small>
          <div class="score-row">
            <span class="fit-pill ${escapeHtml(job.fit_band || "stretch")}">${escapeHtml(fitBandLabels[job.fit_band] || job.fit_band || "Stretch")}</span>
            <span class="score-pill">${escapeHtml(job.score ?? 0)}</span>
            ${reasonChips}
          </div>
          ${whyDetails}
        </div>
      </div>
      <select class="status-select" data-job-id="${job.id}" aria-label="Status for ${escapeHtml(job.title)}">
        ${editableStatuses
          .map((status) => `<option value="${status}" ${job.status === status ? "selected" : ""}>${statusLabels[status]}</option>`)
          .join("")}
      </select>
      <div class="job-source">
        <strong>${escapeHtml(job.source_platform || job.scraper_type || "Careers Site")}</strong>
        <small>${escapeHtml(job.scraper_type || "")}</small>
      </div>
      <div class="job-artifacts">
        <span>Artifacts</span>
        ${artifactHtml(job)}
        <div class="job-draft-action-row">${draftActionHtml(job)}</div>
      </div>
      <div class="job-date">
        <span>Discovered</span>
        <strong>${formatDate(job.discovered_at)}</strong>
      </div>
      <button class="job-open" type="button" data-job-id="${job.id}" aria-label="Select ${escapeHtml(job.title)}">›</button>
    </article>
  `;
}

function renderJobsList() {
  const rows = filteredJobs();
  $("#jobs-list").innerHTML = rows.length
    ? rows.map(jobTile).join("")
    : `<p class="empty">No jobs match the current filters.</p>`;
  wireLogoFallbacks($("#jobs-list"));
}

function renderCoverage() {
  const coverage = state.coverage || { total: 0, dedicated: 0, manual_review: 0, disabled: 0, promoted_percent: 0 };
  const health = state.summary?.scraper_health_counts || {};
  const broken = health.failed || 0;
  const warning = health.warning || 0;
  const healthy = health.ok || 0;
  const unchecked = (state.companies || []).filter((company) => company.enabled && !company.health).length;
  $("#coverage-card").innerHTML = `
    <div class="coverage-score">
      <strong>${coverage.promoted_percent}%</strong>
      <span>Dedicated scraper coverage</span>
    </div>
    <div class="coverage-meter" aria-label="${coverage.promoted_percent}% dedicated scraper coverage">
      <span style="width: ${coverage.promoted_percent}%"></span>
    </div>
    <div class="coverage-stats">
      <div class="coverage-stat"><strong>${coverage.dedicated}</strong><span>Dedicated</span></div>
      <div class="coverage-stat"><strong>${coverage.manual_review}</strong><span>Manual</span></div>
      <div class="coverage-stat"><strong>${coverage.disabled}</strong><span>Disabled</span></div>
    </div>
    <div class="health-summary ${broken || warning ? "has-issues" : ""}">
      <strong>${broken + warning}</strong>
      <span>${broken} broken · ${warning} needs check · ${healthy} healthy · ${unchecked} unchecked</span>
    </div>
  `;
}

function healthPill(company) {
  const health = company.health;
  const status = health?.status || (company.scraper_type === "manual_review" ? "manual_review" : "unknown");
  const details = [health?.strategy || company.adapter || company.scraper_type, health?.checked_at ? `checked ${formatDate(health.checked_at)}` : "not checked yet"]
    .filter(Boolean)
    .join(" · ");
  const message = health?.error || health?.message || details;
  return `
    <span class="status-pill scraper-health ${escapeHtml(status)}" title="${escapeHtml(message)}">
      ${healthLabels[status] || status}
    </span>
  `;
}

function renderCompanies() {
  const rows = [...state.companies].sort((a, b) => {
    const rank = { failed: 0, warning: 1, manual_review: 2, unknown: 3, ok: 4 };
    const healthDelta = (rank[a.health?.status || "unknown"] ?? 5) - (rank[b.health?.status || "unknown"] ?? 5);
    if (healthDelta) return healthDelta;
    if (a.scraper_type !== b.scraper_type) return a.scraper_type === "manual_review" ? -1 : 1;
    return a.company.localeCompare(b.company);
  });
  $("#company-list").innerHTML = rows
    .slice(0, 28)
    .map(
      (company) => `
        <a class="company-row" href="${escapeHtml(company.careers_url)}" target="_blank" rel="noreferrer" aria-label="Open ${escapeHtml(company.company)} careers page">
          ${companyLogo(company.company, company.logo_domain, company.logo_url, "sm")}
          <div>
            <strong>${escapeHtml(company.company)}</strong>
            <span>${company.job_count} tracked roles · ${escapeHtml(company.health?.strategy || company.adapter || company.scraper_type)}</span>
            ${
              company.health?.message || company.health?.error
                ? `<small>${escapeHtml(company.health.error || company.health.message)}</small>`
                : ""
            }
          </div>
          <div class="company-pills">
            ${healthPill(company)}
            ${company.logo_url || company.logo_domain ? `<span class="status-pill logo-status">Logo lookup</span>` : ""}
          </div>
        </a>
      `,
    )
    .join("");
  wireLogoFallbacks($("#company-list"));
}

function render() {
  renderMetrics();
  renderStatusFilter();
  renderPipeline();
  renderJobsList();
  renderCoverage();
  renderCompanies();
  renderDraftModal();
  renderDraftStatusChip();
}

function syncSelectedFromHash() {
  const match = window.location.hash.match(/^#job-(\d+)$/);
  state.selectedJobId = match ? match[1] : state.selectedJobId;
}

function selectJob(jobId, shouldScroll = true) {
  state.selectedJobId = String(jobId);
  if (window.location.hash !== `#job-${jobId}`) {
    history.replaceState(null, "", `#job-${jobId}`);
  }
  renderJobsList();
  if (shouldScroll) scrollToJob(jobId);
}

function scrollToJob(jobId) {
  const target = document.getElementById(`job-${jobId}`);
  if (!target) {
    if (!state.jobs.some((job) => String(job.id) === String(jobId))) return;
    state.status = "";
    $("#status-filter").value = "";
    state.query = "";
    $("#job-search").value = "";
    state.showStretch = true;
    $("#show-stretch").checked = true;
    renderJobsList();
    requestAnimationFrame(() => scrollToJob(jobId));
    return;
  }
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function updateJobStatus(jobId, status) {
  await api(`/api/jobs/${jobId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
  const job = state.jobs.find((item) => String(item.id) === String(jobId));
  if (job) job.status = status;
  render();
}

async function createDraftAndOpen(jobId, customInstructions = "") {
  state.draftModalJobId = null;
  state.draftGeneratingJobId = String(jobId);
  state.draftGenerationMinimized = false;
  state.draftGenerationReady = null;
  state.draftGenerationError = "";
  renderDraftModal();
  renderDraftStatusChip();
  try {
    const draft = await api(`/api/jobs/${jobId}/draft-pack`, {
      method: "POST",
      body: JSON.stringify({ custom_instructions: customInstructions }),
    });
    const job = state.jobs.find((item) => String(item.id) === String(jobId));
    if (state.draftGenerationMinimized) {
      state.draftGenerationReady = {
        folderName: draft.folder_name,
        jobId: String(jobId),
        title: job?.title || "Draft pack",
        company: job?.company || "Application",
      };
      state.draftGeneratingJobId = null;
      renderDraftModal();
      renderDraftStatusChip();
      await loadData();
      return;
    }
    window.location.href = `/draft?folder=${encodeURIComponent(draft.folder_name)}&jobId=${jobId}`;
  } catch (error) {
    state.draftGenerationError = error.message;
    state.draftGeneratingJobId = null;
    state.draftGenerationMinimized = false;
    renderDraftModal();
    renderDraftStatusChip();
    if (!state.draftGenerationError) alert(error.message);
  }
}

function bindEvents() {
  $("#refresh-button").addEventListener("click", loadData);
  $("#job-search").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderPipeline();
    renderJobsList();
  });
  $("#status-filter").addEventListener("change", (event) => {
    state.status = event.target.value;
    renderPipeline();
    renderJobsList();
  });
  $("#show-stretch").addEventListener("change", (event) => {
    state.showStretch = event.target.checked;
    renderPipeline();
    renderJobsList();
  });
  $("#pipeline").addEventListener("click", (event) => {
    const card = event.target.closest(".pipeline-job");
    if (!card) return;
    selectJob(card.dataset.jobId);
  });
  $("#jobs-list").addEventListener("click", async (event) => {
    const createButton = event.target.closest("[data-open-draft-modal]");
    if (createButton) {
      state.draftModalJobId = createButton.dataset.openDraftModal;
      renderDraftModal();
      return;
    }
    if (event.target.closest("a, select, details, button.job-draft-button")) return;
    const item = event.target.closest("[data-job-id]");
    if (!item) return;
    selectJob(item.dataset.jobId, false);
  });
  $("#jobs-list").addEventListener("change", async (event) => {
    if (!event.target.matches(".status-select")) return;
    event.target.disabled = true;
    try {
      await updateJobStatus(event.target.dataset.jobId, event.target.value);
    } catch (error) {
      alert(error.message);
      await loadData();
    } finally {
      event.target.disabled = false;
    }
  });
  document.body.addEventListener("click", async (event) => {
    const minimize = event.target.closest("[data-minimize-draft]");
    if (minimize && state.draftGeneratingJobId) {
      state.draftGenerationMinimized = true;
      renderDraftModal();
      renderDraftStatusChip();
      return;
    }
    const restore = event.target.closest("[data-restore-draft-modal]");
    if (restore && state.draftGeneratingJobId) {
      state.draftGenerationMinimized = false;
      renderDraftModal();
      renderDraftStatusChip();
      return;
    }
    const dismiss = event.target.closest("[data-dismiss-draft-status]");
    if (dismiss) {
      state.draftGenerationReady = null;
      state.draftGenerationError = "";
      renderDraftStatusChip();
      return;
    }
    const close = event.target.matches("[data-modal-close]") ? event.target : null;
    if (close && !state.draftGeneratingJobId) {
      state.draftModalJobId = null;
      renderDraftModal();
      return;
    }
    const generate = event.target.closest("[data-generate-draft]");
    if (!generate) return;
    const instructions = $("#draft-custom-instructions")?.value || "";
    await createDraftAndOpen(generate.dataset.generateDraft, instructions);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || state.draftGeneratingJobId) return;
    if (!state.draftModalJobId) return;
    state.draftModalJobId = null;
    renderDraftModal();
  });
  $("#company-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const message = $("#company-form-message");
    const body = Object.fromEntries(new FormData(form).entries());
    const domain = domainFromUrl(body.careers_url);
    body.logo_url = faviconUrl(domain);
    message.textContent = domain ? `Adding company · logo lookup for ${domain}...` : "Adding company...";
    try {
      await api("/api/companies", { method: "POST", body: JSON.stringify(body) });
      form.reset();
      message.textContent = domain ? "Company added. Logo lookup saved when available." : "Company added with initials fallback.";
      await loadData();
    } catch (error) {
      message.textContent = error.message;
    }
  });
  window.addEventListener("hashchange", () => {
    syncSelectedFromHash();
    renderJobsList();
  });
}

bindEvents();
loadData().catch((error) => {
  $("#last-sync").textContent = `Could not load dashboard: ${error.message}`;
});
