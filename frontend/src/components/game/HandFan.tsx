/**
 * The player's hand, fanned.
 *
 * Cards sit on a shallow arc, rise to meet the pointer, and push their
 * neighbours aside. The fan owns hover entirely (`lift={false}` on the card),
 * because two components animating the same node's `y` produce a fight rather
 * than a lift.
 */

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import type { CardView, ManaView, UnplayableReason } from "../../api/types";
import { CARD_SCALE, cardWidthPx, cardWidthVar } from "../../logic/cardSize";
import { unplayableHint } from "../../logic/mana";
import { HAND_FAN_W, handStep } from "../../logic/zoomFit";
import { bouncy, settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { useCardBase } from "../../state/useCardBase";
import { useHandLift } from "../../state/useHandLift";
import { Card } from "./Card";

/*
 * The fan's width and its pitch live in `logic/zoomFit.ts` (`HAND_FAN_W`,
 * `HAND_MAX_SPREAD`, `handStep`).
 *
 * They used to be `MAX_FAN_W` and `MAX_SPREAD` here, which was right while the fan
 * was the only thing that had an opinion about them. The zoom now has to work out
 * how wide a hand card can be *before* the fan is laid out -- crowding is what
 * bounds it -- so the spacing rule has one home and both callers read it. The
 * action bar used to take 420px out of this row; now that it lives in the right
 * rail the hand has the whole foot.
 */

/** Degrees between neighbouring cards. */
const ARC = 2.6;
/**
 * How far the hovered card lifts, and how far its neighbours slide away.
 *
 * THE LIFT IS A TOKEN AND THIS READS IT, because two things have to agree about
 * it and only one of them is here. `.hand__slot` in `board.css` is a fixed
 * rectangle extended upward by exactly this much -- that padding is the whole
 * fix for a jitter where raising a card took its own hit box out from under the
 * pointer -- so the number lives in CSS and the motion value follows it. Two
 * literals would drift, and the failure when they do is the jitter coming back.
 *
 * It is smaller on a handheld, and the reason is not taste. `.hand` sits 2px
 * under the hint bar in the compact foot, so a 46px lift put the slot's top at
 * y=580 against a hint bar spanning 583-610: the raised card drew straight
 * over "Read" and "Back", and -- worse -- the slot's catchment covered the bar,
 * so moving the pointer up off the hand never fired `mouseleave` and the card
 * stayed raised. The ring and the preview rail already say which card is
 * chosen; the lift is confirming it a third time.
 */
const NEIGHBOUR_PUSH = 26;
/**
 * How far the outermost card sits below the middle one.
 *
 * Unbounded, a twelve-card hand drops its end cards 42px and pushes them through
 * the bottom of the viewport -- the same clipping `--hand-scale` was added to
 * prevent, arriving by a different route.
 */
const MAX_DROOP = 12;

/**
 * The arc, as a fraction of the hand's own half-width.
 *
 * This was `min(MAX_DROOP, distance ** 2 * 1.4)`, which is a parabola only until
 * it hits the ceiling -- and it hits it at |distance| >= 2.93, so from the fourth
 * card outwards *every* card sat at exactly 12. A seven-card hand curved; a
 * fifteen-card hand was flat across its outer two-thirds while `rotate` kept
 * growing, so the end cards were steeply tilted and no lower than their
 * neighbours, which reads as them riding up rather than fanning down.
 *
 * Normalising by `mid` keeps the shape a real parabola at any size: the
 * outermost card always droops exactly `MAX_DROOP` and everything between it and
 * the centre is on the curve.
 */
function droop(distance: number, mid: number): number {
  if (mid <= 0) return 0;
  return MAX_DROOP * (distance / mid) ** 2;
}

interface Props {
  cards: CardView[];
  playableOids: ReadonlySet<number>;
  /** Keyed by oid. A card absent from this map is playable. */
  reasons?: Record<string, UnplayableReason>;
  mana?: ManaView;
  selectedOid: number | null;
  /**
   * How wide a hand card is, as a multiple of `--card-w-base`.
   *
   * Solved against the foot's height and how crowded the fan is (see
   * `state/useZoomFit.ts`). Defaults to the designed ratio, which is also what the
   * zoom returns when it is pinned -- so a bare `<HandFan>` in a test renders the
   * geometry it always did.
   */
  cardScale?: number;
  onActivate: (card: CardView) => void;
  onDropOn: (card: CardView, zone: string) => void;
  disabled?: boolean;
}

export function HandFan({
  cards,
  playableOids,
  reasons = {},
  mana,
  selectedOid,
  cardScale = CARD_SCALE.hand,
  onActivate,
  onDropOn,
  disabled = false,
}: Props) {
  /*
   * WHICH CARD IS RAISED, BY OID -- never by index.
   *
   * It was an index, and an index into a list that changes under it is a bug
   * waiting for a turn to happen. Cast the third card and index 2 is a
   * different card: the wrong slot stays raised, with the preview rail reading
   * a card the pointer is not on. Neither the slot's `mouseleave` nor framer's
   * `onHoverEnd` fires for a node that unmounted, so nothing corrected it.
   *
   * By oid the whole class is gone with no effect to run: the card leaves the
   * hand, `findIndex` returns -1, and the fan renders unraised on the very same
   * commit. A drawn card shifts every slot along and the raised one is still
   * the card the pointer is over, which is the behaviour an index got wrong in
   * the other direction.
   */
  const [heldOid, setHeldOid] = useState<number | null>(null);
  const hover = useUiStore((s) => s.hover);
  const lift = -useHandLift();

  const hoveredIndex = heldOid === null ? -1 : cards.findIndex((c) => c.oid === heldOid);
  const hovered = hoveredIndex === -1 ? null : hoveredIndex;

  /*
   * ...and the store is told when that happens.
   *
   * The local state self-corrects by construction; `hoveredOid` is a global
   * somebody else has to write, and the card that left is still named in it.
   */
  useEffect(() => {
    if (heldOid === null || cards.some((c) => c.oid === heldOid)) return;
    setHeldOid(null);
    if (useUiStore.getState().hoveredOid === heldOid) hover(null);
  }, [cards, heldOid, hover]);

  // The one zone that cannot express its size as a CSS `calc()`: every slot is
  // positioned absolutely at `left: index * step`, and `step` derives from the
  // card width -- so the fan needs the resolved number, not a variable the
  // browser will substitute later.
  const cardW = cardWidthPx(useCardBase(), cardScale);

  const count = cards.length;
  const step = handStep(count, cardW, HAND_FAN_W);
  const width = count > 0 ? cardW + step * (count - 1) : 0;
  const mid = (count - 1) / 2;

  const hoveredCard = hovered === null ? null : cards[hovered];
  const hint = hoveredCard
    ? unplayableHint(hoveredCard, reasons[String(hoveredCard.oid)], mana)
    : null;

  return (
    /*
     * A backstop leave on the whole hand, and it is not redundant.
     *
     * A slot is a fixed rectangle extended upward by the lift, so the catchment
     * of the outermost slots reaches past the fan on three sides. A pointer that
     * exits through that overhang -- upward into the hint bar is the easy one to
     * do by accident -- leaves the slot's own `mouseleave` unfired, and the card
     * stays raised with the preview rail pinned to it for the rest of the game.
     * Leaving the hand outright cannot be ambiguous, so it is the honest place
     * to reset both halves.
     */
    <div
      className="hand"
      style={{ ["--card-w" as string]: cardWidthVar(cardScale) }}
      onMouseLeave={() => {
        setHeldOid(null);
        hover(null);
      }}
    >
      <div className="hand__rail" style={{ width }}>
        <AnimatePresence initial={false}>
          {cards.map((card, index) => {
            const distance = index - mid;
            const isHovered = hovered === index;
            // Neighbours slide away from whichever card is raised.
            const push =
              hovered === null || isHovered
                ? 0
                : (index < hovered ? -1 : 1) *
                  Math.max(0, NEIGHBOUR_PUSH - Math.abs(index - hovered) * 8);

            return (
              /*
               * The slot holds still and the card inside it moves.
               *
               * Both used to be one element: it carried the transform *and* the
               * pointer handlers, so raising the hovered card by 46px moved its
               * hit box out from under the cursor -- `mouseleave` fired, the card
               * settled back down under the cursor, `mouseenter` fired, and the
               * card jittered for as long as you rested near its edge. The slot is
               * a fixed rectangle now, extended upward by the lift so the pointer
               * stays inside it for the whole rise; only `.hand__lift` transforms.
               */
              <div
                className="hand__slot"
                key={card.oid}
                style={{ left: index * step, zIndex: isHovered ? 50 : index }}
                onMouseEnter={() => {
                  setHeldOid(card.oid);
                  hover(card.oid);
                }}
                onMouseLeave={() => {
                  setHeldOid((current) => (current === card.oid ? null : current));
                  hover(null);
                }}
              >
                <motion.div
                  className="hand__lift"
                  initial={{ opacity: 0, y: 90, scale: 0.8 }}
                  animate={{
                    opacity: 1,
                    x: push,
                    y: isHovered ? lift : droop(distance, mid),
                    rotate: isHovered ? 0 : distance * ARC,
                    scale: isHovered ? 1.14 : 1,
                  }}
                  exit={{ opacity: 0, y: -40, scale: 0.8, transition: settle }}
                  transition={bouncy}
                >
                  <Card
                    card={card}
                    variant="board"
                    lift={false}
                    ownsHover={false}
                    draggable={!disabled}
                    playable={playableOids.has(card.oid)}
                    selected={selectedOid === card.oid}
                    dimmed={!disabled && !playableOids.has(card.oid)}
                    onActivate={disabled ? undefined : onActivate}
                    onDropOn={onDropOn}
                  />
                </motion.div>
              </div>
            );
          })}
        </AnimatePresence>
      </div>
      {/*
        Why the hovered card is dim. Dimming alone said "no" without ever
        saying why -- "not enough mana", "sorcery, and it is not your main
        phase" and "no legal target" all looked identical.
      */}
      {hint && (
        <motion.div
          className="hand__hint"
          data-testid="unplayable-hint"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={settle}
        >
          {hint}
        </motion.div>
      )}
      {count === 0 && <div className="hand__empty">No cards in hand</div>}
    </div>
  );
}
