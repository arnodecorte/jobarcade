import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { Variants } from "framer-motion";
import { navigate } from "../lib/hooks";
import { RELEASE } from "../lib/releaseNotes";

/* Bubble navigation: a slim fixed bar (brand + toggle) that pops the five
   routes open as big pastel bubbles — one per theme accent. Replaces the old
   left sidebar. Reduced-motion aware; Esc and backdrop both close it. */

const ICONS: Record<string, JSX.Element> = {
  today: <path d="M3 10.5 12 4l9 6.5M5 9.5V20h14V9.5M9.5 20v-6h5v6" />,
  pipeline: <path d="M4 5h4v14H4zM10 5h4v9h-4zM16 5h4v6h-4z" />,
  jobs: <path d="M4 6h16M4 12h16M4 18h10" />,
  fresh: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" />,
  odds: <path d="M4 19V5m0 14h16M4 19c3-1 5-9 8-9s4 5 8 4" />,
  discover: <path d="M12 21s7-4.2 7-10.5A7 7 0 0 0 5 10.5C5 16.8 12 21 12 21Zm0-7a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />,
  system: (
    <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-3-2-.6.6-2-2-1.2-1.4 1.5L12 8V6h-2v2l-1.8.9L6.8 7.4 4.8 8.6l.6 2L3.4 11v2l2 .6-.6 2 2 1.2 1.4-1.5L10 18v2h2v-2l1.8-.9 1.4 1.5 2-1.2-.6-2L20 14Z" />
  ),
};

type NavItem = { key: string; label: string; tone: string; hint: string };

const NAV: NavItem[] = [
  { key: "today", label: "Today", tone: "rose", hint: "Today's pulls" },
  { key: "pipeline", label: "Pipeline", tone: "berry", hint: "Move roles forward" },
  { key: "jobs", label: "Jobs", tone: "sky", hint: "Every open role" },
  { key: "fresh", label: "Fresh", tone: "mint", hint: "Just found" },
  { key: "odds", label: "Odds", tone: "butter", hint: "Read your chances" },
  { key: "discover", label: "Discover", tone: "rose", hint: "Find companies" },
  { key: "system", label: "System", tone: "mint", hint: "Scraper health" },
];

const cloud: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
  exit: { transition: { staggerChildren: 0.03, staggerDirection: -1 } },
};

const bubble: Variants = {
  hidden: { opacity: 0, scale: 0.3, y: 22 },
  show: { opacity: 1, scale: 1, y: 0, transition: { type: "spring", stiffness: 260, damping: 18 } },
  exit: { opacity: 0, scale: 0.4, y: 8, transition: { duration: 0.12 } },
};

export function BubbleMenu({ route, freshCount = 0 }: { route: string; freshCount?: number }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();
  const toggleRef = useRef<HTMLButtonElement>(null);
  const current = NAV.find((n) => n.key === route) ?? NAV[0];

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      toggleRef.current?.focus();
    };
  }, [open]);

  const go = (key: string) => {
    navigate(key);
    setOpen(false);
  };

  return (
    <>
      <header className="bubblebar">
        <div className="bubblebar-inner">
          <a
            className="bubblebar-brand"
            href="#/today"
            onClick={(e) => {
              e.preventDefault();
              go("today");
            }}
          >
            <span className="brand-badge">JA</span>
            <span className="bubblebar-brand-text">
              JobArcade <span className="brand-beta">{RELEASE.version}</span>
            </span>
          </a>

          <button
            ref={toggleRef}
            type="button"
            className={`bubblebar-toggle tone-${current.tone} ${open ? "is-open" : ""}`}
            aria-expanded={open}
            aria-haspopup="menu"
            aria-label={open ? "Close navigation" : `Navigation — on ${current.label}`}
            onClick={() => setOpen((v) => !v)}
          >
            <span className="bubblebar-toggle-label">{open ? "Close" : current.label}</span>
            {!open && freshCount > 0 && route !== "fresh" && (
              <span className="bubble-badge" aria-hidden="true">{freshCount}</span>
            )}
            <span className="bubblebar-burger" aria-hidden="true">
              <i />
              <i />
            </span>
          </button>
        </div>
      </header>

      <AnimatePresence>
        {open && (
          <motion.div
            className="bubble-scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={() => setOpen(false)}
          >
            <motion.nav
              className="bubble-cloud"
              variants={cloud}
              initial="hidden"
              animate="show"
              exit="exit"
              aria-label="Primary"
              onClick={(e) => e.stopPropagation()}
            >
              {NAV.map((item, i) => (
                <motion.button
                  key={item.key}
                  type="button"
                  className={`bubble tone-${item.tone} ${route === item.key ? "is-active" : ""}`}
                  variants={bubble}
                  whileHover={reduce ? undefined : { scale: 1.06, rotate: i % 2 ? 2.5 : -2.5 }}
                  whileTap={{ scale: 0.95 }}
                  autoFocus={i === 0}
                  onClick={() => go(item.key)}
                >
                  <svg
                    className="bubble-ico"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    {ICONS[item.key]}
                  </svg>
                  <span className="bubble-label">
                    {item.label}
                    {item.key === "fresh" && freshCount > 0 && (
                      <span className="bubble-badge" aria-hidden="true">{freshCount}</span>
                    )}
                  </span>
                  <span className="bubble-hint">{item.hint}</span>
                </motion.button>
              ))}
            </motion.nav>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
