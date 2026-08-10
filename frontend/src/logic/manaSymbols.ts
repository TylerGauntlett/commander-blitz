/**
 * What `public/symbols/` actually contains, and how to name a file in it.
 *
 * Split out of `ManaSymbol` because two callers need it and only one of them is a
 * component: the orb's mana panel asks "is there a published mark for a source
 * that makes one of two colours" while deciding what to render, and `logic/`
 * cannot reach into `components/` to ask. The inventory is data about the repo's
 * own vendored files, so it belongs on this side of the line either way.
 *
 * Kept in step with `mockups/cards/fetch_symbols.py`'s `WANTED` by hand. A
 * disagreement between the two is invisible in the DOM and shows up only as a
 * blank square, which is what `e2e/cycle3.spec.ts`'s `naturalWidth` check exists
 * to catch.
 */

const COLORS = ["W", "U", "B", "R", "G"];

/**
 * The ten two-colour hybrids, in the order Scryfall actually publishes them.
 *
 * That order is *guild* order, not WUBRG-adjacent order, and three of the pairs
 * run backwards against WUBRG: the printed symbols are `{R/W}`, `{G/W}` and
 * `{G/U}`. There is no `{W/R}`, `{W/G}` or `{U/G}` to fetch.
 *
 * This was generated as `a` before `b` in WUBRG order, which put those three
 * non-existent codes in `KNOWN` while `fetch_symbols.py` -- generating the list
 * the same wrong way -- skipped them as "not in symbology". So `hasSymbol` said
 * yes to three files that were not on disk, and the guard meant to prevent a
 * broken image was the thing producing one. Listed literally now, in both places,
 * because a generated pair order is exactly what got this wrong.
 */
const HYBRIDS = ["W/U", "W/B", "U/B", "U/R", "B/R", "B/G", "R/G", "R/W", "G/W", "G/U"];

/**
 * Anything outside this renders as its own notation instead: a generic cost above
 * 16 is not a card this game can contain, and inventing a broken `<img>` for one
 * would be worse than showing text the player can at least look up.
 *
 * Hybrid and phyrexian are here because deck import made them reachable:
 * `cards/proxy.py` rewrites a hybrid *cost* into something the engine parses, but
 * the card's real oracle text is displayed verbatim and is full of `{W/U}` and
 * `{G/P}` inside activation costs.
 */
const KNOWN = new Set([
  ...COLORS,
  "C",
  "X",
  "T",
  "Q",
  "S",
  "E",
  ...Array.from({ length: 17 }, (_, n) => String(n)),
  ...HYBRIDS,
  ...COLORS.map((c) => `2/${c}`),
  ...[...COLORS, "C"].map((c) => `${c}/P`),
  ...COLORS.map((c) => `C/${c}`),
]);

export function hasSymbol(code: string): boolean {
  return KNOWN.has(code);
}

/**
 * The published symbol for a source that makes one of two things, or `null`.
 *
 * The orb's mana panel needs this: "Add {G} or {U}" is one mana of a choice, and
 * `{G/U}` is precisely the mark for that. Callers pass the pair in whatever order
 * they hold it -- `SYMBOL_ORDER` in `logic/mana.ts` puts `C` last where Scryfall
 * writes colourless hybrids `C`-first -- so both orders are tried and the answer
 * is checked against `KNOWN` rather than assumed.
 */
export function pairSymbol(a: string, b: string): string | null {
  if (hasSymbol(`${a}/${b}`)) return `${a}/${b}`;
  if (hasSymbol(`${b}/${a}`)) return `${b}/${a}`;
  return null;
}

/**
 * `{G/U}` is stored as `G-U.svg`: a slash cannot be a filename on Windows, and
 * `fetch_symbols.py`'s `key_for` already makes the same substitution on the way
 * in. The two have to agree or every hybrid pip is a broken image.
 */
export function symbolFile(code: string): string {
  return code.replace("/", "-");
}
