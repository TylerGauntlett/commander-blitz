/** Modal listing a zone's contents. Hidden zones show only what the server sent. */

import type { GameView } from "../api/types";
import { useUiStore } from "../state/uiStore";
import { CardTile } from "./CardTile";

export function ZonePeek({ state }: { state: GameView }) {
  const peekZone = useUiStore((s) => s.peekZone);
  const closePeek = useUiStore((s) => s.closePeek);
  if (!peekZone) return null;

  const player = state.players[peekZone.pid];
  const cards =
    peekZone.zone === "hand"
      ? player.hand
      : peekZone.zone === "graveyard"
        ? player.graveyard
        : peekZone.zone === "exile"
          ? player.exile
          : player.command;

  return (
    <div className="modal-backdrop" onClick={closePeek}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <header className="modal__header">
          <h2>
            {player.name} - {peekZone.zone}
          </h2>
          <button type="button" className="ghost-button" onClick={closePeek}>
            Close
          </button>
        </header>
        <div className="modal__body">
          {cards === null ? (
            <p className="modal__hidden">
              Hidden: {player.hand_count} card{player.hand_count === 1 ? "" : "s"}.
            </p>
          ) : cards.length === 0 ? (
            <p className="modal__hidden">Empty.</p>
          ) : (
            <div className="modal__cards">
              {cards.map((card) => (
                <CardTile key={card.oid} card={card} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
