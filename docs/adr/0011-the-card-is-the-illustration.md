# ADR 0011 — The card is the illustration

**Status:** accepted

Records the art-over-ladder decision. [ADR 0006](0006-no-colour-accessibility-requirement.md)
keeps the scrim and frame floors as plain-legibility gates; this ADR is about why
there is a scrim at all.

## Context

The card face used to carry its *type* as colour: a luminance ladder across the
card stock, one step per type, with a matching ring, on the argument that a type
line is unreadable at pod size and the stock's brightness is not. It worked, and
it had a cost that only showed on a real board: a lane of basic lands under the
ladder was a lane of identical tan rectangles. The ladder tells you a card is one
of eight categories. A picture tells you which card it is.

Three other complaints came from the same face: the title bar was a flex row
that let a long name lose the width fight with its own cost and truncate; mana
costs were a letter on a coloured disc, a mark nobody who plays the game
recognises; and a card with no printing was a hatched plate that read as an error.

The card-face round drew five directions at the widths the client actually
renders. Its recommendation was a cost rail and a symbol-only land on a banded
structure. What shipped was the fourth direction, art bleed — against that
recommendation and deliberately, because the game looking like the game in a
screenshot was accepted as a real goal.

## Decision

**The illustration fills the frame, and everything else sits on it.**

- **Full-bleed art, text on graded scrims.** The head scrim carries the type
  glyph, the name, then the cost on its own row; the foot carries the type line,
  `oracle_text` where there is room, keywords, counters and P/T. Both scrims are
  gradients whose opaque ends must clear a darkness floor and the text carries a
  shadow, because the picture under it was chosen by nobody here.
- **Card type is the glyph and the type line, never a tint.** No
  `.face--type-*` colour rule may come back. The type line is never reduced to
  the bare subtype: with the ladder gone, it and the glyph are the only things
  that say what kind of card this is. Supertypes are dropped at board size
  (`shortType` in `frontend/src/logic/cardStyle.ts`), which is a different thing.
- **Colour identity keeps the frame.** The border and the gradient under the art
  are colour identity (`frameTone`), and on a card with no printing that gradient
  is the whole card, with a quiet `no art` on it (`CardFace`) rather than a
  broken image or a hatch. A land's frame narrows to the colour it taps for and
  its produced-mana symbols go large and centre-frame, so a lane of lands reads
  without reading a name; a land that taps for no colour gets a neutral mark.
- **The name wraps; it does not truncate.** Two lines wherever there is room, and
  the name band may not be left at `flex-shrink: 1` or the art compresses it
  back. The one clamp is the compact mat (`.mat--compact`): one line, and the
  mana cost is dropped, because a permanent on an opponent's board has already
  been paid for and its cost cannot change a decision you are about to make.
- **The frame is a thin proportional border with a floor**
  (`border: max(2px, calc(var(--card-w) * 0.014))` in `frontend/src/styles/cards.css`).
- **Commander is a crown inside the name**, not a badge; a badge is illegible at
  pod size and a crown is a shape.
- **Rules text is `pre-wrap`** on every face and in the handheld reader, because
  the engine puts the keyword line first with a newline after it.
- **Every mana mark goes through `ManaSymbol`**, drawing the vendored Scryfall
  SVGs from `frontend/public/symbols/` — the cost row, rules text and action
  labels (`SymbolText`), the plinth, the panel, the deck picker. Reaching the
  disc fallback means a symbol is missing and `frontend/e2e/cycle3.spec.ts`
  fails the run. The orb's mana panel was the last exception and is not one: the
  mark a player recognises is the mark whichever way the mana is flowing.
- **Mana you have is counted by kind, not repeated.** `manaGroups` in
  `frontend/src/logic/mana.ts` collapses the pool to one chip per kind, the way a
  player says it out loud; a mark per mana wraps at symbol width. A two-colour
  choice is the published hybrid symbol.

## Consequences

- Text over an unknown illustration is the one thing here that can fail
  silently, so it is guarded by number rather than by eye:
  `frontend/tests/palette.test.ts` asserts the art is full bleed, both scrims
  clear the floor, text carries a shadow and no type-colour rule has crept back;
  `frontend/e2e/art.spec.ts` asserts the art fills the frame on the rendered
  board; `frontend/e2e/legibility.spec.ts` asserts the resolved scrim contrast
  and the frame width at pod size, where a `theme.css` override would show and a
  CSS parse would not.
- A card is less *dense* than the banded directions were. Rules text is the
  first thing to go as the card shrinks, and at pod size the picture, the glyph
  and the type line are what is left. That is the trade.
- Before putting art on any new surface, draw a full pod at its smallest card.
  That is the size that decides whether a signal is carrying anything.
- Reversing this means re-adding a type tint, and the tests above are written to
  refuse it. Read them first.

## Rejected

- **The luminance ladder.** Per-category, not per-card; a board that is largely
  lands became a board of one tone.
- **The cost rail, the banded frame, the tactical face and the modern frame.**
  Each was best at one width and worst at another; the rail was the best land at
  pod size and the most expensive port. Their two shared rules — wrap the name,
  drop the cost on the compact mat — were taken regardless.
- **Reducing the type line to the bare subtype** at board size. Cheap, and it
  deletes the one text channel that still says what the card is.
- **Letter-on-a-disc mana**, anywhere, including as a "different idea" for mana
  you hold versus mana you owe.
