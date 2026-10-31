import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { getCompanies, getGoals, getGmailEvidence, getGmailStatus, getIntegrationStatus, getJobs, getOnboarding, getStats, getSummary, saveGoals } from "./lib/api";
import type { Company, Coverage, Goals, GmailEvidence, GmailStatus, IntegrationStatus, Job, OnboardingState, Stats, Summary } from "./lib/api";
import { useAsync, useChameleonUpdateSplash, useHashRoute } from "./lib/hooks";
import { DraftProvider } from "./lib/draftContext";
import { BubbleMenu } from "./components/BubbleMenu";
import { Loading } from "./components/Sprite";
import { Grainient } from "./components/Grainient";
import { AmbientAngie } from "./components/AmbientAngie";
import { DraftOverlay } from "./components/DraftOverlay";
import { ChameleonUpdateSplash } from "./components/ChameleonUpdateSplash";
import { Toast } from "./components/Toast";
import { rejectionMessage } from "./lib/odds";
import { FeedbackChip } from "./components/FeedbackChip";
import { Onboarding } from "./pages/Onboarding";
import { shouldShowOnboarding } from "./lib/onboarding";
import { Today } from "./pages/Today";
import { Pipeline } from "./pages/Pipeline";
import { Jobs } from "./pages/Jobs";
import { Fresh } from "./pages/Fresh";
import { Odds } from "./pages/Odds";
import { System } from "./pages/System";
import { Discover } from "./pages/Discover";
import { freshJobs } from "./lib/jobs";
import { ScraperContext } from "./lib/features";
import { clearLegacyGoals, localGoalsToMigrate } from "./lib/goals";

export type DashData = {
  summary: Summary;
  jobs: Job[];
  companies: Company[];
  coverage: Coverage;
  stats: Stats;
  gmail: GmailStatus;
  gmailEvidence: GmailEvidence[];
  integrations: IntegrationStatus;
  goals: Goals;
  onboarding: OnboardingState;
};

export type PageProps = { data: DashData; reload: () => void; refreshing: boolean };

async function loadAll(): Promise<DashData> {
  const [summary, jobs, companies, stats, gmail, gmailEvidence, integrations, goals, onboarding] = await Promise.all([
    getSummary(),
    getJobs(),
    getCompanies(),
    getStats(),
    getGmailStatus(),
    getGmailEvidence(),
    getIntegrationStatus(),
    getGoals(),
    getOnboarding(),
  ]);
  return {
    summary,
    jobs,
    companies: companies.companies,
    coverage: companies.coverage,
    stats,
    gmail,
    gmailEvidence: gmailEvidence.evidence,
    integrations,
    goals,
    onboarding,
  };
}

export function App() {
  const route = useHashRoute();
  const { data, error, loading, reload } = useAsync(loadAll);
  const [showChameleonUpdate, dismissChameleonUpdate] = useChameleonUpdateSplash();
  const migrated = useRef(false);
  useEffect(() => {
    if (!data || migrated.current) return;
    migrated.current = true;
    let local: Partial<Goals> | null = null;
    try {
      local = localGoalsToMigrate(window.localStorage, data.goals);
    } catch {
      local = null;
    }
    if (local) {
      saveGoals(local)
        .then(() => {
          clearLegacyGoals(window.localStorage);
          reload();
        })
        .catch(() => undefined);
    }
  }, [data]);
  const [toast, setToast] = useState<string | null>(null);
  const closeToast = useCallback(() => setToast(null), []);
  const dataRef = useRef(data);
  dataRef.current = data;
  useEffect(() => {
    const onRejected = () => {
      const d = dataRef.current;
      if (d) setToast(rejectionMessage(d.stats.lifecycle.submitted_total, d.goals.odds_prior));
    };
    window.addEventListener("jobarcade:rejected", onRejected);
    return () => window.removeEventListener("jobarcade:rejected", onRejected);
  }, []);
  const scraper = data?.integrations.features?.scraper ?? false;
  const freshCount = data && scraper ? freshJobs(data.jobs).rows.length : 0;

  if (data && shouldShowOnboarding(data.onboarding.status, route)) {
    return (
      <>
        <Grainient />
        <Onboarding onboarding={data.onboarding} integrations={data.integrations} goals={data.goals} reload={reload} />
      </>
    );
  }

  return (
    <ScraperContext.Provider value={scraper}>
    <DraftProvider onGenerated={reload}>
      <Grainient />
      {data?.onboarding.status === "complete" && showChameleonUpdate && <ChameleonUpdateSplash onDismiss={dismissChameleonUpdate} />}
      <BubbleMenu route={route} freshCount={freshCount} scraper={scraper} />
      <div className="shell">
        <AnimatePresence mode="wait" initial={false}>
          <motion.main
            key={data ? route : "loading"}
            className="main"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.22, 1, 0.36, 1] } }}
            exit={{ opacity: 0, y: -8, transition: { duration: 0.14 } }}
          >
            {error && <div className="banner-error">Could not load dashboard: {error}</div>}
            {!data && loading && <Loading />}
            {data && (() => {
              const props: PageProps = { data, reload, refreshing: loading };
              switch (route) {
                case "pipeline":
                  return <Pipeline {...props} />;
                case "jobs":
                  return <Jobs {...props} />;
                case "fresh":
                  return scraper ? <Fresh {...props} /> : <Today {...props} />;
                case "odds":
                  return <Odds {...props} />;
                case "discover":
                  return scraper ? <Discover {...props} /> : <Today {...props} />;
                case "system":
                  return <System {...props} />;
                default:
                  return <Today {...props} />;
              }
            })()}
          </motion.main>
        </AnimatePresence>
      </div>
      <DraftOverlay />
      <FeedbackChip />
      <AmbientAngie />
      <Toast message={toast} onClose={closeToast} />
    </DraftProvider>
    </ScraperContext.Provider>
  );
}
