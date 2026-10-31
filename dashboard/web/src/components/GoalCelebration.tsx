import { useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Dice } from "./Sprite";
import { formatEta } from "../lib/odds";
import type { Celebration } from "../lib/odds";

type Props = { goal: number; stats: Celebration; onDismiss: () => void };

const pct = (x: number) => Math.round(x * 100);

export function GoalCelebration({ goal, stats, onDismiss }: Props) {
  const reduce = useReducedMotion();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDismiss]);
  return (
    <motion.div
      className="celebrate-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onDismiss}
    >
      <motion.div
        className="celebrate-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="celebrate-title"
        onClick={(e) => e.stopPropagation()}
        initial={reduce ? { opacity: 0 } : { opacity: 0, y: 30, scale: 0.92 }}
        animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 22 }}
      >
        <div className="celebrate-mascot">
          <Dice size="lg" state="wave" />
        </div>
        <h2 id="celebrate-title">Goal hit — {goal} rolls today!</h2>
        <p>
          Your odds of at least one interview went from <strong>{pct(stats.probBefore)}%</strong> to{" "}
          <strong>{pct(stats.probAfter)}%</strong>.
        </p>
        <p className="celebrate-sub">
          At this pace that's about {formatEta(stats.etaDays)} to your first expected interview —{" "}
          {stats.daysSaved.toFixed(1)} days closer than this morning.
        </p>
        <button type="button" className="celebrate-btn" autoFocus onClick={onDismiss}>
          Keep rolling
        </button>
      </motion.div>
    </motion.div>
  );
}
