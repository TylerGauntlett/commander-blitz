/**
 * Looking into a zone.
 *
 * Graveyards, exile and command zones are public, so they are shown in full.
 * An opponent's hand is not: the server sends `hand: null` with only a count,
 * and this says so rather than pretending the zone is empty.
 *
 * The one exception is `hand_revealed` -- cards this seat has been *shown* by
 * "look at target player's hand". The server has already decided who is
 * entitled to those, so showing them here leaks nothing, and a Glasses of Urza
 * that changed no pixel would be an ability the player could not use.
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

/** The cards of someone else's hand this seat has been shown, or null. */
function shown(player: GameView["players"][number]): CardView[] | null {
  return player.hand_revealed.length > 0 ? player.hand_revealed : null;
}

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
    if (peek.zone === "hand") cards = player.hand ?? shown(player);
    else cards = player[peek.zone];
  }
  const hidden = peek?.zone === "hand" && cards === null;
  // Some of the hand may be visible without all of it: you looked, and then
  // they drew. The count is what is still unaccounted for, not the whole hand.
  const stillHidden =
    peek?.zone === "hand" && player && player.hand === null
      ? player.hand_count - (cards?.length ?? 0)
      : 0;
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
              {stillHidden > 0 && (
                <p className="peek__hidden">
                  &hellip;and {stillHidden} more you have not seen
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
