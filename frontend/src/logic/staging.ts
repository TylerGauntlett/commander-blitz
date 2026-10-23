/**
 * The one staged set: whatever the player is building before the turn takes it.
 *
 * Three questions are answered by building a set on the client and sending it
 * once -- which creatures attack and whom, which creatures block and what, and
 * "any number of target permanents" (`logic/pickSeveral.ts`). They used to be
 * three sets in `uiStore` with three shapes, three stage and unstage pairs and
 * a `clearStaging` that emptied each by name, so every new place that read
 * "is anything staged" had to know all three. It is one set now: a map from the
 * thing being staged to what it is staged as, owned by the decision it answers.
 *
 * | kind     | thing         | as                |
 * |----------|---------------|-------------------|
 * | `attack` | attacker oid  | defending seat    |
 * | `block`  | blocker oid   | attacker oid      |
 * | `pick`   | option ordinal| `1` (membership)  |
 *
 * ## Keyed by the decision, so a set never outlives its question
 *
 * A decision has no id, and the store outlives it. `decisionKey` names one
 * from what the engine sends, and a write under a different key starts a new
 * set rather than adding to the old one -- the picks for one Clever
 * Concealment are not still on when the next opens, and the attackers staged
 * for one declaration are not still aimed at the next. `useGame` re-keys on
 * every response, which is what empties a set whose question has gone.
 *
 * ## The order is kept, because `B` reads it
 *
 * An object keyed by oids iterates in ascending number, not in the order the
 * player pressed, so `order` carries that separately. `B` backs a hand-built set
 * out newest first; `marked` says the "all" mark built it, and then `B` takes
 * the whole of it back, because one press of the mark puts it back.
 */

import type { GameView } from "../api/types";

export type StageKind = "attack" | "block" | "pick";

export interface Staged {
  /** The decision this set answers. See `decisionKey`. */
  key: string;
  /** What the set is a set of, or `null` when nothing is staged. */
  kind: StageKind | null;
  /** The thing staged -> what it is staged as. */
  as: Readonly<Record<number, number>>;
  /** The things, in the order they were staged. */
  order: readonly number[];
  /** Every entry was put there by the "all" mark, so one press rebuilds it. */
  marked: boolean;
}

const NONE: Readonly<Record<number, number>> = Object.freeze({});
const NO_ORDER: readonly number[] = Object.freeze([]);

export const NOTHING_STAGED: Staged = Object.freeze({
  key: "",
  kind: null,
  as: NONE,
  order: NO_ORDER,
  marked: false,
});

/**
 * Which decision a set belongs to.
 *
 * The prompt names the source and the options say what it is choosing among;
 * the turn and the step keep two identical prompts apart.
 */
export function decisionKey(state: GameView): string {
  const pending = state.pending;
  if (pending === null) return "";
  return `${state.turn}|${state.step}|${pending.prompt}|${pending.options.map((o) => o.label).join(",")}`;
}

/**
 * The set as a map, when it is a set of `kind`, and an empty one otherwise.
 *
 * The empty one is a constant, so a selector built on this returns the same
 * object until the set changes -- a fresh `{}` per read would re-render every
 * subscriber on every store write.
 */
export function stagedAs(staged: Staged, kind: StageKind): Readonly<Record<number, number>> {
  return staged.kind === kind ? staged.as : NONE;
}

/** The things staged as `kind`, in staging order; empty for any other kind. */
export function stagedOrder(staged: Staged, kind: StageKind): readonly number[] {
  return staged.kind === kind ? staged.order : NO_ORDER;
}

/** The option ordinals picked for the decision `key`, in the order picked. */
export function pickedFor(staged: Staged, key: string): readonly number[] {
  return staged.kind === "pick" && staged.key === key ? staged.order : NO_ORDER;
}

/** A set built in one go, for tests and stories: `stagedSet("attack", { 301: 1 })`. */
export function stagedSet(
  kind: StageKind,
  as: Record<number, number>,
  key = "",
  marked = false,
): Staged {
  return { key, kind, as: { ...as }, order: Object.keys(as).map(Number), marked };
}

/** A pick set built in one go, for tests and stories. */
export function pickedSet(key: string, choices: number[]): Staged {
  return stagedSet("pick", Object.fromEntries(choices.map((c) => [c, 1])), key);
}

/** The set with `thing` staged as `as`; a new set when the question changed. */
export function withStaged(
  staged: Staged,
  key: string,
  kind: StageKind,
  thing: number,
  as: number,
): Staged {
  const same = staged.key === key && staged.kind === kind;
  const base = same ? staged : { ...NOTHING_STAGED, key, kind };
  // Re-aiming keeps the thing where it was in the order: it was not staged again.
  const order = thing in base.as ? base.order : [...base.order, thing];
  return {
    key,
    kind,
    as: { ...base.as, [thing]: as },
    order,
    // A hand-built or re-aimed entry is one the mark would not put back.
    marked: same && staged.marked && staged.as[thing] === as,
  };
}

/** The set with `thing` taken out. */
export function withoutStaged(staged: Staged, thing: number): Staged {
  if (!(thing in staged.as)) return staged;
  const as = { ...staged.as };
  delete as[thing];
  const order = staged.order.filter((t) => t !== thing);
  if (order.length === 0) return { ...NOTHING_STAGED, key: staged.key };
  return { ...staged, as, order, marked: false };
}

/**
 * The set with the "all" mark's entries added.
 *
 * Still `marked` only when the mark built all of it: a set the player had
 * started by hand is one the mark cannot rebuild.
 */
export function withMarked(
  staged: Staged,
  key: string,
  kind: StageKind,
  entries: ReadonlyArray<readonly [number, number]>,
): Staged {
  const same = staged.key === key && staged.kind === kind && staged.order.length > 0;
  let next: Staged = same ? staged : { ...NOTHING_STAGED, key, kind };
  const marked = !same || staged.marked;
  for (const [thing, as] of entries) next = withStaged(next, key, kind, thing, as);
  if (next.order.length === 0) return { ...NOTHING_STAGED, key };
  return { ...next, marked };
}

/**
 * One level of `B`: the whole set when the mark built it, otherwise the newest
 * entry. `null` when there is nothing to back out.
 */
export function backedOut(staged: Staged): Staged | null {
  if (staged.order.length === 0) return null;
  if (staged.marked) return { ...NOTHING_STAGED, key: staged.key };
  return withoutStaged(staged, staged.order[staged.order.length - 1]);
}
