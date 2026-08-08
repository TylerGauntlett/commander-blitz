/**
 * The player's hand, fanned.
 *
 * Cards sit on a shallow arc, rise to meet the pointer, and push their
 * neighbours aside. The fan owns hover entirely (`lift={false}` on the card),
 * because two components animating the same node's `y` produce a fight rather
 * than a lift.
 */

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import type { CardView, ManaView, UnplayableReason } from "../../api/types";
import { CARD_SCALE, cardWidthPx, cardWidthVar } from "../../logic/cardSize";
import { unplayableHint } from "../../logic/mana";
import { bouncy, settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { useCardBase } from "../../state/useCardBase";
import { Card } from "./Card";

/** Cards overlap once the hand is wider than this. */
const MAX_SPREAD = 118;
/**
 * How wide the fan may grow before cards start overlapping harder.
 *
 * The action bar used to take 420px out of this row; now that it lives in the
 * right rail the hand has the whole foot, so the rail that was capped at 760px
 * can breathe. Still a cap rather than `100%`: a two-card hand spread across
 * 1400px reads as two unrelated cards, not as a hand.
 */
const MAX_FAN_W = 1180;
/** Degrees between neighbouring cards. */
const ARC = 2.6;
/** How far the hovered card lifts, and how far its neighbours slide away. */
const HOVER_LIFT = -46;
const NEIGHBOUR_PUSH = 26;
/**
 * Ceiling on the arc's droop.
 *
 * The outer cards sit lower than the middle ones, by the square of their
 * distance from centre. Unbounded, a twelve-card hand drops its end cards 42px
 * and pushes them through the bottom of the viewport -- the same clipping the
 * `--hand-scale` rule was added to prevent, arriving by a different route.
 */
const MAX_DROOP = 12;

interface Props {
  cards: CardView[];
  playableOids: ReadonlySet<number>;
  /** Keyed by oid. A card absent from this map is playable. */
  reasons?: Record<string, UnplayableReason>;
  mana?: ManaView;
  selectedOid: number | null;
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
  onActivate,
  onDropOn,
  disabled = false,
}: Props) {
  const [hovered, setHovered] = useState<number | null>(null);
  const hover = useUiStore((s) => s.hover);

  // The one zone that cannot express its size as a CSS `calc()`: every slot is
  // positioned absolutely at `left: index * step`, and `step` derives from the
  // card width -- so the fan needs the resolved number, not a variable the
  // browser will substitute later.
  const cardW = cardWidthPx(useCardBase(), CARD_SCALE.hand);

  const count = cards.length;
  const step = count > 1 ? Math.min(MAX_SPREAD, (MAX_FAN_W - cardW) / (count - 1)) : 0;
  const width = count > 0 ? cardW + step * (count - 1) : 0;
  const mid = (count - 1) / 2;

  const hoveredCard = hovered === null ? null : cards[hovered];
  const hint = hoveredCard
    ? unplayableHint(hoveredCard, reasons[String(hoveredCard.oid)], mana)
    : null;

  return (
    <div className="hand" style={{ ["--card-w" as string]: cardWidthVar(CARD_SCALE.hand) }}>
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
              <motion.div
                className="hand__slot"
                key={card.oid}
                style={{ left: index * step, zIndex: isHovered ? 50 : index }}
                initial={{ opacity: 0, y: 90, scale: 0.8 }}
                animate={{
                  opacity: 1,
                  x: push,
                  y: isHovered
                    ? HOVER_LIFT
                    : Math.min(MAX_DROOP, Math.abs(distance) ** 2 * 1.4),
                  rotate: isHovered ? 0 : distance * ARC,
                  scale: isHovered ? 1.14 : 1,
                }}
                exit={{ opacity: 0, y: -40, scale: 0.8, transition: settle }}
                transition={bouncy}
                onMouseEnter={() => {
                  setHovered(index);
                  hover(card.oid);
                }}
                onMouseLeave={() => {
                  setHovered((current) => (current === index ? null : current));
                  hover(null);
                }}
              >
                <Card
                  card={card}
                  detail
                  lift={false}
                  draggable={!disabled}
                  playable={playableOids.has(card.oid)}
                  selected={selectedOid === card.oid}
                  dimmed={!disabled && !playableOids.has(card.oid)}
                  onActivate={disabled ? undefined : onActivate}
                  onDropOn={onDropOn}
                />
              </motion.div>
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
