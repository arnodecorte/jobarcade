import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { PageProps } from "../App";
import { PageHeader } from "../components/PageHeader";
import { JobRow } from "../components/JobRow";
import { useHashParam } from "../lib/hooks";
import { EDITABLE_STATUSES, STATUS_LABELS } from "../lib/format";
import { filterAndSort } from "../lib/jobs";
import { listContainer, listItem } from "../lib/motion";

export function Jobs({ data, reload, refreshing }: PageProps) {
  const hashParam = useHashParam();
  const jobMatch = hashParam.match(/^job-(\d+)$/);
  const selectedJobId = jobMatch ? jobMatch[1] : null;
  const hashStatus = jobMatch ? "" : hashParam;

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState(hashStatus);
  const [showStretch, setShowStretch] = useState(false);

  // Lets Pipeline/Today's status links (e.g. "#/jobs/applied") jump straight
  // into a filtered view, even when Jobs is already mounted.
  useEffect(() => {
    if (hashStatus) setStatus(hashStatus);
  }, [hashStatus]);

  const rows = useMemo(
    () => filterAndSort(data.jobs, { query, status, showStretch }),
    [data.jobs, query, status, showStretch],
  );

  // Deep link to a specific job (e.g. from Today's "Apply today" cards): if
  // the current filters hide it, clear them so it becomes visible, then
  // scroll it into view and highlight it.
  useEffect(() => {
    if (!selectedJobId) return;
    const visible = rows.some((r) => String(r.id) === selectedJobId);
    if (!visible) {
      setStatus("");
      setQuery("");
      setShowStretch(true);
      return;
    }
    document.getElementById(`job-${selectedJobId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedJobId, rows]);

  return (
    <>
      <PageHeader
        kicker="The full board"
        title="Jobs"
        sub={`${rows.length} of ${data.jobs.length} roles shown`}
        onRefresh={reload}
        refreshing={refreshing}
      />

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search company, role, location…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {EDITABLE_STATUSES.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={showStretch} onChange={(e) => setShowStretch(e.target.checked)} />
          Show stretch
        </label>
      </div>

      {rows.length ? (
        <motion.div className="job-list" variants={listContainer} initial="hidden" animate="show">
          <AnimatePresence mode="popLayout" initial={false}>
            {rows.map((job) => (
              <motion.div
                key={job.id}
                className="job-list-item"
                variants={listItem}
                exit="exit"
                layout="position"
              >
                <JobRow job={job} onChanged={reload} selected={String(job.id) === selectedJobId} />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      ) : (
        <p className="empty">No jobs match the current filters.</p>
      )}
    </>
  );
}
