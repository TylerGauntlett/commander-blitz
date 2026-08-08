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
 *
 * The container's size never changes. Fanning used to animate `width` on an
 * in-flow flex item, which wrapped the lane onto new rows, grew the mat, and
 * flickered the scrollbar -- the whole board slid out from under the cursor for
 * the length of a spring, which made picking a blocker out of a stack
 * impossible. Only transforms move here, so neighbours never notice.
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
/** Fanned members overlap by this much of a card, so each stays clickable. */
const FAN_STEP_RATIO = 0.58;
/**
 * Widest a fan may spread, in card widths. The mat scrolls on overflow, so an
 * unbounded fan of twelve basics would be clipped rather than reachable; past
 * this the step compresses and the cards overlap more instead.
 */
const MAX_FAN_RATIO = 3.2;

interface Props {
  group: CardStackGroup;
  cardWidth: number;
  draggable?: boolean;
  isPlayable?: (card: CardView) => boolean;
  hasAbility?: (card: CardView) => boolean;
  abilityLabel?: (card: CardView) => string | null;
  isTargetable?: (card: CardView) => boolean;
  isStaged?: (card: CardView) => boolean;
  isSelected?: (card: CardView) => boolean;
  onActivate?: (card: CardView) => void;
  onDropOn?: (card: CardView, zone: string) => void;
}

export function CardStack({
  group,
  cardWidth,
  draggable = false,
  isPlayable,
  hasAbility,
  abilityLabel,
  isTargetable,
  isStaged,
  isSelected,
  onActivate,
  onDropOn,
}: Props) {
  const openStack = useUiStore((s) => s.openStack);
  const openStackGroup = useUiStore((s) => s.openStackGroup);
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const open = openStack === group.key && group.count > 1;

  /*
   * A tapped permanent lies on its side, so its footprint is landscape.
   *
   * `stackKey` includes `tapped`, so a group is either all tapped or all
   * untapped and one orientation covers the whole stack. Sizing the container
   * for it is what lets a lane of tapped lands reflow instead of each one
   * overlapping its neighbour.
   */
  const tapped = group.top.tapped === true;
  const footprintW = tapped ? cardWidth * 1.4 : cardWidth;
  const footprintH = tapped ? cardWidth : cardWidth * 1.4;

  const closedWidth = footprintW + Math.min(group.count - 1, MAX_PLIES) * PLY_X;
  // Spread symmetrically about the closed footprint's centre, so opening a stack
  // pushes cards out both ways rather than always to the right.
  const step =
    group.count > 1
      ? Math.min(footprintW * FAN_STEP_RATIO, (footprintW * MAX_FAN_RATIO) / (group.count - 1))
      : 0;
  const centre = closedWidth / 2 - footprintW / 2;

  return (
    <motion.div
      className={open ? "cardstack cardstack--open" : "cardstack"}
      style={{ width: closedWidth, height: footprintH }}
      onMouseEnter={() => group.count > 1 && openStackGroup(group.key)}
      onMouseLeave={() => openStackGroup(null)}
      data-stack-key={group.key}
      data-stack-count={group.count}
      data-stack-open={open || undefined}
    >
      {group.cards.map((card, index) => {
        const offset = Math.min(index, MAX_PLIES);
        return (
          <motion.div
            className="cardstack__slot"
            key={card.oid}
            animate={{
              x: open ? centre + (index - (group.count - 1) / 2) * step : offset * PLY_X,
              y: open ? 0 : offset * PLY_Y,
            }}
            transition={settle}
            // group.top is cards[0], so it has to be the one drawn on top and
            // the one a click on a closed stack lands on. The hovered member
            // beats all of them, so a fanned card is never half-behind the one
            // to its right when you go to click it.
            style={{
              zIndex: card.oid === hoveredOid ? group.count + 1 : group.count - index,
            }}
          >
            <Card
              card={card}
              draggable={draggable}
              playable={isPlayable?.(card) ?? false}
              hasAbility={hasAbility?.(card) ?? false}
              abilityLabel={abilityLabel?.(card) ?? null}
              targetable={isTargetable?.(card) ?? false}
              staged={isStaged?.(card) ?? false}
              selected={isSelected?.(card) ?? false}
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
