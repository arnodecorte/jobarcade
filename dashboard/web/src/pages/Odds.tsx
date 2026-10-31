import type { PageProps } from "../App";
import { PageHeader } from "../components/PageHeader";
import { OddsCurve } from "../components/OddsCurve";
import { StreakRail } from "../components/StreakRail";
import { useEffect, useRef, useState } from "react";
import { saveGoals } from "../lib/api";
import type { Goals } from "../lib/api";
import { PRIOR_SOURCES, cumulativeProb, effectiveRate, etaDays, formatEta } from "../lib/odds";

export function Odds({ data, reload, refreshing }: PageProps) {
  const { stats } = data;
  const [p, setP] = useState(data.goals.odds_prior);
  const [cadence, setCadence] = useState(data.goals.odds_cadence);
  const timer = useRef<number | undefined>(undefined);
  const pending = useRef<Partial<Goals>>({});
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  const flush = () => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    const patch = pending.current;
    pending.current = {};
    if (Object.keys(patch).length) saveGoals(patch).then(() => reloadRef.current()).catch(() => undefined);
  };
  // Flush (not discard) a pending change when leaving the page.
  useEffect(() => flush, []);
  // Resync from the server whenever it changes and the user has no unsaved edit.
  useEffect(() => {
    if (Object.keys(pending.current).length) return;
    setP(data.goals.odds_prior);
    setCadence(data.goals.odds_cadence);
  }, [data.goals.odds_prior, data.goals.odds_cadence]);
  const persist = (patch: Partial<Goals>) => {
    pending.current = { ...pending.current, ...patch };
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 400);
  };

  const lifecycle = stats.lifecycle;
  const mature = lifecycle.matured_denominator;
  const rate = effectiveRate(p, lifecycle.response_rate_observed, mature);
  const incubating = lifecycle.immature_pending;
  const sent = lifecycle.submitted_total || stats.applications_sent;
  const eta = etaDays(mature, rate, cadence);
  const projectedMature = Math.round(mature + cadence * 14);
  const projectedProb = cumulativeProb(projectedMature, rate);
  const usingObserved = rate !== p;
  const interviews = lifecycle.interviews;
  const hasLanded = interviews > 0;

  return (
    <>
      <PageHeader
        kicker="The numbers game"
        title="Your Odds"
        sub={
          hasLanded
            ? `It's already working — ${interviews} interview${interviews === 1 ? "" : "s"} so far. Every application still stacks the deck toward the next one.`
            : "You get unlimited tries. Every application stacks the deck in your favour."
        }
        onRefresh={reload}
        refreshing={refreshing}
      />

      <div className="odds-grid">
        <section className="felt curve-card">
          <div className="felt-kicker">Next interview, at this pace</div>
          <div className="eta-hero">
            <span className="eta-num">{formatEta(eta)}</span>
            <span className="eta-label">
              away · using {usingObserved ? "observed mature" : "prior"} rate {(rate * 100).toFixed(1)}% and {cadence}/day
            </span>
          </div>
          <p className="felt-sub">
            You've submitted <b style={{ color: "var(--dusk-ink)" }}>{sent}</b>, but only{" "}
            <b style={{ color: "var(--dusk-ink)" }}>{mature}</b> are mature enough for calibration.
            {incubating > 0 ? ` ${incubating} are still incubating.` : ""} In two weeks, if {cadence}/day mature into the sample,
            odds of landing {hasLanded ? "your next interview" : "at least one interview"} reach{" "}
            <b style={{ color: "var(--glow-gold)" }}>{Math.round(projectedProb * 100)}%</b>.
          </p>

          <div className="maturity-strip">
            <div>
              <span>{lifecycle.matured_denominator}</span>
              <small>matured sample</small>
            </div>
            <div>
              <span>{lifecycle.immature_pending}</span>
              <small>pending under {lifecycle.maturity_days}d</small>
            </div>
            <div>
              <span>{lifecycle.follow_up_due}</span>
              <small>follow-up due</small>
            </div>
            <div>
              <span>{lifecycle.rejections}</span>
              <small>known rejections</small>
            </div>
          </div>
          <div className="maturity-strip compact">
            <div>
              <span>{(lifecycle.response_rate_observed * 100).toFixed(1)}%</span>
              <small>observed mature rate</small>
            </div>
            <div>
              <span>{(lifecycle.response_rate_low * 100).toFixed(1)}-{(lifecycle.response_rate_high * 100).toFixed(1)}%</span>
              <small>95% range</small>
            </div>
            <div>
              <span>{lifecycle.matured_no_response}</span>
              <small>matured silence</small>
            </div>
            <div>
              <span>{lifecycle.ghosted}</span>
              <small>{lifecycle.ghosted_days}d+ ghosted</small>
            </div>
          </div>

          <OddsCurve p={rate} sent={mature} cadence={cadence} />

          <div className="felt-controls">
            <div className="felt-control">
              <label>
                Response rate <b>{(p * 100).toFixed(1)}%</b>
              </label>
              <input
                type="range"
                min={0.005}
                max={0.08}
                step={0.005}
                value={p}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setP(v);
                  persist({ odds_prior: v });
                }}
              />
              <div className="hint">
                Starts at a cited 3%. Lower it to stay humble, raise it as you learn yours.
              </div>
              <details className="hint">
                <summary>Why 3%?</summary>
                <ul>
                  {PRIOR_SOURCES.map((src) => (
                    <li key={src.url}>
                      <a href={src.url} target="_blank" rel="noreferrer">{src.label}</a>: {src.figure}
                    </li>
                  ))}
                </ul>
                <p>Published averages for cold applications. Tailored applications often do better; adjust the slider to match your own view.</p>
              </details>
            </div>
            <div className="felt-control">
              <label>
                Target cadence <b>{cadence}/day</b>
              </label>
              <input
                type="range"
                min={1}
                max={10}
                step={1}
                value={cadence}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setCadence(v);
                  persist({ odds_cadence: v });
                }}
              />
              <div className="hint">
                Your actual last-7-day pace: <b>{stats.actual_cadence_7d}/day</b>. Aim a little above it.
              </div>
            </div>
          </div>
        </section>

        <StreakRail stats={stats} />
      </div>
    </>
  );
}
