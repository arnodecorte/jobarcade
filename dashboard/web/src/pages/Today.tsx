import { useCallback, useEffect, useState } from "react";
import { animate, AnimatePresence, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import type { PageProps } from "../App";
import { PageHeader } from "../components/PageHeader";
import { EnergyRing } from "../components/EnergyRing";
import { JobRow } from "../components/JobRow";
import { Companion } from "../components/Companion";
import { InterviewMilestone } from "../components/InterviewMilestone";
import { navigate } from "../lib/hooks";
import { needsSetupBanner } from "../lib/onboarding";
import { formatDate, OUTCOME_STATUSES, PIPELINE_STATUSES, STATUS_LABELS } from "../lib/format";
import { applyTodayQueue } from "../lib/jobs";
import { GoalCelebration } from "../components/GoalCelebration";
import { clearDemo, saveGoals } from "../lib/api";
import { localIsoDate, shouldCelebrate } from "../lib/celebrate";
import { celebrationStats, effectiveRate, etaDays, formatEta } from "../lib/odds";
import { listContainer, listItem, pill, pillsContainer, tile, tilesContainer } from "../lib/motion";

/* Counts from its previous value up to the target on every change, so a fresh
   sweep that bumps "Discovered" reads as a satisfying tick-up, not a jump. */
function CountUp({ value }: { value: number }) {
  const reduceMotion = useReducedMotion();
  const mv = useMotionValue(0); // first mount counts up from zero
  const rounded = useTransform(mv, (v) => Math.round(v).toLocaleString());
  useEffect(() => {
    if (reduceMotion) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration: 0.7, ease: "easeOut" });
    return () => controls.stop();
  }, [value, mv, reduceMotion]);
  return <motion.span>{rounded}</motion.span>;
}

export function Today({ data, reload, refreshing }: PageProps) {
  const { summary, stats, jobs } = data;
  const counts = summary.status_counts || {};
  const { daily_goal: goal, odds_prior: p, odds_cadence: cadence } = data.goals;

  const queue = applyTodayQueue(jobs);
  const lifecycle = stats.lifecycle;
  const rate = effectiveRate(p, lifecycle.response_rate_observed, lifecycle.matured_denominator);
  const eta = etaDays(lifecycle.matured_denominator, rate, cadence);
  const remaining = Math.max(0, goal - stats.pulls_today);

  const todayIso = localIsoDate();
  const [celebrating, setCelebrating] = useState(false);
  const [handled, setHandled] = useState(false);
  useEffect(() => {
    if (!handled && shouldCelebrate(stats.pulls_today, goal, data.goals.last_celebrated_date, todayIso)) setCelebrating(true);
  }, [handled, stats.pulls_today, goal, data.goals.last_celebrated_date, todayIso]);
  const dismissCelebration = useCallback(() => {
    setCelebrating(false);
    setHandled(true);
    saveGoals({ last_celebrated_date: todayIso })
      .then(() => reload())
      .catch(() => undefined);
  }, [todayIso, reload]);
  const sentAfter = lifecycle.submitted_total;
  const celebration = celebrationStats(Math.max(0, sentAfter - stats.pulls_today), sentAfter, p, cadence);

  const metrics: Array<[string, number, string, string]> = [
    ["Discovered", summary.total_jobs || 0, "roles found", "blue"],
    ["Active", summary.active_jobs || 0, "in play", "mint"],
    ["Ready", counts.ready || 0, "ready to send", "butter"],
    ["Applied", counts.applied || 0, "pulls so far", "coral"],
  ];

  const companionMsg =
    remaining === 0
      ? "Goal hit. Every application stacks the deck. 💪"
      : `${remaining} more application${remaining === 1 ? "" : "s"} to hit today's goal!`;

  return (
    <>
      <PageHeader
        kicker="Daily Command Center"
        title="Today"
        sub={`Last sync ${formatDate(summary.last_seen_at)} · ${summary.generated_applications || 0} application folders`}
        onRefresh={reload}
        refreshing={refreshing}
      />

      {needsSetupBanner(data.onboarding.status, data.onboarding.checks) && (
        <div className="setup-banner" role="status">
          <div>
            <strong>Finish setup to unlock AI drafts</strong>
            <span>Connect your local Ollama and JobArcade can tailor each application for you. It takes about a minute.</span>
          </div>
          <button type="button" className="btn rose sm" onClick={() => navigate("setup")}>Finish setup</button>
        </div>
      )}

      {(data.onboarding.demo_jobs ?? 0) > 0 && (
        <div className="setup-banner" role="status">
          <div>
            <strong>You're exploring sample data</strong>
          </div>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              clearDemo().then(() => reload()).catch(() => undefined);
            }}
          >
            Remove it
          </button>
        </div>
      )}

      <InterviewMilestone jobs={jobs} />

      <motion.div
        className="metrics"
        style={{ marginBottom: 18 }}
        variants={tilesContainer}
        initial="hidden"
        animate="show"
      >
        {metrics.map(([label, value, cap, tone]) => (
          <motion.article key={label} className={`metric ${tone}`} variants={tile}>
            <div className="label">{label}</div>
            <div className="value"><CountUp value={value} /></div>
            <div className="cap">{cap}</div>
          </motion.article>
        ))}
      </motion.div>

      <motion.div
        className="glance-row"
        role="navigation"
        aria-label="Pipeline at a glance"
        variants={pillsContainer}
        initial="hidden"
        animate="show"
      >
        {PIPELINE_STATUSES.map((status) => (
          <motion.button
            key={status}
            type="button"
            className={`glance-pill ${status}`}
            variants={pill}
            onClick={() => navigate("jobs", status)}
            title={`Jump to ${STATUS_LABELS[status]} on the Jobs board`}
          >
            <span className="glance-count">{counts[status] || 0}</span>
            <span className="glance-label">{STATUS_LABELS[status]}</span>
          </motion.button>
        ))}
        {OUTCOME_STATUSES.map((status) => (counts[status] || 0) > 0 ? (
          <motion.button
            key={status}
            type="button"
            className={`glance-pill ${status}`}
            variants={pill}
            onClick={() => navigate("jobs", status)}
            title={`Jump to ${STATUS_LABELS[status]} on the Jobs board`}
          >
            <span className="glance-count">{counts[status]}</span>
            <span className="glance-label">{STATUS_LABELS[status]}</span>
          </motion.button>
        ) : null)}
      </motion.div>

      <div className="odds-grid">
        <section className="panel">
          <h2>Apply today</h2>
          <p className="panel-sub">Your best-fit, freshest roles. Knock these out to keep the streak alive.</p>
          {queue.length ? (
            <motion.div className="job-list" variants={listContainer} initial="hidden" animate="show">
              <AnimatePresence mode="popLayout" initial={false}>
                {queue.map((job) => (
                  <motion.div
                    key={job.id}
                    className="job-list-item"
                    variants={listItem}
                    exit="exit"
                    layout="position"
                  >
                    <JobRow job={job} onChanged={reload} onSelect={() => navigate("jobs", `job-${job.id}`)} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          ) : (
            <p className="empty">Nothing queued — run a sweep or loosen filters on the Jobs page.</p>
          )}
        </section>

        <div className="grid-gap">
          <section className="panel">
            <h2>Daily energy</h2>
            <p className="panel-sub">Hit your pulls. Energy is all you need.</p>
            <div className="ring-wrap">
              <EnergyRing value={stats.pulls_today} goal={goal} />
              <div className="energy-status">
                <strong className={remaining === 0 ? "is-done" : ""}>
                  {remaining === 0 ? "✓ Goal complete" : `${remaining} to go`}
                </strong>
                <span className="muted">🔥 {stats.current_streak}-day streak · best {stats.best_streak}</span>
              </div>
            </div>
          </section>

          <button className="felt" style={{ textAlign: "left", cursor: "pointer", border: "none", width: "100%" }} onClick={() => navigate("odds")}>
            <div className="felt-kicker">Next interview</div>
            <div className="eta-hero">
              <span className="eta-num">{formatEta(eta)}</span>
            </div>
            <p className="felt-sub" style={{ marginTop: 2 }}>
              away at {cadence}/day. {lifecycle.matured_denominator} mature of {lifecycle.submitted_total} submitted. Tap to open your odds →
            </p>
          </button>
        </div>
      </div>

      <Companion message={companionMsg} />
      <AnimatePresence>
        {celebrating && <GoalCelebration goal={goal} stats={celebration} onDismiss={dismissCelebration} />}
      </AnimatePresence>
    </>
  );
}
