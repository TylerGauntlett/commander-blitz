/**
 * An opponent's board, at a size you can actually read it.
 *
 * On a handheld an opponent is a strip -- portrait, name, and a summary line --
 * because 1280px cannot hold three boards and a hand at a legible card size.
 * That is the right default: most of the time what you need from a seat you are
 * not attacking is "how much power, how many untapped, any fliers", which the
 * spine answers without you reading a single card.
 *
 * But sometimes you do need to read the cards -- before a big attack, or when
 * something has been enchanted -- and this is that. Held on `R2` rather than
 * toggled, for the reason the design round gives: a toggle needs a second press
 * to put away and leaves the board hidden if you forget, which on a hold is
 * impossible by construction.
 *
 * It renders a `PlayerMat` in its full (non-compact) form at a fixed card width,
 * deliberately **outside** the zoom solver. The solver's whole job is fitting
 * the permanent layout into the space it has; this is a temporary overlay that
 * owns the screen while it is up, so it has no fitting to do and nothing it
 * decides can feed back into the board underneath.
 */

import { motion } from "motion/react";
import type { GameView } from "../../api/types";
import { ease } from "../../motion/springs";
import { PlayerMat } from "./PlayerMat";

interface Props {
  state: GameView;
  /** The seat being read, or null when nothing is held. */
  pid: number | null;
}

/**
 * A fixed, generous card width.
 *
 * Well clear of the 96px floor because reading is the entire point of this
 * surface -- if it were at the floor there would be no reason to open it.
 */
const CARD_SCALE = 1.35;

export function OpponentBoard({ state, pid }: Props) {
  if (pid === null) return null;
  const player = state.players[pid];
  if (!player) return null;

  return (
    <motion.div
      className="oppboard"
      data-testid="opponent-board"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={ease}
      aria-live="polite"
    >
      <div className="oppboard__head">
        <span className="oppboard__who">{player.name}</span>
        <span className="oppboard__life tabular">{player.life}</span>
      </div>
      {/*
        Not mirrored, and that is deliberate.

        On the table an opponent's mat is mirrored so their lands sit against
        their own edge and the two creature rows meet across the middle. Here
        there is no middle to meet across -- this is their board on its own, and
        the natural reading order for a board you are inspecting is the same one
        you read your own in.

        No `onActivate` either: this is a reader, not a second way to act. Every
        legal action against these permanents is already a row in the panel and
        a stop on the board underneath, and giving them a second control here
        would put the same `data-action-id` in the document twice.

        `variant="lanes"` for the same reason one level up. This drew a whole
        second `PlayerOrb` while held -- a duplicate `data-player` and a
        duplicate `life-<pid>` in the document, which `FxLayer` resolves with
        `document.querySelector` and would therefore have anchored to whichever
        came first. The head above already says whose board this is.
      */}
      <PlayerMat
        variant="lanes"
        state={state}
        player={player}
        cardScale={CARD_SCALE}
        actionableOids={EMPTY}
        playableOids={EMPTY}
      />
    </motion.div>
  );
}

const EMPTY: ReadonlySet<number> = new Set<number>();
