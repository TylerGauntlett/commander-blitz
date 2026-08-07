/**
 * The stack, top first.
 *
 * Reversed on purpose: what resolves next should be what you read first.
 */

import { AnimatePresence, motion } from "motion/react";
import type { GameView } from "../../api/types";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy } from "../../motion/springs";

interface Props {
  state: GameView;
}

export function StackPanel({ state }: Props) {
  const items = [...state.stack].reverse();

  return (
    <section className="stackpanel" data-testid="stack-panel">
      <h3 className="rail__title">
        Stack
        {items.length > 0 && <span className="rail__badge tabular">{items.length}</span>}
      </h3>
      <div className="stackpanel__items">
        <AnimatePresence initial={false}>
          {items.map((item, index) => {
            const targets = item.targets
              .map((ref) =>
                ref.kind === "player"
                  ? (state.players[ref.id]?.name ?? `P${ref.id}`)
                  : (findCard(state, ref.id)?.name ?? `#${ref.id}`),
              )
              .join(", ");

            return (
              <motion.div
                className={index === 0 ? "sitem sitem--next" : "sitem"}
                key={item.sid}
                initial={{ opacity: 0, x: -18, scale: 0.94 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 18, scale: 0.94 }}
                transition={bouncy}
                layout
              >
                <div className="sitem__row">
                  <span className="sitem__name">{item.name}</span>
                  {index === 0 && <span className="sitem__next">next</span>}
                </div>
                <div className="sitem__meta">
                  {state.players[item.controller]?.name ?? `P${item.controller}`}
                  {item.kind === "ability" ? " · ability" : ""}
                </div>
                {targets && <div className="sitem__targets">&rarr; {targets}</div>}
              </motion.div>
            );
          })}
        </AnimatePresence>
        {items.length === 0 && <div className="rail__empty">empty</div>}
      </div>
    </section>
  );
}
