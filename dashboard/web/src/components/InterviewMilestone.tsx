import { AnimatePresence, motion } from "framer-motion";
import type { Job } from "../lib/api";
import { useSeenInterviewIds } from "../lib/hooks";

const MILESTONE_STATUSES = new Set(["interviewing", "offer"]);

/** The odds engine otherwise folds a new interview silently into the aggregate rate —
    this is the one moment that calls it out before it disappears into the curve. */
export function InterviewMilestone({ jobs }: { jobs: Job[] }) {
  const [seen, markSeen] = useSeenInterviewIds();
  const fresh = jobs.filter((job) => MILESTONE_STATUSES.has(job.status) && !seen.has(job.id));

  return (
    <AnimatePresence initial={false}>
      {fresh.map((job) => (
        <motion.div
          key={job.id}
          className="milestone-banner"
          initial={{ opacity: 0, y: -8, height: 0, marginBottom: 0 }}
          animate={{ opacity: 1, y: 0, height: "auto", marginBottom: 16 }}
          exit={{ opacity: 0, height: 0, marginBottom: 0 }}
        >
          <span className="milestone-emoji" aria-hidden="true">🎉</span>
          <span className="milestone-text">
            <b>{job.company}</b> moved {job.title} to{" "}
            <b>{job.status === "offer" ? "Offer" : "Interviewing"}</b> — the deck's already paying off. On to the next stage.
          </span>
          <button
            type="button"
            className="milestone-dismiss"
            onClick={() => markSeen(job.id)}
            aria-label={`Dismiss ${job.company} milestone`}
          >
            ✕
          </button>
        </motion.div>
      ))}
    </AnimatePresence>
  );
}
