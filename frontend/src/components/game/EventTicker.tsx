/** Collapsible play-by-play. The narration shows you what happened; this is the record. */

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import type { GameEvent, GameView } from "../../api/types";
import { describeEvent, playerNames } from "../../logic/labels";
import { ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";

/** Keep the DOM small; nobody scrolls back further than this. */
const MAX_LINES = 200;

interface Props {
  state: GameView;
  events: GameEvent[];
}

export function EventTicker({ state, events }: Props) {
  const logOpen = useUiStore((s) => s.logOpen);
  const toggleLog = useUiStore((s) => s.toggleLog);
  const bottom = useRef<HTMLDivElement>(null);
  const names = playerNames(state);

  const lines = events
    .map((event, index) => ({ key: index, text: describeEvent(event, names, state.seat) }))
    .filter((line): line is { key: number; text: string } => line.text !== null)
    .slice(-MAX_LINES);

  // Follow the tail as the game goes on. The deps are triggers, not values the
  // body reads, which is the one thing the exhaustive-deps rule cannot express.
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll triggers, not reads
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [events.length, logOpen]);

  return (
    <section className="ticker" data-testid="event-log">
      <button type="button" className="rail__title rail__title--button" onClick={toggleLog}>
        Log
        <span className="rail__chevron">{logOpen ? "▾" : "▸"}</span>
      </button>
      <AnimatePresence initial={false}>
        {logOpen && (
          <motion.div
            className="ticker__lines"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={ease}
          >
            {lines.map((line) => (
              <p className="ticker__line" key={line.key}>
                {line.text}
              </p>
            ))}
            {lines.length === 0 && <p className="rail__empty">nothing yet</p>}
            <div ref={bottom} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
