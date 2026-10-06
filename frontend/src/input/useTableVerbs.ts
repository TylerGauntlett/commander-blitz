/**
 * The table's two context verbs on a controller: `B` unwinds, `X` does the
 * secondary thing -- and, where there is nothing else, commits the decision.
 *
 * Lifted out of `Table.tsx` as they were. `usePadBindings` binds them.
 */

import { useCallback } from "react";
import type { GameView, LegalAction } from "../api/types";
import type { SoundName } from "../audio/sfx";
import { defendersFor } from "../logic/actionMatch";
import { COMMIT_TESTID, commitmentFor } from "../logic/commit";
import { parseStop } from "../logic/verbs";
import { useUiStore } from "../state/uiStore";
import { getCursor } from "./cursor";

interface Args {
  state: GameView;
  actions: LegalAction[];
  decisionKind: string | null;
  dialOpen: boolean;
  setDialOpen: (open: boolean) => void;
  heldCard: number | null;
  setHeldCard: (oid: number | null) => void;
  /** Whose board is on screen, already guarded. See `useViewingSeat`. */
  viewing: number | null;
  act: (actionId: string) => void;
  onBarAct: (actionId: string) => void;
  cue: (sound: SoundName) => void;
}

export function useTableVerbs({
  state,
  actions,
  decisionKind,
  dialOpen,
  setDialOpen,
  heldCard,
  setHeldCard,
  viewing,
  act,
  onBarAct,
  cue,
}: Args) {
  const selectedOid = useUiStore((s) => s.selectedOid);
  const targetingActionIds = useUiStore((s) => s.targetingActionIds);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const endTargeting = useUiStore((s) => s.endTargeting);
  const select = useUiStore((s) => s.select);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const setPeek = useUiStore((s) => s.setPeek);
  const logOverlay = useUiStore((s) => s.logOverlay);
  const setViewing = useUiStore((s) => s.setViewing);
  const toggleLogOverlay = useUiStore((s) => s.toggleLogOverlay);
  const settingsOpen = useUiStore((s) => s.settingsOpen);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const peek = useUiStore((s) => s.peek);

  /**
   * B: a strict unwind, and it never quits from the top.
   *
   * The order is the order things were put on top of each other, so pressing B
   * repeatedly always ends at the board rather than at a dialog you cannot
   * remember opening. Quitting is a deliberate act in the tool strip -- a back
   * button that eventually leaves the game is how somebody loses a match.
   */
  const back = useCallback(() => {
    /*
     * One level per press, outermost first, and each level says so.
     *
     * The voice is not decoration: `B` at the bottom of the stack does nothing
     * at all, and without a sound the player cannot tell "nothing was open"
     * from "the button did not register" -- which on a controller is the
     * difference between trusting the input and hammering it.
     */
    const unwind = () => {
      // The two holds are outermost: both cover the board, and both are things
      // you opened a moment ago and can put down without losing anything.
      if (dialOpen) {
        setDialOpen(false);
        return true;
      }
      if (heldCard !== null) {
        setHeldCard(null);
        return true;
      }
      // The settings menu, next: a popover the player opened from the tool
      // strip a moment ago, and a `data-modal-root` while it is up, so the
      // ring is inside it with nowhere else to go. `SettingsMenu` puts the
      // ring back on the gear once it has gone.
      if (settingsOpen) {
        setSettingsOpen(false);
        return true;
      }
      // The log overlay is the outermost thing that can be open, and it traps
      // the ring while it is. A panel you can open with one button and cannot
      // close with the button that means "back" is worse than no panel: the
      // ring is inside it and every direction is a wall.
      //
      // Not gated on the layout any more: the log is an overlay at every size
      // now that the left rail is retired, so `B` has to close it everywhere.
      if (logOverlay) {
        toggleLogOverlay();
        return true;
      }
      if (peek) {
        setPeek(null);
        return true;
      }
      // Below the overlays and above targeting: standing at somebody else's
      // seat is a place you are, not a thing that is open over you, so `B`
      // brings you home only once nothing is covering the board.
      if (viewing !== null) {
        setViewing(null);
        return true;
      }
      if (targetingActionIds.length > 0) {
        endTargeting();
        return true;
      }
      if (selectedOid !== null) {
        select(null);
        return true;
      }
      return false;
    };
    if (unwind()) cue("back");
  }, [
    dialOpen,
    setDialOpen,
    heldCard,
    setHeldCard,
    settingsOpen,
    setSettingsOpen,
    logOverlay,
    toggleLogOverlay,
    peek,
    setPeek,
    viewing,
    setViewing,
    targetingActionIds,
    endTargeting,
    selectedOid,
    select,
    cue,
  ]);

  /**
   * X: the secondary verb, which is context's business rather than a fixed one.
   *
   * On a staged attacker it re-aims -- the pod case, where `defendersFor` has
   * several seats and the mouse re-aims by clicking a different orb. On a card
   * whose primary press casts it, it activates an ability instead.
   *
   * AND WHERE IT HAS NOTHING ELSE TO DO, IT COMMITS THE DECISION.
   *
   * Every decision this game asks ends at one control in the commit dock: Pass
   * on a priority window, All attack then Attack on a declaration, All defend
   * then Block. The dock is in the right rail and the ring is almost never near
   * it -- you are in your hand, or out on your own board choosing what to swing
   * -- so `L2` exists to jump there and `A` presses it. Two presses, every
   * phase, thirteen phases a turn. `X` collapses that to one.
   *
   * `X` is empty on most stops, so it takes the job rather than a button being
   * invented for it: no new glyph, and `HintBar` renders `verbs.x`
   * conditionally already, so the one-line bar does not grow. Nothing is
   * displaced -- a card with an ability keeps `Activate`, a staged attacker
   * keeps `Re-aim`.
   *
   * WHICH control is `logic/commit.ts`, shared with `logic/verbs.ts` rather
   * than restated in each. A bar that promises a verb the button does not have
   * is the defect that file exists to prevent, and this is the branch where the
   * two would have drifted first -- "All defend" is disabled on a board where
   * every block is a chump, and only the ranking knows that.
   *
   * TWO OF THE FOUR ARE PRESSED RATHER THAN POSTED. "All attack" and the Attack
   * slab write to `uiStore` and declare what is staged; they exist in no action
   * list and have no id, so `X` clicks the control the panel already rendered.
   * That is the same rule `useCursorNav` uses for `A` -- there is no second
   * routing table, and no way for a pad to reach an action a pointer cannot.
   */
  const secondary = useCallback(() => {
    const ref = parseStop(getCursor());
    const oid = ref.kind === "card" ? ref.id : null;
    if (oid !== null) {
      if (decisionKind === "declare_attackers" && stagedAttacks[oid] !== undefined) {
        const defenders = defendersFor(actions, oid);
        if (defenders.length > 1) {
          const next =
            defenders[(defenders.indexOf(stagedAttacks[oid]) + 1) % defenders.length];
          stageAttack(oid, next);
          return;
        }
      }
      const ability = actions.find((a) => a.source_oid === oid && a.kind === "activate");
      if (ability) {
        onBarAct(ability.id);
        return;
      }
    }
    /*
     * Silent when there is nothing to do, rather than a deny.
     *
     * The bar is the contract: it renders `X` only when `verbsFor` gives it a
     * verb, and `verbsFor` asks the same `commitmentFor` this does. A refusal
     * noise for a button the player was never told about is a noise they cannot
     * explain.
     */
    const commit = commitmentFor(state, actions, {
      stagedAttacks,
      stagedBlocks,
      selectedOid,
      targeting: targetingActionIds.length > 0,
    });
    if (!commit) return;
    if (commit.actionId !== null) {
      act(commit.actionId);
      return;
    }
    /*
     * `.click()` and not a re-implementation. The dock is inside the panel and
     * the staging lives there; reaching in for the button is what keeps the
     * escalation state, the ranking and the declare call in one place.
     */
    document
      .querySelector<HTMLButtonElement>(
        `[data-testid="${COMMIT_TESTID[commit.target]}"]:not([disabled])`,
      )
      ?.click();
  }, [
    decisionKind,
    stagedAttacks,
    stagedBlocks,
    selectedOid,
    targetingActionIds,
    state,
    actions,
    stageAttack,
    onBarAct,
    act,
  ]);

  return { back, secondary };
}
