/**
 * Zones drawn as the piles they are.
 *
 * `Lib 72 / GY 3 / Exile 1` told you three numbers and made you compare them by
 * reading. A pile tells you the number *and* shows you the shape of the game --
 * a library running out is a visibly shrinking stack, which is the one piece of
 * board state you want to notice without looking for it.
 */

/** How many leaves a pile of `count` cards is drawn with. */
export function pileLeaves(count: number): number {
  if (count <= 0) return 0;
  // Capped: past nine leaves the stack is taller than the mat and the extra
  // height says nothing a reader can use. The number on the top leaf stays
  // exact, so the cap costs no information -- only resolution.
  return Math.min(MAX_LEAVES, Math.ceil(count / CARDS_PER_LEAF));
}

/** Cards represented by one leaf. */
export const CARDS_PER_LEAF = 9;

/** Leaves at which a pile stops growing. */
export const MAX_LEAVES = 9;

/**
 * Which pile art a zone gets.
 *
 * The library keeps the plain card-back purple; the graveyard is brown and the
 * exile pile slate, so the three read apart at a glance even before their
 * labels do.
 */
export type PileKind = "lib" | "gy" | "ex" | "cmd";

export const PILE_KIND: Record<string, PileKind> = {
  library: "lib",
  hand: "lib",
  graveyard: "gy",
  exile: "ex",
  command: "cmd",
};
