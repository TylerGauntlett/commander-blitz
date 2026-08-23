/**
 * One band of the battlefield -- lands, creatures, or everything else.
 *
 * The lane is also a drop target: `data-dropzone` is what `Card`'s drag-end
 * hit test reads. Dropping is only ever a shortcut for choosing a legal action,
 * so the lane highlights when, and only when, the server has offered one.
 *
 * A **vacant** lane is additionally a focus stop, and only a vacant one. A pad
 * has no drag, so the ring has to be able to reach the destination itself --
 * but a lane with cards in it is already reachable through those cards, and
 * making it a stop as well would put a ring around the whole band on the way
 * past every card in it. So the stop exists exactly when there is nothing else
 * there to land on, which is also exactly when the player needs it.
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
import { stopId } from "../../input/stops";
import { cardWidthPx, cardWidthVar } from "../../logic/cardSize";
import { splitActionable, stackCards } from "../../logic/stacking";
import { LANE_LABELS, type Lane as LaneName } from "../../logic/zoneGrouping";
import { settle } from "../../motion/springs";
import { useCardBase } from "../../state/useCardBase";
import { CardStack } from "./CardStack";

/** Lane name -> the modifier CSS styles it by. */
const LANE_SLUG: Record<LaneName, string> = {
  Creatures: "creatures",
  "Artifacts & Enchantments": "global",
  Lands: "lands",
};

interface Props {
  lane: LaneName;
  pid: number;
  cards: CardView[];
  /** Host oid -> auras and equipment drawn tucked behind it. */
  attachments?: ReadonlyMap<number, CardView[]>;
  cardScale: number;
  /** Highlight as a legal destination for whatever is being dragged. */
  active?: boolean;
  draggable?: boolean;
  /** Oids named by some legal action -- these are never hidden inside a stack. */
  actionableOids: ReadonlySet<number>;
  isPlayable?: (card: CardView) => boolean;
  hasAbility?: (card: CardView) => boolean;
  abilityLabel?: (card: CardView) => string | null;
  isTargetable?: (card: CardView) => boolean;
  isStaged?: (card: CardView) => boolean;
  isSelected?: (card: CardView) => boolean;
  onActivate?: (card: CardView) => void;
  onDropOn?: (card: CardView, zone: string) => void;
}

export function Lane({
  lane,
  pid,
  cards,
  attachments,
  cardScale,
  active = false,
  draggable = false,
  actionableOids,
  isPlayable,
  hasAbility,
  abilityLabel,
  isTargetable,
  isStaged,
  isSelected,
  onActivate,
  onDropOn,
}: Props) {
  const groups = stackCards(cards, attachments).flatMap((group) =>
    splitActionable(group, actionableOids),
  );

  // The lane hands CSS a `calc()` so the cards themselves resize smoothly, and
  // hands `CardStack` a real number, because a stack's container has to be
  // measured in JavaScript -- a tapped permanent's footprint is landscape, and
  // that width cannot be expressed as a static rule.
  const cardWidth = cardWidthPx(useCardBase(), cardScale);

  return (
    <motion.div
      // An empty lane keeps its full height rather than collapsing: it is a
      // reserved slot, not a gap. Collapsing meant the first creature of the
      // game shoved the land row down by a card and killing it shoved the row
      // back up, which moved every drop target mid-decision. See board.css.
      className={[
        active ? "lane lane--active" : "lane",
        `lane--${LANE_SLUG[lane]}`,
        cards.length === 0 ? "lane--vacant" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-dropzone={`lane:${pid}:${lane}`}
      data-stop={draggable && cards.length === 0 ? stopId.lane(pid, lane) : undefined}
      data-testid={`lane-${pid}-${lane.replace(/\W+/g, "-")}`}
      layout
      transition={settle}
      style={{ ["--card-w" as string]: cardWidthVar(cardScale) }}
    >
      <div className="lane__label">
        {/* Named so the handheld sheet can truncate the word without touching
            the count beside it -- see `.band--front .lane__label` there. */}
        <span className="lane__name">{LANE_LABELS[lane]}</span>
        <span className="lane__count tabular">{cards.length}</span>
      </div>
      {/*
        `data-fan` marks a row that lays cards out along one axis and is allowed
        to run out of room. The gate in `e2e/handheldAssert.ts` measures every
        one of them for overflow, because a row that spills is invisible under
        `overflow: hidden` -- the mockup round found its hand 79px past the foot
        and sitting on a button that had quietly stopped being clickable, with
        the page reporting no overflow at all.
      */}
      <div className="lane__cards" data-fan>
        {groups.map((group) => (
          <CardStack
            key={group.key}
            group={group}
            cardWidth={cardWidth}
            draggable={draggable}
            isPlayable={isPlayable}
            hasAbility={hasAbility}
            abilityLabel={abilityLabel}
            isTargetable={isTargetable}
            isStaged={isStaged}
            isSelected={isSelected}
            onActivate={onActivate}
            onDropOn={onDropOn}
          />
        ))}
        {cards.length === 0 && <span className="lane__empty">&mdash;</span>}
      </div>
    </motion.div>
  );
}
