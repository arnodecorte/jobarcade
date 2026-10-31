/* Living backdrop: four soft pastel blobs (theme tokens) drift on seamless
   loops behind the whole app, with a faint film-grain overlay on top so the
   gradient never looks flat or banded. Fixed, inert, and reduced-motion aware
   (animations freeze via CSS). Renders behind everything at z-index -1. */
export function Grainient() {
  return (
    <div className="grainient" aria-hidden="true">
      <span className="grainient-blob b1" />
      <span className="grainient-blob b2" />
      <span className="grainient-blob b3" />
      <span className="grainient-blob b4" />
      <span className="grainient-grain" />
    </div>
  );
}
