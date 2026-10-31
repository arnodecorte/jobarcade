import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

type Props = {
  id: string;
  text: string;
  index: number;
  onChange: (text: string) => void;
};

export function SortableParagraphItem({ id, text, index, onChange }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} className="draft-para-row">
      <button
        type="button"
        className="drag-handle"
        aria-label={`Drag paragraph ${index + 1}`}
        {...attributes}
        {...listeners}
      >
        ⠿
      </button>
      <label className="field" style={{ flex: 1 }}>
        Paragraph {index + 1}
        <textarea rows={5} value={text} onChange={(e) => onChange(e.target.value)} />
      </label>
    </div>
  );
}
