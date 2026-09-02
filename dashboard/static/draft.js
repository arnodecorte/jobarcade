const $ = (selector) => document.querySelector(selector);

let state = {
  job: null,
  draft: null,
  tab: "cv",
  busy: false,
  message: "",
  showCreateModal: false,
  generationMinimized: false,
  generationReady: false,
  generationError: "",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function counterClass(length, limit) {
  if (!limit) return "";
  if (length > limit) return "is-error";
  if (length > Math.floor(limit * 0.9)) return "is-warning";
  return "";
}

function fieldCounter(value, limit) {
  const length = String(value || "").length;
  return `<span class="field-counter ${counterClass(length, limit)}">${length} / ${limit}</span>`;
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

function faviconUrl(domain) {
  return domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64` : "";
}

function companyLogo(company, domain, logoUrl, size = "md") {
  const fallback = initialsLogo(company);
  const src = logoUrl || faviconUrl(domain);
  if (!src) return `<span class="company-logo ${size} fallback">${escapeHtml(fallback)}</span>`;
  return `
    <span class="company-logo ${size}">
      <img src="${escapeHtml(src)}" alt="" loading="lazy" data-fallback="${escapeHtml(fallback)}" />
    </span>
  `;
}

const variantLabels = {
  compact_one_page: "Compact 1-page",
  classic_two_page: "Classic 2-page",
  enriched_two_page: "Enriched 2-page",
};

const roleFocusLabels = {
  marketing: "Marketing",
  content: "Content",
  brand: "Brand",
  community: "Community",
  commercial_ops: "Commercial / Ops",
};

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
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

function params() {
  return new URLSearchParams(window.location.search);
}

async function loadJob(jobId) {
  if (!jobId) return null;
  const jobs = await api(`/api/jobs?limit=300`);
  return jobs.find((job) => String(job.id) === String(jobId)) || null;
}

function roleEditor(role, section, index) {
  const bullets = Array.isArray(role.bullets) ? role.bullets : [];
  return `
    <section class="draft-role">
      <div class="draft-role-toolbar">
        <label class="draft-include-toggle">
          <input type="checkbox" data-draft-field="${section}.${index}.include" ${role.include !== false ? "checked" : ""} />
          Include in CV
        </label>
        <span>
          <button type="button" class="icon-button" data-action="move-role" data-section="${section}" data-index="${index}" data-direction="-1" aria-label="Move role up">↑</button>
          <button type="button" class="icon-button" data-action="move-role" data-section="${section}" data-index="${index}" data-direction="1" aria-label="Move role down">↓</button>
        </span>
      </div>
      <div class="draft-role-grid">
        <label class="draft-field">Role <input data-draft-field="${section}.${index}.role" value="${escapeHtml(role.role || "")}" /></label>
        <label class="draft-field">Company <input data-draft-field="${section}.${index}.company" value="${escapeHtml(role.company || "")}" /></label>
        <label class="draft-field">Period <input data-draft-field="${section}.${index}.period" value="${escapeHtml(role.period || "")}" /></label>
        <label class="draft-field">Location <input data-draft-field="${section}.${index}.location" value="${escapeHtml(role.location || "")}" /></label>
      </div>
      ${bullets
        .map(
          (bullet, bulletIndex) => `
            <label class="draft-field bullet-field">
              <span class="draft-field-heading">Bullet ${bulletIndex + 1}
                <button type="button" class="inline-remove-button" data-action="remove-bullet" data-section="${section}" data-index="${index}" data-bullet-index="${bulletIndex}">Remove</button>
              </span>
              <textarea data-draft-field="${section}.${index}.bullets.${bulletIndex}" rows="2">${escapeHtml(bullet)}</textarea>
              ${fieldCounter(bullet, 165)}
            </label>
          `,
        )
        .join("")}
      <button type="button" class="secondary compact-action" data-action="add-bullet" data-section="${section}" data-index="${index}">Add bullet</button>
    </section>
  `;
}

function artifactLinks(artifact) {
  if (!artifact) return "";
  const folder = encodeURIComponent(artifact.folder_name);
  const links = [];
  if (artifact.has_cv) links.push(`<a class="artifact-pill ready" href="/applications/${folder}/cv.pdf" target="_blank" rel="noreferrer">CV PDF</a>`);
  if (artifact.has_letter) links.push(`<a class="artifact-pill ready" href="/applications/${folder}/motivation-letter.pdf" target="_blank" rel="noreferrer">Letter PDF</a>`);
  if (artifact.has_cv && artifact.has_letter) links.push(`<a class="artifact-pill ready" href="/applications/${folder}/bundle.zip">Bundle</a>`);
  return links.length ? `<div class="artifact-list">${links.join("")}</div>` : "";
}

function renderSummary() {
  const job = state.job;
  const draft = state.draft;
  if (!job) {
    $("#draft-job-summary").innerHTML = `<p class="empty">Job not found.</p>`;
    return;
  }
  $("#draft-job-summary").innerHTML = `
    ${companyLogo(job.company, job.company_logo_domain, job.company_logo_url)}
    <div>
      <h2>${escapeHtml(job.title)}</h2>
      <p>${escapeHtml(job.company)} · ${escapeHtml(job.location || "Location unknown")}</p>
      <div class="draft-summary-pills">
        <span class="artifact-pill draft-ai">Local AI Draft</span>
        ${
          draft?.meta?.state === "ready_for_review"
            ? `<span class="artifact-pill draft-review">Draft Pack Ready for Review</span>`
            : draft?.artifact?.has_draft_data
              ? `<span class="artifact-pill muted">Editable draft saved</span>`
              : ""
        }
      </div>
    </div>
  `;
  $("#draft-subtitle").textContent = draft?.meta?.review_label || "Create, review, and adjust the local draft pack before stronger review.";
  wireLogoFallbacks($("#draft-job-summary"));
}

function renderMessage() {
  const message = $("#draft-page-message");
  if (!state.message) {
    message.hidden = true;
    message.textContent = "";
    return;
  }
  message.hidden = false;
  message.textContent = state.message;
}

function renderActions() {
  const root = $("#draft-stage-actions");
  const jobId = state.job?.id;
  if (!state.draft) {
    root.innerHTML = `<button type="button" data-action="open-create-modal" ${state.busy ? "disabled" : ""}>Create Draft</button>`;
    return;
  }
  root.innerHTML = `
    <button type="button" data-action="save" ${state.busy ? "disabled" : ""}>Save Draft</button>
    <button type="button" data-action="build" class="secondary" ${state.busy ? "disabled" : ""}>Build PDF</button>
    <button type="button" data-action="ready" class="secondary" ${state.busy ? "disabled" : ""}>Mark Draft Pack Ready for Review</button>
    <a class="button secondary" href="/#job-${jobId}">Back to Job</a>
  `;
}

function renderCreateModal() {
  const existing = document.querySelector("#draft-modal-root");
  if (existing) existing.remove();
  if (!state.showCreateModal || !state.job) return;
  const root = document.createElement("div");
  root.id = "draft-modal-root";
  root.innerHTML = `
    <div class="modal-backdrop" role="presentation" data-modal-close>
      <section class="draft-create-modal" role="dialog" aria-modal="true" aria-labelledby="draft-modal-title">
        <div class="draft-modal-heading">
          ${companyLogo(state.job.company, state.job.company_logo_domain, state.job.company_logo_url, "sm")}
          <div>
            <h2 id="draft-modal-title">Create Draft Pack</h2>
            <p>${escapeHtml(state.job.title)} · ${escapeHtml(state.job.company)}</p>
          </div>
        </div>
        <label class="draft-field">
          Optional guidance for the local draft model
          <textarea id="draft-custom-instructions" rows="7" placeholder="Example: Put Belkin Marketing Operations on page 1 and emphasize trade marketing execution."></textarea>
        </label>
        <p class="draft-helper-copy">Use this for role-specific priorities. The draft will still need human review.</p>
        <div class="draft-modal-actions">
          <button type="button" class="secondary" data-modal-close>Cancel</button>
          <button type="button" data-action="generate">Generate Draft</button>
        </div>
      </section>
    </div>
  `;
  document.body.appendChild(root);
  wireLogoFallbacks(root);
}

function renderLoadingOverlay() {
  const existing = document.querySelector("#draft-loading-root");
  if (existing) existing.remove();
  if (!state.busy || state.generationMinimized || !state.message.toLowerCase().includes("generating")) return;
  const root = document.createElement("div");
  root.id = "draft-loading-root";
  root.innerHTML = `
    <div class="modal-backdrop is-busy" role="status" aria-live="polite">
      <section class="draft-loading-card">
        <button type="button" class="draft-minimize-button" data-action="minimize-generation">Minimize</button>
        <div class="angie-draft-sprite" aria-hidden="true"></div>
        <div>
          <h2>Generating draft pack</h2>
          <p>${escapeHtml(state.job?.title || "Draft pack")} · ${escapeHtml(state.job?.company || "Angelica Job Hunt HQ")}</p>
        </div>
        <div class="draft-thinking-line" aria-label="Draft generation status">
          <span>Reading the job listing</span>
          <span>Applying your guidance</span>
          <span>Preparing editable CV and letter YAML</span>
          <span>Checking guardrails</span>
        </div>
        <p class="draft-loading-note">You can minimize this while the local model works.</p>
      </section>
    </div>
  `;
  document.body.appendChild(root);
}

function renderGenerationStatusChip() {
  const existing = document.querySelector("#draft-status-root");
  if (existing) existing.remove();
  const showBusy = state.busy && state.generationMinimized && state.message.toLowerCase().includes("generating");
  if (!showBusy && !state.generationReady && !state.generationError) return;
  const root = document.createElement("div");
  root.id = "draft-status-root";
  if (state.generationReady) {
    root.innerHTML = `
      <aside class="draft-status-chip is-ready" aria-live="polite">
        <div class="angie-draft-sprite mini" aria-hidden="true"></div>
        <div>
          <strong>Draft pack ready</strong>
          <span>${escapeHtml(state.job?.title || "Draft pack")} · ${escapeHtml(state.job?.company || "Application")}</span>
        </div>
        <button type="button" class="button" data-action="open-ready-draft">Open</button>
        <button type="button" class="draft-chip-close" data-action="dismiss-generation" aria-label="Dismiss draft status">&times;</button>
      </aside>
    `;
  } else if (state.generationError) {
    root.innerHTML = `
      <aside class="draft-status-chip is-error" aria-live="polite">
        <div class="angie-draft-sprite mini" aria-hidden="true"></div>
        <div>
          <strong>Draft generation failed</strong>
          <span>${escapeHtml(state.generationError)}</span>
        </div>
        <button type="button" class="draft-chip-close" data-action="dismiss-generation" aria-label="Dismiss draft status">&times;</button>
      </aside>
    `;
  } else {
    root.innerHTML = `
      <aside class="draft-status-chip" role="status" aria-live="polite">
        <button type="button" class="draft-chip-main" data-action="restore-generation" aria-label="Restore draft generation status">
          <div class="angie-draft-sprite mini" aria-hidden="true"></div>
          <div>
            <strong>Generating draft pack</strong>
            <span>${escapeHtml(state.job?.title || "Draft pack")} · ${escapeHtml(state.job?.company || "Application")}</span>
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

function renderTabs() {
  return `
    <div class="draft-tabs">
      ${["builder", "cv", "letter", "listing", "preview"]
        .map((tab) => `<button type="button" class="${state.tab === tab ? "active" : ""}" data-tab="${tab}">${tab[0].toUpperCase()}${tab.slice(1)}</button>`)
        .join("")}
    </div>
  `;
}

function renderBuilder(cv, review) {
  const highlights = Array.isArray(cv.selected_highlights) ? cv.selected_highlights : [];
  const variant = cv.variant || (Number(cv.max_pages || 2) <= 1 ? "compact_one_page" : "classic_two_page");
  const roleFocus = cv.role_focus || "marketing";
  const allRoles = [
    ...(cv.experience || []).map((role, index) => ({ role, section: "experience", index })),
    ...(cv.additional || []).map((role, index) => ({ role, section: "additional", index })),
  ];
  const reviewItems = Array.isArray(review?.items) ? review.items : [];
  return `
    <div class="builder-layout">
      <section class="builder-panel">
        <h3>CV Strategy</h3>
        <div class="builder-control-grid">
          <label class="draft-field">
            Presentation
            <select data-draft-field="cv.variant">
              ${Object.entries(variantLabels)
                .map(([value, label]) => `<option value="${value}" ${variant === value ? "selected" : ""}>${label}</option>`)
                .join("")}
            </select>
          </label>
          <label class="draft-field">
            Role focus
            <select data-draft-field="cv.role_focus">
              ${Object.entries(roleFocusLabels)
                .map(([value, label]) => `<option value="${value}" ${roleFocus === value ? "selected" : ""}>${label}</option>`)
                .join("")}
            </select>
          </label>
          <label class="draft-field">
            Page budget
            <input type="number" min="1" max="2" data-draft-field="cv.max_pages" value="${Number(cv.max_pages || (variant === "compact_one_page" ? 1 : 2))}" />
          </label>
        </div>
        <div class="variant-hint">
          ${variant === "compact_one_page"
            ? "Best default for Angelica right now: sharp, dense, and no sparse second page."
            : variant === "enriched_two_page"
              ? "Use when a role benefits from extra context, selected impact, and additional experience."
              : "Legacy layout with a fixed second page for certifications and additional experience."}
        </div>
      </section>

      <section class="builder-panel">
        <h3>Selected Impact</h3>
        <div class="highlight-list">
          ${highlights
            .map(
              (highlight, index) => `
                <label class="draft-field">
                  Highlight ${index + 1}
                  <textarea data-draft-field="cv.selected_highlights.${index}" rows="2">${escapeHtml(highlight)}</textarea>
                  ${fieldCounter(highlight, 135)}
                </label>
              `,
            )
            .join("")}
        </div>
        <button type="button" class="secondary compact-action" data-action="add-highlight" ${highlights.length >= 4 ? "disabled" : ""}>Add highlight</button>
      </section>

      <section class="builder-panel">
        <h3>Role Stack</h3>
        <div class="role-stack">
          ${allRoles
            .map(
              ({ role, section, index }) => `
                <article class="role-stack-row ${role.include === false ? "is-muted" : ""}">
                  <label class="draft-include-toggle">
                    <input type="checkbox" data-draft-field="${section}.${index}.include" ${role.include !== false ? "checked" : ""} />
                    <span>
                      <strong>${escapeHtml(role.role || "Untitled role")}</strong>
                      <small>${escapeHtml(role.company || "")} · ${escapeHtml(section === "experience" ? "Primary" : "Additional")}</small>
                    </span>
                  </label>
                  <span>
                    <button type="button" class="icon-button" data-action="move-role" data-section="${section}" data-index="${index}" data-direction="-1" aria-label="Move role up">↑</button>
                    <button type="button" class="icon-button" data-action="move-role" data-section="${section}" data-index="${index}" data-direction="1" aria-label="Move role down">↓</button>
                  </span>
                </article>
              `,
            )
            .join("")}
        </div>
      </section>

      <aside class="builder-review">
        <div>
          <span class="review-score">${Number(review?.score || 0)}</span>
          <strong>${escapeHtml(review?.band || "Not reviewed")}</strong>
          <small>${Number(review?.proof_bullets || 0)} quantified proof bullets · ${Number(review?.included_roles || 0)} included roles</small>
        </div>
        ${
          reviewItems.length
            ? `<ul>${reviewItems
                .map((item) => `<li class="${escapeHtml(item.level)}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></li>`)
                .join("")}</ul>`
            : `<p class="empty compact-empty">No major CV review flags.</p>`
        }
      </aside>
    </div>
  `;
}

function renderContent() {
  const root = $("#draft-page-content");
  if (!state.job) {
    root.innerHTML = `<p class="empty">This draft page needs a valid job or folder parameter.</p>`;
    return;
  }
  if (!state.draft) {
    root.innerHTML = `
      <div class="draft-empty-state">
        <h3>No draft yet</h3>
        <p>Use the button above to create a local Ollama draft for this role. Once it is ready, this page becomes the editing workspace.</p>
      </div>
    `;
    return;
  }
  const draft = state.draft;
  const cv = draft.cv || {};
  const letter = draft.letter || {};
  const paragraphs = Array.isArray(letter.paragraphs) ? letter.paragraphs : [];
  const bodyLength = paragraphs.reduce((sum, paragraph) => sum + String(paragraph || "").length, 0);

  let body = "";
  if (state.tab === "builder") {
    body = renderBuilder(cv, draft.cv_review);
  } else if (state.tab === "cv") {
    body = `
      <div class="draft-editor">
        <label class="draft-field">Target title <input data-draft-field="cv.title" value="${escapeHtml(cv.title || "")}" /></label>
        <label class="draft-field">
          Tagline
          <textarea data-draft-field="cv.tagline" rows="3">${escapeHtml(cv.tagline || "")}</textarea>
          ${fieldCounter(cv.tagline, 170)}
        </label>
        <label class="draft-field">
          Profile
          <textarea data-draft-field="cv.profile" rows="5">${escapeHtml(cv.profile || "")}</textarea>
          ${fieldCounter(cv.profile, 600)}
        </label>
        <h3>Experience</h3>
        ${(cv.experience || []).map((role, index) => roleEditor(role, "experience", index)).join("")}
        <h3>Additional Experience</h3>
        ${(cv.additional || []).map((role, index) => roleEditor(role, "additional", index)).join("")}
      </div>
    `;
  } else if (state.tab === "letter") {
    body = `
      <div class="draft-editor">
        <label class="draft-field">Subtitle <input data-draft-field="letter.subtitle" value="${escapeHtml(letter.subtitle || "")}" /></label>
        <div class="draft-limit-row">
          <span>${paragraphs.length} paragraphs</span>
          ${fieldCounter("x".repeat(bodyLength), 2050)}
        </div>
        ${paragraphs
          .map(
            (paragraph, index) => `
              <label class="draft-field">
                Paragraph ${index + 1}
                <textarea data-draft-field="letter.paragraphs.${index}" rows="5">${escapeHtml(paragraph)}</textarea>
              </label>
            `,
          )
          .join("")}
      </div>
    `;
  } else if (state.tab === "listing") {
    body = `<pre class="listing-preview">${escapeHtml(draft.listing || "")}</pre>`;
  } else {
    body = draft.artifact?.has_cv || draft.artifact?.has_letter
      ? `
        <div class="preview-grid">
          ${draft.artifact.has_cv ? `<iframe title="CV preview" src="/applications/${encodeURIComponent(draft.folder_name)}/cv.pdf"></iframe>` : ""}
          ${draft.artifact.has_letter ? `<iframe title="Letter preview" src="/applications/${encodeURIComponent(draft.folder_name)}/motivation-letter.pdf"></iframe>` : ""}
        </div>
      `
      : `<p class="empty compact-empty">Build the PDFs to preview them here.</p>`;
  }

  root.innerHTML = `
    ${renderTabs()}
    ${Array.isArray(draft.warnings) && draft.warnings.length ? `<ul class="draft-warnings">${draft.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : ""}
    <form id="draft-form">${body}</form>
    ${artifactLinks(draft.artifact)}
  `;
}

function setDeepDraftValue(target, path, value) {
  const parts = path.split(".");
  if (parts[0] === "cv") {
    target.cv = target.cv || {};
    if (parts[1] === "selected_highlights") {
      target.cv.selected_highlights = target.cv.selected_highlights || [];
      target.cv.selected_highlights[Number(parts[2])] = value;
      return;
    }
    target.cv[parts[1]] = value;
    return;
  }
  if (parts[0] === "letter" && parts[1] === "subtitle") {
    target.letter = target.letter || {};
    target.letter.subtitle = value;
    return;
  }
  if (parts[0] === "letter" && parts[1] === "paragraphs") {
    target.letter = target.letter || {};
    target.letter.paragraphs = target.letter.paragraphs || [];
    target.letter.paragraphs[Number(parts[2])] = value;
    return;
  }
  const section = parts[0];
  if (section !== "experience" && section !== "additional") return;
  target.cv = target.cv || {};
  target.cv[section] = target.cv[section] || [];
  const roleIndex = Number(parts[1]);
  target.cv[section][roleIndex] = target.cv[section][roleIndex] || { bullets: [] };
  if (parts[2] === "bullets") {
    target.cv[section][roleIndex].bullets = target.cv[section][roleIndex].bullets || [];
    target.cv[section][roleIndex].bullets[Number(parts[3])] = value;
  } else {
    target.cv[section][roleIndex][parts[2]] = value;
  }
}

function collectDraftFromForm() {
  const draft = structuredClone(state.draft || { cv: {}, letter: {} });
  document.querySelectorAll("[data-draft-field]").forEach((field) => {
    setDeepDraftValue(draft, field.dataset.draftField, field.type === "checkbox" ? field.checked : field.value);
  });
  return {
    cv: {
      max_pages: Number(draft.cv?.max_pages || (draft.cv?.variant === "compact_one_page" ? 1 : 2)),
      variant: draft.cv?.variant || (Number(draft.cv?.max_pages || 2) <= 1 ? "compact_one_page" : "classic_two_page"),
      role_focus: draft.cv?.role_focus || "",
      title: draft.cv?.title || "",
      tagline: draft.cv?.tagline || "",
      profile: draft.cv?.profile || "",
      selected_highlights: (draft.cv?.selected_highlights || []).filter((item) => String(item || "").trim()),
      experience: draft.cv?.experience || [],
      additional: draft.cv?.additional || [],
    },
    letter: {
      max_pages: Number(draft.letter?.max_pages || 1),
      subtitle: draft.letter?.subtitle || "",
      paragraphs: draft.letter?.paragraphs || [],
    },
  };
}

function syncDraftFromVisibleForm() {
  if (!state.draft) return;
  state.draft = { ...state.draft, ...collectDraftFromForm() };
}

function moveRole(section, index, direction) {
  syncDraftFromVisibleForm();
  const roles = state.draft?.cv?.[section] || [];
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= roles.length) return;
  [roles[index], roles[nextIndex]] = [roles[nextIndex], roles[index]];
  renderAll();
}

function addBullet(section, index) {
  syncDraftFromVisibleForm();
  const role = state.draft?.cv?.[section]?.[index];
  if (!role) return;
  role.bullets = role.bullets || [];
  if (role.bullets.length >= 5) return;
  role.bullets.push("");
  renderAll();
}

function removeBullet(section, index, bulletIndex) {
  syncDraftFromVisibleForm();
  const role = state.draft?.cv?.[section]?.[index];
  if (!role?.bullets) return;
  role.bullets.splice(bulletIndex, 1);
  renderAll();
}

function addHighlight() {
  syncDraftFromVisibleForm();
  state.draft.cv = state.draft.cv || {};
  state.draft.cv.selected_highlights = state.draft.cv.selected_highlights || [];
  if (state.draft.cv.selected_highlights.length >= 4) return;
  state.draft.cv.selected_highlights.push("");
  renderAll();
}

function renderAll() {
  renderSummary();
  renderActions();
  renderMessage();
  renderContent();
  renderCreateModal();
  renderLoadingOverlay();
  renderGenerationStatusChip();
}

async function loadDraftFromLocation() {
  const search = params();
  const folder = search.get("folder");
  const jobId = search.get("jobId");
  state.job = await loadJob(jobId);
  if (folder) {
    state.draft = await api(`/api/applications/${encodeURIComponent(folder)}/draft`);
    state.tab = "builder";
  } else {
    state.draft = null;
  }
  renderAll();
}

async function createDraft(customInstructions = "") {
  const search = params();
  const jobId = search.get("jobId");
  if (!jobId) return;
  state.busy = true;
  state.showCreateModal = false;
  state.generationMinimized = false;
  state.generationReady = false;
  state.generationError = "";
  state.message = "Generating draft with local Ollama. This can take a minute...";
  renderAll();
  try {
    const draft = await api(`/api/jobs/${jobId}/draft-pack`, {
      method: "POST",
      body: JSON.stringify({ custom_instructions: customInstructions }),
    });
    window.history.replaceState(null, "", `/draft?folder=${encodeURIComponent(draft.folder_name)}&jobId=${jobId}`);
    state.draft = draft;
    state.tab = "builder";
    state.message = "Draft pack ready for review.";
    state.generationReady = state.generationMinimized;
  } catch (error) {
    state.message = error.message;
    state.generationError = error.message;
  } finally {
    state.busy = false;
    renderAll();
  }
}

async function saveDraft() {
  if (!state.draft?.folder_name) return;
  state.busy = true;
  state.message = "Saving draft...";
  renderAll();
  try {
    state.draft = await api(`/api/applications/${encodeURIComponent(state.draft.folder_name)}/draft`, {
      method: "PUT",
      body: JSON.stringify(collectDraftFromForm()),
    });
    state.message = "Draft saved.";
  } catch (error) {
    state.message = error.message;
  } finally {
    state.busy = false;
    renderAll();
  }
}

async function buildDraft() {
  if (!state.draft?.folder_name) return;
  await saveDraft();
  state.busy = true;
  state.message = "Building PDFs...";
  renderAll();
  try {
    const result = await api(`/api/applications/${encodeURIComponent(state.draft.folder_name)}/build`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.draft.artifact = result.artifact;
    state.tab = result.ok ? "preview" : state.tab;
    state.message = result.ok ? "Build complete. The draft pack is ready for review." : result.error;
    state.draft = await api(`/api/applications/${encodeURIComponent(state.draft.folder_name)}/draft`);
  } catch (error) {
    state.message = error.message;
  } finally {
    state.busy = false;
    renderAll();
  }
}

async function markReady() {
  if (!state.draft?.folder_name) return;
  state.busy = true;
  state.message = "Marking this draft pack ready for review...";
  renderAll();
  try {
    const result = await api(`/api/applications/${encodeURIComponent(state.draft.folder_name)}/ready-for-review`, {
      method: "POST",
      body: JSON.stringify({ job_id: state.job?.id }),
    });
    state.draft.meta = result.meta;
    state.draft.artifact = result.artifact;
    state.message = "Draft pack ready for review.";
  } catch (error) {
    state.message = error.message;
  } finally {
    state.busy = false;
    renderAll();
  }
}

function bindEvents() {
  $("#draft-refresh-button").addEventListener("click", loadDraftFromLocation);
  document.body.addEventListener("click", async (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      syncDraftFromVisibleForm();
      state.tab = tab.dataset.tab;
      renderAll();
      return;
    }
    const action = event.target.closest("[data-action]");
    if (!action) return;
    if (action.dataset.action === "open-create-modal") {
      state.showCreateModal = true;
      renderAll();
    }
    if (action.dataset.action === "minimize-generation") {
      state.generationMinimized = true;
      renderAll();
      return;
    }
    if (action.dataset.action === "restore-generation") {
      state.generationMinimized = false;
      renderAll();
      return;
    }
    if (action.dataset.action === "dismiss-generation") {
      state.generationReady = false;
      state.generationError = "";
      renderAll();
      return;
    }
    if (action.dataset.action === "open-ready-draft") {
      state.generationReady = false;
      renderAll();
      return;
    }
    if (action.dataset.action === "generate") await createDraft($("#draft-custom-instructions")?.value || "");
    if (action.dataset.action === "move-role") {
      moveRole(action.dataset.section, Number(action.dataset.index), Number(action.dataset.direction));
      return;
    }
    if (action.dataset.action === "add-bullet") {
      addBullet(action.dataset.section, Number(action.dataset.index));
      return;
    }
    if (action.dataset.action === "remove-bullet") {
      removeBullet(action.dataset.section, Number(action.dataset.index), Number(action.dataset.bulletIndex));
      return;
    }
    if (action.dataset.action === "add-highlight") {
      addHighlight();
      return;
    }
    if (action.dataset.action === "save") await saveDraft();
    if (action.dataset.action === "build") await buildDraft();
    if (action.dataset.action === "ready") await markReady();
  });
  document.body.addEventListener("click", (event) => {
    const close = event.target.matches("[data-modal-close]") ? event.target : null;
    if (!close || state.busy) return;
    state.showCreateModal = false;
    renderAll();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || state.busy || !state.showCreateModal) return;
    state.showCreateModal = false;
    renderAll();
  });
  function handleDraftFieldEdit(event) {
    if (!event.target.matches("[data-draft-field]")) return;
    state.draft = { ...(state.draft || {}), ...collectDraftFromForm() };
    if (event.target.dataset.draftField === "cv.variant") {
      state.draft.cv.max_pages = event.target.value === "compact_one_page" ? 1 : 2;
      renderAll();
      return;
    }
    const counter = event.target.closest(".draft-field")?.querySelector(".field-counter");
    const field = event.target.dataset.draftField;
    const limit = field === "cv.tagline" ? 170 : field === "cv.profile" ? 600 : field.includes(".bullets.") ? 165 : field.includes("selected_highlights") ? 135 : null;
    if (counter && limit) {
      const length = event.target.value.length;
      counter.textContent = `${length} / ${limit}`;
      counter.className = `field-counter ${counterClass(length, limit)}`.trim();
    }
  }
  document.body.addEventListener("input", handleDraftFieldEdit);
  document.body.addEventListener("change", handleDraftFieldEdit);
}

bindEvents();
loadDraftFromLocation().catch((error) => {
  state.message = error.message;
  renderAll();
});
