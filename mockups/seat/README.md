# Opponent seat exploration — handheld

Five directions for **an opponent's seat on a 1280×800 Steam Deck screen**, and
a sixth that combines them, for picking a direction before `PlayerOrb.tsx` and
the compact half of [`handheld.css`](../../frontend/src/styles/handheld.css) are
touched. Open any `.html` directly — no build, no server, no network.

```
01-dogtag.html          one cell, one gutter, one radius · the conservative one
02-vitals.html          life and commander damage are one object · the seat is one target
03-plinth-strip.html    the art is the ground · creatures become pips
04-meters.html          every number has a denominator · two ends of one track
05-seat-card.html       one 300px card at every density · the rest goes back to the board
06-muster.html          all five combined, plus the two channels none of them draws
_seat.css               the Deck bezel, the ghosted board, the palette; inlined per file
_seat.js                the pod, the marks, the review shell; inlined per file
assert.js               the gates, as numbers; inlined per file
inline.py               splices the masters into each file; --check for CI
measure.mjs             drives all six at all three densities, prints the table below
shots/                  1280×800 PNGs, one per file per density
                        · 06-muster-detail.png is two seats at 3x, for the meters
```

Every file boots to **three opponents** and takes three keys:

```
1 2 3   how many opponents are at the table
s       cycle the first seat: rest → active → targetable → out → noart
m       run the gate and draw its failures on the elements that failed
```

**06 is not a sixth direction** — it is 01–05 taken apart and reassembled around
a hole all five of them share, which is that none of them draws the opponent's
battlefield. See [the third finding](#3-none-of-the-five-shows-board-state-they-show-zone-counts)
below and the file's own header.

These are about **an opponent**. [`../self/`](../self/README.md) is the sequel
and the round this one's sixth file caused: five directions for **the viewer's
own orb**, with these seats drawn beside them at full fidelity as the thing to
match. It answers one question left open here and raises one that undercuts a
little of the above. The zone marks demoted below are demoted because 96px is
96px: on the viewer's 518px column they go back to being targets at 68–72px. But
06's battlefield row and its commander-damage gauge are both **deleted from the
viewer's panel entirely** there, because the pod already draws commander damage
on these seats and the viewer's own board is 841×518 of lanes six pixels away.
Both channels are exactly right on an opponent's card and redundant on your own,
which is a distinction none of the gates in this folder can see. [`../orb/`](../orb/README.md) is the same
component on a desktop 190px column and is the direct parent of this round;
[`../handheld/`](../handheld/README.md) is the Steam Deck board and the pad that
drives it; [`../`](../README.md) is the board, [`../cards/`](../cards/README.md)
the card face, [`../menu/`](../menu/README.md) the main menu and
[`../flow/`](../flow/README.md) the lobby. All of them share `../art/`.

Unlike the pad round these are **not interactive** past the three review keys.
An opponent's seat is one component in one moment, so the comparison is about
form — but a seat has *three* forms, one per density, and that is exactly the
thing a single screenshot has been hiding.

---

## The complaint, and what it measures to

> *The full words like X Creatures takes up considerable space and doesn't feel
> like a game panel. There is also the commander damage that could be better
> visualized as it feels floating and disjointed. Lastly, all items should fit
> cleanly and uniformly unlike the inconsistent padding shown today.*

Three complaints, and all three are numbers.

**1. The threat line is a sentence.** `.orb__spine` renders `threatParts()` as
prose — "1 creature · 1 untapped · 2 power" — at 16px, one line, `nowrap`,
ellipsised
([handheld.css:604-632](../../frontend/src/styles/handheld.css#L604-L632)). At
three opponents a seat is 332px wide and that sentence is most of a row. It is
also the only thing on the seat drawn as *words*: everything beside it is a chip
with a number in it, which is why it reads as a caption that wandered into a
control panel.

**2. Commander damage floats because it is a plate in a row of plates.**
`.orb__cmd` is one of three `.orb__panel`s laid along the strip, each with its
own padding and its own internal gutter, and it draws **one chip per opposing
seat including the zeros**. Its meter is already the fraction of 21
([PlayerOrb.tsx:566-576](../../frontend/src/components/game/PlayerOrb.tsx#L566-L576)),
which is the right idea drawn 3px tall underneath a chip that does not use it.

**3. The padding is not inconsistent by accident — there are seven of them.**
Read off the stylesheets; every one of these is on screen at once on a single
compact seat:

| | |
|---|---|
| `.mat--compact` | `5px 7px` — [handheld.css:228](../../frontend/src/styles/handheld.css#L228) |
| `.mat--compact .orb__body` | `2px` — [handheld.css:750](../../frontend/src/styles/handheld.css#L750) |
| `.mat--compact .cmdslot` | `3px` — [handheld.css:782](../../frontend/src/styles/handheld.css#L782) |
| `.orb__spine` | `3px 6px` — [handheld.css:611](../../frontend/src/styles/handheld.css#L611) |
| `.mat--compact .orb__panel` | `1px 4px` — [handheld.css:1255](../../frontend/src/styles/handheld.css#L1255) |
| `.cmd-pip` | `1px 4px 2px` — [board.css:864](../../frontend/src/styles/board.css#L864) |
| `.pile__leaf--top` (compact) | `0 6px` — [handheld.css:888](../../frontend/src/styles/handheld.css#L888) |

…plus one more from the second opponent (`.piles` gains `1px`,
[handheld.css:1027](../../frontend/src/styles/handheld.css#L1027)) and one more
from the third (`.mat--compact` becomes `2px 6px`,
[handheld.css:1046](../../frontend/src/styles/handheld.css#L1046)), and at least
four gutters: `2px 10px`
([handheld.css:749](../../frontend/src/styles/handheld.css#L749)), `3px 8px`
([handheld.css:608](../../frontend/src/styles/handheld.css#L608)), `4px`
([board.css:823](../../frontend/src/styles/board.css#L823)) and `6px 5px`
([board.css:1018](../../frontend/src/styles/board.css#L1018)).

Each of the eleven is locally reasonable and none of them is visible in the CSS.
All of it is visible on screen as the ragged edge the round was opened about, so
`assert.js` counts them: **`padKinds` and `gapKinds` are gates in this round**,
and every direction here reports 2–3 and 1–4 against the shipped seven and four.

---

## The arithmetic nobody had done

`handheld.css` re-values the rails inside `@media (max-width: 1366px)`, so at
1280×800 the board column is `1280 − 12 − 8 − 243 = **1017px**`, and
`.play__opponents` is a flex row with a 10px gap. A seat therefore gets:

```
one opponent      1017 × 96      --pod-seat-h, handheld.css:160
two opponents      503 × 96
three opponents    332 × 84      the shorter cap, handheld.css:1041
```

Into 332 × 84 the shipped seat has to put **fifteen facts**: seat name,
commander name, portrait, life, three commander-damage chips, up to five threat
clauses, and four or five zone counts. And four of those zone counts are
**44×44 touch targets**, because they are the only route into `ZonePeek`.

Five targets at 44px is **220px of a 332px seat.** Two thirds of an opponent,
spent on controls. That is the fact this whole round runs into.

### What the shipped layout does about it, which is worth knowing before you judge anything here

**From the second opponent onwards it stops drawing commander damage.**
`handheld.css:1097-1100` sets `.orb__mana` and `.orb__cmd` to `display: none`
under `:has(> .mat--compact:nth-child(2))`, and the file argues the case
properly: commander damage is a progress number rather than a threat number, the
viewer's own orb still shows every seat's damage against *them*, and R2 has the
full mat. It is a fair argument.

It also means **the screenshot this round was opened on — the one with `P0 0`
and `P2 0` on it — is the one-opponent seat**, and the pod seat is the one with
the channel missing entirely. Every direction in this round draws commander
damage at all three densities. That is what they are all buying with their
layout, and it is why the arithmetic here is harder than the shipped layout's.

Each direction answers the 220px differently:

| | how it reaches a zone | what it costs |
|---|---|---|
| **01 Dogtag** | keeps all of them at 44px | the seat wraps to three rows and stands **150px** |
| **02 Vitals** | the whole seat is one stop | one extra input to open a graveyard |
| **03 Plinth Strip** | targets sit **on** the art, so the picture costs no column | the art is the only identity channel |
| **04 Meters** | one 44px target, and it is the graveyard | hand, exile and command are reached through the sheet |
| **05 Seat Card** | three targets in a fixed 300px card | 96px at three seats instead of 84 |

---

## Three findings that belong to no direction

**1. An opponent's hand is not a control, and the library already knows it.**
`PlayerOrb.tsx` argues the case for the library in so many words — *"hidden
information, and a control that does nothing when clicked is worse than no
control"*
([PlayerOrb.tsx:96-101](../../frontend/src/components/game/PlayerOrb.tsx#L96-L101))
— so the library renders as a plain element. The hand next to it is the same
fact: `types.ts` sends `hand: null` for every seat but the viewer, and
`ZonePeek.tsx` renders **"Hidden — 4 cards"**, which is the number already
printed on the chip you just pressed. It is a 44×44 button anyway.

The exception is the one the library already has. `hand_revealed` carries the
cards this seat has been *shown* — by "look at target player's hand" and nothing
else — and when it is non-empty the peek has something to open. So the rule is
the library's own rule applied to the zone beside it: **a button when there is
something behind it, a mark when there is not.** Marco's hand is a control in
these five and the other two seats' hands are not, which is why both cases are
on screen at once.

Five targets becomes three. **That is 88px of a 332px seat, and it is why the
seats in this round fit at all.** It is worth doing whichever direction wins,
and it is worth doing on its own.

**2. Every count on the seat lost its name and nothing replaced it.**
`.pile__label` is hidden on a handheld — "Lib", "Hand", "GY", "CMD" all go
([handheld.css:1758](../../frontend/src/styles/handheld.css#L1758)) — and what
is left of a zone is a coloured chip with a number in it. The reasoning was that
the piles are in a fixed order with distinct graphics, and
[`docs/handheld-playtest.md`](../../docs/handheld-playtest.md) already records
the answer: *a fixed order only helps somebody who already knows it.*

So every mark in this round is a **shape**, and the same shape in all five
files: a headstone is a graveyard, a fan of three cards is a hand, a face-down
card is a library, a dashed outline is exile, a star is the command zone, a
crown is commander damage. That is `.pile__label`'s job done in the space the
label could not have. This is a legibility argument about a chip whose label was
removed, and **not** a colour-accessibility one, which
[ADR 0006](../../docs/adr/0006-no-colour-accessibility-requirement.md) puts out
of scope; the zone hues are the shipped ones and are unchanged.

The marks are `aria-hidden` SVG with the real name on the cell's `aria-label`,
surfaced by hover and by the cursor — the route `../handheld/` established when
it deleted the client's native tooltips. There are no `title` attributes in this
round and the gate fails a file that grows one.

### 3. None of the five shows board state; they show zone counts

This is the one that produced 06, and it is worth more than the layout argument
above it.

Every direction here draws **five zone counts** and a **creature summary** and
the pair reads as "their board". They are not the same thing. Read off the
fixture:

| the channel | in the data | drawn by |
|---|---|---|
| creatures, untapped, power, fliers | `seat.threat` | all five |
| library, hand, graveyard, exile, command | `seat.lib` … `seat.cmd` | all five |
| **artifacts and enchantments** | **`seat.threat.other`** | **none of them** |
| **lands** | **not in the model at all** | **none of them** |

`threat.other` has been in [`_seat.js`](_seat.js) since the round opened and
[`threatParts()`](_seat.js) drops it on the floor, which is the shipped
`logic/threat.ts`'s own behaviour copied faithfully. Marco's Favorable Winds and
the Duelist's Impact Tremors are both on those battlefields — they are in
[`../handheld/_table.js`](../handheld/_table.js), where this pod comes from —
and both are invisible on every seat in this round.

Lands are worse than invisible. They were never in the model, and `manaOpen` has
been standing in for them: it counts **untapped sources**, so a seat with five
lands and none open and a seat with one land read identically, and neither says
anything about how developed the board is. `_seat.js` now carries `lands` for
all three seats, read off `../handheld/`'s actual battlefields — 3, 5 and 4.

So the honest scoreboard against *"how many lands, creatures and enchantments
have they got"* is: **creatures yes, lands no, noncreature permanents no** — in
all five, at every density. No amount of layout work fixes that; it is content,
and it is why the sixth file exists. It costs two cells.

---

## The six, compared

Measured, not estimated — `node mockups/seat/measure.mjs` prints exactly this.
The shipped column is read off the stylesheets where a number is derivable and
marked `—` where it is not.

| | shipped | 01 Dogtag | 02 Vitals | 03 Plinth | 04 Meters | 05 Card | 06 Muster |
|---|---|---|---|---|---|---|---|
| **Seat at 1 opponent** | 1017 × 96 | **1017 × 54** | 1017 × 74 | 1017 × 74 | 1017 × 90 | **300 × 96** | 332 × 96 |
| **Seat at 3 opponents** | 332 × 84 | 332 × **150** | **332 × 74** | **332 × 74** | 332 × 90 | 300 × 96 | 332 × 96 |
| **Height vs budget, 1 / 3** | 0 / 0 | **−42** / +66 | **−22 / −10** | **−22 / −10** | −6 / +6 | 0 / +12 | 0 / +12 |
| **Board width returned** | 0 | 0 | 0 | 0 | 0 | **+717 at one seat** | **+685 at one seat** |
| **Distinct cell geometries** | — | **2** | **2** | 3 | 4 | 3 | 3 |
| **Distinct paddings** | **7–9** | 2 | 2 | 2 | 3 | 2 | 2 |
| **Distinct gutters** | **≥4** | **1** | 2 | 3 | 4 | 3 | **1** |
| **Smallest type** | — | 16 | 16 | 16 | 16 | 16 | 16 |
| **Targets per seat** | 4–5 | **4–5** | 1 | **4–5** | 1 | **4–5** | 1 — the seat |
| **Smallest target** | 44 | 44 | 74 | 44 | 44 | 44 | **332 × 96** |
| **Commander damage at 3 seats** | **not drawn** | one cell per source | **21-track per source** | one chip, the worst | **both ends of one track** | one chip, the worst | **both ends, one tick per source** |
| **Threat** | a sentence | one cell each | one mark each | **pips per creature** | pips **against your life** | one mark each | **a count per kind, plus pips** |
| **Lands** | **not drawn** | **no** | **no** | **no** | **no** | **no** | **counted** |
| **Tapped lands** | **not drawn** | **no** | **no** | **no** | **no** | **no** | **a meter** |
| **Creatures, counted** | a clause | a cell | a mark | pips only | pips only | a mark | **a count and a meter** |
| **Tapped creatures** | **not drawn** | **no** | **no** | pips only | pips only | **no** | **a meter** |
| **Artifacts, enchantments** | **not drawn** | **no** | **no** | **no** | **no** | **no** | **counted** |
| **Commander name at 3 seats** | dropped | clipped | clipped | clipped | clipped | clipped | **fits whole** |
| **Draws the commander** | 44px thumb | 44px thumb | **no** | **the whole seat** | **no** | 52 × 88 thumb | **72 × 43 window + the ground** |
| **Survives `noart`** | n/a | yes | yes | **loses identity** | yes | yes | **yes, name intact** |
| **Density branches killed** | — | **all 3** | **all 3** | **all 3** | **all 3** | **all 3** | **all 3** |
| **Port cost** | — | **lowest** | medium | medium | high | high | highest |

Every direction passes the gate at every density and in all five seat states.
`escaped`, `belowFloor`, `smallHits`, `titleAttrs`, `brokenImages` and
`collapsedRegions` are zero everywhere; `clipped` is 0–3 and is always a
commander's name being ellipsised, never a count.

**06 clips nothing at any density.** Moving the counts out of its head row and
into a row of their own left the commander's name about 190px instead of 110,
which is the first seat in this round where *Isperia, Supreme Judge* fits whole
at three opponents. Its `2 paddings / 1 gutter` is also the tightest pair here
and ties 01 — the direction that spent everything else to get there — so the two
uniformity gates the complaint reduces to are answered by the file carrying the
most information, not by the one carrying the least.

### 01 — Dogtag *(the conservative one, and the one that prices the floors)*

*One cell, one gutter, one radius.* Four constants and a refusal to have a
fifth: 44px of height, 4px of gap, 8px of corner, 4px of plate padding. Every
datum then becomes one cell in one rack — the threat clauses, the damage chips
and the zone marks all end up the same object, which is complaint 1 and
complaint 3 answered without changing a single piece of information or its
order. The rack wraps, so there are no density branches at all: the layout is a
consequence of the width rather than of a seat count.

It reports **2 cell geometries, 2 paddings and 1 gutter** — the tightest numbers
in the round — and it is the cheapest port by a distance: `.orb__spine` swaps
`threatClause` for a mark and a number, and `handheld.css`'s three `:has()`
branches become `flex-wrap`.

**At one opponent it is the best result here: 1017 × 54, forty-two pixels back.**
One row of cells is all a seat ever needed at that width, and the shipped seat
is 96px only because it stretches to whatever it is given.

**At three it does not fit.** Fifteen cells of ~48px is 780px of rack against
332, so it wraps to three rows and stands **150px** — 66px over budget, taken
straight off the viewer's board. That is not a tuning problem, it is what 44px
targets cost at that width, and it is worth having drawn once. Judge this one on
the duel and on the idea, not on the pod.

### 02 — Vitals

*A player dies two ways; draw them as one object.* Life is the largest number on
the shipped seat and commander damage is chips parked in a plate that floats
wherever the row leaves room — but they are the same fact, **how close is this
seat to dead**, drawn as two unrelated components. Here they are one block, the
block is first, and it is the only thing on the seat allowed to be large: the
life numeral, and beside it one track per source filled to its fraction of 21.

Sixteen sits three quarters across its track. Nothing on the shipped seat has
ever said that out loud — the player is expected to hold 21 in their head and
subtract, which was the desktop round's clearest single finding and is still not
built.

The second move is what makes the rest fit: **the seat is one stop.** It takes
the player-target action when one is legal and otherwise opens the seat sheet,
where the board, the zones and the per-source detail live at a readable size.
The counts stay on the strip as marks, because reading them is constant and
opening them is rare. **74px at every density**, 2 cell geometries, 2 paddings —
and it is the only direction that keeps a per-source damage track at three
seats, which is the channel the shipped layout deletes there.

**What it gives up is the portrait, and it does not get it back at any density.**
The lethal block plus two runs of marks is the whole width; there is no column
left for a picture, so four seats are told apart by name. That is the desktop
round's finding 4 accepted rather than answered, and it is the honest reason to
prefer 03 or 05 if a pod is the case you care about.

Its weak point on screen is the tracks column: at 74px wide, a source at zero is
a nearly invisible sliver, and the numeral on a full track sits at the right-hand
edge of its own fill. It reads well at 16 and less well at 3.

### 03 — Plinth Strip

*The commander is not in the seat; the commander IS the seat.* The desktop round
shipped this argument and the handheld layout did not inherit it: on a 190px
column the art became the orb's ground and four seats stopped being four grey
rectangles told apart by a name, while on the strip the same art is a 44px
thumbnail in a column of its own — paying full width for a picture too small to
recognise. Here the art is the ground again, it costs no column and no plate,
and every number sits on it. **That is where the room for 44px zone targets comes
from, and this is the only direction that keeps all of them at three seats and
still comes in under budget.**

**The creatures become pips**, and this is the idea worth stealing on its own.
"4 creatures · 2 untapped · 4 power · 1 flier" is four clauses, about 170px, and
a player reading it is reassembling one picture out of four numbers. One pip per
creature says it in 60px and says it better: filled is untapped, outlined is
tapped, a clipped corner flies, and the total power rides at the end in a chip.
"Two open blockers, one of them in the air" without reading a word.

**One damage chip, not three.** The shipped plate draws every seat including the
zeros and its reason is real — a plate that appears on the first hit is a reflow
at the worst possible moment — but a *reserved* slot answers that just as well as
a filled one. So the chip is a fixed slot showing the source nearest to lethal,
filled to its fraction of 21, and the rest are one input away. 80px back at
three opponents.

It is **74px at every density**: 22px back at one and two opponents, 10px back
at three, and every `:has()` branch gone.

**Its risk is the one the desktop round recorded, and `s` → `noart` is where you
see it.** The art is the only thing carrying seat identity, so a commander
shuffled back into the library takes the whole ground with it and what is left is
the flat plate the other four have. And at 332px the marks cover most of the
picture anyway — the identity claim is strong at one opponent and weak at three,
which is the reverse of where it is needed.

### 04 — Meters

*Every number on a seat is secretly a fraction, and the seat prints the
numerator.* `16` is 16 of 21. `25` is 25 of 40. `2 power` is 2 of the 34 life
**I** have. `84` is 84 of a 99-card deck. The player does four divisions in their
head, per seat, per turn, on a 7-inch screen; this direction does them instead.
Nothing here is a bare number — it is a fill with the number written on it, and
because the fills share one scale, **three seats compare by length**, which a row
of chips can never do.

The new object is the **lethal gauge: one track with two ends.** Life fills from
the left; commander damage closes from the right, one hatched tick per source at
its fraction of 21. When they touch, the seat is dead — which is exactly true.
It is the only drawing in this round where *am I closer with damage or with the
commander* is answered by looking. The Duelist at 18 life with 16 commander
damage against them reads as a seat about to die, from across the row.

And the board gauge is a **correction**: it is scaled against the viewer's own
life, because "4 power" means nothing on its own and "4 of the 34 that would kill
me" is the actual question.

**It costs rows.** A meter row cannot go under 18px with a 16px numeral on it, so
the seat is 90px at every density — 6px better than 96 at one and two opponents,
6px worse than 84 at three. It also has the loosest numbers in the round (4
geometries, 3 paddings, 4 gutters), because a gauge, a mark and a target are
genuinely three different objects here and it does not pretend otherwise.

### 05 — Seat Card

*Design for the narrowest seat and give it to everybody.* `handheld.css` holds
**three** layouts for one component, chosen by counting seats with
`:has(> .mat--compact:nth-child(2))` and `:nth-child(3)`. That is the
`.orb--compact` problem the desktop round named — *"the component is maintained
twice"* — arriving one layout later with an extra copy, and the way it drifted is
on record in the file itself: two opponents fell straight through the gap between
the branches and every two-player-plus-one seat sat 16px over its cap until a
Storybook sweep caught it.

So: **one card, 300px wide, the same at one opponent and at three.** Nothing
conditional but whose turn it is. It also takes the desktop round's one stealable
idea — the life dial stamped over the portrait's lower right, half on the picture
and half off it, so life costs the overlap instead of a row.

**And that is where the prize is.** A seat that does not stretch does not eat the
row: at one opponent it takes 300 of 1017 and hands back **717px — seven cards at
96px.** The handheld layout clipped every opponent's lanes to zero height because
"112px of orb plus a row of cards cannot both be legible at this width", and at
one opponent that was never true; it was true of a seat that grew to fill
whatever it was given. The green ghost beside the seats is that room, and it
shrinks on its own as seats arrive — 717 at one, 407 at two, 97 at three.

**It costs 12px at three opponents** (96 against 84), because one card has to
hold a portrait, a name, a threat row and a zone row and 84px will not do it. The
trade is that the 12px buys back a component instead of a branch.

### 06 — Muster *(the five combined, around the row none of them has)*

*Lands, creatures, other — counted, and split tapped from untapped.* Not a sixth
direction: 01–05 read back with finding 3 in hand, and rebuilt around the five
facts a player actually takes at a glance.

```
how many lands            how many of them are tapped
how many creatures        how many of them are tapped
how many other permanents
```

**The answer is a row, and the row is three cells of one kind.**

```
[land] 2/3      [creature] 2/4      [gem] 1
 untapped / total, with a 3px meter along the cell's bottom edge
```

The denominator is the count — exact, at any board size, with nothing to count.
The numerator is what is still untapped, which is the number that decides
whether they can block or hold up a counterspell. The meter is that same
fraction as a *length*, so "are they tapped out" is answered without reading and
the dim trough **is** the tapped count. All three sit at the same x on every
seat, so three opponents' mana compare by bar length down a column.

A meter and not a pip run, because a pip run cannot do lands: eight is the
honest cap (`pileLeaves`'s reason) and a Commander board passes eight lands by
turn eight, at which point the run stops being able to show the ratio at all. A
meter is exact at twenty lands and costs no width. The fourth cell is the
**detail** and is visibly not one of the three — 03's pips, one per creature,
filled is untapped and a clipped corner flies, plus the total power. It is the
only place fliers are drawn and the only place a creature is an individual.

*Two versions of that cell were built and the first one is worth recording.* It
filled the whole cell height to the fraction with a 2px rule at the boundary,
which was crisp — and which, at two thirds of a 62px cell, lands exactly where
the slash in `2/3` sits, so the boundary read as a second divider inside the
numeral. A meter that has to dodge its own label is in the wrong place. The
bottom edge is never crossed by type, and a bar on a baseline is already what a
reader takes a fraction from.

**What it takes from where:** 05's fixed card (at **332px** — the width
`handheld.css:1041` already gives a seat at three opponents, so it is designed
for the worst case and never grows); 04's lethal gauge; 02's one tick per source
on it, so a pod keeps per-source damage where the shipped layout deletes it;
03's pips and art-as-ground; 01's discipline — **2 paddings, 1 gutter**, three
cell geometries differing only in height.

**What the row cost, because it cost something.** 96px will not hold four rows
one of which is 44 tall — 18 + 22 + 44 is already 84 of the 81 that four rows
and three gutters leave. So **the zone counts are marks here and not targets**:
five numbers to read on a 20px row, with the seat sheet as the route into any of
them. Three things make that the right way round — finding 1 already said two of
the five were never buttons and a third only sometimes; reading a zone count is
constant and opening one is rare; and the seat is itself a stop, **332 × 96** of
it, which is the largest target in the round by a distance.

If zone targets are non-negotiable the trade goes the other way: keep a 44px
foot row and the three counts have to share it with five 44px marks, which
leaves about 100px for them — enough only if the pips go.

**The picture, which is the other thing the row bought.** `art_crop` is 626×457,
landscape, and [`../README.md`](../README.md) records that there is nothing
sharper to fetch. 05 renders it into a **52 × 88** portrait column — 0.59:1 —
so `object-fit: cover` throws away most of the painting to show a vertical
slice, which is why the commander is hard to place on a 05 card and why 03 had
to spend the whole seat on the ground to get identity back. A **72 × 43 window**
keeps the picture's full width and trims only its top and bottom margins, where
an `art_crop` keeps its background: more of the painting in two thirds of the
area, and the 55px it hands back is what the two full-width rows are made of.
The portrait is also uncovered, because life moved into the gauge.

The art appears **twice on purpose** — once in that window as a picture somebody
can recognise, once as the card's ground under a heavy veil as colour identity
across 332px. One file, one fetch, no extra column. And because the head row is
now only a name, **`noart` is not the risk it is on 03**: a commander in a
hidden zone costs a picture, not an identity. Press `s` four times.

**What it costs:** 96px at three opponents, the same twelve pixels 05 spends;
the zone targets above; and the highest port cost in the round, because it is
the union of four directions plus a `logic/threat.ts` change and a `types.ts`
field. Nothing can draw lands until the engine counts them.

**It is also the only file sitting on a different board.** 01–05 ghost the
shipped handheld layout — rail beside the play area only, hand running the full
width underneath it, battlefield as three stacked lanes. 06 ghosts a sketched
one instead: a 26px **game information** strip across the very top spanning both
columns, then the rail as a full-height column with the buttons at its foot, the
hand stopping where the rail begins, and the battlefield as two rows — creatures
and the noncreature permanents sharing the top, lands across the bottom. The
arithmetic is untouched (the play column is still 1017px, the foot still 148px
and `--seat-h` still 96, so a seat is still 332 × 96 at three opponents; the
strip's 32px comes off the ghost board, which is the honest place for it), but a footprint comparison
between six files only means something while all six are measured against one
board, so **if that layout is the one, its rules belong in the masters** and
06's overrides go away. They are at the end of its `<style>` and `<script>`,
under one comment each, for exactly that reason.

---

## Recommendation

**Take 06, and do all three findings regardless of what you take.**

The round's first recommendation was *03's seat at 05's fixed width* and it was
right about the two pieces and wrong about the size of the job: that combination
was never measured, and building it surfaced finding 3 — that neither 03 nor 05
nor any of the other three tells you how many lands or how many enchantments an
opponent has. **06 is that combination, built and measured**, with the two
missing cells in it and 04's gauge and 02's per-source ticks as well.

It is 332 × 96 at every density, passes the gate in all five seat states,
reports **2 paddings and 1 gutter** — the tightest pair in the round, tying the
direction that spent everything else to get there — and is the only seat here
that clips nothing at three opponents. It costs 12px of the viewer's board at
three opponents, hands back 685px at one, **and it spends the zone targets** to
buy the battlefield row. That is the one decision in it worth arguing about, and
the argument is in the file: 96px will not hold a 44px zone row and a
battlefield row at the same time, and of the two, only one answers the question
an opponent's seat is looked at for.

**If 06 is too much to port at once**, it decomposes cleanly, and the order
below is that decomposition.

Port order, cheapest and highest-confidence first:

1. **The hand is a button only when `hand_revealed` is non-empty** (finding 1).
   Independent of every layout question, a handful of lines in `PlayerOrb.tsx`,
   and it is 88px of a 332px seat. Do this one first whatever else happens.
2. **The threat line becomes marks** (from 01, in 03's pip form where there is
   room). `threatParts()` already returns exactly the right shape; what changes
   is that `threatClause()` stops being rendered and its text moves to
   `aria-label`. This is complaint 1, and it is a `.orb__spine` rewrite and
   nothing else.
3. **One damage chip, reserved, showing the worst source, filled to its fraction
   of 21** (from 03, with 02's and 04's fill). This is complaint 2 — and it is
   also how commander damage comes back at three opponents, where the shipped
   layout currently drops it. The per-source detail belongs in the R2 sheet
   where there is room to name who.
4. **One cell, one gutter, one radius** (from 01). Complaint 3 is seven paddings
   and four gutters; this is the only item on the list that is purely a diff to
   `handheld.css`, and `assert.js`'s `padKinds` is how you know it landed.
5. **Lands, tapped lands, and noncreature permanents** (finding 3, and 06's
   battlefield row). This one is not a layout change at all: `logic/threat.ts`
   has to count them and `types.ts` has to send them before any seat can draw
   them, and until that lands no direction in this round can answer the question
   it was reviewed on. The tapped half is the cheap part — the board already
   reads each permanent's tapped flag to draw the card rotated, so it is a sum
   over a field that exists. Three cells and a meter, once the data is there.
6. **The lethal gauge** (from 04), later and on its own schedule. It is the best
   single idea in the round and the least like anything the client draws today,
   which is exactly why it should not ride in on the same change as the layout.
7. **The fixed card** (from 05, at 06's 332px), last, because it is the change
   that deletes the three `:has()` branches and wants the rest to have settled
   first.

**Do not** take 01 as the layout — its one-row seat at a duel is genuinely the
best thing here, but a 150px opponents' row at three seats is a bigger regression
than everything above put together. **Do not** take 02 or 04 if a pod is the case
you care about: both spend the portrait, and four unrecognisable seats is the
defect the desktop round ranked fourth. **Do not** ship 03 without checking
`noart` — a commander in a hidden zone takes its entire ground away, and that
state is one `s` press from here; 06 is the file to look at for what that state
should do instead. And **do not** ship any of them believing they show a board:
they show zones, and finding 3 is the reason.

---

## Notes on fidelity

- **The pod is real in shape, tuned in value.** The three opponents, their
  commanders, their boards and their zone counts come from
  [`../handheld/_table.js`](../handheld/_table.js), so this round and the pad
  round are looking at the same game. Two numbers are deliberately not that
  file's: seat 3 has taken **16** commander damage rather than 12, which is the
  only way to put a seat past the warn threshold (15) and see what a direction
  does about it, and seat 2 has taken **3** rather than 0 so the plate has a
  middling value as well as a zero and a near-lethal one. Marco's `revealed: 2`
  is likewise chosen so that both branches of finding 1 are on screen at once.
- **Nothing the shipped seat draws is dropped, and that turned out to be the
  wrong bar.** Every channel the shipped seat draws is present in all six at
  every density — seat name, commander name, portrait, life, per-source
  commander damage against 21, creatures, untapped, power, fliers, open mana,
  and every zone count including exile, which appears only when it is non-empty,
  so a seat can show four marks or five and every direction survives that
  reflow. Two directions compress commander damage to its worst source and say
  so; none of them drops it. **What the bar missed is what the shipped seat does
  not draw either** — lands, and artifacts and enchantments — which is finding 3
  and is the whole of 06. `_seat.js` now carries `lands` for the three seats,
  read off `../handheld/`'s battlefields; `threat.other` was always there.
- **The three densities are the round.** A seat that only works at one opponent
  is not a seat; `1`, `2` and `3` are how you check, and the table above is
  measured at all three.
- **The five seat states are the other half.** `s` cycles them. `out` is the one
  that broke every direction first: each of them originally grew an extra
  row for the loss reason and each overflowed its own budget doing it. They all
  take the same resolution now — the commander's name is the least useful thing
  on a seat that has already lost, so the loss reason takes its slot and the
  seat does not change size at the exact moment somebody is looking at it.
- **The board under the seats is ghosted at the real proportions**, for the same
  reason the desktop round drew a ghost mat beside every panel: a claim about
  footprint should be visible rather than asserted. Every pixel a seat takes is
  a pixel off the viewer's own board. **06 ghosts a different arrangement of
  that board** — see its section above — at the same width, the same foot height
  and the same play column, so the seat measurements stay comparable even though
  the picture under them is not the shipped one.
- **`noart` is the state that separates 03 from 06**, and it is worth pressing
  `s` four times for. On 03 a commander in a hidden zone takes the seat's entire
  identity with it, because the art *is* the seat. On 06 it takes a picture and
  leaves the name, because the window is one cell among several rather than the
  ground everything sits on.
- **Each file inlines its own copy of the masters**, because each must open
  standalone from `file://` — `fetch()` is blocked there, which is the whole
  reason for the convention. Run `python inline.py` after editing a master;
  `python inline.py --check` fails if any file is stale and is CI-shaped.
- **Colour accessibility is out of scope** —
  [ADR 0006](../../docs/adr/0006-no-colour-accessibility-requirement.md). There
  is no greyscale key in these files and no "survives greyscale" row in the
  table above. The shape-plus-colour marks are here for the reason in finding 2,
  which is that the labels are gone.

## The gates

`assert.js` travels inside every file, so `SEAT_ASSERT()` works in a console with
no server. `m` runs it and outlines the elements that failed, in place.

Four gates are [`../handheld/assert.js`](../handheld/assert.js)'s, unchanged,
because this is a component inside that round's screen and a floor that stops at
the component boundary is not a floor:

```
16px    nothing carrying information is smaller
44px    nothing focusable or tappable is smaller
0       native title tooltips: a controller cannot reach one
0       elements escaping their own seat, and 0 regions collapsed to nothing
```

Two are this round's own, and they are the ones the complaint reduces to:

```
boxKinds   distinct geometries among the seat's cells (height | padding | radius)
padKinds   distinct paddings among every padded box in the seat, containers included
gapKinds   distinct gutters among every flex and grid box in the seat
```

A number here is not a verdict — one is not automatically better than two, and a
direction may spend a second geometry deliberately to separate two families of
fact. What the gate forbids is spending one by accident, which is how a strip
acquires seven.

Five bugs in this round were found by the gates and by nothing else, and each is
noted where it happened: a priority tick that resolved against the deck instead
of its seat and drew 6px outside it, invisibly, under `overflow: hidden`;
`* { box-sizing }` not matching pseudo-elements, which put 05's returned-board
ghost 2px over the row's own budget; a zone mark at 40px whose two-digit count
was 35px of content in 32px of box; a font-size check that divided by the
bezel's scale and so reported a 16px floor as 17.9, passing type that fails on
the device; and a clip check asked of boxes with `overflow: visible`, where
`scrollWidth` also counts the hover label every mark carries — it reported four
"clipped" counts on a seat 1017px wide with nothing wrong.

## For whoever builds the real seat

- **Test ids must survive.** `player-<pid>`, `pile-<pid>-<zone>` and above all
  `life-<pid>`, which must hold the **bare number and nothing else** —
  `lifeOf()` in [e2e/helpers.ts](../../frontend/e2e/helpers.ts) does
  `Number(textContent)` on it. Every mockup here puts them on the node a click
  would land on. `spine-<pid>` exists on the shipped seat and nothing currently
  asserts it; 01 and 05 keep a threat row it could sit on, 03, 04 and 06 do not,
  so it needs a decision rather than a rename.
- **Nothing in the seat may carry `data-action-id`.** It is a gesture surface;
  the action panel keeps sole ownership of the id, and `e2e/cycle3.spec.ts` and
  `e2e/action-panel.spec.ts` both assert it. 02's seat-as-one-stop is the one to
  watch — a seat that takes the player-target action must route through
  `onSelect`, not grow an id. 06 keeps that gesture on the card *and* keeps the
  zone marks as stops on top of it, so it is the one that has to get the nesting
  right: the card cannot be a `<button>`, because the marks inside it are.
- **The opponents' row must stay capped.** `board.css:55-66` calls
  `fit-content(58%)` load-bearing because every pixel of height in that row is a
  pixel off the viewer's board, and an uncapped row was the handheld layout's
  single largest defect. Whatever `--pod-seat-h` becomes, it stays a cap, and
  `handheld.css:1030-1040` already records what happens when you lower it
  instead of changing the content.
- **Draw all three densities before believing a single-seat shot.** Two
  opponents is the case that has already been missed once.
- **`threatOf()` and `types.ts` gate two of 06's cells.** The lands count and
  the noncreature-permanent count are not layout work — nothing can draw them
  until the engine counts them and the payload carries them. `threat.other` is
  the cheaper half: it already exists in this round's fixture because it already
  exists in the game state, and only the renderer drops it.
