/**
 * Looking into a zone.
 *
 * Graveyards, exile and command zones are public, so they are shown in full.
 * An opponent's hand is not: the server sends `hand: null` with only a count,
 * and this says so rather than pretending the zone is empty.
 */

import { AnimatePresence, motion } from "motion/react";
import type { CardView, GameView } from "../../api/types";
import { CARD_SCALE, cardWidthVar } from "../../logic/cardSize";
import { splitActionable, stackCards } from "../../logic/stacking";
import { bouncy, ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { StaticCard } from "./Card";

/** Ratio of `--card-w-base`; see logic/cardSize.ts. */
const NO_ACTIONS: ReadonlySet<number> = new Set();

const TITLES: Record<string, string> = {
  graveyard: "Graveyard",
  exile: "Exile",
  command: "Command zone",
  hand: "Hand",
};

interface Props {
  state: GameView;
}

export function ZonePeek({ state }: Props) {
  const peek = useUiStore((s) => s.peek);
  const setPeek = useUiStore((s) => s.setPeek);

  const player = peek ? state.players[peek.pid] : null;
  let cards: CardView[] | null = null;
  if (player && peek) {
    if (peek.zone === "hand") cards = player.hand;
    else cards = player[peek.zone];
  }
  const hidden = peek?.zone === "hand" && cards === null;
  // Duplicates collapse here too -- eight Swamps in a graveyard is one entry.
  const groups = cards
    ? stackCards(cards).flatMap((group) => splitActionable(group, NO_ACTIONS))
    : [];

  return (
    <AnimatePresence>
      {peek && player && (
        <motion.div
          className="peek-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={ease}
          onClick={() => setPeek(null)}
        >
          <motion.div
            className="peek"
            role="dialog"
            aria-modal="true"
            data-testid="zone-peek"
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={bouncy}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="peek__head">
              <h2 className="peek__title">
                {player.name} &middot; {TITLES[peek.zone] ?? peek.zone}
              </h2>
              <button type="button" className="btn btn--ghost" onClick={() => setPeek(null)}>
                Close
              </button>
            </header>

            <div
              className="peek__cards"
              style={{ ["--card-w" as string]: cardWidthVar(CARD_SCALE.peek) }}
            >
              {hidden && (
                <p className="peek__hidden">
                  Hidden &mdash; {player.hand_count} card
                  {player.hand_count === 1 ? "" : "s"}
                </p>
              )}
              {cards?.length === 0 && <p className="peek__hidden">Empty</p>}
              {groups.map((group) => (
                <div className="peek__slot" key={group.key}>
                  <StaticCard card={group.top} variant="detail" />
                  {group.count > 1 && <span className="peek__count">&times;{group.count}</span>}
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
