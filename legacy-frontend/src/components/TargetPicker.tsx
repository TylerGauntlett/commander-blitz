/**
 * Disambiguating a play that has several legal target choices.
 *
 * The server already enumerated one action per legal target tuple, so this is
 * purely a menu over those actions -- the client never decides what is legal.
 */

import type { GameView, LegalAction } from "../api/types";

interface Props {
  state: GameView;
  actions: LegalAction[];
  busy: boolean;
  onPick: (action: LegalAction) => void;
  onCancel: () => void;
}

export function TargetPicker({ state, actions, busy, onPick, onCancel }: Props) {
  if (actions.length === 0) return null;
  const cardName = state.players[state.seat].hand?.find(
    (card) => card.oid === actions[0].source_oid,
  )?.name;

  return (
    <div className="target-picker">
      <div className="target-picker__title">Choose targets for {cardName ?? "this spell"}</div>
      <div className="target-picker__options">
        {actions.map((action) => (
          <button
            type="button"
            key={action.id}
            className="action-button"
            disabled={busy}
            onClick={() => onPick(action)}
          >
            {action.label}
          </button>
        ))}
      </div>
      <button type="button" className="ghost-button" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}
