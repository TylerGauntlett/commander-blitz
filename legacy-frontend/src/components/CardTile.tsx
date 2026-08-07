/**
 * A card, rendered as a text tile.
 *
 * No images anywhere in this app: it keeps the client entirely offline (matching
 * the engine's no-network card data) and removes a whole asset pipeline.
 */

import { useDraggable } from "@dnd-kit/core";
import type { CardView } from "../api/types";
import { counterBadges, manaPips, statLine } from "../logic/zoneGrouping";
import { useUiStore } from "../state/uiStore";

interface Props {
  card: CardView;
  draggable?: boolean;
  playable?: boolean;
  targetable?: boolean;
  staged?: boolean;
  compact?: boolean;
  onClick?: (card: CardView) => void;
}

export function CardTile({
  card,
  draggable = false,
  playable = false,
  targetable = false,
  staged = false,
  compact = false,
  onClick,
}: Props) {
  const hover = useUiStore((s) => s.hover);
  const selected = useUiStore((s) => s.selectedOid) === card.oid;

  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `card-${card.oid}`,
    data: { oid: card.oid },
    disabled: !draggable,
  });

  const classes = [
    "card-tile",
    compact ? "card-tile--compact" : "",
    card.tapped ? "card-tile--tapped" : "",
    playable ? "card-tile--playable" : "",
    targetable ? "card-tile--targetable" : "",
    staged ? "card-tile--staged" : "",
    selected ? "card-tile--selected" : "",
    card.attacking ? "card-tile--attacking" : "",
    card.blocking ? "card-tile--blocking" : "",
    isDragging ? "card-tile--dragging" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const stats = statLine(card);
  const badges = counterBadges(card);

  return (
    <div
      ref={setNodeRef}
      className={classes}
      onMouseEnter={() => hover(card.oid)}
      onMouseLeave={() => hover(null)}
      onClick={() => onClick?.(card)}
      title={`${card.name}\n${card.type_line}\n\n${card.oracle_text}`}
      {...listeners}
      {...attributes}
    >
      <div className="card-tile__top">
        <span className="card-tile__name">{card.name}</span>
        <span className="card-tile__cost">
          {manaPips(card.mana_cost).map((pip) => (
            <span className={`pip pip--${pip.symbol}`} key={pip.key}>
              {pip.symbol}
            </span>
          ))}
        </span>
      </div>
      {!compact && <div className="card-tile__type">{card.type_line}</div>}
      <div className="card-tile__bottom">
        <span className="card-tile__keywords">
          {card.keywords.map((keyword) => keyword.replace("_", " ")).join(", ")}
        </span>
        {stats && <span className="card-tile__stats">{stats}</span>}
      </div>
      {badges.length > 0 && (
        <div className="card-tile__counters">
          {badges.map((badge) => (
            <span className="counter-badge" key={badge}>
              {badge}
            </span>
          ))}
        </div>
      )}
      {card.is_commander && <span className="card-tile__commander">CMD</span>}
      {card.summoning_sick && card.types.includes("Creature") && (
        <span className="card-tile__sick" title="Summoning sick">
          zZ
        </span>
      )}
    </div>
  );
}
