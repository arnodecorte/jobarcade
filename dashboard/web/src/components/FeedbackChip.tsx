import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { sendFeedback } from "../lib/api";
import { useHashRoute } from "../lib/hooks";

type Mode = "collapsed" | "open" | "sending" | "sent";

/** Persistent corner chip — opposite the Dice companion — for quick improvement notes. */
export function FeedbackChip() {
  const route = useHashRoute();
  const [mode, setMode] = useState<Mode>("collapsed");
  const [message, setMessage] = useState("");

  async function send() {
    if (!message.trim()) return;
    setMode("sending");
    try {
      await sendFeedback(message.trim(), route);
      setMessage("");
      setMode("sent");
      setTimeout(() => setMode("collapsed"), 1600);
    } catch {
      setMode("open");
    }
  }

  if (mode === "collapsed") {
    return (
      <button type="button" className="feedback-fab" onClick={() => setMode("open")} aria-label="Leave feedback">
        ✎
      </button>
    );
  }

  return (
    <AnimatePresence>
      <motion.div
        className="feedback-panel"
        initial={{ opacity: 0, y: 10, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10 }}
      >
        {mode === "sent" ? (
          <p className="feedback-thanks">Thanks — noted! 🌱</p>
        ) : (
          <>
            <strong>Improvement idea?</strong>
            <textarea
              rows={3}
              autoFocus
              placeholder="What would make this better?"
              value={message}
              disabled={mode === "sending"}
              onChange={(e) => setMessage(e.target.value)}
            />
            <div className="feedback-actions">
              <button className="btn ghost sm" type="button" onClick={() => setMode("collapsed")} disabled={mode === "sending"}>
                Cancel
              </button>
              <button className="btn rose sm" type="button" onClick={send} disabled={mode === "sending" || !message.trim()}>
                {mode === "sending" ? "Sending…" : "Send"}
              </button>
            </div>
          </>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
