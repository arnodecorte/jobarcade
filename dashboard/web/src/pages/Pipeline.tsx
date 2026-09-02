import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { PageProps } from "../App";
import { PageHeader } from "../components/PageHeader";
import { CompanyLogo } from "../components/CompanyLogo";
import { StatusSelect } from "../components/StatusSelect";
import { navigate, useCollapsedColumns } from "../lib/hooks";
import { PIPELINE_STATUSES, STATUS_LABELS } from "../lib/format";
import { filterAndSort } from "../lib/jobs";

export function Pipeline({ data, reload, refreshing }: PageProps) {
  const [showStretch, setShowStretch] = useState(false);
  const [collapsed, toggleCollapsed] = useCollapsedColumns();
  const jobs = filterAndSort(data.jobs, { query: "", status: "", showStretch });

  return (
    <>
      <PageHeader
        kicker="Move it forward"
        title="Pipeline"
        sub="Drag each role from discovered to applied. Advancing a card logs a pull."
        onRefresh={reload}
        refreshing={refreshing}
      />

      <div className="toolbar">
        <label className="check">
          <input type="checkbox" checked={showStretch} onChange={(e) => setShowStretch(e.target.checked)} />
          Show stretch roles
        </label>
      </div>

      <div className="kanban">
        {PIPELINE_STATUSES.map((status) => {
          const colJobs = jobs.filter((j) => j.status === status);
          const isCollapsed = collapsed.has(status);
          return (
            <section key={status} className={`col ${status} ${isCollapsed ? "is-collapsed" : ""}`}>
              <header>
                <button
                  type="button"
                  className="col-collapse-toggle"
                  onClick={() => toggleCollapsed(status)}
                  aria-label={isCollapsed ? `Expand ${STATUS_LABELS[status]}` : `Collapse ${STATUS_LABELS[status]}`}
                  aria-expanded={!isCollapsed}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                </button>
                <h3
                  className="col-title-link"
                  role="button"
                  tabIndex={0}
                  title={`Jump to ${STATUS_LABELS[status]} on the Jobs board`}
                  onClick={() => navigate("jobs", status)}
                  onKeyDown={(e) => e.key === "Enter" && navigate("jobs", status)}
                >
                  {STATUS_LABELS[status]}
                </h3>
                <span className="count-pill">{colJobs.length}</span>
              </header>
              {!isCollapsed && (
                colJobs.length ? (
                  <AnimatePresence mode="popLayout" initial={false}>
                    {colJobs.map((job, i) => (
                      <motion.div
                        key={job.id}
                        className="kard"
                        layout
                        initial={{ opacity: 0, y: -10 }}
                        animate={{
                          opacity: 1,
                          y: 0,
                          transition: { delay: i * 0.05, type: "spring", stiffness: 320, damping: 28 },
                        }}
                        exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.12 } }}
                      >
                        <CompanyLogo company={job.company} domain={job.company_logo_domain} url={job.company_logo_url} size="sm" />
                        <div className="meta">
                          <strong>{job.title}</strong>
                          <small>{job.company}</small>
                          <div style={{ marginTop: 6 }}>
                            <StatusSelect jobId={job.id} status={job.status} onChanged={reload} />
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                ) : (
                  <p className="col-empty">No roles yet</p>
                )
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
