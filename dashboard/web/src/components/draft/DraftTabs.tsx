export type TabKey = "builder" | "cv" | "letter" | "listing" | "preview";

const TABS: { key: TabKey; label: string }[] = [
  { key: "builder", label: "Builder" },
  { key: "cv", label: "CV" },
  { key: "letter", label: "Letter" },
  { key: "listing", label: "Listing" },
  { key: "preview", label: "Preview" },
];

type Props = { active: TabKey; onChange: (tab: TabKey) => void };

export function DraftTabs({ active, onChange }: Props) {
  return (
    <div className="draft-tabs" role="tablist">
      {TABS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          role="tab"
          aria-selected={active === key}
          className={active === key ? "active" : ""}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
