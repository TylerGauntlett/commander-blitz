/**
 * A mana symbol, drawn as the actual mana symbol.
 *
 * These used to be a letter on a CSS disc -- a `G` in a green circle -- which is
 * a mark nobody who plays the game recognises. The real ones are published as
 * SVG from Scryfall's open `/symbology` endpoint, and `mockups/cards/fetch_symbols.py`
 * pulls them. They are vendored into `public/symbols/` under exactly the
 * architecture the card art uses (docs/card-catalog.md): fetch once, store in the
 * repo, skip on re-run, nothing running anywhere at render time. `e2e/art.spec.ts`
 * fails the run if the page fetches from any host but this server, and that
 * covers these too.
 *
 * Drawn with `<img>` rather than inlined. Scryfall's symbols ship fully coloured,
 * so there is nothing to recolour through `currentColor` -- which is just as
 * well, because an `<img>` could not be recoloured anyway -- and 54 cached files
 * beat inlining the same path data into every pip on a board.
 *
 * The class names are unchanged from the disc this replaces (`pip`, `pip--inline`,
 * `pip--{tone}`), because a pile of specs select on them and because the tone is
 * still a true fact about the symbol. `data-symbol` carries the code for the
 * tests that used to read the letter out of `textContent`, which an image does
 * not have.
 *
 * Which codes have artwork, and what file each one lives in, is
 * `logic/manaSymbols.ts` -- the orb's mana panel asks the same questions from a
 * module that cannot import a component.
 */

import { hasSymbol, symbolFile } from "../../logic/manaSymbols";

interface Props {
  /** The symbol's code without braces: `G`, `4`, `T`. */
  code: string;
  /** Extra classes. `pip--inline` for a symbol inside a sentence. */
  className?: string;
  /** What to show if there is no SVG for this code. Defaults to the code. */
  fallback?: string;
  /** Overrides the braced notation on hover, e.g. "Green" in the deck picker. */
  title?: string;
}

export function ManaSymbol({ code, className, fallback, title }: Props) {
  const classes = className ? `pip ${className}` : "pip";
  // The braced notation, so a screen reader hears "{G}" rather than nothing.
  // It is the same string the oracle text would have used.
  const label = `{${code}}`;

  if (!hasSymbol(code)) {
    return (
      <span className={`${classes} pip--text`} data-symbol={code} title={title ?? label}>
        {fallback ?? code}
      </span>
    );
  }

  return (
    <img
      className={classes}
      // Root-relative: the hand, the preview rail and the action panel all draw
      // these, and none of them know where they are in a URL.
      src={`/symbols/${symbolFile(code)}.svg`}
      alt={label}
      title={title ?? label}
      data-symbol={code}
      draggable={false}
    />
  );
}
