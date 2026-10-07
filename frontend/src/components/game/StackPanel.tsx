/**
 * The stack, drawn as a stack.
 *
 * Top first, and reversed on purpose: what resolves next should be what you
 * read first. It used to be name + controller + targets as text rows, which is
 * a strange thing to show in a format where responding to the stack is the
 * skill -- so items are now real card faces piled with an offset, and the
 * targeting relationship is drawn by `CombatArrows` rather than spelled out.
 *
 * `data-stack-sid` on each wrapper is the arrow anchor. Deliberately not
 * `data-oid`: a triggered ability borrows its source permanent's face, and that
 * permanent is on the battlefield carrying the same oid already.
 */

import { AnimatePresence, motion } from "motion/react";
import type { GameView, StackItemView } from "../../api/types";
import { stopId } from "../../input/stops";
import { CARD_SCALE, cardWidthPx, cardWidthVar } from "../../logic/cardSize";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy } from "../../motion/springs";
import { useCardBase } from "../../state/useCardBase";
import { StaticCard } from "./Card";

/** How far each ply below the top peeks out. */
const PLY_Y = 26;

interface Props {
  state: GameView;
  /**
   * A press on a ply: a target, when a spell is waiting for one on the stack,
   * and otherwise a read. See `useTableGestures.onStackItem`.
   */
  onPress?: (item: StackItemView) => void;
}

export function StackPanel({ state, onPress }: Props) {
  const items = [...state.stack].reverse();
  // The pile is absolutely positioned, so its container height has to be
  // computed rather than declared -- which means a number, not a `calc()`.
  const cardW = cardWidthPx(useCardBase(), CARD_SCALE.stack);

  return (
    <section className="stackpanel" data-testid="stack-panel">
      <h3 className="rail__title">
        Stack
        {items.length > 0 && <span className="rail__badge tabular">{items.length}</span>}
      </h3>

      {items.length === 0 && <div className="rail__empty">empty</div>}

      {items.length > 0 && (
        <div
          className="stackpile"
          style={{
            ["--card-w" as string]: cardWidthVar(CARD_SCALE.stack),
            // The pile is absolutely positioned, so the container has to be
            // told how tall the whole thing came out.
            height: `${cardW * 1.4 + PLY_Y * (items.length - 1)}px`,
          }}
        >
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
                  className={
                    index === 0 ? "stackpile__ply stackpile__ply--next" : "stackpile__ply"
                  }
                  key={item.sid}
                  data-stack-sid={item.sid}
                  data-testid={`stack-item-${item.sid}`}
                  style={{ top: index * PLY_Y, zIndex: items.length - index }}
                  initial={{ opacity: 0, x: -20, scale: 0.92 }}
                  animate={{ opacity: 1, x: 0, scale: 1 }}
                  exit={{ opacity: 0, x: 24, scale: 0.92 }}
                  transition={bouncy}
                  layout
                  data-hint={targets ? `${item.name} → ${targets}` : item.name}
                >
                  {item.card ? (
                    <StaticCard card={item.card} variant="detail" />
                  ) : (
                    <div className="stackpile__ghost">{item.name}</div>
                  )}

                  {/*
                    THE PLY IS SOMEWHERE THE RING CAN STAND.

                    A stop over the whole ply, so walking the stack reads each
                    card in the rail (`data-preview-oid`) and `Y` opens it in
                    full -- the stack is what you answer, and it was the one
                    thing on the board you could not read before deciding to.
                    `stack:<sid>` and not `card:<oid>`: a trigger borrows its
                    source's face, and that permanent already wears the oid on
                    the battlefield. No `data-action-id`: a counterspell's
                    target chips live in the panel, and a press here resolves
                    to one of them the way a board card does.
                  */}
                  <button
                    type="button"
                    className="stackpile__hit"
                    aria-label={item.name}
                    data-stop={stopId.stack(item.sid)}
                    data-preview-oid={item.card?.oid}
                    onClick={() => onPress?.(item)}
                  />

                  <div className="stackpile__tag">
                    {index === 0 && <span className="stackpile__next">next</span>}
                    {item.kind === "ability" && (
                      <span className="stackpile__kind">ability</span>
                    )}
                    <span className="stackpile__who">
                      {state.players[item.controller]?.name ?? `P${item.controller}`}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </section>
  );
}
