import { useEffect, useState } from "react";
import { getProfile, saveProfile } from "../../lib/api";
import type { ProfileDoc } from "../../lib/api";
import { linesToList } from "../../lib/onboarding";
import { StepFooter, StepHead } from "./StepFooter";
import type { StepProps } from "./types";

const join = (list?: string[]) => (list || []).join("\n");

export function ProfileStep({ onboarding, onBack, onSkip, onContinue, reload }: StepProps) {
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(onboarding.profile_error || "");
  const [f, setF] = useState({
    name: "", tagline: "", email: "", phone: "", location: "", linkedin: "", portfolio: "",
    facts: "", skills: "", roles: "", locations: "", remote: true,
    adjacent: "", excluded: "", maxYears: "", senior: false, internships: false, patterns: "",
  });
  const [linkedinUrl, setLinkedinUrl] = useState<string | undefined>();
  const [portfolioUrl, setPortfolioUrl] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getProfile()
      .then((p: ProfileDoc) => {
        if (!alive) return;
        const c = p.candidate || {};
        const k = c.contact || {};
        const t = p.target_preferences || {};
        setF({
          name: c.name || "", tagline: c.tagline || "", email: k.email || "", phone: k.phone || "",
          location: k.location || "", linkedin: k.linkedin || "", portfolio: k.portfolio || "",
          facts: c.career_facts || "", skills: join(c.skills), roles: join(t.target_roles),
          locations: join(t.target_locations), remote: t.allow_remote ?? true,
          adjacent: join(t.adjacent_roles), excluded: join(t.excluded_functions),
          maxYears: t.max_years_experience == null ? "" : String(t.max_years_experience),
          senior: t.exclude_senior_titles ?? false, internships: t.exclude_internships ?? false,
          patterns: join(t.excluded_language_patterns),
        });
        setLinkedinUrl(k.linkedin_url);
        setPortfolioUrl(k.portfolio_url);
        setLoaded(true);
      })
      .catch((err) => alive && setLoadError((err as Error).message));
    return () => {
      alive = false;
    };
  }, []);

  const set = <K extends keyof typeof f>(key: K, value: (typeof f)[K]) => {
    if (key === "linkedin") setLinkedinUrl("");
    if (key === "portfolio") setPortfolioUrl("");
    setF((prev) => ({ ...prev, [key]: value }));
  };

  async function save() {
    setSaving(true);
    setError("");
    try {
      const years = f.maxYears.trim();
      if (years && !/^\d+$/.test(years)) throw new Error("Max years of experience should be a whole number, or leave it empty.");
      await saveProfile({
        candidate: {
          name: f.name, tagline: f.tagline, career_facts: f.facts, skills: linesToList(f.skills),
          contact: {
            email: f.email, phone: f.phone, location: f.location,
            linkedin: f.linkedin, portfolio: f.portfolio,
            ...(linkedinUrl !== undefined ? { linkedin_url: linkedinUrl } : {}),
            ...(portfolioUrl !== undefined ? { portfolio_url: portfolioUrl } : {}),
          },
        },
        target_preferences: {
          target_roles: linesToList(f.roles), target_locations: linesToList(f.locations), allow_remote: f.remote,
          adjacent_roles: linesToList(f.adjacent), excluded_functions: linesToList(f.excluded),
          max_years_experience: years ? Number(years) : null,
          exclude_senior_titles: f.senior, exclude_internships: f.internships,
          excluded_language_patterns: linesToList(f.patterns),
        },
      });
      reload();
      await onContinue();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <StepHead
        kicker="Step 2 · About you"
        title="Tell JobArcade who you are"
        sub="This stays in config/profile.yaml on your machine. The AI only ever writes from the facts you give it here, so the more accurate this is, the better your drafts."
      />
      {loadError ? (
        <div className="ob-callout" role="alert">
          <strong>Your profile file needs a look</strong>
          <span className="ob-callout-detail">{loadError}</span>
          <span>Fix config/profile.yaml by hand and reload, or skip this step for now. Nothing will be overwritten.</span>
        </div>
      ) : (
        <div className="ob-body">
          <div className="ob-grid2">
            <label className="field">Name<input value={f.name} onChange={(e) => set("name", e.target.value)} autoComplete="name" /></label>
            <label className="field">Tagline<input value={f.tagline} onChange={(e) => set("tagline", e.target.value)} placeholder="One line on what you do best" /></label>
            <label className="field">Email<input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} autoComplete="email" /></label>
            <label className="field">Phone<input value={f.phone} onChange={(e) => set("phone", e.target.value)} autoComplete="tel" /></label>
            <label className="field">Location<input value={f.location} onChange={(e) => set("location", e.target.value)} placeholder="City, Country" /></label>
            <label className="field">LinkedIn<input value={f.linkedin} onChange={(e) => set("linkedin", e.target.value)} placeholder="linkedin.com/in/you" /></label>
            <label className="field">Portfolio<input value={f.portfolio} onChange={(e) => set("portfolio", e.target.value)} placeholder="yoursite.com" /></label>
          </div>
          <label className="field">
            Career facts
            <textarea rows={6} value={f.facts} onChange={(e) => set("facts", e.target.value)} placeholder="Roles, employers, dates, results. Only true facts, the AI will not invent beyond these." />
          </label>
          <div className="ob-grid2">
            <label className="field">Skills<textarea rows={3} value={f.skills} onChange={(e) => set("skills", e.target.value)} placeholder="Comma or one per line" /></label>
            <label className="field">Target roles<textarea rows={3} value={f.roles} onChange={(e) => set("roles", e.target.value)} placeholder="e.g. Product Marketing Manager" /></label>
            <label className="field">Accepted locations<textarea rows={3} value={f.locations} onChange={(e) => set("locations", e.target.value)} placeholder="e.g. Amsterdam, Utrecht" /></label>
            <label className="ob-check"><input type="checkbox" checked={f.remote} onChange={(e) => set("remote", e.target.checked)} /> Open to remote</label>
          </div>
          <details className="ob-advanced">
            <summary>Advanced filters</summary>
            <div className="ob-grid2">
              <label className="field">Adjacent roles<textarea rows={3} value={f.adjacent} onChange={(e) => set("adjacent", e.target.value)} /></label>
              <label className="field">Excluded functions<textarea rows={3} value={f.excluded} onChange={(e) => set("excluded", e.target.value)} /></label>
              <label className="field">Max years of experience<input inputMode="numeric" value={f.maxYears} onChange={(e) => set("maxYears", e.target.value)} placeholder="No limit" /></label>
              <label className="field">Language patterns to exclude<textarea rows={3} value={f.patterns} onChange={(e) => set("patterns", e.target.value)} /></label>
              <label className="ob-check"><input type="checkbox" checked={f.senior} onChange={(e) => set("senior", e.target.checked)} /> Exclude senior titles</label>
              <label className="ob-check"><input type="checkbox" checked={f.internships} onChange={(e) => set("internships", e.target.checked)} /> Exclude internships</label>
            </div>
          </details>
          <p className="ob-note">
            Education, languages, certifications and an optional signature image for your letters live in
            config/profile.yaml. Add them there whenever you like; they show up on every CV and letter you build.
          </p>
          {error && <p className="ob-error" role="alert">{error}</p>}
        </div>
      )}
      <StepFooter onBack={onBack} onSkip={onSkip} onContinue={save} busy={saving} continueDisabled={!loaded || !!loadError} />
    </>
  );
}
