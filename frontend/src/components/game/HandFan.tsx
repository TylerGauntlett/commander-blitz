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
import type { CardView } from "../../api/types";
import { bouncy, settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { Card } from "./Card";

/** Cards overlap once the hand is wider than this. */
const MAX_SPREAD = 118;
const CARD_W = 146;
/** Degrees between neighbouring cards. */
const ARC = 2.6;
/** How far the hovered card lifts, and how far its neighbours slide away. */
const HOVER_LIFT = -46;
const NEIGHBOUR_PUSH = 26;

interface Props {
  cards: CardView[];
  playableOids: ReadonlySet<number>;
  selectedOid: number | null;
  onActivate: (card: CardView) => void;
  onDropOn: (card: CardView, zone: string) => void;
  disabled?: boolean;
}

export function HandFan({
  cards,
  playableOids,
  selectedOid,
  onActivate,
  onDropOn,
  disabled = false,
}: Props) {
  const [hovered, setHovered] = useState<number | null>(null);
  const hover = useUiStore((s) => s.hover);

  const count = cards.length;
  const step = count > 1 ? Math.min(MAX_SPREAD, (760 - CARD_W) / (count - 1)) : 0;
  const width = count > 0 ? CARD_W + step * (count - 1) : 0;
  const mid = (count - 1) / 2;

  return (
    <div className="hand" style={{ ["--card-w" as string]: `${CARD_W}px` }}>
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
                  y: isHovered ? HOVER_LIFT : Math.abs(distance) ** 2 * 1.4,
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
      {count === 0 && <div className="hand__empty">No cards in hand</div>}
    </div>
  );
}
