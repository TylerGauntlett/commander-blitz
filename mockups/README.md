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
handheld/                 a Steam Deck board, driven by a real pad
seat/                     an opponent's seat at 332x84, three densities, six directions
rail/                     the action rail at 243x514, one direction across three decisions
self/                     your own orb at 154x518 — and what to take off it
handheld-board/           the whole 1280x800 screen, at full fidelity
door/                     the latest: the front door as a game menu, three cards on a Deck
```

These five are about the **board**. [`cards/`](cards/README.md) is a separate,
later exploration of the **card face** — five directions for the frame, drawn at
each of the four widths the client uses, with the real Scryfall mana symbols
instead of the letter-on-a-disc pips. It picks up three problems these mockups
did not look at: the name colliding with its own mana cost, the invented mana
symbols, and lands all being one tan rectangle.

[`handheld-board/`](handheld-board/README.md) is the most recent, and the only
round that draws **the whole 1280x800 screen** rather than one component over a
sketch of one. It puts `seat/06-muster.html`'s opponent card, `self/03-plinth.html`'s
player orb and `rail/`'s action panel on the same Deck, on the layout 06
sketched, with the real board state and real art — three files, one game, one
turn apart, differing only in what the rail is deciding. Its reason for existing
is that every earlier round made claims its own mockup could not check: a strip
saying "3 lands, 2 untapped" over a dashed sketch is unfalsifiable, and a row
saying "Bloodghast 2/1" beside a grey rectangle is not the design it will be
beside Bloodghast. So the round's own gate is **`seatsAgree`** — the seat's five
counts, derived three independent ways, must match — and the type and target
floors are asked of the whole screen instead of one panel. Running the rail to
the foot of the screen the way 06 sketched it takes it from 514px to **748**, and
the action list from the shipped board's 172px to 363–398: seven or eight rows
without scrolling, with the card reader back off its hold. Six findings, of which
the sharpest is that the hand overflowed its own row by 79px and sat on top of a
button, invisibly, because the deck is `overflow: hidden` and nothing was
asserting the number. It is also the first screen on which `self/`'s
three visual arguments — a fourth seat joining the pod, zone chips sized against
an opponent's, and a portrait crop — can be looked at rather than reasoned about;
the crop, which was that direction's one stated price at 40% of the painting's
width, comes back to 84% because this layout's foot is 122px taller and the
portrait is the elastic member.

[`door/`](door/README.md) is the most recent, and the only round whose subject is
a **control** rather than a layout. It takes the front door -- a wordmark, a gold
button, a text field and a footer of 11px links -- and makes a Steam Deck main
menu out of the one game-shaped object already on it: the fan of four card backs
at [`HomeScreen.tsx:78-87`](../frontend/src/components/lobby/HomeScreen.tsx#L78-L87),
which today is decoration. Three cards, Decks / Play / Join, sliding apart from
the selected one and stacking on the far side, driven by a real `Gamepad` build
lifted whole from `handheld/`.

Being about a control rather than a layout is what makes it the first round with
**two drivers**. `measure.mjs` walks each file through all three selections,
because the pose it opens on is the one pose in which nothing is stacked;
`drive.mjs` presses things, because "three cards that are actually selectable" is
a claim a still cannot check -- and it earned its place immediately by finding a
tile that passed every layout gate in the round while being unclickable, its Join
field sitting in the plate's centre and swallowing the click it had to swallow to
be typeable.

Its own gate is **`labelClear`**: the brief asks two cards to overlap, and
overlap's failure mode is a card covering the one thing that says what the card
under it *is*. From it fall the round's three portable findings -- **the stack
depth is bounded by the longest label** (a name has to fit the sliver its card has
left, which is why 02's spine is worth more than it looks); **a stacked card's
name must sit on its outer edge**, which costs the launcher direction the
left-aligned title it most wanted; and **the stack costs a card everything except
its name**, so a direction whose idea lives in the body of the card is a direction
the stack argues against. It is also the first surface in this folder authored *at*
the 16px and 44px floors rather than repaired to them: eight of the shipped door's
own text sizes are named in `handheld.css`'s generated 144-selector override list,
which is every word on that screen bar the wordmark.

[`self/`](self/README.md) is the round before it and the only one whose subject is
**the viewer**. It started as "draw your own orb in the grammar `seat/` settled"
and turned into a round about **subtraction**: the first pass passed every gate
and was still busy, because a uniformity gate only proves the noise is evenly
spaced. Two channels came off — the viewer's commander damage, which the pod
already carries on the opponents' seats six pixels above, and the board counts,
which re-state the 841×518 of lanes beside them. Ten cells where there were
nineteen. And then a second correction the gates were just as blind to: with the
room freed, the viewer's zone chips had grown to 68px beside identical 20px chips
on the seats six pixels above, which is a component shouting at its neighbour.
They are a seat's size again, inside transparent 44px targets — **the target is
bigger than the ink**.

It is also the only round whose ghosts are on the *other* side: the three
opponents are real muster seats and the lanes are the dashed rectangles, since
the question is not whether the orb is good but whether it says anything that
seat already says. Its findings: **no gate can see redundancy** — that one has to
be noticed; the seat's decision to demote its zone marks is a cost of 96px rather
than a fact about zones; the commander's portrait is a control and every
direction draws its three states (`In play` / green `Ready` / amber `Need 8`)
rather than implying them; and once commander damage goes, **the orb stops
varying with how many opponents are at the table at all**, which removes the last
reason `.orb--compact` exists.

[`rail/`](rail/README.md) is the round before that, and the only one that is **one
direction drawn three times** rather than five compared: the right rail at
243×514, answering declare-attackers, declare-blockers and the main phase out of
the same parts. Its question is not which shape looks best but whether one shape
survives all three decisions, so the shared master carries the grammar and a file
may add only its own list — 01 adds no CSS at all. It starts from a fraction
rather than a look: `handheld.css` gives the rail's four panels 514px and the
rows that the turn is actually spent in get **172 of them**, so the round's own
gate is `listShare` and it fails a file under half. All three come out at 78–86%.
It also carries three findings that hold whichever direction wins — the numeral
chip's off-centre-at-16px bug exists a second time in the hint bar's `.glyph`,
the enlarged card's rules box has the same reflow-on-scrollbar defect as the
action list, and **a mana cost and a card name do not both fit a 243px row at the
16px floor**, which nothing currently says out loud.

[`seat/`](seat/README.md) is the round before it, and the narrowest: **one opponent's
seat on the handheld board**, where three of them share 1017px and the shipped
strip answers that by deleting a channel. It is the only round with a
*uniformity* gate — it counts the distinct paddings, gutters and cell geometries
on the component, because "nothing lines up" turns out to be the number seven —
and it carries three findings that hold whichever direction wins: an opponent's
hand is a 44px button into a panel that says "Hidden"; every zone count lost its
label at 16px with nothing put in its place; and **an opponent's seat does not
show their board.** It shows their zones. Lands are not in the payload at all
and the noncreature-permanent count is in it and rendered by nothing, so "how
many lands and enchantments have they got" is unanswerable from the strip at any
density. The round's sixth file is the first one that answers it.

[`handheld/`](handheld/README.md) is the round both of those sit inside, and the only one that
is about **input** rather than about looks: five ways a Steam Deck's sticks, d-pad
and face buttons could drive a Commander board, each a live `Gamepad` API build
with a keyboard fallback. It starts from a measurement taken on the board these
five designed — at 1280x800, `shots/05-planar-art.png`'s layout puts **444 of
635 rendered elements below 12px, the smallest at 2.11px** — and takes a 16px
floor as a hard constraint, which turns out to decide the layout rather than
decorate it. It also answers `docs/roadmap.md`'s first backlog line.

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
