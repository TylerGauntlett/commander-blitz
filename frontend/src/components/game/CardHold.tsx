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
 *
 * ## And it is the desktop's whole-card view too
 *
 * The rail's reader is a fixed height on a desktop as well (`.preview` in
 * `board.css`), so a card with real rules text scrolls inside a box the
 * pointer cannot reach without leaving the card -- and leaving the card empties
 * the rail. The Deck had this surface and the desktop had nothing. So the same
 * hold opens from a mouse: right-click a card (the convention every digital
 * card client uses for "show me this bigger"), or press `i` over it, which is
 * the key `Y` already was. `cursor.ts:readingOid` is why `i` reads the card
 * under the pointer rather than wherever the invisible ring last rested.
 *
 * A pointer cannot "press anything else" to put it down the way a pad does,
 * so the backdrop takes the click and closes, and there is a Close button for
 * anybody who does not guess that. `Escape` needs nothing here: it is `B`,
 * and `Table`'s `back` unwinds the hold before anything else.
 *
 * `role="dialog"` and `aria-modal`, named for the card, as `ZonePeek` and
 * `GameOverScreen` are. Focus is handled the way theirs is -- by the ring's
 * trap on `data-modal-root`, not by a hand-rolled `focus()` that would fight
 * it -- and the Close button deliberately carries no `data-stop`, so on a pad
 * the ring still has nothing to land on and any press is still the way out.
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
import { ease } from "../../motion/springs";
import { StaticCard } from "./Card";

interface Props {
  /** The card being held open, or `null`. */
  card: CardView | null;
  /** Put the card down. A click on the backdrop or the Close button. */
  onClose?: () => void;
}

export function CardHold({ card, onClose }: Props) {
  if (!card) return null;

  return (
    <motion.div
      className="hold hold--card"
      data-modal-root
      data-testid="card-hold"
      role="dialog"
      aria-modal="true"
      aria-label={card.name}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={ease}
      aria-live="polite"
      // Outside the card, and only outside it: the card itself may scroll on a
      // very long one, and a click that grabbed its scrollbar must not close it.
      onClick={(event) => {
        if (!(event.target as Element).closest(".hold__card")) onClose?.();
      }}
      // A right-click on the open hold is the same "I am done looking" as a
      // left one, and the browser's own menu over a full-screen card is noise.
      // Stopped here, because the hold is drawn inside `.table` and the
      // table's own right-click OPENS the hold: the pointer has not moved, so
      // `hoveredOid` still names the card, and the close would be undone by
      // the same event one element up.
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClose?.();
      }}
    >
      {onClose && (
        <button
          type="button"
          className="btn btn--ghost hold__close"
          data-testid="card-hold-close"
          onClick={(event) => {
            event.stopPropagation();
            onClose();
          }}
        >
          Close
        </button>
      )}
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
