/**
 * A card leaving the battlefield.
 *
 * Purely presentational: it is handed a start point, an end point and a caption,
 * and it flies. `FxLayer` owns resolving all three -- where the card was, which
 * pile it is going to, and how long it may live -- because those need the DOM
 * and the game state, and this needs neither.
 *
 * Two beats in one animation. It holds still for a moment with its caption
 * showing, because "why did that die" is the question and a card already in
 * flight is unreadable; then it falls into its pile. The caption fades before
 * the card does, so the last third is pure motion.
 *
 * `CardFace` directly rather than `StaticCard`: `StaticCard` carries its own
 * `initial`/`animate` pair that fades it *in* on mount, which is the opposite of
 * a death and would fight this component's transform on a nested node.
 */

import { motion } from "motion/react";
import type { CSSProperties } from "react";
import type { CardView } from "../../api/types";
import { CardFace } from "./CardFace";

/** Where a departing card ends up, as far as the animation is concerned. */
export type GhostTone = "graveyard" | "exile" | "hand" | "library" | "command";

/**
 * Which pile a destination reads as.
 *
 * `library` and `command` share the neutral treatment: neither is a death, and
 * a tucked commander should not be mourned like a destroyed one.
 */
export function ghostTone(to: string): GhostTone {
  switch (to) {
    case "exile":
      return "exile";
    case "hand":
      return "hand";
    case "command":
      return "command";
    case "library":
      return "library";
    default:
      return "graveyard";
  }
}

export interface CardGhostProps {
  /** For `data-ghost-oid`, so tests and stories can pick one out of a wipe. */
  oid: number;
  /** The card's face, or null when it can no longer be resolved -- see below. */
  card: CardView | null;
  /** The printed name. The only thing a token ghost has left. */
  name: string;
  /** "Destroyed by Vandalblast". Built in `logic/labels.ts`, never here. */
  caption: string;
  to: string;
  /** Board-relative start, the card's last known position. */
  from: { x: number; y: number };
  /** Board-relative end, the centre of the pile it lands in. */
  toPoint: { x: number; y: number };
  /**
   * How wide the card actually was, in pixels.
   *
   * Measured rather than taken from `CARD_SCALE`, because an opponent's mat
   * draws its cards smaller (`opponentCardScale`) -- a ghost sized at the
   * viewer's own scale would jump larger the instant it appeared, over the card
   * it is supposed to be replacing.
   */
  width: number;
  /** Seconds. Already divided by the narration speed by the caller. */
  duration: number;
  /** Seconds to wait before moving, so a wipe reads as a sweep. */
  delay: number;
}

export function CardGhost({
  oid,
  card,
  name,
  caption,
  to,
  from,
  toPoint,
  width,
  duration,
  delay,
}: CardGhostProps) {
  const tone = ghostTone(to);
  // The fraction of the flight spent holding still. Below about a fifth of a
  // second the caption cannot be read at all, so this is a floor rather than a
  // pure ratio.
  const hold = Math.min(0.4, 0.24 / duration);

  return (
    <motion.div
      className={`fx-ghost fx-ghost--${tone}`}
      data-testid="card-ghost"
      data-ghost-oid={oid}
      data-ghost-to={to}
      style={
        {
          left: from.x,
          top: from.y,
          // A pixel literal, not a ratio of `--card-w-base`: this is the width
          // the card was *observed* at, and every mat draws its own.
          ["--card-w" as string]: `${width}px`,
        } as CSSProperties
      }
      initial={{ x: 0, y: 0, scale: 1, opacity: 1, rotate: 0 }}
      animate={{
        // Keyframed rather than tweened so the hold is part of the same
        // animation: two sequential motions would need their own timers, which
        // is exactly the bookkeeping `FxLayer` centralises.
        x: [0, 0, toPoint.x - from.x],
        y: [0, 0, toPoint.y - from.y],
        scale: [1, 1.04, 0.3],
        rotate: [0, -3, 10],
        opacity: [1, 1, 0],
      }}
      transition={{ duration, delay, times: [0, hold, 1], ease: [0.4, 0, 0.7, 1] }}
    >
      {card ? (
        <div className="card card--static fx-ghost__card">
          <div className="card__pivot">
            <CardFace card={card} variant="board" />
          </div>
          {/* Inside the card, and last, so it tints the art rather than
              painting behind it -- and so it never reaches the caption, whose
              whole job is to stay readable. */}
          <div className="fx-ghost__wash" />
        </div>
      ) : (
        /*
         * A token, almost always. Tokens cease to exist the instant they leave
         * the battlefield -- `sba._tokens_and_attachments` pops them out of
         * `state.objects` -- so by the time this beat plays there is no card
         * anywhere to draw. A name is better than nothing at all, which is the
         * same trade the spotlight's plate makes for a countered spell.
         */
        <span className="fx-ghost__plate">{name}</span>
      )}
      <motion.span
        className="fx-ghost__cause"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: [0, 1, 1, 0], y: [4, 0, 0, 0] }}
        transition={{ duration, delay, times: [0, hold / 2, 0.55, 0.75] }}
      >
        {caption}
      </motion.span>
    </motion.div>
  );
}
