import { useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { PageProps } from "../App";
import { PageHeader } from "../components/PageHeader";
import { JobRow } from "../components/JobRow";
import { formatDate } from "../lib/format";
import { freshJobs } from "../lib/jobs";
import { listContainer, listItem } from "../lib/motion";

export function Fresh({ data, reload, refreshing }: PageProps) {
  const { date, rows } = useMemo(() => freshJobs(data.jobs), [data.jobs]);

  return (
    <>
      <PageHeader
        kicker="Since the last sweep"
        title="Fresh"
        sub={
          date
            ? `${rows.length} role${rows.length === 1 ? "" : "s"} found on ${formatDate(date)}`
            : "No sweeps recorded yet"
        }
        onRefresh={reload}
        refreshing={refreshing}
      />

      {rows.length ? (
        <motion.div className="job-list" variants={listContainer} initial="hidden" animate="show">
          <AnimatePresence mode="popLayout" initial={false}>
            {rows.map((job) => (
              <motion.div key={job.id} className="job-list-item" variants={listItem} exit="exit" layout="position">
                <JobRow job={job} onChanged={reload} selected={false} />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      ) : (
        <p className="empty">No new jobs since the last sweep.</p>
      )}
    </>
  );
}
