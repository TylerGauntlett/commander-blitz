/**
 * A pile of interchangeable permanents drawn as one.
 *
 * Twelve basics and a row of tokens push the interesting permanents off the
 * screen, so identical ones collapse into a stack with a count badge. Hovering
 * fans it out; every member stays individually clickable.
 *
 * Every member is always mounted, even when hidden behind the top card. That is
 * deliberate: mounting and unmounting on hover would destroy each card's
 * `layoutId` identity, and a Forest tapped for mana would pop instead of
 * turning. Closed and open are the same nodes at different offsets.
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
import type { CardStackGroup } from "../../logic/stacking";
import { settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { Card } from "./Card";

/** How far each hidden ply peeks out from under the top card. */
const PLY_X = 7;
const PLY_Y = -4;
/** Beyond this many, plies sit on top of each other: the badge carries the count. */
const MAX_PLIES = 2;

interface Props {
  group: CardStackGroup;
  cardWidth: number;
  draggable?: boolean;
  isPlayable?: (card: CardView) => boolean;
  isTargetable?: (card: CardView) => boolean;
  isStaged?: (card: CardView) => boolean;
  onActivate?: (card: CardView) => void;
  onDropOn?: (card: CardView, zone: string) => void;
}

export function CardStack({
  group,
  cardWidth,
  draggable = false,
  isPlayable,
  isTargetable,
  isStaged,
  onActivate,
  onDropOn,
}: Props) {
  const openStack = useUiStore((s) => s.openStack);
  const openStackGroup = useUiStore((s) => s.openStackGroup);
  const open = openStack === group.key && group.count > 1;

  const gap = 10;
  const closedWidth = cardWidth + Math.min(group.count - 1, MAX_PLIES) * PLY_X;
  const openWidth = group.count * cardWidth + (group.count - 1) * gap;

  return (
    <motion.div
      className={open ? "cardstack cardstack--open" : "cardstack"}
      animate={{ width: open ? openWidth : closedWidth }}
      transition={settle}
      style={{ height: cardWidth * 1.4 }}
      onMouseEnter={() => group.count > 1 && openStackGroup(group.key)}
      onMouseLeave={() => openStackGroup(null)}
      data-stack-key={group.key}
      data-stack-count={group.count}
    >
      {group.cards.map((card, index) => {
        const offset = Math.min(index, MAX_PLIES);
        return (
          <motion.div
            className="cardstack__slot"
            key={card.oid}
            animate={{
              x: open ? index * (cardWidth + gap) : offset * PLY_X,
              y: open ? 0 : offset * PLY_Y,
            }}
            transition={settle}
            style={{ zIndex: index + 1 }}
          >
            <Card
              card={card}
              draggable={draggable}
              playable={isPlayable?.(card) ?? false}
              targetable={isTargetable?.(card) ?? false}
              staged={isStaged?.(card) ?? false}
              lift={open || group.count === 1}
              onActivate={onActivate}
              onDropOn={onDropOn}
            />
          </motion.div>
        );
      })}

      {group.count > 1 && !open && (
        <span className="cardstack__count" aria-label={`${group.count} copies`}>
          &times;{group.count}
        </span>
      )}
    </motion.div>
  );
}
