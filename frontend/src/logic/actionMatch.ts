/**
 * Matching UI gestures to legal actions.
 *
 * Dragging is an *ergonomic shortcut for selecting a legal action*, never a
 * rules operation: the client only ever offers what the server already said is
 * legal, and sends back that action's opaque id.
 */

import type { GameView, LegalAction } from "../api/types";
import { type Lane, laneFor } from "./zoneGrouping";

/** Every action that would play this card from hand. */
export function actionsForCard(actions: LegalAction[], oid: number): LegalAction[] {
  return actions.filter(
    (action) =>
      action.source_oid === oid && (action.kind === "play_land" || action.kind === "cast"),
  );
}

/** Can this card be dropped on this lane? */
export function canDropOnLane(
  state: GameView,
  actions: LegalAction[],
  oid: number,
  lane: Lane,
): boolean {
  const candidates = actionsForCard(actions, oid);
  if (candidates.length === 0) return false;
  const card = state.players[state.seat].hand?.find((entry) => entry.oid === oid) ?? null;
  if (!card) return false;
  // Instants and sorceries have no lane of their own; they may be dropped
  // anywhere, since where they land is meaningless.
  const isSpell = card.types.includes("Instant") || card.types.includes("Sorcery");
  return isSpell || laneFor(card) === lane;
}

/**
 * Which lanes should highlight while this card is being dragged.
 */
export function dropTargets(
  state: GameView,
  actions: LegalAction[],
  oid: number,
  lanes: readonly Lane[],
): Lane[] {
  return lanes.filter((lane) => canDropOnLane(state, actions, oid, lane));
}

/** True when playing this card still needs the player to pick a target. */
export function needsTargetChoice(actions: LegalAction[], oid: number): boolean {
  const candidates = actionsForCard(actions, oid);
  return candidates.length > 1 || candidates.some((a) => a.targets.length > 0);
}

/** The single action to submit, or null when the player must disambiguate. */
export function resolveSingleAction(actions: LegalAction[], oid: number): LegalAction | null {
  const candidates = actionsForCard(actions, oid);
  return candidates.length === 1 ? candidates[0] : null;
}

/** Actions that target a specific object, for the target picker's highlights. */
export function actionsTargeting(actions: LegalAction[], targetOid: number): LegalAction[] {
  return actions.filter((action) =>
    action.targets.some((ref) => ref.kind === "object" && ref.id === targetOid),
  );
}

export function attackActions(actions: LegalAction[]): LegalAction[] {
  return actions.filter((action) => action.kind === "add_attacker");
}

export function blockActions(actions: LegalAction[]): LegalAction[] {
  return actions.filter((action) => action.kind === "add_blocker");
}

/*
 * All three of these are sorted, and that is not cosmetic.
 *
 * They are what the action panel builds its rows from, and the server's action
 * list is not order-stable between polls -- so an unsorted list reordered the
 * panel underneath the player mid-decision, moving the row they were reaching
 * for. Sorting by oid is the same reasoning `autoBlock.ts` gives for breaking
 * its ties by oid: the same board must always produce the same list, or it
 * cannot be reasoned about.
 */

/** Creatures this player may declare as attackers, deduplicated, in oid order. */
export function availableAttackers(actions: LegalAction[]): number[] {
  const seen = new Set<number>();
  for (const action of attackActions(actions)) {
    if (action.source_oid !== null) seen.add(action.source_oid);
  }
  return [...seen].sort((a, b) => a - b);
}

/** Players a given attacker may be sent at, in seat order. */
export function defendersFor(actions: LegalAction[], attackerOid: number): number[] {
  return attackActions(actions)
    .filter((action) => action.source_oid === attackerOid)
    .flatMap((action) => action.targets.filter((r) => r.kind === "player").map((r) => r.id))
    .sort((a, b) => a - b);
}

/** Attackers a given blocker may block, in oid order. */
export function blockableBy(actions: LegalAction[], blockerOid: number): number[] {
  return blockActions(actions)
    .filter((action) => action.source_oid === blockerOid)
    .flatMap((action) => action.targets.filter((r) => r.kind === "object").map((r) => r.id))
    .sort((a, b) => a - b);
}

/** Creatures this player may declare as blockers, deduplicated, in oid order. */
export function availableBlockers(actions: LegalAction[]): number[] {
  const seen = new Set<number>();
  for (const action of blockActions(actions)) {
    if (action.source_oid !== null) seen.add(action.source_oid);
  }
  return [...seen].sort((a, b) => a - b);
}

export function findByKind(actions: LegalAction[], kind: string): LegalAction | null {
  return actions.find((action) => action.kind === kind) ?? null;
}

export function isOurDecision(state: GameView): boolean {
  return state.pending !== null && state.pending.player === state.seat;
}
