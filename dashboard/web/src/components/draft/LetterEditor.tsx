import { uuid } from "../../lib/uuid";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import type { DraftLimits } from "../../lib/api";
import { SortableParagraphItem } from "./SortableParagraphItem";

export type LetterState = {
  subtitle: string;
  paragraphs: Array<{ id: string; text: string }>;
};

function charClass(len: number, limit: number) {
  if (len > limit) return "counter-error";
  if (len > Math.floor(limit * 0.9)) return "counter-warn";
  return "";
}

type Props = { letter: LetterState; limits: DraftLimits; onChange: (letter: LetterState) => void };

export function LetterEditor({ letter, limits, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const bodyLen = letter.paragraphs.reduce((s, p) => s + p.text.length, 0);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = letter.paragraphs.findIndex((p) => p.id === active.id);
      const newIndex = letter.paragraphs.findIndex((p) => p.id === over.id);
      onChange({ ...letter, paragraphs: arrayMove(letter.paragraphs, oldIndex, newIndex) });
    }
  }

  function updatePara(id: string, text: string) {
    onChange({
      ...letter,
      paragraphs: letter.paragraphs.map((p) => (p.id === id ? { ...p, text } : p)),
    });
  }

  function addParagraph() {
    if (letter.paragraphs.length >= 5) return;
    onChange({
      ...letter,
      paragraphs: [...letter.paragraphs, { id: uuid(), text: "" }],
    });
  }

  function removeParagraph(id: string) {
    onChange({ ...letter, paragraphs: letter.paragraphs.filter((p) => p.id !== id) });
  }

  return (
    <div className="draft-editor">
      <label className="field">
        Subtitle
        <input
          type="text"
          value={letter.subtitle}
          onChange={(e) => onChange({ ...letter, subtitle: e.target.value })}
        />
      </label>

      <div className="draft-limit-row">
        <span>
          {letter.paragraphs.length} paragraph{letter.paragraphs.length !== 1 ? "s" : ""}
        </span>
        <span className={`field-counter ${charClass(bodyLen, limits.letter_body)}`}>
          {bodyLen} / {limits.letter_body} total chars
        </span>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext
          items={letter.paragraphs.map((p) => p.id)}
          strategy={verticalListSortingStrategy}
        >
          {letter.paragraphs.map((p, i) => (
            <div key={p.id} className="draft-para-wrapper">
              <SortableParagraphItem
                id={p.id}
                text={p.text}
                index={i}
                onChange={(text) => updatePara(p.id, text)}
              />
              <button
                type="button"
                className="draft-remove para-remove"
                onClick={() => removeParagraph(p.id)}
                aria-label={`Remove paragraph ${i + 1}`}
              >
                ×
              </button>
            </div>
          ))}
        </SortableContext>
      </DndContext>

      {letter.paragraphs.length < 5 && (
        <button type="button" className="btn ghost sm" onClick={addParagraph}>
          + Add paragraph
        </button>
      )}
    </div>
  );
}
