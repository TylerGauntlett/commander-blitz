/**
 * Narrowing a decision that is too long to read.
 *
 * `op_choose_type` asks "choose a creature type" with every subtype in the
 * loaded pool as an option -- around four hundred of them. The prompt dialog
 * drew one button per option, which is a wall nobody can read with a mouse and
 * worse with a controller: the ring focuses with `preventScroll`, so every
 * option past the fold of the scroller was unreachable by pad outright.
 *
 * `ChoiceCombo` is the surface that replaced it. This is the part of it with no
 * DOM in it: which options a typed query leaves, and in what order. Kept
 * separate because the ordering rule is the half worth testing on its own --
 * `Enter` commits the highlighted row, and which row that is has to be
 * predictable rather than "whichever the engine happened to sort first".
 */

/**
 * How many options it takes before a decision is a wall rather than a choice.
 *
 * Above this the dialog switches to the combobox. Every decision that ships
 * today is comfortably under it -- discarding to hand size, at nine, is the
 * largest -- so mulligans, modal spells and target choices keep exactly the row
 * of buttons they have always had. `tests/promptFilter.test.ts` holds that
 * line, because lowering this under a shipped prompt would silently rebuild a
 * surface nobody asked to change.
 */
export const COMBO_MIN = 12;

/** Anything with a searchable label. */
export interface Filterable {
  text: string;
}

/**
 * A label reduced to what a player is actually typing at.
 *
 * Case and diacritics both go: nobody types the umlaut in "Jotun", and a filter
 * that requires one is a filter that appears broken for the handful of types
 * that have one.
 */
export function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/**
 * The options a query leaves, best match first.
 *
 * AND across whitespace-separated terms, the same shape as the catalogue's
 * colour filter: "elf w" means both, so a second word narrows rather than
 * widens.
 *
 * THE RANKING IS WHAT MAKES `Enter` SAFE. Typing "elf" matches Elf, Elf Warrior
 * and Werewolf, and the one the player means is the exact match -- so exact
 * sorts above prefix, prefix above a substring anywhere. Within a band the
 * engine's order survives, which is alphabetical, so the list a player scrolls
 * is still A-Z.
 *
 * An empty query returns the input untouched -- the same array, in the same
 * order -- so the unfiltered list costs nothing and cannot be reordered by
 * accident.
 */
export function narrow<T extends Filterable>(items: T[], query: string): T[] {
  const q = fold(query).trim();
  if (!q) return items;
  const terms = q.split(/\s+/);

  const banded: { item: T; band: number; at: number }[] = [];
  items.forEach((item, at) => {
    const text = fold(item.text);
    if (!terms.every((term) => text.includes(term))) return;
    const band = text === q ? 0 : text.startsWith(q) ? 1 : 2;
    banded.push({ item, band, at });
  });

  banded.sort((a, b) => a.band - b.band || a.at - b.at);
  return banded.map((entry) => entry.item);
}
