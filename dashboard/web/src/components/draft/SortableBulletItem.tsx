import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

type Props = {
  id: string;
  text: string;
  limit: number;
  onChange: (text: string) => void;
  onRemove: () => void;
};

function charClass(len: number, limit: number) {
  if (len > limit) return "counter-error";
  if (len > Math.floor(limit * 0.9)) return "counter-warn";
  return "";
}

export function SortableBulletItem({ id, text, limit, onChange, onRemove }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  const len = text.length;
  return (
    <div ref={setNodeRef} style={style} className="draft-bullet-row">
      <button
        type="button"
        className="drag-handle"
        aria-label="Drag to reorder bullet"
        {...attributes}
        {...listeners}
      >
        ⠿
      </button>
      <div className="draft-bullet-body">
        <textarea
          rows={2}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          className="draft-bullet-textarea"
        />
        <span className={`field-counter ${charClass(len, limit)}`}>
          {len} / {limit}
        </span>
      </div>
      <button type="button" className="draft-remove" onClick={onRemove} aria-label="Remove bullet">
        ×
      </button>
    </div>
  );
}
