/**
 * Everything `Table` derives from the legal-action list and the selection.
 *
 * Twelve memos, all pure functions of `(state, actions, uiStore selection)`:
 * which cards are playable, which permanents offer an ability, which oids and
 * players the current targeting could still land on, which creatures may be
 * declared, what a hovered spell would tap, which lanes accept the selected
 * card. None of them touch the DOM, none of them fire an effect, and every one
 * used to sit inline in `Table.tsx` between the callbacks that read them and
 * the ones that build them -- 170 lines of a 2,000-line component. Moved as
 * they were; the memo boundaries and dependency lists are unchanged.
 */

import { useMemo } from "react";
import type { GameView, LegalAction } from "../api/types";
import { abilityText, availableAttackers, canDropOnLane } from "../logic/actionMatch";
import { sourcesSpentBy } from "../logic/mana";
import { findCard, LANES } from "../logic/zoneGrouping";

export interface TableDerivedInput {
  state: GameView;
  actions: LegalAction[];
  /** `uiStore.targetingActionIds`: the actions the selection is narrowing to. */
  targetingActionIds: string[];
  /** The pending decision's kind when it is ours, else null. */
  decisionKind: string | null;
  inCombatDecision: boolean;
  selectedOid: number | null;
  /** `uiStore.stagedBlocks`: blocker oid -> attacker oid. */
  stagedBlocks: Record<number, number>;
  hoveredOid: number | null;
}

export function useTableDerived({
  state,
  actions,
  targetingActionIds,
  decisionKind,
  inCombatDecision,
  selectedOid,
  stagedBlocks,
  hoveredOid,
}: TableDerivedInput) {
  /** Cards in hand the server says can be played right now. */
  const playableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of actions) {
      if (
        action.source_oid !== null &&
        (action.kind === "cast" || action.kind === "play_land")
      ) {
        set.add(action.source_oid);
      }
    }
    return set;
  }, [actions]);

  /**
   * Permanents offering an activated ability right now.
   *
   * The same predicate `onBoardCard` already uses to route a click; this only
   * draws the affordance for it. The action itself stays in the action bar, so
   * the rune adds no `data-action-id` and cannot duplicate one.
   *
   * Note this is only the *available* state. The server can express an ability
   * it is offering but not one you cannot afford -- `unplayable_reason` covers
   * hand cards alone -- so there is deliberately no greyed-out variant.
   */
  const abilityOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of actions) {
      if (action.kind === "activate" && action.source_oid !== null) set.add(action.source_oid);
    }
    return set;
  }, [actions]);

  /** What the popover says a permanent offers, by source oid. */
  const abilityLabels = useMemo(() => {
    // `base_label`, not `label`: the engine offers one action per legal
    // target, so `label` here would name whichever target happened to be
    // first and read as a promise the popover cannot keep.
    const byOid = new Map<number, Set<string>>();
    for (const action of actions) {
      if (action.kind !== "activate" || action.source_oid === null) continue;
      const seen = byOid.get(action.source_oid) ?? new Set<string>();
      // The ability's text alone: the popover sits on the card, which is
      // already saying its own name. Same helper the panel row uses.
      seen.add(
        abilityText(action.base_label, findCard(state, action.source_oid)?.name ?? null),
      );
      byOid.set(action.source_oid, seen);
    }
    // Naming the first of several was a promise the popover could not keep
    // either: a permanent with a mana ability and a sacrifice ability would
    // advertise only one of them. Count instead, and let the panel enumerate.
    return new Map(
      [...byOid].map(([oid, labels]) => [
        oid,
        labels.size === 1 ? [...labels][0] : `${labels.size} abilities`,
      ]),
    );
  }, [actions, state]);

  /** Every oid named by any legal action: never hide these inside a stack. */
  const actionableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of actions) {
      if (action.source_oid !== null) set.add(action.source_oid);
      for (const ref of action.targets) {
        if (ref.kind === "object") set.add(ref.id);
      }
    }
    return set;
  }, [actions]);

  /** The actions the current selection is waiting to resolve to. */
  const targeting = useMemo(
    () => actions.filter((a) => targetingActionIds.includes(a.id)),
    [actions, targetingActionIds],
  );

  const targetableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of targeting) {
      for (const ref of action.targets) {
        if (ref.kind === "object") set.add(ref.id);
      }
    }
    return set;
  }, [targeting]);

  const targetablePids = useMemo(() => {
    const set = new Set<number>();
    for (const action of targeting) {
      for (const ref of action.targets) {
        if (ref.kind === "player") set.add(ref.id);
      }
    }
    // During attacker declaration, opponents are always pointable.
    if (decisionKind === "declare_attackers" && selectedOid !== null) {
      for (const action of actions) {
        if (action.kind === "add_attacker" && action.source_oid === selectedOid) {
          for (const ref of action.targets) {
            if (ref.kind === "player") set.add(ref.id);
          }
        }
      }
    }
    return set;
  }, [targeting, decisionKind, selectedOid, actions]);

  /**
   * The target question is settled and only the *variant* question is left.
   *
   * True when every action still in the running names the same targets — so
   * clicking the board again cannot narrow anything, and what remains is
   * "kicked or not", which only the panel can ask. Also true for a selection
   * of untargeted variants, where there was never a target to pick.
   */
  const targetChosen = useMemo(() => {
    if (targeting.length < 2) return false;
    const signature = (a: (typeof targeting)[number]) =>
      a.targets.map((ref) => `${ref.kind}:${ref.id}`).join(",");
    const first = signature(targeting[0]);
    return targeting.every((a) => signature(a) === first);
  }, [targeting]);

  /** Creatures that may still be declared, for the amber "click me" rim. */
  const combatCandidates = useMemo(() => {
    if (!inCombatDecision) return new Set<number>();
    if (decisionKind === "declare_attackers") return new Set(availableAttackers(actions));
    return new Set(
      actions
        .filter((a) => a.kind === "add_blocker")
        .map((a) => a.source_oid)
        .filter((oid): oid is number => oid !== null),
    );
  }, [inCombatDecision, decisionKind, actions]);

  /** Opponents' attackers that something of ours is staged to block. */
  const blockedAttackers = useMemo(() => new Set(Object.values(stagedBlocks)), [stagedBlocks]);

  /**
   * The lands a hovered card would tap, straight from the engine's solver.
   *
   * The mana row could say what you have but not what a play would leave you
   * with, which is the interesting question in a turn with two plays in it.
   * Nothing is computed here: `pays` is the payment `solve_payment` actually
   * found, so this cannot disagree with what casting the spell will really do.
   */
  const spending = useMemo(
    () => (hoveredOid === null ? new Set<number>() : sourcesSpentBy(actions, hoveredOid)),
    [hoveredOid, actions],
  );

  /** Lanes that would accept a drop of the selected hand card. */
  const activeLanes = useMemo(() => {
    const set = new Set<string>();
    if (selectedOid === null) return set;
    for (const lane of LANES) {
      if (canDropOnLane(state, actions, selectedOid, lane)) {
        set.add(`${state.seat}:${lane}`);
      }
    }
    return set;
  }, [selectedOid, state, actions]);

  return {
    playableOids,
    abilityOids,
    abilityLabels,
    actionableOids,
    targeting,
    targetableOids,
    targetablePids,
    targetChosen,
    combatCandidates,
    blockedAttackers,
    spending,
    activeLanes,
  };
}
