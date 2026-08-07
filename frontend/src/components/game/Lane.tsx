/**
 * One band of the battlefield -- lands, creatures, or everything else.
 *
 * The lane is also a drop target: `data-dropzone` is what `Card`'s drag-end
 * hit test reads. Dropping is only ever a shortcut for choosing a legal action,
 * so the lane highlights when, and only when, the server has offered one.
 */

import { motion } from "motion/react";
import type { CardView } from "../../api/types";
import { splitActionable, stackCards } from "../../logic/stacking";
import type { Lane as LaneName } from "../../logic/zoneGrouping";
import { settle } from "../../motion/springs";
import { CardStack } from "./CardStack";

interface Props {
  lane: LaneName;
  pid: number;
  cards: CardView[];
  cardWidth: number;
  /** Highlight as a legal destination for whatever is being dragged. */
  active?: boolean;
  draggable?: boolean;
  /** Oids named by some legal action -- these are never hidden inside a stack. */
  actionableOids: ReadonlySet<number>;
  isPlayable?: (card: CardView) => boolean;
  isTargetable?: (card: CardView) => boolean;
  isStaged?: (card: CardView) => boolean;
  onActivate?: (card: CardView) => void;
  onDropOn?: (card: CardView, zone: string) => void;
}

export function Lane({
  lane,
  pid,
  cards,
  cardWidth,
  active = false,
  draggable = false,
  actionableOids,
  isPlayable,
  isTargetable,
  isStaged,
  onActivate,
  onDropOn,
}: Props) {
  const groups = stackCards(cards).flatMap((group) => splitActionable(group, actionableOids));

  return (
    <motion.div
      className={active ? "lane lane--active" : "lane"}
      data-dropzone={`lane:${pid}:${lane}`}
      data-testid={`lane-${pid}-${lane.replace(/\W+/g, "-")}`}
      layout
      transition={settle}
      style={{ ["--card-w" as string]: `${cardWidth}px` }}
    >
      <div className="lane__label">
        <span>{lane}</span>
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
            isTargetable={isTargetable}
            isStaged={isStaged}
            onActivate={onActivate}
            onDropOn={onDropOn}
          />
        ))}
        {cards.length === 0 && <span className="lane__empty">&mdash;</span>}
      </div>
    </motion.div>
  );
}
