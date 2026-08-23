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
 * exile pile slate, so they read apart at a glance even before their labels do.
 *
 * HAND HAS ITS OWN KIND, and it did not, which was a real defect rather than a
 * tidy-up. It shared `lib`, so the two most-read counts on an opponent's seat
 * rendered as the same purple stack -- and on a handheld, where the compact
 * strip drops the words, the only thing telling "89 cards left in their deck"
 * from "7 cards in their hand" was which came first. That is exactly the
 * argument `docs/handheld-playtest.md` records for taking `.pile__label` back:
 * a fixed order only helps somebody who already knows it.
 */
export type PileKind = "lib" | "hand" | "gy" | "ex" | "cmd";

export const PILE_KIND: Record<string, PileKind> = {
  library: "lib",
  hand: "hand",
  graveyard: "gy",
  exile: "ex",
  command: "cmd",
};
