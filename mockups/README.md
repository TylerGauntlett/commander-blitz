# Board theme exploration

Five static mockups of one board state, for picking a direction before any
component is touched. Open any `.html` directly — no build, no server, no network.

```
01-arcane-slate.html      graphite + brass   · priority stone, phase ribbon
02-candlelit-table.html   walnut + leather   · zones as physical furniture
03-neon-arena.html        near-black + neon  · strike band, opponent mana meter
04-ink-and-signal.html    monochrome         · actions grouped by source card
05-planar-art.html        indigo + real art  · the art what-if
shots/                    PNG of each, 2560×1278
fetch_art.py              pulls art/ (mockup 5 only)
_state.js                 the shared board state, kept readable; inlined per file
cards/                    a later, narrower exploration: the card face itself
menu/                     a later exploration: the new-game screen
```

These five are about the **board**. [`cards/`](cards/README.md) is a separate,
later exploration of the **card face** — five directions for the frame, drawn at
each of the four widths the client uses, with the real Scryfall mana symbols
instead of the letter-on-a-disc pips. It picks up three problems these mockups
did not look at: the name colliding with its own mana cost, the invented mana
symbols, and lands all being one tan rectangle.

[`menu/`](menu/README.md) is a third, about the **new-game screen** —
`docs/roadmap.md`'s "Redesign main page". Five directions again, but unlike these
they are **interactive**: each one picks decks, opens a dossier, sets difficulty,
imports from Moxfield and opens a chair to another player. It also establishes a
constraint that applies to everything in this folder: **`art_crop` is 626×457 and
there is nothing sharper to fetch**, so any surface bigger than about 780px has
to be deliberately soft with something crisp on top of it.

All five render **turn 8 of the reference screenshot, at declare-attackers**, with
the same 30 permanents, the same hand, the same life totals — so differences on
screen are differences in design, not in content.

---

## What's wrong with the current board

Four things, in the order they cost the most:

**1. The table is green, and green is already taken.** `--felt-0: #0a1410` in
`frontend/src/theme.css` is a green ground. But `--playable: #5ce08a` is the "you
can do this" rim, and `.face--land-G` is the Forest tone. The one hue carrying the
most important signal on the board is the same hue as the board. Meanwhile
`frontend/src/styles/cards.css` goes to real trouble encoding card type in the
paper and colour identity in the border — an encoding spent against a ground that
competes with it. Every mockup here starts by making the table neutral, and it is
the single cheapest change on this page.

**2. Every control has the same weight.** `.btn` in `frontend/src/styles/ui.css` is
one 7×14px rectangle serving "Attack with 0", "Quit", "Undo", "Auto-pass" and the
speed toggle alike. The most-pressed control in the game looks exactly like the
least-pressed one. All five mockups split controls into three tiers: one large
non-rectangular commit button, contextual choices, and a demoted utility strip.

**3. Activated abilities have no presence on the card.** `Table.onBoardCard`
([Table.tsx:356](../frontend/src/components/game/Table.tsx#L356)) already routes a
click on a permanent to its `kind === "activate"` actions, and `LegalAction`
carries `source_oid` + `ability_index`. But nothing draws it — the only surface is
a sentence-shaped ghost button in `.bar__overflow`. All five mockups put a rune on
the card and a popover behind it.

**4. Two thirds of the screen is dead.** `.play` in `board.css` gives opponents
`1.25fr` against the viewer's `1fr`, permanently, so a one-opponent board spends
its largest row on empty felt while your own creature lane — the thing the current
decision is about — falls below the fold. That is
[playtest-feedback-03.md](../docs/playtest-feedback-03.md) Cycle 4 item 1, still
open. Every mockup here sizes the opponent row to its content instead.

There is a fifth, found while building: **the client hard-codes `--card-w: 104px`**,
so a 2560px display shows exactly the same small cards a 1366px one does. All five
mockups use `clamp()` instead — and, more importantly, **key it off viewport
height, not width**. The binding constraint on a 1600×950 laptop is vertical: three
lanes of cards plus a hand simply do not fit, which is why the shipped client's
`--hand-scale` media queries exist. But `--hand-scale` only ever shrinks the *hand*,
never the board, so the board is what spills. Scaling both together is what makes
all five of these fit at 950px.

---

## The five, compared

| | 01 Arcane Slate | 02 Candlelit | 03 Neon Arena | 04 Ink & Signal | 05 Planar |
|---|---|---|---|---|---|
| **Ground** | cool graphite | walnut + oxblood | near-black + rim light | warm monochrome | indigo void |
| **Commit control** | brass hex "priority stone" | wax seal | slanted neon slab | red stadium pill | gold slab |
| **Ability affordance** | violet halo + rune | violet rune, no pulse | violet diamond, hard glow | violet ring | violet rune |
| **Opponent board** | smaller cards | dimmed by candle falloff | **lands → mana meter** | smaller cards | smaller cards |
| **Combat surface** | staged-attacker strip in foot | same | **strike band between boards** | grouped action index | staged strip |
| **Phase track** | 5 phases, combat expands | brass plaque | angled HUD segments | underline only | pill segments |
| **Reads at pod size** | yes | yes | yes | **it is the design** | **no** |
| **Risk to ship** | low | medium (art direction) | medium (new combat surface) | low | high |

### 01 — Arcane Slate *(recommended)*
The conservative one. Nothing about the information architecture changes; the
ground goes neutral, panels become recessed wells instead of 1px boxes, and the
commit action becomes a hex-cut "priority stone" that always says the one thing
the turn is waiting on. The phase track collapses 13 equal ticks into 5 phases and
expands only the live one. This is the direction that could ship a piece at a time.

### 02 — Candlelit Table
The physical one. Its real idea is **zones as furniture**: `Lib 72 / GY 3 / Exile 1`
stop being text chips and become card piles whose height is the count, and life
becomes a brass dial. That reads well and takes more room than the chips did — the
opponent's whole side column had to shrink twice to fit. Worth stealing the life
dial and the piles even if the wood is not to taste.

### 03 — Neon Arena
The most structurally interesting, and the two ideas are separable from the skin:

- **The strike band.** Declared attackers leave the creature row and stand in a lit
  band between the boards, leaving a ghost behind. One "at Edgar Markov" plate
  replaces five copies of "Attack p1 with …". The wrapping sentence list is gone.
- **The mana meter.** The opponent's three lands become `R×2 open, W/B×1 tapped`.
  That is [playtest-feedback-03.md](../docs/playtest-feedback-03.md) Cycle 4 item 2,
  and `produces` already ships the data. Note the meter lists one entry **per
  source, not per symbol** — Scoured Barrens makes W *or* B and counting it twice
  would claim mana that does not exist.

### 04 — Ink & Signal
One rule: hue is spent on exactly two things — mana, and interaction state.
Everything else is grey, and card type is carried by the luminance ladder plus the
glyph. This was not a style choice, it was `cards.css`'s own argument taken to its
conclusion: at the time the seven type fills were graded 0.58 → 0.92 relative
luminance *precisely so the seven tones stayed separable at pod size*, asserted by
`frontend/tests/palette.test.ts`. (That ladder has since been removed with the
art-bleed redesign — see "What was actually built" — so this reads as history.)
The question this mockup asks is whether the hue currently spent on
card bodies is buying anything that the green "you can play this" rim would rather
have. Its second idea — **actions grouped under the card that offers them** — is
the best answer here to the wall of server-written sentences, and is independent
of the palette.

### 05 — Planar (the art what-if)
Real art, and **it costs the board its type encoding**. Look at
`shots/05-planar-art.png` at 110px: land, creature and enchantment are no longer
separable, because the art band overwrites the exact channel the luminance ladder
lives in, and it overwrites it with something whose brightness nobody controls.
The frame keeps a hairline of type tint and it is not enough at that size.

The panel on the right is the other bet, and it is the one worth taking: **text
frames on the board, art only in the preview rail**. It costs nothing — the board's
encoding is untouched — and it delivers most of what art is actually for, which is
recognising and enjoying the card you are reading.

---

## Card art: what actually works

[docs/card-catalog.md](../docs/card-catalog.md) is what was eventually built.
The superseded proposal was Moxfield search → card
id → asset CDN, fetched once and stored in the repo. Each leg, tested:

| Step | Result |
|---|---|
| `api2.moxfield.com/v2/cards/search/user?q=…` | **403 Cloudflare interstitial** to any scripted client |
| `assets.moxfield.net/cards/card-AWala-normal.webp` | 200, 53 KB — but needs the id only the blocked search returns, and serves the *whole card*, not the art |
| `api.scryfall.com/cards/named?exact=…` | 200, open, no key, returns `image_uris.art_crop` |
| `cards.scryfall.io/art_crop/….jpg` | 200, ~40–100 KB |
| `api.scryfall.com/cards/search?q=!"Vampire" t:token` | 200 — tokens resolve too |

**The doc's architecture is right and its endpoint is not.** Keep fetch-once →
store-in-repo → skip-if-present → no service running anywhere; swap the lookup to
Scryfall. That is also a strict improvement, because `art_crop` is already the
cropped art band a frame wants, where Moxfield's asset would need the art cropped
back out of a rendered card.

`fetch_art.py` implements exactly that in ~60 lines of stdlib. Running it twice
downloads nothing the second time.

**Coverage, measured across both decks:** 133 of 138 non-token cards resolve.
The five that do not are custom names in `data/cards/` — `Gyre Strait Leviathan`
(internally `aetherling_serpent`), `Surge of Growth`, `Tidal Broodmaster`,
`Wave of Growth`, `Whelming Tide`. So an art pipeline needs a text-frame fallback
for ~4% of cards, and mockup 05 shows that fallback on the board rather than
pretending it away.

21 crops for this board state come to 1.4 MB.

---

## What was actually built

Mockup 05 was taken, art and all -- against the recommendation below, and
deliberately. The card face then went **further than 05**, to direction D of
`cards/index.html`: the illustration now fills the whole frame and the text sits
on graded scrims. See [docs/mockup-fidelity.md](../docs/mockup-fidelity.md).

That settles the objection above in the opposite direction from the one
first tried. The first answer was to *move* the type encoding -- keep the `--stock`
luminance ladder and add a type ring drawn over the art. The second answer, and the
shipped one, is that **the encoding was solving a problem the illustration solves
better**. A ladder tells you a card is one of eight categories; a picture tells you
which card it is. Twelve Forests under the ladder were twelve copies of "one of the
tan ones" -- the same scanning problem the ladder was built for, one level up.

So the stock fill and the type ring are both gone. What carries a card now is the
illustration itself, the name, the type glyph and the type line, plus a land's
produced-mana symbols at centre-frame. The frame keeps colour *identity*, which was
never what the ladder encoded.

The failure mode moved with it, and so did the guards. What can now fail invisibly
is white text over somebody's bright crop, so that is what is asserted by number:
`frontend/tests/palette.test.ts` checks both scrims are gradients whose opaque ends
clear a darkness floor, and `frontend/e2e/legibility.spec.ts` checks the same on the
*rendered* board, where a `theme.css` override would show up and a CSS parse would
not.

`cards/fetch_symbols.py` graduated from prototype support to a real part of the
build: its SVGs are vendored to `frontend/public/symbols/` and every mana symbol
in the client is now the published one rather than a letter on a coloured disc.

Also taken: the neutral (indigo) ground, fluid height-keyed `--card-w`, the
opponent row sizing to content, the three button tiers, the ability rune, the
five-phase ribbon, and -- from mockup 02 -- the life dial and the zone piles.

Art comes from a Scryfall bulk dump, downloaded once at build time and served by
the app itself; see [docs/card-catalog.md](../docs/card-catalog.md).

---

## Recommendation

**Take 01 as the base, and port three things from the others.**

01 is the direction that can be adopted incrementally without breaking the
Playwright suite — it keeps every structural class name, so it lands as token
edits plus targeted rules rather than a component rewrite.

Port order, cheapest and highest-confidence first:

1. **Neutral ground.** `frontend/src/theme.css` — `--felt-*` and `--rail-*` only.
   No component changes at all. This is the biggest visible win per line changed.
2. **Three button tiers.** `frontend/src/styles/ui.css` — add `.btn--commit` (large,
   shaped, keyboard-hinted) and demote the tool row to icons. `ActionBar.tsx` already
   separates `PRIMARY` from the overflow, so the split exists; only the styling of
   each tier is missing.
3. **The ability rune.** `cards.css` + `CardFace.tsx` + a `hasAbility` prop from
   `Table.tsx`, computed the way `onBoardCard` already computes it:
   `actions.filter(a => a.kind === "activate" && a.source_oid === card.oid)`.
   **Caveat for whoever builds this:** the server can express an *available*
   ability but not an unaffordable one — `legality.py`'s `unplayable_reason` covers
   hand cards only — so a greyed-out "you can't afford this" state needs a new
   field. The mockups only ever show the available state.
4. **Fluid `--card-w`.** One line in `theme.css`; note `.card--tapped` measures as
   its own height, so any test reading card size must read `--card-w`, as
   [playtest-feedback-03.md](../docs/playtest-feedback-03.md) already warns.
5. **Opponent row sizes to content.** `board.css` `.play` grid rows `1.25fr 1fr`
   → `auto 1fr`. Closes Cycle 4 item 1.

Then, as separate pieces of work with their own arguments:

- **The mana meter** (from 03) closes Cycle 4 item 2 and is worth doing on its own.
- **The strike band** (from 03) is the most convincing answer to the combat
  sentence-list, but it moves a surface `full-game.spec.ts` and `clarity.spec.ts`
  both drive — every legal pair must keep its own `data-action-id`, which is what
  lets the action bar stand down.
- **Art in the preview rail only** (from 05). Low risk, and `fetch_art.py` is
  already the importer `docs/roadmap.md` asks for.

**Do not** take art onto the board itself without checking a four-player pod;
`shots/05-planar-art.png` at 110px is what that costs.

> **Superseded.** Art did go onto the board, and then to the edge of it -- see
> "What was actually built" above. Checking it at pod size is the part of this
> warning that still stands. What `shots/05-planar-art.png` actually shows is art
> *plus* a type ladder the art overwrites: two encodings competing for one
> channel. Committing to the illustration and dropping the ladder reads better
> than either half did.

---

## Notes on fidelity

> Where the **shipped client** and mockup 05 differ today, and which of those
> differences are bugs, is tracked in [`docs/mockup-fidelity.md`](../docs/mockup-fidelity.md).
> The notes below are about the mockups themselves. Read the other file before
> "correcting" anything in the client to match a mockup — several differences are
> deliberate decisions made after these were drawn.

- Same board state everywhere, from `data/cards/*.json` — card names, costs and P/T
  are the real ones. `Sunlit Barrens` in the original screenshot is **Scoured Barrens**.
- **One deliberate substitution:** one of the eight Forests is a Terramorphic
  Expanse. Nothing on the screenshot's board has an available activated ability —
  Gyre Sage's only ability is a *mana* ability, and `engine/legality.py` never
  offers those as actions (the payment solver taps them). Terramorphic Expanse's
  `{T}, Sacrifice:` is a real `activate` action at this exact step, so it is what
  the ability affordance is demonstrated on.
- Each file inlines its own copy of the state and renderer, because each must open
  standalone from `file://`. `_state.js` is the readable master; edit it and
  re-inline.
- Verified per file at **both 2560×1278 and 1600×950**: no horizontal or vertical
  overflow, no console errors, no external network requests, no broken images.
  Mockup 05 requests only local `art/*.jpg`.
- Two of those checks are worth keeping if any of this is built, because
  `overflow:hidden` on `body` hides both failures completely — the page reports
  `scrollHeight === clientHeight` while the board visibly runs under the foot:
  - **last-lane spill** — measure the last `.lane`'s `bottom` against
    `.table__foot`'s `top`. Measuring the *mat* does not work: it is stretched to
    its grid row, so its box always ends exactly at the row edge no matter how far
    the cards inside overflow. Both of those bugs were in these mockups and both
    passed a naive overflow check.
  - **panel collapse** — assert the action list still has a height. At 950px it
    silently flattened to 0 in three of the five before a `min-height` floor.

  This is the same lesson [playtest-feedback-03.md](../docs/playtest-feedback-03.md)
  draws from the mana-pip bug: an assertion about content passes happily through a
  layout failure, so where a visual property reduces to a number, assert the number.
