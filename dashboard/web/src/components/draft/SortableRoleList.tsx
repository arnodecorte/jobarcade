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
import { SortableRoleBlock, type SortableRole } from "./SortableRoleBlock";

type Props = {
  roles: SortableRole[];
  bulletLimit: number;
  onChange: (roles: SortableRole[]) => void;
};

export function SortableRoleList({ roles, bulletLimit, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = roles.findIndex((r) => r.id === active.id);
      const newIndex = roles.findIndex((r) => r.id === over.id);
      onChange(arrayMove(roles, oldIndex, newIndex));
    }
  }

  function updateRole(id: string, updated: SortableRole) {
    onChange(roles.map((r) => (r.id === id ? updated : r)));
  }

  function removeRole(id: string) {
    onChange(roles.filter((r) => r.id !== id));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={roles.map((r) => r.id)} strategy={verticalListSortingStrategy}>
        {roles.map((r) => (
          <SortableRoleBlock
            key={r.id}
            id={r.id}
            roleData={r}
            bulletLimit={bulletLimit}
            onChange={(updated) => updateRole(r.id, updated)}
            onRemove={() => removeRole(r.id)}
          />
        ))}
      </SortableContext>
    </DndContext>
  );
}
