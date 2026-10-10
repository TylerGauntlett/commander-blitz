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

/** One play-mode row: a card or ability, plus every way to aim it. */
export interface ActionGroup {
  key: string;
  /** Representative, for the name, cost and label the row draws. */
  head: LegalAction;
  /** One per legal target tuple, in target order. Length 1 is the common case. */
  actions: LegalAction[];
}

/** The one dimension a row collapses over: which legal target this copy aims at. */
function groupKey(action: LegalAction): string {
  return [
    action.kind,
    action.source_oid ?? -1,
    action.ability_index ?? -1,
    action.x,
    action.choice ?? -1,
    action.base_label,
  ].join("|");
}

/**
 * Lowest target id an action names, for ordering the chips within a row.
 *
 * A no-target variant sorts last, agreeing with the order `targeting.py` puts
 * an optional spec's choices in: declining is the tail of the list, not a
 * creature you might mistake for the obvious pick.
 */
function firstTargetId(action: LegalAction): number {
  // Finite, so an all-untargeted comparison is 0 rather than NaN.
  let low = Number.MAX_SAFE_INTEGER;
  for (const ref of action.targets) low = Math.min(low, ref.id);
  return low;
}

/**
 * Play-mode rows: one per card or ability, not per legal target tuple.
 *
 * `legality._cast_variant` and `_activate_actions` emit one action per tuple
 * returned by `enumerate_target_tuples`, so a Simic Charm with six targetable
 * creatures on the board is six `cast` actions -- and the panel drew them as
 * six identical rows, because for a card it draws the card, never the label.
 * This is presentational only: the engine must keep one action per object per
 * variant (deduplicating there was the bug that made the
 * second and third Forest in hand unclickable), and it is also the RL action
 * space.
 *
 * Kicked and unkicked casts of the same card stay two rows -- they are two
 * different things to do, and `base_label` is what says so.
 *
 * Group order is the server's, which is legality's: lands, casts, suspends,
 * activations. Within a group the chips sort by target id for the reason the
 * combat helpers above give: the action list is not order-stable between
 * polls, and an unsorted list moves the control the player is reaching for.
 */
export function groupPlayActions(actions: LegalAction[]): ActionGroup[] {
  const byKey = new Map<string, ActionGroup>();
  for (const action of actions) {
    const key = groupKey(action);
    const found = byKey.get(key);
    if (found) found.actions.push(action);
    else byKey.set(key, { key, head: action, actions: [action] });
  }
  return [...byKey.values()].map((group) => ({
    ...group,
    actions: [...group.actions].sort((a, b) => firstTargetId(a) - firstTargetId(b)),
  }));
}

/**
 * An activated ability's own text, with the card's name taken off the front.
 *
 * `legality._activate_actions` labels every ability `"<Card name>: <text>"`,
 * which is the right label in a log and the wrong one in a 230px rail: the
 * name is the part that survives the ellipsis and the ability is the part
 * that does not, so a Mind Stone's two rows both read "Mind Stone: {T}…". The
 * panel row and the ability menu draw the card's name once, separately, and
 * this for the rest. Only a prefix that IS the source's name is stripped --
 * an ability whose text happens to contain a colon keeps it.
 */
export function abilityText(baseLabel: string, sourceName: string | null): string {
  if (sourceName) {
    const prefix = `${sourceName}: `;
    if (baseLabel.startsWith(prefix)) return baseLabel.slice(prefix.length);
  }
  return baseLabel;
}

export function findByKind(actions: LegalAction[], kind: string): LegalAction | null {
  return actions.find((action) => action.kind === kind) ?? null;
}

export function isOurDecision(state: GameView): boolean {
  return state.pending !== null && state.pending.player === state.seat;
}
