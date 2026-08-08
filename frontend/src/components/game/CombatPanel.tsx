/**
 * Declaring attackers and blockers.
 *
 * The engine declares incrementally (one `add_attacker` at a time) but a player
 * thinks in whole attacks, so the whole set is staged locally and posted once
 * to `/declare`. Staging keys by attacker oid, which is exactly the constraint
 * the server enforces: one creature, one assignment.
 *
 * THIS PANEL OWNS THE COMBAT DECISION OUTRIGHT. Cycle 2 left the action bar
 * rendering the same decision beside it -- "Done blocking" in the rail, "No
 * blocks" here -- because the panel's buttons carried no action id, and standing
 * the bar down would have left the decision with no `data-action-id` anywhere,
 * breaking the guarantee at the top of `Table.tsx`. So the panel now carries the
 * ids instead: one option button per legal pair, exactly the list the bar's
 * overflow used to show, and the bar stands down like it does for a modal.
 *
 * The buttons still *stage* rather than commit, for the reason `Table.onBarAct`
 * documents: posting `add_blocker` one at a time has no inverse, and a single
 * blocker committed onto a menace attacker can strand the declaration with no
 * legal `finish_declaration` at all.
 */

import { AnimatePresence, motion } from "motion/react";
import type { GameView, LegalAction } from "../../api/types";
import { availableAttackers, blockableBy, defendersFor } from "../../logic/actionMatch";
import { autoBlocks } from "../../logic/autoBlock";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy, ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";

interface Props {
  state: GameView;
  actions: LegalAction[];
  onDeclare: (kind: "attackers" | "blockers", pairs: [number, number][]) => void;
  /** Stage or unstage one pair. The same handler the action bar used to use. */
  onStage: (actionId: string) => void;
  onSkip: (actionId: string) => void;
  disabled: boolean;
}

export function CombatPanel({ state, actions, onDeclare, onStage, onSkip, disabled }: Props) {
  const pending = state.pending;
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const stageBlock = useUiStore((s) => s.stageBlock);
  const selectedOid = useUiStore((s) => s.selectedOid);

  const isAttack = pending?.kind === "declare_attackers";
  const isBlock = pending?.kind === "declare_blockers";
  const mine = pending !== null && pending.player === state.seat;
  const open = mine && (isAttack || isBlock) && !state.game_over;

  const name = (oid: number) => findCard(state, oid)?.name ?? `#${oid}`;
  /** P/T for a staged creature, so the list reads as a board rather than names. */
  const stats = (oid: number) => {
    const card = findCard(state, oid);
    if (!card || card.power === null || card.toughness === null) return null;
    return `${card.power}/${card.toughness}`;
  };

  const attackPairs = Object.entries(stagedAttacks).map(
    ([attacker, defender]) => [Number(attacker), defender] as [number, number],
  );
  const blockPairs = Object.entries(stagedBlocks).map(
    ([blocker, attacker]) => [Number(blocker), attacker] as [number, number],
  );
  const staged = isAttack ? attackPairs : blockPairs;

  const available = isAttack
    ? availableAttackers(actions)
    : [
        ...new Set(actions.filter((a) => a.kind === "add_blocker").map((a) => a.source_oid)),
      ].filter((oid): oid is number => oid !== null);

  /** Every legal pair, one button each -- the bar's old overflow, moved here. */
  const options = actions.filter(
    (action) => action.kind === "add_attacker" || action.kind === "add_blocker",
  );

  /** True when this exact pair is already staged, so the button reads as on. */
  const isPairStaged = (action: LegalAction): boolean => {
    if (action.source_oid === null) return false;
    if (action.kind === "add_attacker") {
      const defender = action.targets.find((ref) => ref.kind === "player")?.id;
      return defender !== undefined && stagedAttacks[action.source_oid] === defender;
    }
    const attacker = action.targets.find((ref) => ref.kind === "object")?.id;
    return attacker !== undefined && stagedBlocks[action.source_oid] === attacker;
  };

  // "Do the obvious thing" for the two commonest decisions in the game. Both are
  // pure local staging, so they are exactly as reversible as clicking each
  // creature: every pairing is on screen and nothing reaches the server until
  // Confirm.
  const unstagedAttackers = available.filter((oid) => stagedAttacks[oid] === undefined);
  const attackWithAll = () => {
    for (const oid of unstagedAttackers) {
      const [first] = defendersFor(actions, oid);
      if (first !== undefined) stageAttack(oid, first);
    }
  };

  // Blocking is the one that actually needs judgement -- "block everything" is a
  // way to lose a board -- so it is ranked rather than exhaustive. See
  // logic/autoBlock.ts for the ranking and what it deliberately ignores.
  const suggested = isBlock ? autoBlocks(state, actions) : [];
  const newBlocks = suggested.filter(({ blocker }) => stagedBlocks[blocker] === undefined);
  const blockWithAll = () => {
    for (const { blocker, attacker } of newBlocks) stageBlock(blocker, attacker);
  };

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
                  ? "Now click the attacker to block. Click your creature again to let it go."
                  : "Click one of your creatures, then the attacker it blocks. Nothing is committed until you confirm."}
            </p>
          </div>

          <div className="combat__staged" data-staged={staged.length}>
            {staged.length === 0 ? (
              <span className="combat__none">
                {available.length === 0
                  ? isAttack
                    ? "Nothing can attack."
                    : "Nothing can block."
                  : "Nothing staged yet."}
              </span>
            ) : (
              staged.map(([source, target], index) => (
                // A numbered row rather than a chip: at four attackers the
                // chips wrapped into a paragraph you had to read, where a list
                // can be counted.
                <span key={source} className="stage stage--on" data-staged-oid={source}>
                  <span className="stage__key">{index + 1}</span>
                  <span className="stage__name">
                    {isAttack
                      ? `${name(source)} → ${state.players[target]?.name ?? target}`
                      : `${name(source)} blocks ${name(target)}`}
                  </span>
                  {stats(source) && <span className="stage__pt tabular">{stats(source)}</span>}
                </span>
              ))
            )}
          </div>

          {/*
            One button per legal pair, carrying the server's real action id. This
            is the surface `full-game.spec.ts` and `clarity.spec.ts` drive, and
            it is why the action bar can stand down without leaving the decision
            unreachable. Clicking stages; nothing here posts.
          */}
          {options.length > 0 && (
            <div className="combat__options" data-testid="combat-options">
              {options.map((action) => {
                const on = isPairStaged(action);
                return (
                  <button
                    type="button"
                    key={action.id}
                    className={on ? "chip chip--on" : "chip"}
                    data-action-id={action.id}
                    data-action-kind={action.kind}
                    aria-pressed={on}
                    disabled={disabled}
                    onClick={() => onStage(action.id)}
                    title={on ? `${action.label} — click to call it back` : action.label}
                  >
                    {action.label}
                  </button>
                );
              })}
            </div>
          )}

          {/*
            The commit dock. One large control for the thing the turn is waiting
            on, and the alternatives demoted to a row beneath it -- rather than
            three same-sized buttons where the most-pressed and least-pressed
            look identical.
          */}
          <div className="commit-dock">
            <motion.button
              type="button"
              className="btn btn--primary commit"
              disabled={disabled || staged.length === 0}
              onClick={() => onDeclare(isAttack ? "attackers" : "blockers", staged)}
              whileHover={{ y: -2, scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              transition={bouncy}
              data-testid="combat-confirm"
            >
              <span className="commit__main">
                {isAttack
                  ? `Attack with ${attackPairs.length}`
                  : `Confirm ${blockPairs.length} block${blockPairs.length === 1 ? "" : "s"}`}
              </span>
            </motion.button>
            <div className="commit-alt">
              {isAttack ? (
                <button
                  type="button"
                  className="btn btn--ghost"
                  data-testid="combat-all"
                  disabled={disabled || unstagedAttackers.length === 0}
                  onClick={attackWithAll}
                  title="Send every creature that can attack"
                >
                  All attack{unstagedAttackers.length > 0 && ` (${unstagedAttackers.length})`}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn--ghost"
                  data-testid="combat-all"
                  disabled={disabled || newBlocks.length === 0}
                  onClick={blockWithAll}
                  title={
                    newBlocks.length === 0
                      ? "No block here is worth making on its own"
                      : "Block where it is worth it: survive and kill first, then walls, then trades"
                  }
                >
                  All defend{newBlocks.length > 0 && ` (${newBlocks.length})`}
                </button>
              )}
              {finish && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  data-action-id={finish.id}
                  data-action-kind={finish.kind}
                  disabled={disabled}
                  onClick={() => onSkip(finish.id)}
                  data-testid="combat-skip"
                >
                  {isAttack ? "No attacks" : "No blocks"}
                </button>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Attackers this blocker may legally be assigned to. */
export function legalBlockTargets(actions: LegalAction[], blockerOid: number): number[] {
  return blockableBy(actions, blockerOid);
}
