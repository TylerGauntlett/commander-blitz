/**
 * The action bar.
 *
 * Every legal action is reachable from here, so the whole game is playable
 * without ever dragging anything. Drag-and-drop is a shortcut, not a
 * requirement.
 */

import type { GameView, LegalAction } from "../api/types";
import { decisionPrompt, turnLabel } from "../logic/labels";

interface Props {
  state: GameView;
  actions: LegalAction[];
  busy: boolean;
  onAct: (action: LegalAction) => void;
  onUndo: () => void;
  onNewGame: () => void;
}

/** Actions handled by dedicated UI (drag to a lane, the combat overlay). */
const HANDLED_ELSEWHERE = new Set(["add_attacker", "add_blocker"]);

export function PriorityBar({ state, actions, busy, onAct, onUndo, onNewGame }: Props) {
  const isCombatDeclaration =
    state.pending?.kind === "declare_attackers" || state.pending?.kind === "declare_blockers";

  const shown = actions.filter(
    (action) => !(isCombatDeclaration && HANDLED_ELSEWHERE.has(action.kind)),
  );

  return (
    <div className="priority-bar">
      <div className="priority-bar__status">
        <span className="priority-bar__turn">{turnLabel(state)}</span>
        <span className="priority-bar__prompt">{decisionPrompt(state)}</span>
      </div>
      <div className="priority-bar__actions">
        {shown.map((action) => (
          <button
            type="button"
            key={action.id}
            className={`action-button action-button--${action.kind}`}
            disabled={busy}
            onClick={() => onAct(action)}
          >
            {action.label}
          </button>
        ))}
        {shown.length === 0 && !state.game_over && (
          <span className="priority-bar__waiting">Opponent is thinking...</span>
        )}
      </div>
      <div className="priority-bar__controls">
        <button type="button" className="ghost-button" disabled={busy} onClick={onUndo}>
          Undo
        </button>
        <button type="button" className="ghost-button" onClick={onNewGame}>
          New game
        </button>
      </div>
    </div>
  );
}
