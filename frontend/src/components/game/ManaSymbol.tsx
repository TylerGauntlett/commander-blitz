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
 * well, because an `<img>` could not be recoloured anyway -- and 28 cached files
 * beat inlining the same path data into every pip on a board.
 *
 * The class names are unchanged from the disc this replaces (`pip`, `pip--inline`,
 * `pip--{tone}`), because a pile of specs select on them and because the tone is
 * still a true fact about the symbol. `data-symbol` carries the code for the
 * tests that used to read the letter out of `textContent`, which an image does
 * not have.
 */

/**
 * What `public/symbols/` actually contains, per `fetch_symbols.py`'s `WANTED`.
 *
 * Anything outside this renders as its own notation instead: a generic cost
 * above 16 is not a card this game can contain, and inventing a broken `<img>`
 * for one would be worse than showing text the player can at least look up --
 * the same call `symbolTokens` already makes.
 *
 * Hybrid and phyrexian are here now. They used to be excluded because the engine
 * rejects those costs at load time, but deck import changed that: `cards/proxy.py`
 * rewrites a hybrid *cost* into something the engine parses, and then displays
 * the card's real oracle text, which is full of `{W/U}` and `{G/P}` inside
 * activation costs.
 */
const COLORS = ["W", "U", "B", "R", "G"];

const KNOWN = new Set([
  ...COLORS,
  "C",
  "X",
  "T",
  "Q",
  "S",
  "E",
  ...Array.from({ length: 17 }, (_, n) => String(n)),
  ...COLORS.flatMap((a, i) => COLORS.slice(i + 1).map((b) => `${a}/${b}`)),
  ...COLORS.map((c) => `2/${c}`),
  ...[...COLORS, "C"].map((c) => `${c}/P`),
  ...COLORS.map((c) => `C/${c}`),
]);

export function hasSymbol(code: string): boolean {
  return KNOWN.has(code);
}

/**
 * `{G/U}` is stored as `G-U.svg`: a slash cannot be a filename on Windows, and
 * `fetch_symbols.py`'s `key_for` already makes the same substitution on the way
 * in. The two have to agree or every hybrid pip is a broken image.
 */
function fileFor(code: string): string {
  return code.replace("/", "-");
}

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
      src={`/symbols/${fileFor(code)}.svg`}
      alt={label}
      title={title ?? label}
      data-symbol={code}
      draggable={false}
    />
  );
}
