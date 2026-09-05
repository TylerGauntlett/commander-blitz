/**
 * The commit dock: one large control for the thing the turn is waiting on,
 * and the alternatives demoted to a row beneath it.
 *
 * Lifted out of `ActionPanel.tsx` as it was. The panel still decides which
 * actions are the commit, the finish and the X answer, and whether it stands
 * down; this draws them. The invariant it inherits: the slab carries no
 * `data-action-id` of its own, so every id stays in the document exactly
 * once, and the dock is the same shape in every state -- the idle bar below
 * is the half that makes that true when there is nothing to press.
 */

import { motion } from "motion/react";
import type { GameView, LegalAction } from "../../api/types";
import { actionAttrs, stopId } from "../../input/stops";
import { bouncy } from "../../motion/springs";
import { ActionIcon } from "../ui/ActionIcon";

type Mode = "attack" | "block" | "play" | "chooseX";

interface Props {
  mode: Mode;
  state: GameView;
  disabled: boolean;
  isCombat: boolean;
  nothingToDeclare: boolean;
  attackPairs: [number, number][];
  blockPairs: [number, number][];
  staged: [number, number][];
  unstagedAttackers: number[];
  wouldAttack: number;
  attackWithAll: () => void;
  blockWithAll: () => void;
  newBlocks: { blocker: number; attacker: number }[];
  finish: LegalAction | null;
  commit: LegalAction | null;
  xAction: LegalAction | null;
  clampedX: number;
  onAct: (actionId: string) => void;
  onDeclare: (kind: "attackers" | "blockers", pairs: [number, number][]) => void;
}

export function CommitDock({
  mode,
  state,
  disabled,
  isCombat,
  nothingToDeclare,
  attackPairs,
  blockPairs,
  staged,
  unstagedAttackers,
  wouldAttack,
  attackWithAll,
  blockWithAll,
  newBlocks,
  finish,
  commit,
  xAction,
  clampedX,
  onAct,
  onDeclare,
}: Props) {
  /*
   * THE DOCK IS THE SAME SHAPE IN EVERY STATE, and this is the half that makes
   * it true when there is nothing to press.
   *
   * The well was always mounted and its contents were not, so between decisions
   * it collapsed to its own padding -- 18px -- and sprang back to 66 or 90 the
   * moment an action arrived. The whole rail below it moved with it, every time
   * a turn passed. `.preview` above already holds a constant height for exactly
   * this reason; `board.css` spends four paragraphs on why.
   *
   * So the bar is never absent, only idle: the same slab in the same quiet
   * treatment a disabled one wears, carrying the panel's own waiting mark
   * (`.acts__dot`, which is what `.acts__thinking` uses in the head). Gold
   * means "this is what the turn is waiting on", and while the engine is
   * playing out somebody else's turn it is not.
   *
   * IT IS NOT AN ACTION AND IS NOT A BUTTON. A `div`, not a disabled
   * `<button>`: there is nothing here to press even in principle, and a
   * disabled control is a promise that it will become pressable. It carries no
   * `data-action-id` -- the exactly-once invariant at the top of this file --
   * and no `data-stop`, so the controller cursor cannot land on it either.
   * `aria-hidden` because `.acts__none` in the list above already says
   * "Waiting..." to a screen reader, and saying it twice is worse than once.
   */
  const idleBar = (
    <div className="bar">
      <div className="commit commit--idle" aria-hidden="true">
        <span className="commit__dots" data-testid="commit-idle">
          <span className="acts__dot" />
          <span className="acts__dot" />
          <span className="acts__dot" />
        </span>
      </div>
    </div>
  );

  return (
    <div className="commit-dock">
      {/*
        What the count used to be doing on the button, moved off it -- and
        now rendered in EVERY mode rather than only in combat.

        `Attack with 0` -> `Attack with 10` is a label that changes width,
        so the button re-centres itself under the thumb every time a
        creature is staged, which is exactly while you are aiming at it.
        `mockups/handheld-board/` names this and puts the number on a line
        of its own above the bar. It is also the line the block forecast
        wants, so the two states share one row rather than each inventing a
        place to sit.

        OUTSIDE THE MODE TERNARY, because a line that exists only in combat
        is a line that appears when combat starts -- 25px of dock arriving
        on top of the bar changing, which moved the rail a second time. Out
        of combat it renders empty and `.commit-note`'s `min-height: 1lh`
        keeps its row; `ActionPanel.stories`' `expectStableDock` fails if
        that ever stops being true.
      */}
      <p className="commit-note tabular">
        {mode === "attack"
          ? `${attackPairs.length} attacking`
          : mode === "block"
            ? `${blockPairs.length} blocked of ${Object.keys(state.combat?.attackers ?? {}).length}`
            : // Empty, and the row is held open by `.commit-note`'s
              // `min-height: 1lh` rather than by a non-breaking space. A
              // NBSP works and formats down to an invisible character in
              // this file, which is a thing the next person deletes by
              // accident; one mechanism in the stylesheet is better than
              // two, one of which cannot be seen.
              ""}
      </p>
      {mode === "chooseX" ? (
        // The only control in the document carrying an id for this decision.
        // The other twenty values are reachable through the stepper, which
        // changes which id this slab points at rather than adding more.
        xAction ? (
          <div className="bar">
            <motion.button
              type="button"
              className="commit"
              {...actionAttrs(xAction.id)}
              data-action-kind={xAction.kind}
              disabled={disabled}
              onClick={() => onAct(xAction.id)}
              whileHover={disabled ? undefined : { y: -2 }}
              whileTap={{ scale: 0.97 }}
              transition={bouncy}
              data-testid="commit"
            >
              <span className="commit__main">Pay X = {clampedX}</span>
            </motion.button>
          </div>
        ) : (
          idleBar
        )
      ) : isCombat ? (
        nothingToDeclare && finish ? (
          /*
              With nothing declarable there is nothing to confirm, so
              declining *is* the decision and it takes the whole bar. The
              two marks go with it: "all" and "none" of an empty set are
              the same button pressed twice.
            */
          <div className="bar">
            <motion.button
              type="button"
              className="commit"
              {...actionAttrs(finish.id)}
              data-action-kind={finish.kind}
              disabled={disabled}
              onClick={() => onAct(finish.id)}
              whileHover={disabled ? undefined : { y: -2 }}
              whileTap={{ scale: 0.97 }}
              transition={bouncy}
              data-testid="combat-skip"
            >
              <span className="commit__main">
                {mode === "attack" ? "No attacks" : "No blocks"}
              </span>
            </motion.button>
          </div>
        ) : (
          /*
              EVERY CHOICE, THE DECISION, NO CHOICE -- in that order, on one
              row.

              These were a full-width slab with two 12px outlined pills
              under it, which spends a whole row on the two answers nobody
              presses and reads as one button with a caption. One shape
              either side of the slab is the relationship they actually
              have, and it puts all three at the 44px floor in the height
              the slab alone was taking.

              The marks themselves are DRAWN, not typed. They were `▣` and
              `▢`, filled and empty of one square, which is the true
              relationship and an unreadable picture of it -- playtest
              found two squares nobody could tell apart. `ui/ActionIcon`
              has the argument.

              The names live in `aria-label` and `data-hint` and nowhere
              else. A `title` would reach the mouse only, and this bar is
              driven by a controller as often as by a thumb.

              ALL THREE CARRY A STOP, and for a while only one of them did.
              "No attacks" is a server action and got `act:` out of
              `actionAttrs`; the mark and the slab are local staging, exist
              in no action list, and so had nothing for the ring to land on
              -- the two most-pressed controls of a combat step were mouse
              only, on a client whose whole point is that it plays on a
              handheld. They are stops in document order all -> slab ->
              skip, which is also left -> right on screen, so `L2` lands on
              the mark and one press of right reaches the slab.
            */
          <div className="bar">
            {mode === "attack" ? (
              <button
                type="button"
                className="commit-mark"
                data-stop={stopId.commitMark("all")}
                data-testid="combat-all"
                disabled={disabled || unstagedAttackers.length === 0}
                onClick={attackWithAll}
                /*
                  THE NUMBER IS WHAT THIS PRESS WOULD DO, not how many
                  creatures exist. "All attack (4 of 7)" says both halves of
                  the ranking in the place a controller player actually
                  reads them -- `aria-label` is the accessible name, so it
                  is what the ring announces and what the hint carries.
                */
                aria-label={
                  wouldAttack === 0
                    ? "All attack"
                    : wouldAttack < unstagedAttackers.length
                      ? `All attack (${wouldAttack} of ${unstagedAttackers.length})`
                      : `All attack (${wouldAttack})`
                }
                data-hint={
                  wouldAttack < unstagedAttackers.length
                    ? "Send everything worth sending. Press again for the rest."
                    : "Send every creature that can attack"
                }
              >
                <ActionIcon name="all" />
              </button>
            ) : (
              <button
                type="button"
                className="commit-mark"
                data-stop={stopId.commitMark("all")}
                data-testid="combat-all"
                disabled={disabled || newBlocks.length === 0}
                onClick={blockWithAll}
                aria-label={`All defend${newBlocks.length > 0 ? ` (${newBlocks.length})` : ""}`}
                data-hint={
                  newBlocks.length === 0
                    ? "No block here is worth making on its own"
                    : "Block where it is worth it: survive and kill first, then walls, then trades"
                }
              >
                <ActionIcon name="all" />
              </button>
            )}

            <motion.button
              type="button"
              className="commit"
              data-stop={stopId.commit}
              disabled={disabled || staged.length === 0}
              data-empty={staged.length === 0 ? "true" : "false"}
              aria-label={
                mode === "attack"
                  ? `Attack with ${attackPairs.length}`
                  : `Confirm ${blockPairs.length} block${blockPairs.length === 1 ? "" : "s"}`
              }
              onClick={() => onDeclare(mode === "attack" ? "attackers" : "blockers", staged)}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.97 }}
              transition={bouncy}
              data-testid="combat-confirm"
            >
              <span className="commit__main">{mode === "attack" ? "Attack" : "Block"}</span>
            </motion.button>

            {finish && (
              <button
                type="button"
                className="commit-mark"
                {...actionAttrs(finish.id)}
                data-action-kind={finish.kind}
                disabled={disabled}
                onClick={() => onAct(finish.id)}
                data-testid="combat-skip"
                aria-label={mode === "attack" ? "No attacks" : "No blocks"}
                data-hint={mode === "attack" ? "No attacks" : "No blocks"}
              >
                <ActionIcon name="skip" />
              </button>
            )}
          </div>
        )
      ) : commit ? (
        <div className="bar">
          <motion.button
            type="button"
            className="commit"
            {...actionAttrs(commit.id)}
            data-action-kind={commit.kind}
            disabled={disabled}
            onClick={() => onAct(commit.id)}
            whileHover={disabled ? undefined : { y: -2 }}
            whileTap={{ scale: 0.97 }}
            transition={bouncy}
            data-testid="commit"
          >
            <span className="commit__main">{commit.label}</span>
          </motion.button>
        </div>
      ) : (
        /*
          Not your turn, or a dialog owns the decision. This is the branch
          the whole rail used to collapse on -- `commit` is null while the
          engine plays out every other seat's turn, which is most of the
          wall-clock of a four-player game.
        */
        idleBar
      )}
    </div>
  );
}
