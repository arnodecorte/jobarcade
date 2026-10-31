import { AddJobButton } from "./AddJobButton";

type Props = {
  kicker: string;
  title: string;
  sub?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
};

export function PageHeader({ kicker, title, sub, onRefresh, refreshing }: Props) {
  return (
    <header className="topbar">
      <div>
        <div className="kicker">{kicker}</div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {onRefresh && (
        <div className="topbar-actions">
          <AddJobButton onAdded={onRefresh} />
          <button className="btn ghost sm" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "Syncing…" : "↻ Refresh"}
          </button>
        </div>
      )}
    </header>
  );
}
