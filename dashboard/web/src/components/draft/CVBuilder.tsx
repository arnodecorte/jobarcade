import { useEffect, useState } from "react";
import type { BrandSource, BrandThemeState, CvReview, DraftLimits } from "../../lib/api";
import type { CvState } from "./CVEditor";
import { ChameleonMascotAnimation } from "./ChameleonMascotAnimation";
import { SortableRoleList } from "./SortableRoleList";
import type { SortableRole } from "./SortableRoleBlock";

type Props = {
  cv: CvState;
  limits: DraftLimits;
  review: CvReview;
  brandTheme: BrandThemeState;
  brandSource: BrandSource;
  busy: boolean;
  brandBusy: boolean;
  onExtractBrandTheme: () => void;
  onResetBrandTheme: () => void;
  onSetBrandThemeMode: (mode: "light" | "dark") => void;
  onSetBrandTypography: (enabled: boolean) => void;
  onSetBrandUrl: (brandUrl: string) => void;
  onChange: (cv: CvState) => void;
};

const variantLabels: Record<CvState["variant"], string> = {
  grotesk_one_page: "Grotesk 1-page",
  compact_one_page: "Compact 1-page",
  classic_two_page: "Classic 2-page",
  enriched_two_page: "Enriched 2-page",
};

const focusLabels: Record<Exclude<CvState["role_focus"], "">, string> = {
  marketing: "Marketing",
  content: "Content",
  brand: "Brand",
  community: "Community",
  commercial_ops: "Commercial / Ops",
};

function isVictoryArt(role: SortableRole): boolean {
  const roleKey = `${role.role} ${role.company}`.toLowerCase();
  return roleKey.includes("victory art") || roleKey.includes("curatorial");
}

function providerLabel(provider?: string): string {
  if (provider === "firecrawl") return "Firecrawl source";
  if (provider === "firecrawl-demo") return "Firecrawl demo";
  if (provider === "local") return "Local source";
  return provider ? `${provider} source` : "";
}

export function CVBuilder({
  cv,
  limits,
  review,
  brandTheme,
  brandSource,
  busy,
  brandBusy,
  onExtractBrandTheme,
  onResetBrandTheme,
  onSetBrandThemeMode,
  onSetBrandTypography,
  onSetBrandUrl,
  onChange,
}: Props) {
  const experienceRoles = [...cv.experience, ...cv.additional];
  const victoryRole = experienceRoles.find(isVictoryArt);
  const victoryMissing = !victoryRole;
  const victoryExcluded = Boolean(victoryRole && !victoryRole.include);
  const [brandUrlDraft, setBrandUrlDraft] = useState(brandSource.url || "");
  const theme = brandTheme.theme;
  const chameleonDisabled = busy || brandBusy;
  const darkMode = theme?.mode === "dark";
  const darkRecommended = Boolean(
    theme?.dark_recommended || /dark|black|cinematic/i.test(`${theme?.energy || ""} ${theme?.tone || ""}`)
  );
  const typographyResolution = theme?.typography_resolution;
  // Legacy themes have a flat {source, family, notes, ...} shape; current
  // themes nest a distinct resolution per role — fall back to the flat
  // object itself so older brand-theme.yaml files keep displaying correctly.
  const bodyResolution = typographyResolution?.body ?? typographyResolution;
  const headingResolution = typographyResolution?.heading ?? typographyResolution;
  const typographyNotes = [
    ...(bodyResolution?.notes || []),
    ...(bodyResolution?.warnings || []),
    ...(headingResolution?.notes || []),
    ...(headingResolution?.warnings || []),
  ];
  const swatches = theme
    ? [
        ["Accent", theme.accent],
        ...(theme.page_bg ? ([["Page", theme.page_bg]] as string[][]) : []),
        ["Header", theme.soft_bg],
        ["Rule", theme.rule],
        ["Link", theme.link],
      ]
    : [];
  useEffect(() => {
    setBrandUrlDraft(brandSource.url || "");
  }, [brandSource.url]);

  return (
    <div className="cv-builder">
      <div className="builder-main">
        <section className="builder-panel">
          <h3>CV Strategy</h3>
          <div className="builder-control-grid">
            <label className="field">
              Presentation
              <select
                aria-label="CV variant"
                value={cv.variant}
                onChange={(e) => {
                  const variant = e.target.value as CvState["variant"];
                  onChange({
                    ...cv,
                    variant,
                    max_pages: variant === "compact_one_page" || variant === "grotesk_one_page" ? 1 : 2,
                  });
                }}
              >
                {(Object.keys(variantLabels) as CvState["variant"][]).map((variant) => (
                  <option key={variant} value={variant}>
                    {variantLabels[variant]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Role focus
              <select
                aria-label="Role focus"
                value={cv.role_focus || "marketing"}
                onChange={(e) => onChange({ ...cv, role_focus: e.target.value as CvState["role_focus"] })}
              >
                {(Object.keys(focusLabels) as Exclude<CvState["role_focus"], "">[]).map((focus) => (
                  <option key={focus} value={focus}>
                    {focusLabels[focus]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Pages
              <input
                aria-label="Page budget"
                type="number"
                min={1}
                max={2}
                value={cv.max_pages}
                onChange={(e) => onChange({ ...cv, max_pages: Number(e.target.value) })}
              />
            </label>
          </div>
          <p className="variant-hint">
            {cv.variant === "grotesk_one_page"
              ? "Recommended for marketing drafts: one page with Summary, Experience, Education, Skills, and Languages."
              : cv.variant === "compact_one_page"
                ? "Legacy compact layout with sidebar and condensed earlier experience."
                : cv.variant === "enriched_two_page"
                ? "Use when extra proof points or broader context are worth a second page."
                : "Legacy two-page layout for existing applications and compatibility checks."}
          </p>
        </section>

        <section id="chameleon-panel" className={brandBusy ? "builder-panel chameleon-panel is-brand-busy" : "builder-panel chameleon-panel"}>
          <div className="chameleon-panel-content">
            <div className="draft-section-header compact">
              <h3>Chameleon</h3>
              <span className={brandTheme.enabled ? "theme-mode on" : "theme-mode"}>{brandTheme.enabled ? "Chameleon" : "Base"}</span>
            </div>
            <p className="variant-hint">
              {brandTheme.enabled
                ? "Subtle company color resonance is selected. Build PDFs to render the themed CV and letter."
                : "Base theme is selected. Extract company branding to create an optional themed CV and letter."}
            </p>
            <div className="theme-source-form">
              <label className="field">
                Brand URL
                <input
                  type="url"
                  value={brandUrlDraft}
                  placeholder="https://company.com"
                  disabled={chameleonDisabled}
                  onChange={(e) => setBrandUrlDraft(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn ghost sm"
                disabled={chameleonDisabled || brandUrlDraft.trim() === (brandSource.url || "")}
                onClick={() => onSetBrandUrl(brandUrlDraft)}
              >
                Save Source
              </button>
            </div>
            <div className={brandSource.kind === "company_site" ? "theme-source good" : "theme-source warn"}>
              <strong>{brandSource.kind === "company_site" ? "Company site" : brandSource.kind === "careers" ? "Careers fallback" : "Brand source"}</strong>
              <span>{brandSource.reason}</span>
            </div>
            {theme && (
              <>
                <label className={darkMode ? "theme-toggle-row is-dark" : "theme-toggle-row"}>
                  <span>
                    <strong>Dark Mode</strong>
                    <small>
                      {darkRecommended
                        ? "Recommended: the brand profile leans dark."
                        : "Optional: use when a bold human-review version makes sense."}
                    </small>
                  </span>
                  <input
                    type="checkbox"
                    checked={darkMode}
                    disabled={chameleonDisabled || !brandTheme.enabled}
                    onChange={(e) => onSetBrandThemeMode(e.target.checked ? "dark" : "light")}
                    aria-label="Toggle dark Chameleon mode"
                  />
                </label>
                <label className={theme.typography_enabled ? "theme-toggle-row is-typography" : "theme-toggle-row"}>
                  <span>
                    <strong>Typography</strong>
                    <small>
                      {theme.typography_available
                        ? `Optional: use ${typographyResolution?.family || "resolved brand typography"} in the PDFs.`
                        : "No safe font match found; default CV typography stays active."}
                    </small>
                  </span>
                  <input
                    type="checkbox"
                    checked={Boolean(theme.typography_enabled)}
                    disabled={chameleonDisabled || !brandTheme.enabled || !theme.typography_available}
                    onChange={(e) => onSetBrandTypography(e.target.checked)}
                    aria-label="Toggle Chameleon typography"
                  />
                </label>
                <div className="theme-swatches" aria-label="Brand theme colors">
                  {swatches.map(([label, color]) => (
                    <span key={label} className="theme-swatch">
                      <i style={{ backgroundColor: color }} />
                      <small>{label}</small>
                      <code>{color}</code>
                    </span>
                  ))}
                </div>
                <div className="theme-meta">
                  {theme.provider && <span>{providerLabel(theme.provider)}</span>}
                  <span>Confidence {Math.round((theme.confidence || 0) * 100)}%</span>
                  {theme.source_url && (
                    <a href={theme.source_url} target="_blank" rel="noreferrer">
                      Source
                    </a>
                  )}
                </div>
                {theme.typography && (theme.typography.primary || theme.typography.heading || theme.energy || theme.tone) && (
                  <div className="theme-profile">
                    {theme.typography.primary && <span>Body: {theme.typography.primary}</span>}
                    {theme.typography.heading && <span>Headings: {theme.typography.heading}</span>}
                    {bodyResolution?.family && <span>PDF body font: {bodyResolution.family}</span>}
                    {headingResolution?.family && headingResolution.family !== bodyResolution?.family && (
                      <span>PDF heading font: {headingResolution.family}</span>
                    )}
                    {theme.energy && <span>Energy: {theme.energy}</span>}
                    {theme.tone && <span>Tone: {theme.tone}</span>}
                  </div>
                )}
                {typographyNotes.length > 0 && (
                  <ul className="theme-notes typography-notes">
                    {typographyNotes.map((note, index) => (
                      <li key={index}>{note}</li>
                    ))}
                  </ul>
                )}
                {[...(theme.notes || []), ...(brandTheme.warnings || [])].length > 0 && (
                  <ul className="theme-notes">
                    {[...(theme.notes || []), ...(brandTheme.warnings || [])].map((note, index) => (
                      <li key={index}>{note}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
            <div className="theme-actions">
              <button type="button" className="btn primary sm" disabled={chameleonDisabled} onClick={onExtractBrandTheme}>
                Extract Theme
              </button>
              <button type="button" className="btn ghost sm" disabled={chameleonDisabled || !theme} onClick={onResetBrandTheme}>
                Reset Base
              </button>
            </div>
          </div>
          {brandBusy && (
            <div className="chameleon-busy-overlay" role="status" aria-live="polite">
              <ChameleonMascotAnimation compact />
              <strong>Collecting brand cues</strong>
              <span>Sampling colors, checking typography, and caching safe fonts when available.</span>
            </div>
          )}
        </section>

        <section className="builder-panel">
          <div className="draft-section-header compact">
            <h3>Experience Order</h3>
            <span className="builder-role-count">{experienceRoles.filter((role) => role.include).length} included</span>
          </div>
          {(victoryMissing || victoryExcluded) && (
            <p className="builder-warning">
              Victory Art is mandatory for marketing Grotesk CVs. Keep it included as Curatorial & Marketing Assistant.
            </p>
          )}
          <SortableRoleList
            roles={experienceRoles}
            bulletLimit={limits.bullet}
            onChange={(experience) =>
              onChange({
                ...cv,
                experience,
                additional: [],
                selected_highlights: cv.variant === "grotesk_one_page" ? [] : cv.selected_highlights,
              })
            }
          />
        </section>
      </div>

      <aside className="builder-review">
        <div className="review-head">
          <span className="review-score">{review.score}</span>
          <strong>{review.band}</strong>
          <small>
            {review.proof_bullets} proof bullets · {review.included_roles} included roles
          </small>
        </div>
        {review.items.length > 0 ? (
          <ul>
            {review.items.map((item, index) => (
              <li key={index} className={item.level}>
                <strong>{item.title}</strong>
                <span>{item.detail}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="draft-status-msg">No major CV review flags.</p>
        )}
      </aside>
    </div>
  );
}
