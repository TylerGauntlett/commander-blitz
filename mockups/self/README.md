# Your own orb — handheld

Five directions for **the viewer's own orb on a 1280×800 Steam Deck screen**,
drawn in the palette [`../seat/06-muster.html`](../seat/06-muster.html) settled
for an opponent — and around the question that palette raised, which is not *how
should the orb look* but **what should still be on it**. For picking a direction
before [`PlayerOrb.tsx`](../../frontend/src/components/game/PlayerOrb.tsx),
[`CommandZone.tsx`](../../frontend/src/components/game/CommandZone.tsx) and the
`.play__mine` half of [`handheld.css`](../../frontend/src/styles/handheld.css)
are touched. Open any `.html` directly — no build, no server, no network.

```
01-ledger.html    the five surviving facts, in the same cells the seats use
02-banner.html    five facts do not need a column — 74px tall, +2 cards per lane
03-plinth.html    the art is the ground, the life dial is the seal
04-dial.html      life is the only thing left that moves — a 148px instrument
05-console.html   six of eight things left are controls — size them that way
_self.css         the bezel, the opponents' seats, the shared cells, the palette
_self.js          the fixture, the marks, the portrait button, the review shell
assert.js         the gates, as numbers; inlined per file
inline.py         splices the masters into each file; --check for CI
measure.mjs       drives all five at three densities and seven states
detail.mjs        one orb at 3x, for looking at rather than measuring
shots/            1280×800 PNGs per file per state, plus *-detail.png at 3x
```

Every file boots to **three opponents, you holding priority**, and takes three
keys:

```
1 2 3   how many opponents are at the table
s       rest → priority → spending → cmdzone → unpaid → out → noart
m       run the gate and draw its failures on the elements that failed
```

**The three opponents are real muster seats, not ghosts.** That is the one
structural difference from the seat round's harness and it is the whole reason
this one exists: the question is not "is this orb good", it is **"does this orb
belong on the same table as that seat"** — and, as it turned out, "is it saying
anything that seat already says". The lanes, the right rail and the hand row are
the ghosts.

---

## What this round is actually about

The first pass drew everything the shipped orb draws, in muster's cells. It
passed every gate and it was still busy, **because passing a uniformity gate only
proves the noise is evenly spaced.** Two channels came out, and they were the two
largest.

### 1. The viewer's commander damage

The pod already carries commander damage on the opponents' seats, six pixels
above. A second copy of the same subject on the panel below is the reader doing
the deduplicating. In the first pass this was three named rows, a 21-notch track
and a gauge full of hatching — about **70px of a 518px column**, and visually the
loudest thing on the panel by a wide margin.

**What that costs, said plainly.** An opponent's seat draws
`worstSource(seat)` — the worst damage *that seat* has taken, from anyone — so
what **you** have taken is not on any of them. `DMG[0]` is still in the fixture,
still says 16 from the Duelist, and no direction here draws it. If it turns out
to be wanted, the cheap fix is **not** to put it back on the orb: flip the
*seat's* chip from "worst damage they have taken" to "damage they have dealt to
you". That is the more decision-changing number on an opponent's card anyway, and
it puts the fact where the reader is already looking.

### 2. The board counts

Lands, creatures, other permanents, total power and the creature pip run —
muster's whole battlefield row, which exists because an opponent's board is *not
drawn anywhere else*. Yours is. It is **841 × 518 of the same screen**, at 66×92
a card, in three labelled lanes, with a green rim on what you can use. A count of
it on the panel beside it is the client re-stating its own default view.

`perms`, `detailCell`, `pipsCell`, `powerCell` and `gaugeTicks` are all still in
`_self.js` and all still used — by `seatHTML`, for the **opponents**, where
muster's argument for them holds exactly as it did. They are not dead code; they
are the other half of the point.

### What survives

Five things, and every one is either something the board cannot show or something
you press:

| | |
|---|---|
| who you are, whose turn it is, whether you may act | a name, a ring, a tick |
| your commander | **the portrait, which is the button that casts it** |
| your life | one number |
| your mana | by kind, with what a hovered spell would take |
| the five zones | a seat's 21px chip, inside a 44px target |

**A consequence worth naming: the reduced orb does not vary with how many
opponents are at the table.** Commander damage was the only channel that did.
Press 1 2 3 — the opponents' row changes and the panel does not move a pixel,
which removes the last reason `.orb--compact` and its `:has()` branches exist.

The numbers, before and after, from the same gate:

| | first pass | after |
|---|---|---|
| cells on the panel (01) | 19 | **10** |
| the viewer's zone chip | 20px, and not reachable at all | **20px, inside a 44px target** |
| channels drawn twice on one screen | 2 | **0** |

---

## The portrait is a control and stays one

`CommandZone.tsx` renders the commander's portrait as the thing you press to cast
it, with the cost beside it and the tax beside the cost. Every direction here
keeps that — `.win` is a `<button>`, at 44px or more in both dimensions in all
five — and the three states are drawn, not implied:

| state | the button |
|---|---|
| on the battlefield | plain edge, caption reads `In play`, **no price** — a commander's mana cost while it is already in play is not a number anybody acts on |
| in the command zone, **and you can pay** | the `--playable` rim, `④🌳💧 +2` and **`Ready`** in green |
| in the command zone, and you cannot | the `--staged` rim, the same price, and `Need 8` in amber |

**Castable and affordable are two different things**, and the `unpaid` review
state exists so the second row of that table is on screen rather than assumed:
`{4}{G}{U}` is six, plus two of tax is eight, against three open.

Two things the desktop round learned the hard way and this one inherits:

- **It is `aria-disabled`, never `disabled`.** A disabled control dispatches no
  mouse events, so "the full card is one hover away in the preview rail" was
  false for a commander you could not currently cast — which is most of the game.
  [`../orb/README.md`](../orb/README.md) records the fix.
- **The cost belongs on the button.** It moved off its own row and onto the
  portrait's caption strip, which every direction was drawing anyway. A price is
  part of the control it is a price for.

---

## The box, measured rather than guessed

```
play column     1280 − 12 (deck padding) − 8 (gap) − 243 (--rail-r at 19vw) = 1017
viewer's mat    634 (shell) − 96 (--pod-seat-h) − 4 (gap)                   =  534
.mat padding    8px, kept — logic/zoomFit.ts reads it as VIEWER_MAT.padY
--mat-side      clamp(132px, 12vw, 190px) at 1280                           =  154
```

**The orb is 154 × 518 and the lanes beside it are 841 × 518.** A direction may
take a different box; it says so in its own file, the gate holds it to whatever
it declared, and the ghost lanes grow or shrink by what it took. Only 02 does —
and it hands 160px of width back rather than taking any.

---

## The one state, and the seven `s` walks

`../handheld/_handheld.js`'s `ME` — turn 8 at declare-attackers, the same game the
seat and pad rounds look at.

> Aesi, Tyrant of Gyre Strait · **34 life of 40** · mana `G5 U3 G/U1 C1` ·
> Lib 72 · Hand 6 · GY 3 · **Exile 1** (so the fifth zone mark is present, which
> is the reflow every direction has to survive) · CMD 0.

The board counts and `DMG[0]` are **still in the fixture and drawn by nothing** —
on purpose. The panel is choosing not to draw a channel it has, which is a design
decision; being unable to draw one it lacks would be a payload bug, and that is
what `06-muster.html` exists to fix on the other side of the table.

| state | what it is for |
|---|---|
| `rest` | **somebody else's turn.** Not the empty state — it is where an orb spends most of a four-player game, and the one a design that only looks right lit up will fail. |
| `priority` | your turn **and** you may act — two different things, drawn two ways |
| `spending` | hovering Beast Within `{2}{G}`, so three mana rows show what you would have left and a `−n` for what goes |
| `cmdzone` | Aesi back in the command zone, **+2 tax**, and you can pay: the green `Ready` button |
| `unpaid` | the same, with three mana open instead of ten. Priced, not lit — **and the round's mana reflow**: four groups become two |
| `out` | eliminated. The panel must not change size at the moment somebody is looking at it. |
| `noart` | `logic/cardArt.ts` returns `undefined` before the image map is fetched and `null` when a printing has no art. |

---

## The findings

### 1. The target is bigger than the ink, and that is the whole answer

Muster demoted an opponent's five zone marks from 44px buttons to plain 20px
chips and argued it properly: 96px will not hold a 44px row *and* the battlefield
row. **None of that reaches your own orb** — four of the five have something real
behind them, and a 518px column has room.

The first pass concluded from that "so make them 44px, then 68, then 72, because
the floor is a floor and the room exists". **That was wrong, and it was wrong in
a way no gate could catch.** Set beside the opponents' seats six pixels above,
whose chips are 20px, the viewer's read as bloated: the same five facts, in the
same colours, three times the size, on the panel that needed the *least*
emphasis. Size is a signal, and it was saying something untrue.

**The chip is a seat's, to the pixel; the button around it is 44 and
transparent.** The panel spends the height on being reachable and none of its ink
on it. `boxKinds` was as happy at 72px as at 21 — a uniformity gate measures
whether sizes are consistent *within* a component and has nothing to say about
whether one component is shouting at the one next to it.

The library stays a plain chip in all five — hidden information whoever owns it,
and
[`PlayerOrb.tsx:96-101`](../../frontend/src/components/game/PlayerOrb.tsx#L96-L101)
already argues that a control which does nothing when clicked is worse than no
control. **Which ones you can press is drawn rather than learned:** the four
buttons' chips carry a lit top edge and a dropped bottom one, the library a
recessed one. The fills are identical, so the difference is in the relief and
survives `e2e/greyscale.spec.ts`.

### 2. A uniformity gate cannot see redundancy, and cannot see shouting

The first pass scored `padKinds` 2, `gapKinds` 1 and `boxKinds` 3 against the
shipped column's seven and four — and was still hard to read, twice over.

Every one of those evenly-spaced cells was a number, and two of the subjects were
already on screen elsewhere. And when those went, the cells that remained grew
until they were three times the size of the identical cells on the seats above.
**Both failures pass every gate in `assert.js` cleanly**, because `boxKinds`
measures whether sizes are consistent *within* a component and nothing measures a
component against its neighbour. That is a question about the whole board, and it
is the one thing in this round that had to be noticed rather than measured —
twice, and by looking at it.

### 3. Three answers to the same picture, and the round does not pick one

`art_crop` is 626 × 457 — 1.37:1 — and `mockups/README.md` records there is
nothing sharper to fetch. The three column directions crop it three ways and each
says so:

| | window | ratio | of the painting's width |
|---|---|---|---|
| 02 banner | 92 × 68 | 1.35:1 | **~100%** — the whole composition, smallest |
| 05 console | 148 × 74 | 2:1 | **100%**, trimmed top and bottom |
| 01 ledger | 148 × 170 | 0.87:1 | ~64% |
| 04 dial | 148 × 130 | 1.14:1 | ~83% |
| 03 plinth | 148 × 250 | 0.59:1 | **~40%** — largest picture, heaviest crop |

Whether a small whole painting beats a large slice of one is a real question and
this is the round that puts all of them on the table.

### 4. `::after` is spoken for, and `.dial > *` is not what you meant

Two separate bugs that render identically — a solid pie where a ring was meant —
and between them they cost more time than any layout decision here. The hover
label every mark carries is `[data-name]::after`, including `opacity: 0`, which a
file's own `::after` does not override unless it says so; and a blanket
`.dial > *` rule matched the hole element and turned its `position: absolute`
off at equal specificity. The donut now lives in `_self.css` with both traps
written down beside it.

---

## The gates, and the numbers they measured

Four floors are `../seat/assert.js`'s, unchanged: **16px of type, zero native
tooltips, nothing escaping its box, nothing collapsed.** `boxKinds`, `padKinds`
and `gapKinds` stay live. Two things differ: **the 44px target floor has teeth
here** (finding 1), and **both dimensions of the box are checked**, because a
column can fail by being too wide as well as too tall — which is what
`handheld.css:1218` records happening in the shipped client, where `.mat__side`
grew, `overflow-y: auto` turned it into a scrollbar rather than a visible fault,
and the graveyard pile ended up behind the hand.

Pasted from `node measure.mjs`, not hand-written:

```
BY DENSITY (state: priority)
file             n  orb      budget   lanes  cells  box  pad  gap  font  hit  esc  clip  PASS
---------------  -  -------  -------  -----  -----  ---  ---  ---  ----  ---  ---  ----  ----
01-ledger.html   1  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
01-ledger.html   2  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
01-ledger.html   3  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
02-banner.html   1  999×74   999×74   12     10     3    2    1    16    44   0    0     yes
02-banner.html   2  999×74   999×74   12     10     3    2    1    16    44   0    0     yes
02-banner.html   3  999×74   999×74   12     10     3    2    1    16    44   0    0     yes
03-plinth.html   1  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
03-plinth.html   2  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
03-plinth.html   3  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
04-dial.html     1  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
04-dial.html     2  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
04-dial.html     3  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
05-console.html  1  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
05-console.html  2  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
05-console.html  3  154×518  154×518  10     10     3    2    1    16    44   0    0     yes
```

**All 50 rows pass** — five files × (three densities + seven states). Every panel
holds **10 cells**, down from 19, and 8 in `unpaid` where two mana rows go.
`minHitPx` is 44 everywhere: the zone chips are 21px and the buttons around them
are 44, which is the shape of finding 1. The
only non-zero cell anywhere is `clip: 1` in `out` (the loss line
`Lost — 21 commander damage` ellipsising in a 140px strip) and in 02's `unpaid`
(the commander's name giving way to a longer cast label in the head row).
Clipping is not a failure on its own — a direction that clips a **count** has
lost the datum, and none of these does.

**Against the shipped viewer's column: `padKinds` 2 and `gapKinds` 1, versus
seven and four.**

---

## The five

### 01 — Ledger · `01-ledger.html`
*The conservative one, and the bar the others clear.* Same column, same order the
shipped panel uses, nothing invented — and the five surviving facts in the same
cells the seats use. The room the subtraction bought goes to **the two things
that cannot be mistaken for an opponent's**: a 148 × 170 portrait and a 100px
life cell with a 48px numeral. Everything else — mana groups, zone chips — is a
seat's size exactly. **Cheapest port in the round: CSS over surviving markup.**

### 02 — Banner · `02-banner.html`
*Five facts do not need a column.* A 154 × 518 column exists because the shipped
orb has fifteen things to stack; after the cut there are five, and five things
need one line. **999 × 74** — four columns, one subject each: the portrait, life
at 40px, who-you-are over your mana, and a rail of five 44px zone targets.

Costs 78px of lane height, hands back the whole 154px column and its gutter:
**ten cards per lane become twelve**, drawn in green. Also the only file at
`boxKinds: 2`, and the only one that crops the painting not at all.

**Biggest bill in the round**, and it is a board decision taken on an orb's
evidence: `.mat`'s grid at
[`board.css:114`](../../frontend/src/styles/board.css#L114), `.mat--compact`
after it, and `--pod-lanes-h`'s solver reads a lane width this changes — so
`logic/zoomFit.ts` is in scope, which nothing else here touches.

### 03 — Plinth · `03-plinth.html`
*The commander is not in the panel; the commander IS the panel.* The direction
the subtraction helped most: a full-bleed ground under muster's veil and a
**148 × 250 portrait**, the largest picture in either round and nine times the
area of a seat's window, with the life dial stamped over its lower right —
costing the overlap instead of a row.

The overhang is *reserved* rather than indented, which is the desktop round's
hard-won fix. Its own cost is stated plainly: about 40% of the painting's width
is off the sides, and this is the direction that will find out what that does to
a commander whose art is a wide landscape.

### 04 — Dial · `04-dial.html`
*Of what is left, what actually moves?* The portrait changes three times a game,
the name never, the zones by one. **Life is the only continuous quantity a player
tracks on their own panel**, and the shipped orb draws it as a 34px disc in a
corner. This gives it a **148px ring — the full width of the column**: 48px
numeral, the arc filled to life over 40, the remainder drawn as the part that is
not there.

Its counter-argument is in the file: a dial cannot be compared across seats the
way a bar can, and the seats above use bars.

### 05 — Console · `05-console.html`
*Six of the eight things left are controls or the price of one.* Mana **one group
to a row at 44px** with the symbol at 24, and life deliberately the smallest thing
on the panel at 30px. Its mana block is the elastic region rather than a fixed one
above a spacer, so the `unpaid` reflow spends its 94px as air *around* the rows
that shrank instead of as a void beneath them.

**04 and 05 disagree about the same panel** — 132px of life versus 30 — and that
disagreement is the round's real decision. Look at them side by side rather than
at either alone.

---

## Recommendation

**Take 01, and take 02's question seriously before you build it.**

01 is the only direction that costs nothing but CSS, changes no board geometry,
and loses no channel that survived the cut. It is deliberately the least
interesting file here, and that is the argument for it: everything this round
found is expressible inside it.

But **02 is the finding, not just a direction.** The 154 × 518 column was sized
for fifteen things and there are five. If the counts and the damage rows are
really going, the column itself is the next thing to question, and 02 is what
that looks like: 78px of height for what a column spent 518 on, and two more
cards in every lane. Its bill reaches `logic/zoomFit.ts`, so it is a board
decision — answer it on `../handheld/`'s evidence, not an orb mockup's.

Then, in order:

1. **The portrait's three-state button** (all five files, `winButton` in
   `_self.js`). Independent of every layout question and the smallest change with
   the most direct effect on play: `Ready` in green when you can actually cast,
   `Need 8` in amber when you cannot, nothing when it is already in play.
2. **The 21px chip inside the 44px button** (`zoneMarks` and `.zhit`). A one-line
   markup change that makes the viewer's zones reachable *and* the same weight as
   an opponent's. Do not do it by growing the chip.
3. **03's life seal**, if the identity claim is wanted. It buys a row for an
   overlap. Do not take its ground without also taking its veil rule and its
   narrow column.

**Do not take 04 and 05 together.** They are the two ends of one question about
how much of this panel life deserves, and picking both means picking neither.

---

## Notes on fidelity

- **Real in shape, chosen in value.** Aesi, Tyrant of Gyre Strait is a real
  commander with its real cost and its real `art_crop` from `../art/`; the three
  opponents are `../seat/_seat.js`'s, unchanged, so the seats above the orb are
  the same seats that round drew.
- **Nothing that survived the cut is missing from any of the five.** Name,
  priority, whose turn it is, portrait, two-line commander name, commander state,
  mana cost, commander tax, castability, life, loss reason, the mana row with its
  spend preview and its split disc for an ambiguous source, and all five zone
  counts. What was cut is listed at the top of this file and at the top of
  `_self.js`, with the reason.
- **No native tooltips anywhere.** A `title` opens on hover and on nothing else,
  so on a controller it is information that cannot be reached. The client had 45
  and has none left; the gate fails a file that grows one.
- **The accessible name never describes something the sighted reader cannot
  see.** `lifeLabel` is separate from the opponents' `gaugeLabel` for exactly
  this reason — a shared string would have put commander damage back on the panel
  through a quieter door.
- **`inline.py --check` is CI-safe** and the masters are the single source: five
  hand-inlined copies of one file quietly stop being the same file, which is the
  contract `../seat/` and `../handheld/` run on.
