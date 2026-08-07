/** The viewer's hand: draggable, and clickable as a fallback. */

import { useDroppable } from "@dnd-kit/core";
import type { CardView, LegalAction } from "../api/types";
import { actionsForCard } from "../logic/actionMatch";
import { CardTile } from "./CardTile";

interface Props {
  cards: CardView[];
  actions: LegalAction[];
  onPlay: (card: CardView) => void;
}

export function Hand({ cards, actions, onPlay }: Props) {
  const { setNodeRef } = useDroppable({ id: "hand" });

  return (
    <div ref={setNodeRef} className="hand">
      <div className="hand__label">Hand ({cards.length})</div>
      <div className="hand__cards">
        {cards.map((card) => (
          <CardTile
            key={card.oid}
            card={card}
            draggable
            playable={actionsForCard(actions, card.oid).length > 0}
            onClick={onPlay}
          />
        ))}
        {cards.length === 0 && <span className="hand__empty">No cards in hand</span>}
      </div>
    </div>
  );
}
