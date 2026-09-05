/**
 * The board's five regions, as the ring experiences them.
 *
 * `L1`/`R1` step between them and trap the ring inside the one it is in;
 * `L2` jumps to the thing that submits the turn; the group follows the ring
 * wherever the pointer or a decision puts it; and each new decision sends the
 * ring to the region it lives in, once. Lifted out of `Table.tsx` as it was,
 * dependency lists included -- the comments explain why each one is narrow.
 */

import { useCallback, useEffect, useRef } from "react";
import type { GameView, LegalAction } from "../api/types";
import type { SoundName } from "../audio/sfx";
import { availableBlockers, blockableBy } from "../logic/actionMatch";
import { groupForDecision } from "../logic/focusGroup";
import type { useGame } from "../state/useGame";
import { getCursor, setCursor, subscribeCursor } from "./cursor";
import {
  type GroupId,
  getGroup,
  groupOf,
  groupRoot,
  landableStopsIn,
  nextGroup,
  rememberStop,
  rememberedStop,
  resetGroups,
  setGroup,
} from "./groups";
import { stopElement, stopId } from "./stops";

export interface TableRegionsInput {
  state: GameView;
  actions: LegalAction[];
  /** The pending decision's kind when it is ours, else null. */
  decisionKind: string | null;
  /** Whether a full-screen surface owns the decision instead of the board. */
  modalOwnsDecision: boolean;
  narration: ReturnType<typeof useGame>["narration"];
  cue: (sound: SoundName) => void;
}

export function useTableRegions({
  state,
  actions,
  decisionKind,
  modalOwnsDecision,
  narration,
  cue,
}: TableRegionsInput) {
  /* ------------------------------------------------------------- regions
   *
   * `L1`/`R1` step between the board's five regions and trap the ring inside
   * the one it is in, because directional navigation crosses a 96px seat strip,
   * three lanes, a fanned hand and a 243px rail one card at a time.
   * `HintBar` has advertised `L1 Zone` since it was written and nothing has
   * ever been bound to it. See `input/groups.ts`.
   */

  /** Enter a region, landing where the ring was when it last left. */
  const enterGroup = useCallback((id: GroupId | null) => {
    if (id === null) {
      setGroup(null);
      return;
    }
    const here = getGroup();
    const cursor = getCursor();
    // Leaving: note where we were, so coming back is a jump and not a reset.
    if (here && cursor) rememberStop(here, cursor);

    setGroup(id);
    const root = groupRoot(id);
    if (!root) return;
    /*
     * LANDABLE, not merely present.
     *
     * This took the first `[data-stop]` in document order, which is a different
     * question from the one `groupsPresent` asks to decide the region is worth
     * entering at all: on a handheld an opponent's cards are clipped to zero
     * height and still in the document, so the first stop in a region can be
     * one nobody can see while the region genuinely has others. One helper now
     * answers both.
     */
    const stops = landableStopsIn(root);
    const wanted = rememberedStop(id);
    // The remembered stop only if it is still there and still visible -- a card
    // can have left play since, and a stop id that names nothing puts the ring
    // nowhere.
    const remembered = stops.some((el) => el.dataset.stop === wanted) ? wanted : undefined;
    const target = remembered ?? stops[0]?.dataset.stop;
    if (target) setCursor(target);
  }, []);

  /**
   * `L2` SENDS THE RING TO THE THING THAT SUBMITS YOUR TURN.
   *
   * It used to send it to the tool strip, which `Menu` already did -- two
   * buttons for one jump, and neither of them for the jump that matters. The
   * commit slab is where a turn is actually spent: Attack, Block, Done, Pass.
   * It lives in the right rail, and on a handheld the ring is almost never
   * near it -- you are in your hand, or out on an opponent's board picking
   * something to attack, and the rail is the far corner of the screen. Walking
   * there is a dozen presses across a 96px seat strip, three lanes and a fanned
   * hand, or two `R1` steps if you happen to know the region order. Neither is
   * a thing to ask for once per phase, thirteen phases a turn.
   *
   * The slab specifically, and not the region: `enterGroup` would land on
   * whichever action the ring last used, and what somebody pressing this wants
   * is the button that ENDS the decision. Entering the region first is still
   * right -- it keeps the "where were you when you left" bookkeeping honest,
   * and the trap has to move with the ring -- so this is that, with the
   * landing spot overridden.
   *
   * IN COMBAT THE LANDING IS THE `ALL` MARK, one press left of the slab. The
   * dock there is three controls -- all, Attack/Block, no-attacks -- and "all"
   * is the one that answers the question outright: it stages every attacker or
   * every worthwhile block, so from it the whole decision is A, or right-then-A
   * to declare whatever you had already picked by hand. Landing on the slab
   * instead puts the ring on a button that is DISABLED until something is
   * staged, which is the state it is in at the instant the decision opens --
   * so `L2` appeared to jump to a dead control.
   *
   * Named rather than taken by document order, even though the two agree
   * today. The order of a row is a layout fact and this is a behavioural one;
   * a mark added to the left of it later must not silently steal the landing.
   *
   * The region is the fallback for the moment there is no slab (the panel is
   * mid-decision and offers only rows), and a deny for the moment there is no
   * panel at all, because a jump that silently does nothing is the defect the
   * whole hint bar was rewritten to stop.
   */
  const jumpToCommit = useCallback(() => {
    const acts = groupRoot("acts");
    if (!acts || landableStopsIn(acts).length === 0) {
      cue("deny");
      return;
    }
    enterGroup("acts");
    // The dock sits outside the panel's scrolling pane, which is what makes it
    // findable by class here rather than by the action id it happens to carry
    // this phase -- `actionAttrs` names the slab after the decision, so its
    // stop id is different on every one of them.
    const dock = document.querySelector<HTMLElement>(".commit-dock");
    if (!dock) return;
    const stops = landableStopsIn(dock);
    const all = stops.find((el) => el.dataset.stop === stopId.commitMark("all"));
    const slab = (all ?? stops[0])?.dataset.stop;
    if (slab) setCursor(slab);
  }, [enterGroup, cue]);

  const stepGroup = useCallback(
    (step: 1 | -1) => {
      const next = nextGroup(getGroup(), step);
      if (next === null) {
        cue("deny");
        return;
      }
      enterGroup(next);
    },
    [enterGroup, cue],
  );

  /*
   * The ring keeps its own group in step with where it actually is.
   *
   * The player can leave a region without pressing a shoulder: the pointer
   * snaps the ring anywhere, `A` on a card can open a dialog, and a decision
   * can move it. Reconciling from the cursor means the trap is always about
   * where the ring IS rather than about where it was last sent.
   */
  useEffect(() => {
    return subscribeCursor(() => {
      const stop = getCursor();
      if (!stop) return;
      const el = stopElement(stop, document.querySelector<HTMLElement>(".table") ?? undefined);
      if (!el) return;
      const found = groupOf(el);
      if (found && found !== getGroup()) setGroup(found);
    });
  }, []);

  // A new game must not inherit the last one's region or its remembered stops.
  useEffect(() => () => resetGroups(), []);

  /*
   * Where the decision is, when the decision changes.
   *
   * Keyed on the pending kind and the step ONLY. Run on every render this would
   * drag the ring back each time the engine pushed a state -- several times a
   * second while an AI plays -- and a ring that returns to where the app thinks
   * you should be is worse than one that stays where you put it.
   */
  const modalOwns = modalOwnsDecision;

  /**
   * Is the board a place this combat decision can actually be MADE?
   *
   * The one thing `groupForDecision` cannot answer, because it is about the
   * layout rather than about the game. A block is your creature and then the
   * attacker it stops, and at 1280x800 an opponent's lanes are clipped to zero
   * height -- so `stops.ts:onScreen` refuses to land the ring on an attacker,
   * correctly, and the board holds half a decision. Sent there, `A` on your own
   * creature answered nothing and every direction out of it was a wall or a
   * seat. The panel has carried the whole pairing as rows the entire time.
   *
   * Asked of the WHOLE TABLE rather than of the board region, and that is the
   * half worth getting right: on a desktop the attackers are drawn in
   * `.play__opponents` and the ring reaches them by walking out of the board,
   * because `escapeGroup` makes the region trap soft. The question is "is that
   * card on screen anywhere", not "is it in this box".
   *
   * Asked of the DOM and not of the card count: a clipped card still reports
   * its own full box, which is why `landableStopsIn` walks the ancestors.
   * Attacking is unaffected -- your own creatures are the decision there, and
   * the seats you aim at are stops at every size.
   */
  const boardCanDecide = useCallback(() => {
    if (decisionKind !== "declare_blockers") return true;
    const table = document.querySelector<HTMLElement>(".table");
    if (!table) return true;
    const reachable = new Set(landableStopsIn(table).map((el) => el.dataset.stop));
    return availableBlockers(actions).some((blocker) =>
      blockableBy(actions, blocker).some((attacker) => reachable.has(stopId.card(attacker))),
    );
  }, [decisionKind, actions]);

  /*
   * ONCE PER DECISION, and a ref rather than a dependency list is what makes it
   * once.
   *
   * The first version keyed the effect on the pending kind, the step AND
   * `narration.busy` -- and `busy` flips true then false after every action a
   * player takes. Casting a spell in your main phase changes neither the step
   * nor the pending kind, so the first two are stable and the third re-fired
   * the effect on its own: go and read something on the board, cast, and the
   * ring is yanked back to your hand. That is exactly the "returns to where the
   * app thinks you should be" failure the note above is about, arriving through
   * the dependency list rather than through the rule.
   *
   * So the KEY is the decision, the ref remembers which key was last acted on,
   * and narration only decides *when* -- never *whether*.
   */
  const focusedFor = useRef<string | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the narrow key is the point; see above.
  useEffect(() => {
    const key = `${state.pending?.kind ?? ""}|${state.step}`;
    if (focusedFor.current === key) return;
    // Wait for the board to stop moving, but do not treat waiting as done: the
    // key is still unclaimed, so the next run after narration settles takes it.
    if (narration.busy) return;
    focusedFor.current = key;
    const wanted = groupForDecision(state, actions, modalOwns, boardCanDecide());
    if (wanted && wanted !== getGroup()) enterGroup(wanted);
  }, [state.pending?.kind, state.step, narration.busy]);

  return { enterGroup, jumpToCommit, stepGroup };
}
