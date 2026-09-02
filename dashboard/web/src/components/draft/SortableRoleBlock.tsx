import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { SortableBulletList } from "./SortableBulletList";
import { uuid } from "../../lib/uuid";

export type SortableRole = {
  id: string;
  role: string;
  company: string;
  period: string;
  location: string;
  include: boolean;
  bullets: Array<{ id: string; text: string }>;
};

type Props = {
  id: string;
  roleData: SortableRole;
  bulletLimit: number;
  onChange: (role: SortableRole) => void;
  onRemove: () => void;
};

export function SortableRoleBlock({ id, roleData, bulletLimit, onChange, onRemove }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  function updateField(key: keyof Omit<SortableRole, "id" | "bullets">, value: string) {
    onChange({ ...roleData, [key]: value });
  }

  function addBullet() {
    if (roleData.bullets.length >= 5) return;
    onChange({
      ...roleData,
      bullets: [...roleData.bullets, { id: uuid(), text: "" }],
    });
  }

  return (
    <div ref={setNodeRef} style={style} className="draft-role-card">
      <div className="draft-role-card-header">
        <button
          type="button"
          className="drag-handle role-drag"
          aria-label="Drag to reorder role"
          {...attributes}
          {...listeners}
        >
          ⠿
        </button>
        <span className="draft-role-label">
          {roleData.role || "Untitled role"} · {roleData.company || "—"}
        </span>
        <label className="draft-include-mini">
          <input
            type="checkbox"
            checked={roleData.include}
            onChange={(e) => onChange({ ...roleData, include: e.target.checked })}
          />
          Include
        </label>
        <button type="button" className="draft-remove" onClick={onRemove} aria-label="Remove role">
          ×
        </button>
      </div>
      <div className="draft-role-grid">
        {(["role", "company", "period", "location"] as const).map((key) => (
          <label key={key} className="field">
            {key.charAt(0).toUpperCase() + key.slice(1)}
            <input
              type="text"
              value={roleData[key]}
              onChange={(e) => updateField(key, e.target.value)}
            />
          </label>
        ))}
      </div>
      <SortableBulletList
        bullets={roleData.bullets}
        limit={bulletLimit}
        onChange={(bullets) => onChange({ ...roleData, bullets })}
      />
      {roleData.bullets.length < 5 && (
        <button type="button" className="btn ghost sm draft-add-bullet" onClick={addBullet}>
          + Add bullet
        </button>
      )}
    </div>
  );
}
