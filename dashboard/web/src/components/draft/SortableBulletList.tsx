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
import { SortableBulletItem } from "./SortableBulletItem";

type Bullet = { id: string; text: string };

type Props = {
  bullets: Bullet[];
  limit: number;
  onChange: (bullets: Bullet[]) => void;
};

export function SortableBulletList({ bullets, limit, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = bullets.findIndex((b) => b.id === active.id);
      const newIndex = bullets.findIndex((b) => b.id === over.id);
      onChange(arrayMove(bullets, oldIndex, newIndex));
    }
  }

  function updateBullet(id: string, text: string) {
    onChange(bullets.map((b) => (b.id === id ? { ...b, text } : b)));
  }

  function removeBullet(id: string) {
    onChange(bullets.filter((b) => b.id !== id));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={bullets.map((b) => b.id)} strategy={verticalListSortingStrategy}>
        {bullets.map((b) => (
          <SortableBulletItem
            key={b.id}
            id={b.id}
            text={b.text}
            limit={limit}
            onChange={(text) => updateBullet(b.id, text)}
            onRemove={() => removeBullet(b.id)}
          />
        ))}
      </SortableContext>
    </DndContext>
  );
}
