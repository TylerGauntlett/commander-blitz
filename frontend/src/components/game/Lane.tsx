/**
 * One band of the battlefield -- lands, creatures, or everything else.
 *
 * The lane is also a drop target: `data-dropzone` is what `Card`'s drag-end
 * hit test reads. Dropping is only ever a shortcut for choosing a legal action,
 * so the lane highlights when, and only when, the server has offered one.
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
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
      data-testid={`lane-${pid}-${lane.replace(/\W+/g, "-")}`}
      layout
      transition={settle}
      style={{ ["--card-w" as string]: cardWidthVar(cardScale) }}
    >
      <div className="lane__label">
        <span>{LANE_LABELS[lane]}</span>
        <span className="lane__count tabular">{cards.length}</span>
      </div>
      <div className="lane__cards">
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
