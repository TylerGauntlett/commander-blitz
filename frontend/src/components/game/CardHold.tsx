/**
 * The card you are pointing at, as big as the screen will allow.
 *
 * The rail's reader is always on: it carries a card's name, cost, type, P/T and
 * rules at 16px, which is what you need most of the time and is the reason it
 * was worth 236px of a 748px rail. This is the deeper read for the times that
 * is not enough -- a card with six lines of rules, or one whose art you want to
 * see because the illustration is how you recognise it next turn.
 *
 * ## It is a hold, not a toggle
 *
 * The same argument the `R2` opponent hold makes: a toggle needs a second press to put
 * away and leaves the screen covered if you forget, whereas letting go is not
 * something you can forget to do. On a keyboard it is `i` held, which is what
 * `input/buttons.ts` already maps to `Y`.
 *
 * ## It closes a hint the app was already making
 *
 * `logic/verbs.ts` returns `Y Read` on every card stop and `HintBar` has drawn
 * it since it was written, with **nothing bound to `Y` anywhere in the app**.
 * An advertised button that does nothing is worse than an unadvertised one: it
 * teaches the player that the bar is not to be trusted.
 *
 * ## `data-modal-root`, so the ring stays put
 *
 * There is nothing in here to press -- it is a picture and its text -- so the
 * trap is not about reachability. It is about the ring not walking around the
 * board underneath a full-screen overlay while the player cannot see where it
 * has gone.
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
import { ease } from "../../motion/springs";
import { StaticCard } from "./Card";

interface Props {
  /** The card being held open, or `null`. */
  card: CardView | null;
}

export function CardHold({ card }: Props) {
  if (!card) return null;

  return (
    <motion.div
      className="hold hold--card"
      data-modal-root
      data-testid="card-hold"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={ease}
      aria-live="polite"
    >
      {/*
        `variant="big"` at 330px, which is the handheld-board round's (`docs/design-record.md#handheld-board`) number
        and is the same component the desktop rail draws -- the roadmap's rule
        for this whole round is that the card sizes are fine as they are and
        what changes is which one is used where.

        `StaticCard` and never `Card`, for the reason `CardPreview` gives: a
        second `layoutId` for the same oid would make framer animate the board
        card into this one.
      */}
      <div className="hold__card">
        <StaticCard card={card} variant="big" />
      </div>
    </motion.div>
  );
}
