import type { DraftLimits } from "../../lib/api";
import type { SortableRole } from "./SortableRoleBlock";
import { SortableRoleList } from "./SortableRoleList";
import { uuid } from "../../lib/uuid";

export type CvState = {
  max_pages: number;
  variant: "grotesk_one_page" | "compact_one_page" | "classic_two_page" | "enriched_two_page";
  role_focus: "marketing" | "content" | "brand" | "community" | "commercial_ops" | "";
  title: string;
  tagline: string;
  profile: string;
  selected_highlights: string[];
  experience: SortableRole[];
  additional: SortableRole[];
};

function charClass(len: number, limit: number) {
  if (len > limit) return "counter-error";
  if (len > Math.floor(limit * 0.9)) return "counter-warn";
  return "";
}

function addBlankRole(list: SortableRole[]): SortableRole[] {
  return [
    ...list,
    { id: uuid(), role: "", company: "", period: "", location: "", include: true, bullets: [] },
  ];
}

type Props = { cv: CvState; limits: DraftLimits; onChange: (cv: CvState) => void };

export function CVEditor({ cv, limits, onChange }: Props) {
  const tagLen = cv.tagline.length;
  const profLen = cv.profile.length;

  return (
    <div className="draft-editor">
      <label className="field">
        Target title
        <input
          type="text"
          value={cv.title}
          onChange={(e) => onChange({ ...cv, title: e.target.value })}
        />
      </label>

      <label className="field">
        Tagline
        <textarea
          rows={3}
          value={cv.tagline}
          onChange={(e) => onChange({ ...cv, tagline: e.target.value })}
        />
        <span className={`field-counter ${charClass(tagLen, limits.tagline)}`}>
          {tagLen} / {limits.tagline}
        </span>
      </label>

      <label className="field">
        Profile
        <textarea
          rows={5}
          value={cv.profile}
          onChange={(e) => onChange({ ...cv, profile: e.target.value })}
        />
        <span className={`field-counter ${charClass(profLen, limits.profile)}`}>
          {profLen} / {limits.profile}
        </span>
      </label>

      <div className="draft-section-header">
        <h3>Experience</h3>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => onChange({ ...cv, experience: addBlankRole(cv.experience) })}
        >
          + Add role
        </button>
      </div>
      <SortableRoleList
        roles={cv.experience}
        bulletLimit={limits.bullet}
        onChange={(experience) => onChange({ ...cv, experience })}
      />

      <div className="draft-section-header">
        <h3>Additional Experience</h3>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => onChange({ ...cv, additional: addBlankRole(cv.additional) })}
        >
          + Add role
        </button>
      </div>
      <SortableRoleList
        roles={cv.additional}
        bulletLimit={limits.bullet}
        onChange={(additional) => onChange({ ...cv, additional })}
      />
    </div>
  );
}
