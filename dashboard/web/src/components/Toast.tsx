import { useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

type Props = { message: string | null; onClose: () => void; durationMs?: number };

export function Toast({ message, onClose, durationMs = 6000 }: Props) {
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!message) return;
    const t = window.setTimeout(onClose, durationMs);
    return () => window.clearTimeout(t);
  }, [message, durationMs, onClose]);
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          key={message}
          className="toast"
          role="status"
          aria-live="polite"
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: 24, scale: 0.96 }}
          animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.15 } }}
          transition={{ type: "spring", stiffness: 300, damping: 26 }}
        >
          <span className="toast-text">{message}</span>
          <button type="button" className="toast-close" onClick={onClose} aria-label="Dismiss">
            ×
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
