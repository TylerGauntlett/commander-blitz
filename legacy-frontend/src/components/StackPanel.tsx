/** The stack, top item first -- the order it will resolve in. */

import type { GameView } from "../api/types";

export function StackPanel({ state }: { state: GameView }) {
  if (state.stack.length === 0) {
    return (
      <div className="stack-panel stack-panel--empty">
        <div className="stack-panel__label">Stack</div>
        <span className="stack-panel__none">empty</span>
      </div>
    );
  }

  const items = [...state.stack].reverse();
  return (
    <div className="stack-panel">
      <div className="stack-panel__label">Stack ({items.length})</div>
      <ol className="stack-panel__items">
        {items.map((item, index) => (
          <li
            key={item.sid}
            className={index === 0 ? "stack-item stack-item--top" : "stack-item"}
          >
            <span className="stack-item__name">{item.name}</span>
            <span className="stack-item__owner">{state.players[item.controller].name}</span>
            {item.targets.length > 0 && (
              <span className="stack-item__targets">
                {"-> "}
                {item.targets
                  .map((ref) =>
                    ref.kind === "player"
                      ? state.players[ref.id].name
                      : (state.battlefield.find((c) => c.oid === ref.id)?.name ?? `#${ref.id}`),
                  )
                  .join(", ")}
              </span>
            )}
            {index === 0 && <span className="stack-item__badge">resolves next</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}
