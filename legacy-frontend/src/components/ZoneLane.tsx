/** One droppable band of the battlefield. */

import { useDroppable } from "@dnd-kit/core";
import type { CardView } from "../api/types";
import type { Lane } from "../logic/zoneGrouping";
import { CardTile } from "./CardTile";

interface Props {
  lane: Lane;
  pid: number;
  cards: CardView[];
  /** Highlighted because the card being dragged can legally be played here. */
  active?: boolean;
  compact?: boolean;
  targetableOids?: Set<number>;
  stagedOids?: Set<number>;
  onCardClick?: (card: CardView) => void;
}

export function ZoneLane({
  lane,
  pid,
  cards,
  active = false,
  compact = false,
  targetableOids,
  stagedOids,
  onCardClick,
}: Props) {
  const { setNodeRef, isOver } = useDroppable({
    id: `lane-${pid}-${lane}`,
    data: { lane, pid },
  });

  const classes = [
    "zone-lane",
    active ? "zone-lane--active" : "",
    isOver && active ? "zone-lane--over" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div ref={setNodeRef} className={classes} data-lane={lane}>
      <div className="zone-lane__label">
        {lane}
        <span className="zone-lane__count">{cards.length}</span>
      </div>
      <div className="zone-lane__cards">
        {cards.map((card) => (
          <CardTile
            key={card.oid}
            card={card}
            compact={compact}
            targetable={targetableOids?.has(card.oid)}
            staged={stagedOids?.has(card.oid)}
            draggable={lane === "Creatures"}
            onClick={onCardClick}
          />
        ))}
      </div>
    </div>
  );
}
