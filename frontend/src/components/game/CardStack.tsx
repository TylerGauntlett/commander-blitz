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
 * The container's size never changes *for anything this component does*. Fanning
 * used to animate `width` on an in-flow flex item, which wrapped the lane onto new
 * rows, grew the mat, and flickered the scrollbar -- the whole board slid out from
 * under the cursor for the length of a spring, which made picking a blocker out of
 * a stack impossible. Only transforms move here, so neighbours never notice.
 *
 * One thing outside this component does resize it: the zoom (`state/useZoomFit.ts`)
 * re-solves `cardWidth`, and `.cardstack` in cards.css transitions `width` and
 * `height` so the container arrives with its cards instead of snapping ahead of
 * them. That is not the case the paragraph above forbids. A zoom change reflows the
 * lane by definition -- as a permanent entering play does -- and it cannot land
 * mid-drag, because it is triggered by a game-state change or a viewport resize and
 * a drag produces neither until it has ended. The rule that still holds without
 * exception: **nothing driven by hover may change this container's size.**
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
import {
  ATTACH_X_RATIO,
  ATTACH_Y_RATIO,
  MAX_PLIES,
  PLY_X,
} from "../../logic/cardStackGeometry";
import type { CardStackGroup } from "../../logic/stacking";
import { settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { Card } from "./Card";

/*
 * `PLY_X`, `MAX_PLIES` and the two attachment ratios live in
 * `logic/cardStackGeometry.ts`. They describe how much room a closed stack takes,
 * and `logic/zoomFit.ts` has to predict that at a card width nothing has rendered
 * at yet -- so they are shared rather than duplicated. What stays here is
 * everything that is only about drawing.
 */

/** How far each hidden ply lifts as it peeks out. */
const PLY_Y = -4;
/**
 * Above every other member of this unit. Whatever the pointer is on has to be
 * whole: a half-covered card is one you cannot read and can only half click.
 */
const TOP_Z = 39;
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

  /*
   * A host and its attachments are one object on the table, so they are one
   * container here -- but the container has to be *sized* for the whole unit,
   * or the peeking aura would lie across whatever permanent is next to it.
   *
   * This is static sizing off the attachment count, which is a different thing
   * from the hover fan the file header warns about: that one may not animate
   * `width`, because a live drag must not reflow the lane underneath itself.
   */
  const attachX = cardWidth * ATTACH_X_RATIO;
  const attachY = cardWidth * ATTACH_Y_RATIO;
  const attachCount = group.attachments.length;

  // The plies' own width, which is what the fan is centred on. A host is always
  // a group of one (see `stackCards`), so the two never both apply -- but the
  // fan must stay measured against the cards it spreads, not the container.
  const plyWidth = footprintW + Math.min(group.count - 1, MAX_PLIES) * PLY_X;
  const closedWidth = plyWidth + attachCount * attachX;
  const closedHeight = footprintH + attachCount * attachY;
  // Spread symmetrically about the closed footprint's centre, so opening a stack
  // pushes cards out both ways rather than always to the right.
  const step =
    group.count > 1
      ? Math.min(footprintW * FAN_STEP_RATIO, (footprintW * MAX_FAN_RATIO) / (group.count - 1))
      : 0;
  const centre = plyWidth / 2 - footprintW / 2;

  return (
    <motion.div
      className={open ? "cardstack cardstack--open" : "cardstack"}
      style={{ width: closedWidth, height: closedHeight }}
      onMouseEnter={() => group.count > 1 && openStackGroup(group.key)}
      onMouseLeave={() => openStackGroup(null)}
      data-stack-key={group.key}
      data-stack-count={group.count}
      data-stack-attached={attachCount || undefined}
      data-stack-open={open || undefined}
    >
      {/*
        Auras and equipment, drawn under the permanent they are on -- the way
        they sit on a table, and the reason they are in this container at all
        rather than loose in the global lane. Each is still a whole `Card`: it
        can be hovered for its face, targeted, and clicked.

        Rendered before the host so the host's slot wins the paint order at
        equal z, and stepped down through `attachCount - index` so an aura never
        covers the one printed under it.
      */}
      {group.attachments.map((card, index) => (
        <motion.div
          className="cardstack__slot cardstack__attach"
          key={card.oid}
          animate={{ x: (index + 1) * attachX, y: (index + 1) * attachY }}
          transition={settle}
          style={{
            zIndex: card.oid === hoveredOid ? TOP_Z : attachCount - index - 1,
          }}
        >
          <Card
            card={card}
            playable={isPlayable?.(card) ?? false}
            hasAbility={hasAbility?.(card) ?? false}
            abilityLabel={abilityLabel?.(card) ?? null}
            targetable={isTargetable?.(card) ?? false}
            staged={isStaged?.(card) ?? false}
            selected={isSelected?.(card) ?? false}
            onActivate={onActivate}
          />
        </motion.div>
      ))}

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
              zIndex: card.oid === hoveredOid ? TOP_Z : attachCount + group.count - index,
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
