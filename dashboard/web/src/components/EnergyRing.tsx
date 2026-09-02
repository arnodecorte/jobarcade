import { motion } from "framer-motion";

type Props = { value: number; goal: number };

export function EnergyRing({ value, goal }: Props) {
  const r = 54; // leaves room for the thicker stroke without crowding the 132px ring
  const strokeWidth = 12; // thicker, more confident arc
  const c = 2 * Math.PI * r;
  const pct = goal > 0 ? Math.min(1, value / goal) : 0;
  const done = goal > 0 && value >= goal;

  return (
    <motion.div
      className="ring"
      animate={done ? { scale: [1, 1.06, 1] } : { scale: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 15 }}
    >
      <svg width="132" height="132" viewBox="0 0 132 132">
        <circle cx="66" cy="66" r={r} fill="none" stroke="var(--bg-2)" strokeWidth={strokeWidth} opacity={0.6} />
        <motion.circle
          cx="66"
          cy="66"
          r={r}
          fill="none"
          stroke={done ? "var(--mint-deep)" : "var(--rose-deep)"}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ duration: 0.9, ease: [0.4, 0, 0.2, 1] }}
        />
      </svg>
      {/* Single source of truth for "done" copy lives beside the ring, not duplicated in here. */}
      <span className="ring-center">
        <motion.b key={value} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
          {value}
        </motion.b>
        <small>of {goal} today</small>
      </span>
    </motion.div>
  );
}
