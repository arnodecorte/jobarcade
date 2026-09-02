import type { Stats } from "../lib/api";

function heatLevel(count: number): string {
  if (count <= 0) return "";
  if (count === 1) return "l1";
  if (count === 2) return "l2";
  if (count === 3) return "l3";
  return "l4";
}

function last90(daily: Stats["daily"]): number[] {
  const byDate = new Map(daily.map((d) => [d.date, d.count]));
  const out: number[] = [];
  const today = new Date();
  for (let i = 89; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    out.push(byDate.get(d.toISOString().slice(0, 10)) ?? 0);
  }
  return out;
}

export function StreakRail({ stats }: { stats: Stats }) {
  const cells = last90(stats.daily);
  const badges = [
    { label: "First pull", earned: stats.applications_sent >= 1 },
    { label: "10 sent", earned: stats.applications_sent >= 10 },
    { label: "25 sent", earned: stats.applications_sent >= 25 },
    { label: "1 expected interview · 50", earned: stats.applications_sent >= 50 },
    { label: "3-day streak", earned: stats.best_streak >= 3 },
    { label: "7-day streak", earned: stats.best_streak >= 7 },
  ];

  return (
    <div className="rail">
      <div className="rail-tile">
        <div className="rail-num">
          <span className="flame">🔥</span>
          {stats.current_streak}
        </div>
        <div className="rail-cap">day streak · best {stats.best_streak}</div>
      </div>
      <div className="rail-tile">
        <div className="rail-num">{stats.applications_sent}</div>
        <div className="rail-cap">total submitted outcomes</div>
      </div>
      <div className="rail-tile">
        <div className="rail-cap" style={{ marginBottom: 8 }}>last 90 days</div>
        <div className="heat">
          {cells.map((count, i) => (
            <i key={i} className={heatLevel(count)} title={count ? `${count} applied` : "no applications"} />
          ))}
        </div>
      </div>
      <div className="rail-tile">
        <div className="rail-cap" style={{ marginBottom: 10 }}>milestones</div>
        <div className="badges">
          {badges.map((b) => (
            <span key={b.label} className={`badge ${b.earned ? "earned" : ""}`}>
              {b.earned ? "★" : "☆"} {b.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
