# Card face exploration

Five directions for the card face, small and enlarged, for picking one before
`CardFace.tsx` is touched. Open `index.html` directly — no build, no server, no
network.

```
index.html          the comparison page, self-contained
_cards.js           the sample card set, kept readable; inlined into the page
fetch_symbols.py    Scryfall /symbology -> symbols/
symbols/            28 real mana symbols as SVG, 93 KB
shots/              cards.png, cards-grey.png, cards-land.png at 2560 wide
```

Every direction is drawn at the four widths the client actually uses — 60px (a
3-opponent mat), 104px (your own battlefield), 146px (the hand) and 286px (the
preview rail) — so a direction that only works enlarged is visibly a direction
that only works enlarged.

---

## What's wrong with the card today

Three things, in the order they cost the most.

**1. The title bar is a three-item flex row.** `.face__title` in
[`frontend/src/styles/cards.css`](../../frontend/src/styles/cards.css) puts the
type glyph, the name and the mana cost on one line, so a long name competes with
its own cost for width. `Aesi, Tyrant of Gyre Strait` loses that competition:
[`docs/mockup-fidelity.md`](../../docs/mockup-fidelity.md) defect #4 records the
command-zone card clipping it to "Aesi, Tyra…". **Every direction here puts the
name and the cost on separate axes**, which is the one change all five share.

**2. Mana costs are invented symbols.** `manaPips` in
[`logic/cardStyle.ts`](../../frontend/src/logic/cardStyle.ts) renders a bare
letter on a CSS disc. Nobody who plays Magic reads a tinted `G` on a circle as a
Forest's mana. The real marks are published as SVG from an open endpoint, which
is what `fetch_symbols.py` pulls.

**3. Lands are the least designed card on screen.** `.face--land-*` gives every
land the same tan rectangle at the same luminance, separated only by hue and a
letter watermark — and lands are roughly forty percent of a board. Each direction
below redesigns the land rather than tinting it.

---

## Two decisions all five share

Neither is a direction; both fell out of building all five and apply whichever
one is taken.

**A name wraps rather than truncating.** Two lines wherever there is room for a
second one. Truncation is only used at 60px, where a second line costs a quarter
of the card's height. This is worth stating because it is easy to lose by
accident: the name band is a flex item, and leaving it at the default
`flex-shrink: 1` let the art beneath it compress the band back to one line at
104px and 146px — reintroducing the exact bug the page exists to remove.

**The 60px mat card drops the mana cost entirely.** A permanent on an opponent's
board has already been paid for. Its cost is the one line on the card that cannot
change any decision you are about to make, and at 60px it was competing for a row
against the name and the type line. All five drop it there, so the comparison
stays about the designs rather than about which one blinked first.

A third, smaller one: at 60px the type line is suppressed when it would only
repeat the name. A basic land's subtype *is* its name, so a Forest was drawing
the word "Forest" twice on a card 84px tall.

---

## The five, compared

| | A Modern Frame | B Banded | C Cost Rail | D Art Bleed | E Tactical |
|---|---|---|---|---|---|
| **Cost lives** | own row, right-aligned | own band under the name | vertical rail, left edge | scrim over the art, top | badge on the art, top-right |
| **Stock** | colour-identity gradient | flat paper, colour edge | flat paper, colour rail | art + graded scrims | dark, colour edge |
| **P/T** | lozenge, bottom right | footer band | foot of the rail | scrim, bottom right | footer band |
| **Land** | symbol embossed behind the textbox | two bands: name + mana strip | rail widens into a spine | one huge symbol, centre-frame | symbol dominates the frame |
| **Reads at 60px** | worst — most chrome | good | **best — the spine survives** | good | **best — designed for it** |
| **Enlarged** | **best — most card-like** | good | fine | **best — most attractive** | good |
| **Port cost** | medium | low | high | medium | medium |

### A — Modern Frame
The literal reading of the brief and the closest to a real post-8th-Edition card:
name band, then a cost row of its own, a bevelled art window, a type band with a
rarity-gem slot, a parchment textbox, a P/T lozenge. It is the best enlarged card
here and the worst 60px one, and those are the same fact — three raised bands
plus a footer is a lot of chrome, and on a 60px card it eats the art down to a
sliver. It needs a `min-height` floor on the art band to stay recognisable there.

The rarity gem is **drawn hollow on purpose**. It is a real slot on a real card
and there is nothing to put in it: `CardView`
([`api/types.ts`](../../frontend/src/api/types.ts)) carries no rarity, no set
code and no collector number. Filling it means plumbing new fields from
`CatalogCardDTO` through `card_view`. The hollow gem is what that costs, drawn.

### B — Banded
Chrome reduced to a flat rounded rect; everything is a full-width band on a fixed
rhythm, so the eye lands in the same place on every card. Its real property is
that **nothing reflows between sizes** — the small card is the large card with
the text band removed, so a card does not change shape when you hover it. Least
"Magic-looking" of the five and the cheapest to port: it is closest to the class
structure `cards.css` already has.

### C — Cost Rail
The cost leaves the horizontal flow entirely — a vertical rail down the left
edge, with P/T at its foot. This is the strongest possible answer to problem 1: a
name cannot collide with a cost because they are on different axes, at any width,
for any name.

Its land is the best land here. The rail widens into a coloured spine with the
produced symbol at its head, so a row of eight Forests reads as a row of spines
without reading a single name — which is what a board of lands is actually for.
Highest port cost of the five, because `.face` becomes a row rather than a
column and every child moves.

At 60px the rail is 15px across and "5/5" is not, so P/T moves into the body
there. That is a real seam in the design, and it is the price of the axis trick.

### D — Art Bleed
Art fills the frame; text sits on graded scrims top and bottom. The most
attractive and the least dense — this is the direction that finds out how much
chrome a card actually needs, and the answer it gives is "less than A uses". Its
land is a full-bleed illustration with one very large symbol centre-frame, and it
is the best-looking land of the five while saying the least.

The risk is the one `mockups/README.md` already argued about art on the board:
with no stock showing, the card's ground is whatever the illustration is, and two
cards can differ by nothing but their art.

### E — Tactical
Designed at 60px first and scaled up unchanged, so a card's shape does not move
between the mat and the preview — the enlarged version is the same geometry with
the textbox unhidden. Dark stock, maximum type size, hard contrast. The cost
rides on the art as a badge rather than sitting in the text flow, which is C's
trick spent on the other axis: the name still gets a full row.

Its land at small sizes is the symbol and almost nothing else, over a dimmed art
ground. At 60px that is more legible than anything else on this page.

---

## Greyscale: what this costs

`shots/cards-grey.png` is the twin of `shots/cards.png`. Read it before deciding.

**None of the five preserve card type through greyscale**, and that is deliberate
— the constraint was explicitly lifted for this exploration in favour of
resembling real Magic frames. In the grey twin A, B and C are three mid-grey
cards you cannot tell apart by type, and D and E are two dark ones. Type survives
only as the words in the type line.

What that means concretely, so it is not a surprise later:

- [`frontend/tests/palette.test.ts`](../../frontend/tests/palette.test.ts) parses
  `cards.css` and asserts the seven type fills span 0.58 → 0.92 relative
  luminance. Any of these five fails it.
- [`frontend/e2e/greyscale.spec.ts`](../../frontend/e2e/greyscale.spec.ts)
  asserts the type ring's ladder on the rendered board. Same.

Shipping any direction here means rewriting both, and deciding what — if
anything — replaces the ladder. The type glyph is the cheapest candidate: it is
already computed by `typeGlyph`, it is a shape rather than a hue, and none of
these five currently draw it.

**One thing greyscale gains.** The real mana symbols are distinct *shapes* — a
tree, a droplet, a skull, a flame, a sun — where the current pips are the same
disc with a different letter and a different tint. Colour identity therefore
reads in the grey twin better than it does today, and it also reads on a **tapped**
card: the symbols are circular, so a land rotated 90° still says what it makes.
A horizontal text watermark does not.

---

## Mana symbols

`fetch_symbols.py` makes one call to `api.scryfall.com/symbology`, which lists
every card symbol with an `svg_uri`, and downloads the 28 this game can produce:
WUBRG + C, generic 0–16, X, and the four non-mana symbols `SYMBOL_LABELS` covers
(tap, untap, snow, energy). Hybrid and phyrexian are deliberately not downloaded
— the engine rejects those costs at load time, so a prototype drawing one would
be drawing a card this game cannot contain.

Same architecture as the art: fetch once, store in the repo, skip on re-run,
nothing running anywhere at render time. Same provenance too — these are Wizards'
marks, served by Scryfall, exactly like the `art_crop` images
[`docs/card-catalog.md`](../../docs/card-catalog.md) already vendors. Running the
script twice downloads nothing the second time. All 28 come to 93 KB.

They are drawn with `<img src="symbols/G.svg">`, never inlined. A mockup has to
open standalone from `file://`, where `fetch()` is blocked by the opaque origin
but an `<img>` is not. The symbols ship fully coloured, so nothing needs
recolouring through `currentColor` — which is just as well, because an `<img>`
could not be recoloured anyway. **If this is ported, the same constraint applies
in reverse:** the client can inline them if it wants CSS control, but it will be
re-deriving colours Scryfall already baked in.

---

## The sample set

Eleven cards, picked to break the layouts rather than flatter them. `_cards.js`
records what each one is for and the page shows it under the picker. The load
bearing ones:

- **Aesi, Tyrant of Gyre Strait** — the longest name in the pool against a
  3-symbol cost. The collision.
- **Gyre Strait Leviathan** — no printing anywhere, so the text-frame fallback.
  Also the widest cost at 7 pips. Five of the 138 non-token cards across both
  decks are like this.
- **Terramorphic Expanse** — a land that produces no colour *and* has a real
  activated ability. Every design that leans on the produced symbol has to answer
  this one, and all five answer it with the same neutral grey mark.
- **Acidic Slime** — counters, damage marked, a keyword and summoning sickness at
  once.
- **Explosive Vegetation** — the longest rules text, and no P/T.

Two of them are not on the board state the other mockups render: `mockups/fetch_art.py`
was extended with **Sol Ring** and **Beast Within** because the board has no
artifact and no instant, which is two of the eight `typeTone` values with no
sample. Both are real cards in `data/cards/`.

---

## Notes on fidelity

- **This page is allowed to scroll vertically.** The no-overflow rule in
  [`mockups/README.md`](../README.md) exists because a board mockup that scrolls
  is a board that does not fit; a gallery is not a board. Horizontal overflow is
  still a failure and there is none at either viewport.
- Verified at **2560×1278** and **1600×950**, across all 11 cards × 5 directions
  × the four toggle combinations: no console errors, no external network
  requests, no broken images, no horizontal overflow, no clipped rules text on
  any enlarged card, no truncated name above 60px, and nothing rendering below
  **8.5px** — the floor `mockup-fidelity.md` #5 says is already binding on the
  client at one opponent.
- Those last three are measured, not looked at, for the reason
  `mockups/README.md` gives: a check about content passes happily through a
  layout failure. Two of them caught real bugs while building —
  - `.face { height: 100% }` inside a card whose height is `auto` with a
    `min-height`: the percentage had nothing definite to resolve against, so the
    face collapsed to its content and every enlarged card wore a band of empty
    stock under its textbox. It looks like padding. It is not.
  - the name band's default `flex-shrink: 1`, above.
- The greyscale toggle is an **inspection tool, not a gate**. It is there so the
  cost above is visible per direction, not to fail a direction.

---

## Recommendation

**Take C's cost rail and E's land, on B's band structure.**

That is not a fourth direction; it is the three findings the page produced,
which happen to sit in different files:

1. **The cost belongs on a different axis from the name** (C). This is the
   original problem and C is the only answer that cannot fail — not at any width,
   not for any name. E's badge is the same idea with less structural cost, and is
   the fallback if C's row-flex rewrite is too much.
2. **A land is its symbol** (E at small, C at large). Both beat the current tan
   rectangle by a wide margin, and the symbol is the only thing on a land that
   reads at 60px, sideways, in greyscale.
3. **Bands, not bevels** (B). B is the cheapest to port — closest to the class
   structure `cards.css` already has — and its no-reflow property is worth more
   in play than A's frame is: a card that changes shape when you hover it costs
   you the place you were looking.

**Do not take A wholesale.** Its enlarged card is the best on the page and its
60px card is the worst, and the board has far more 60px cards than 286px ones.
Take its enlarged arrangement — name, cost, art, type, textbox, P/T, in that
order — which is the brief's arrangement, and which all five already use.

**D is the one to take if the goal is that the game look good in a screenshot**,
and it is a real goal. It is also the one that gives up the most information, and
`mockups/README.md`'s argument against art on the board applies to it in full.
