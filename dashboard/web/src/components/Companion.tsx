import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Angie, type SpriteState } from "./Sprite";

const IDLE: SpriteState = "type"; // working away at her desk beside you
const WAVE_MS = 2160; // 3 wave loops × 720ms, matches angie-wave in app.css

export function Companion({ message }: { message: string }) {
  const [spriteState, setSpriteState] = useState<SpriteState>(IDLE);

  // Greet each new message with a quick wave, then settle back to working.
  useEffect(() => {
    if (!message) return;
    setSpriteState("wave");
    const t = setTimeout(() => setSpriteState(IDLE), WAVE_MS);
    return () => clearTimeout(t);
  }, [message]);

  return (
    <div className="companion">
      <AnimatePresence>
        {message && (
          <motion.div
            className="bubble"
            initial={{ opacity: 0, y: 8, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8 }}
            key={message}
          >
            {message}
          </motion.div>
        )}
      </AnimatePresence>
      <Angie size="sm" state={spriteState} />
    </div>
  );
}
