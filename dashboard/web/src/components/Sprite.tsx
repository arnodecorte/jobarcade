export type SpriteState =
  | "walk"
  | "trot"
  | "sit"
  | "wave"
  | "type"
  | "gesture"
  | "focus"
  | "work"
  | "read";

export function Angie({
  size = "md",
  state = "walk",
}: {
  size?: "sm" | "md" | "lg";
  state?: SpriteState;
}) {
  return <div className={`angie ${size} state-${state}`} aria-hidden="true" />;
}

export function Loading({ message = "Loading your hunt…" }: { message?: string }) {
  return (
    <div className="loading-screen" role="status" aria-live="polite">
      <Angie size="lg" state="work" />
      <p>{message}</p>
    </div>
  );
}
