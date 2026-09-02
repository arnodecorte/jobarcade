let state = {
  raw: null,
  query: "",
  company: "",
  relevantOnly: false,
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function assessmentLabel(value) {
  if (!value) return "";
  try {
    const parsed = JSON.parse(value);
    if (parsed.included) {
      return `${parsed.fit_band || "included"} · ${parsed.score || 0}`;
    }
    return parsed.hard_fail_reason || "excluded";
  } catch {
    return value;
  }
}

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    throw new Error(`Expected JSON from ${path}, got ${contentType || "unknown content"}: ${text.slice(0, 40)}`);
  }
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function loadRawData() {
  $("#database-status").textContent = "Loading raw backend snapshot...";
  state.raw = await api("/api/raw-jobs?limit=5000");
  render();
}

function filteredRows() {
  const rows = state.raw?.rows || [];
  const query = state.query.trim().toLowerCase();
  return rows.filter((job) => {
    const matchesCompany = !state.company || job.company === state.company;
    const matchesRelevant = !state.relevantOnly || job.is_relevant;
    const haystack = [
      job.company,
      job.title,
      job.location,
      job.country,
      job.department,
      job.employment_type,
      job.source_platform,
      job.source_job_id,
    ]
      .join(" ")
      .toLowerCase();
    return matchesCompany && matchesRelevant && (!query || haystack.includes(query));
  });
}

function renderCompanyFilter() {
  const select = $("#raw-company-filter");
  const companies = (state.raw?.company_counts || []).map((item) => item.company);
  select.innerHTML = `<option value="">All companies</option>${companies
    .map((company) => `<option value="${escapeHtml(company)}">${escapeHtml(company)}</option>`)
    .join("")}`;
  if (!companies.includes(state.company)) state.company = "";
  select.value = state.company;
}

function render() {
  const summary = state.raw?.summary || {};
  const rows = filteredRows();
  renderCompanyFilter();
  $("#database-status").textContent = `Latest capture: ${formatDate(summary.latest)}. Showing ${rows.length} of ${summary.total || 0} raw rows.`;
  $("#raw-summary").innerHTML = `
    <article class="metric"><span>Raw rows</span><strong>${summary.total || 0}</strong></article>
    <article class="metric"><span>Relevant</span><strong>${summary.relevant || 0}</strong></article>
    <article class="metric"><span>Visible</span><strong>${rows.length}</strong></article>
    <article class="metric"><span>Companies</span><strong>${(state.raw?.company_counts || []).length}</strong></article>
  `;
  $("#raw-company-grid").innerHTML = (state.raw?.company_counts || [])
    .map(
      (item) => `
        <button class="raw-company-chip ${state.company === item.company ? "active" : ""}" type="button" data-company="${escapeHtml(item.company)}">
          <strong>${escapeHtml(item.company)}</strong>
          <span>${item.raw_count} raw · ${item.relevant_count || 0} relevant</span>
        </button>
      `,
    )
    .join("");
  $("#raw-jobs-table").innerHTML = rows.length
    ? rows
        .slice(0, 1000)
        .map((job) => {
          const title = job.apply_url
            ? `<a class="role-link" href="${escapeHtml(job.apply_url)}" target="_blank" rel="noreferrer">${escapeHtml(job.title)}</a>`
            : `<span class="role-link">${escapeHtml(job.title)}</span>`;
          return `
            <tr>
              <td>${job.is_relevant ? `<span class="status-pill ready">yes</span>` : ""}</td>
              <td><strong>${escapeHtml(job.company)}</strong><small>${escapeHtml(job.employment_type || "")}</small></td>
              <td>${title}<small>${escapeHtml(job.source_job_id || "")}</small></td>
              <td>${escapeHtml(job.location || job.country || "Unknown")}</td>
              <td>${escapeHtml(job.department || "")}</td>
              <td><span class="artifact-pill">${escapeHtml(assessmentLabel(job.assessment_summary))}</span></td>
              <td><span class="artifact-pill">${escapeHtml(job.source_platform || job.scraper_type || "")}</span><small>${escapeHtml(formatDate(job.captured_at))}</small></td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td colspan="7" class="empty">No raw rows match the current filters.</td></tr>`;
}

function bindEvents() {
  $("#refresh-button").addEventListener("click", loadRawData);
  $("#raw-search").addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
  });
  $("#raw-company-filter").addEventListener("change", (event) => {
    state.company = event.target.value;
    render();
  });
  $("#raw-relevant-only").addEventListener("change", (event) => {
    state.relevantOnly = event.target.checked;
    render();
  });
  $("#raw-company-grid").addEventListener("click", (event) => {
    const chip = event.target.closest(".raw-company-chip");
    if (!chip) return;
    state.company = state.company === chip.dataset.company ? "" : chip.dataset.company;
    render();
  });
}

bindEvents();
loadRawData().catch((error) => {
  $("#database-status").textContent = `Could not load raw database: ${error.message}`;
});
