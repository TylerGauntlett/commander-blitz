/**
 * Declaring attackers and blockers.
 *
 * The engine declares incrementally (one `add_attacker` at a time) but a player
 * thinks in whole attacks, so the whole set is staged locally and posted once
 * to `/declare`. Staging keys by attacker oid, which is exactly the constraint
 * the server enforces: one creature, one assignment.
 */

import { AnimatePresence, motion } from "motion/react";
import type { GameView, LegalAction } from "../../api/types";
import { availableAttackers, blockableBy, defendersFor } from "../../logic/actionMatch";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy, ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";

interface Props {
  state: GameView;
  actions: LegalAction[];
  onDeclare: (kind: "attackers" | "blockers", pairs: [number, number][]) => void;
  onSkip: (actionId: string) => void;
  disabled: boolean;
}

export function CombatPanel({ state, actions, onDeclare, onSkip, disabled }: Props) {
  const pending = state.pending;
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const unstageAttack = useUiStore((s) => s.unstageAttack);
  const unstageBlock = useUiStore((s) => s.unstageBlock);
  const selectedOid = useUiStore((s) => s.selectedOid);

  const isAttack = pending?.kind === "declare_attackers";
  const isBlock = pending?.kind === "declare_blockers";
  const mine = pending !== null && pending.player === state.seat;
  const open = mine && (isAttack || isBlock) && !state.game_over;

  const name = (oid: number) => findCard(state, oid)?.name ?? `#${oid}`;

  const attackPairs = Object.entries(stagedAttacks).map(
    ([attacker, defender]) => [Number(attacker), defender] as [number, number],
  );
  const blockPairs = Object.entries(stagedBlocks).map(
    ([blocker, attacker]) => [Number(blocker), attacker] as [number, number],
  );

  const available = isAttack
    ? availableAttackers(actions)
    : [
        ...new Set(actions.filter((a) => a.kind === "add_blocker").map((a) => a.source_oid)),
      ].filter((oid): oid is number => oid !== null);

  // "Done"/finish is how you decline entirely.
  const finish = actions.find((a) => a.kind === "finish_declaration");

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="combat"
          data-testid="combat-panel"
          data-combat-kind={isAttack ? "attackers" : "blockers"}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          transition={ease}
        >
          <div className="combat__head">
            <h3 className="combat__title">
              {isAttack ? "Declare attackers" : "Declare blockers"}
            </h3>
            <p className="combat__hint">
              {isAttack
                ? selectedOid
                  ? "Click an opponent to send it at them."
                  : "Click your creatures to attack. Click again to call it back."
                : selectedOid
                  ? "Now click the attacker to block."
                  : "Click one of your creatures, then the attacker it blocks."}
            </p>
          </div>

          <div className="combat__staged">
            {isAttack &&
              attackPairs.map(([attacker, defender]) => (
                <button
                  type="button"
                  key={attacker}
                  className="chip chip--staged"
                  onClick={() => unstageAttack(attacker)}
                  title="Remove from the attack"
                >
                  {name(attacker)} &rarr; {state.players[defender]?.name ?? defender}
                </button>
              ))}
            {isBlock &&
              blockPairs.map(([blocker, attacker]) => (
                <button
                  type="button"
                  key={blocker}
                  className="chip chip--staged"
                  onClick={() => unstageBlock(blocker)}
                  title="Remove this block"
                >
                  {name(blocker)} blocks {name(attacker)}
                </button>
              ))}
            {(isAttack ? attackPairs : blockPairs).length === 0 && (
              <span className="combat__none">
                {available.length === 0
                  ? isAttack
                    ? "Nothing can attack."
                    : "Nothing can block."
                  : "Nothing staged yet."}
              </span>
            )}
          </div>

          <div className="combat__buttons">
            <motion.button
              type="button"
              className="btn btn--primary"
              disabled={disabled || (isAttack ? attackPairs : blockPairs).length === 0}
              onClick={() =>
                onDeclare(
                  isAttack ? "attackers" : "blockers",
                  isAttack ? attackPairs : blockPairs,
                )
              }
              whileHover={{ y: -2, scale: 1.03 }}
              whileTap={{ scale: 0.96 }}
              transition={bouncy}
              data-testid="combat-confirm"
            >
              {isAttack
                ? `Attack with ${attackPairs.length}`
                : `Confirm ${blockPairs.length} block${blockPairs.length === 1 ? "" : "s"}`}
            </motion.button>
            {finish && (
              <button
                type="button"
                className="btn btn--ghost"
                disabled={disabled}
                onClick={() => onSkip(finish.id)}
                data-testid="combat-skip"
              >
                {isAttack ? "No attacks" : "No blocks"}
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * Which defenders a staged attacker could be pointed at.
 *
 * Exported so the board can cycle a creature through its legal targets on
 * repeated clicks rather than opening a menu.
 */
export function nextDefender(
  actions: LegalAction[],
  attackerOid: number,
  current: number | undefined,
): number | null {
  const options = defendersFor(actions, attackerOid);
  if (options.length === 0) return null;
  if (current === undefined) return options[0];
  const index = options.indexOf(current);
  // Past the end means "stop attacking with this one".
  return index === -1 || index === options.length - 1 ? null : options[index + 1];
}

/** Attackers this blocker may legally be assigned to. */
export function legalBlockTargets(actions: LegalAction[], blockerOid: number): number[] {
  return blockableBy(actions, blockerOid);
}
