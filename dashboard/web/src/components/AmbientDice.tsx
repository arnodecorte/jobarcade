import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Dice } from "./Sprite";

/* Every few minutes Dice dashes across the bottom of the screen — a small
   moment of life, never in the way (pointer-events: none, low corner). */
const MIN_GAP = 300_000; // 5 min
const JITTER = 180_000; // up to +3 min

export function AmbientDice() {
  const [walking, setWalking] = useState(false);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (reduceMotion) return;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(() => setWalking(true), MIN_GAP + Math.random() * JITTER);
    };
    schedule();
    return () => clearTimeout(timer);
  }, [reduceMotion]);

  return (
    <AnimatePresence>
      {walking && (
        <motion.div
          key="ambient-dice"
          style={{ position: "fixed", bottom: 0, left: 0, zIndex: 5, pointerEvents: "none" }}
          initial={{ x: "-12vw" }}
          animate={{ x: "112vw" }}
          transition={{ duration: 5, ease: "linear" }}
          onAnimationComplete={() => {
            setWalking(false);
            // re-arm the next stroll
            window.setTimeout(() => setWalking(true), MIN_GAP + Math.random() * JITTER);
          }}
        >
          <Dice size="lg" state="trot" />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
