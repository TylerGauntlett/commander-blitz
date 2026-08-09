# Player orb exploration

Five mockups of the player panel — commander, life, mana, and the state of every
zone — for picking a direction before
[`PlayerOrb.tsx`](../../frontend/src/components/game/PlayerOrb.tsx) and
[`CommandZone.tsx`](../../frontend/src/components/game/CommandZone.tsx) are
touched. Open any `.html` directly — no build, no server, no network.

```
01-astrolabe.html        one instrument      · commander damage becomes a gauge
02-docket.html           status is a header  · the 190px column goes to the board
03-plinth.html           the commander IS the panel · the life seal
04-ink-and-signal.html   a ledger            · one track, two scales
05-totem.html            one component, every seat · the zones become a pole
_orb.js                  the shared state; kept readable, inlined per file
```

These five are about the **orb**. [`../`](../README.md) is the board
exploration, [`../cards/`](../cards/README.md) the card face,
[`../menu/`](../menu/README.md) the main menu and [`../flow/`](../flow/README.md)
the setup flow; all five rounds share `../art/` and its one `manifest.json`.

Unlike the menu and flow rounds these are **not interactive**. The orb is one
component in one moment, so each file draws the viewer's panel in a single state
and the comparison is about form.

Each file also renders a ghosted mat beside the panel, at the real board's card
proportions, so a direction's claim about **footprint** is visible rather than
asserted. Footprint was explicitly in scope this round: a direction may argue for
a different column, or for not being a column at all, as long as it says what
that costs.

---

## The one state, and why it is that one

Every conditional channel is on screen at once. A mockup that hid the
commander-damage row or the exile pile would not be evidence that the direction
preserves them.

> Your turn **and** you hold priority (two different things, drawn two ways) ·
> commander in the command zone, castable, `+2` tax owed · two of three opponents
> have connected with their commanders, one of them at 16 — past the warn
> threshold · exile is not empty · a hovered spell would tap two of your lands ·
> the library has been drawn down to 41 while the graveyard has grown to 12, so
> the piles have something comparative to say.

The states each file cannot show — active, targetable, eliminated, and the other
five commander states — are named in the note under every mockup, with how that
direction expresses them.

---

## What is wrong with the orb today

Not much, and that is worth saying first: every channel is present and every
channel is legible. The problems are of form, and there are four.

**1. It is six visual languages in one column.** A brass disc, a portrait
banner, outlined chips, dot pips, leaf stacks and a text label are stacked in
190px with nothing relating them. Three of those blocks — life, commander damage,
zone counts — are answering one question ("how is this player doing?") in three
unrelated shapes, so you read them one at a time.

**2. Commander damage is the only stat in the game with a known maximum, and it
is drawn as a number.** `16` and `7` in two chips
([PlayerOrb.tsx:243-255](../../frontend/src/components/game/PlayerOrb.tsx#L243-L255)).
Sixteen is five away from lethal and seven is fourteen away, and nothing on
screen says so — you are expected to hold 21 in your head and subtract. Every
direction here answers this, and it is the round's clearest single finding.

**3. The component is maintained twice.** `.orb--compact` is a second design
wearing the first one's class names: its own dial size, plinth, name clamp and
label scale, with override blocks at
[board.css:427-457](../../frontend/src/styles/board.css#L427-L457) and again
inside the dial and piles blocks. Two implementations of one component drift.

**4. Four seats look identical.** In a pod, four orbs are four grey rectangles
distinguished by a name in 12px type. The one asset that would tell them apart
instantly — the commander's art — is already loaded and is drawn at 80px.

---

## The five, compared

Sizes are measured in the browser, not estimated. Today's column is **190px
wide**, and the orb gets roughly **341px of height** at 1600×950.

| | 01 Astrolabe | 02 Docket | 03 Plinth | 04 Ink & Signal | 05 Totem |
|---|---|---|---|---|---|
| **Measured** | 256 × 460 | full width × 104 | **190 × 318** | 150 × 434 | **96 × 356** |
| **Fits 1600×950** | **no** | yes | yes | yes | yes |
| **Board width returned** | −66 (costs) | **+190** | 0 | +40 | +94 |
| **Commander damage** | **21-notch arc** | track to 21, per source | chips | 21-seg track | chips |
| **Zones** | radial spokes | piles | piles | 9-seg ledger | **proportional pole** |
| **Tells four seats apart** | no | no | **yes (in colour)** | no | no |
| **Says two things at once** | yes | yes | **partly — see below** | **it is the design** | yes |
| **Kills `.orb--compact`** | no | partly | no | no | **yes** |
| **Port cost** | high | **highest** | low (CSS only) | **lowest** | medium |

### 01 — Astrolabe

*The component is called an orb and is currently a rectangle.* Life at the
centre; one ring around it carrying the two things that move. The top half is a
21-notch commander-damage arc with a bead per source — sixteen sits visibly near
the end of its track, so the position carries the warning without anything having
to point at it. The bottom half is the five zones as spokes
hanging inward from the ring, exact counts on chips, leaves at one per nine
cards.

**It does not fit.** 256 × 460 against 190 × ~341 — 66px too wide and 119px too
tall, and shrinking the ring to ~180px takes the zone numerals to 8px. Judge this
one on the idea, not the geometry.

### 02 — Docket

*Nothing about a player's status is tall.* Rotate the orb ninety degrees into a
104px strip across the top of the mat and the lanes run the full width beneath
it — at 1120px that is two more cards per lane before anything wraps, drawn in
the mockup as the dashed green cards. Sections divided by hairlines, in the order
you ask the questions.

Commander damage finally gets the room a column never had: one row per source
with a track that runs to 21, and the warn tier hatched as well as reddened.

**The most expensive port of the five**: `.mat`'s grid
([board.css:104](../../frontend/src/styles/board.css#L104)) becomes a header row
plus a single column, `.mat--compact` follows, and `--pod-lanes-h`'s solver reads
a lane width this changes.

**One thing it nearly broke.** The first draft made MANA its own section, two
hairlines from the commander's cost. `CommandZone.tsx` calls that adjacency "the
reason the commander moved into this panel at all", so the mana row is now inside
the identity block, one line under the cost — which is where it is today.

### 03 — Plinth

*The commander is not in the panel; the commander IS the panel.* The art becomes
the ground — blurred, scrimmed, tinted to the deck's colour identity — with a
crisp window on top. Four seats stop looking alike, which is the only thing here
that helps in a pod and the one thing the current orb cannot do.

**The life seal** is the stealable idea: the dial stamped over the portrait's
lower right, half on the art and half off it, costing the overlap instead of a
row. That is how the panel lands at **190 × 318** — the same column, shorter,
with nothing dropped.

**Art ceiling.** The crop is 626×457; the wash renders it at 190px (0.30×) and
the window at 160px (0.26×). Nothing is upscaled — the blur is for the type's
sake. That is only true because this panel is narrow. Do not port the wash to
anything wider than ~780px without re-reading [`../README.md`](../README.md).

**The verdict is mixed** — as it was for menu 05. The tint is entirely spent on
seat identity, so it has nothing left for seat *state*. What saves it is the
portrait, which differs per seat regardless of the wash, so the identity claim
degrades rather than dies. That is the call to make about this direction.

### 04 — Ink & Signal

*The bar the other four have to clear.* A ledger: hairline rules, one type scale,
aligned columns, one filled object per question. **Hue is spent on mana and on
nothing else** — priority is a filled square, ready is an inverse tag, the warn
tier is a solid fill plus an inverted numeral. There is no hue anywhere on the
panel but the mana pips and the art, which is the whole claim.

**One track, two scales** is the idea worth taking anywhere. Commander damage and
the five zones are the same object at two resolutions — 21 segments because 21 is
lethal, and nine segments because `pileLeaves` is already one leaf per nine cards
capped at nine. The zone ledger is the shipped pile's own scale on its side, with
a label column to align against, so a library at 41 still reads long beside a
graveyard at 12 *and* the exact counts line up in a way the wrapped piles never
managed.

**It is narrower and taller**: 150 × 434. Seven labelled rows plus eyebrows beat
five piles in a wrapped flex row. On a 16:9 board that is the right way round,
but it is a trade.

### 05 — Totem

*Design for the narrow seat and give it to everybody.* Fit the whole thing in
96px — narrower than the compact column is today — and the viewer's orb and an
opponent's become the same markup at the same size, with nothing conditional but
whose turn it is. `.orb--compact` and its override blocks stop existing.

**The pole**: the five zones become stacked bands whose height is their count.
Measured in the mockup, Lib 41 is a 38px band and CMD 1 is a 14px sliver. It is
the same comparative read the bottom-aligned piles were built for, except the
comparison shares one edge instead of five — which is why it still works at 96px
when nothing else does.

**What it costs:** the smallest portrait of the five, and the long state words
("On the battlefield") wrap to two lines. The failure mode to check this against
is [mockup-fidelity.md](../../docs/mockup-fidelity.md) defect #5 — "Aesi,
Tyra…" — which is why the two-line name clamp here is load-bearing rather than
decorative.

---

## Recommendation

**Take 03 as the base and port two things into it.**

03 is the only direction that gets shorter without getting wider, ports as CSS
over surviving markup, and answers the pod problem — four seats that look like
four decks. Its life seal pays for itself in layout, and its risk is confined to
one thing (the tint) that the app can lose without losing the panel.

Port order, cheapest and highest-confidence first:

1. **The 21-notch damage gauge** (from 01, or 04's flat version of it). This is
   the round's clearest finding and it is independent of every layout question:
   commander damage has a maximum and should be drawn against it. 04's
   21-segment track is the cheap form; 01's arc is the expressive one.
2. **One track, two scales** (from 04). If the zone piles ever need to survive a
   narrower column, the nine-segment ledger is the same information in less
   width, and it aligns the counts.
3. **The seat-shaped component** (from 05), later. Killing `.orb--compact` is
   worth doing on its own schedule; the pole is how you would do it.

**Do not** take 03's wash without also taking its blur rule and its narrow
column, and do not take 02 unless the board is genuinely width-starved enough to
justify re-shaping `.mat` — that is a board decision, not an orb decision, and it
should be made on the board's evidence.

---

## Notes on fidelity

- **The panel state is real in shape, invented in value.** Aesi, Tyrant of Gyre
  Strait is a real commander with its real cost and its real art crop from
  `../art/`; the opponents are real commanders from the same folder. The counts,
  life total and damage numbers are chosen to exercise every branch, not read out
  of a game.
- **Nothing is lost.** Every channel `PlayerOrb.tsx` and `CommandZone.tsx` draw is
  present in all five: name, priority, portrait, `CMD` badge, two-line name,
  state said three ways (word + glyph + portrait luminance, none of them hue),
  mana cost, commander tax, life, loss reason, per-source commander damage with
  its warn tier and its tooltips, the mana row with floating and spent pips and
  its one split pip for an ambiguous source, and all five zone counts.
- **The library is not a button in any of the five.** It is hidden information,
  and a control that does nothing when clicked is worse than no control
  ([PlayerOrb.tsx:96-101](../../frontend/src/components/game/PlayerOrb.tsx#L96-L101)).
  The other four zones stay the only route into `ZonePeek`.
- **The mana slot keeps its line whether or not it has pips.** Mana empties
  several times a turn and a collapsing slot moves the board under the cursor
  ([PlayerOrb.tsx:270-275](../../frontend/src/components/game/PlayerOrb.tsx#L270-L275)).
- Each file inlines its own copy of the state, because each must open standalone
  from `file://` — verified: `fetch()` is blocked there, which is the whole reason
  for the convention. `_orb.js` is the readable master: edit it and re-inline.
- Verified per file at **2560×1278 and 1600×950**: no console messages, no
  network requests beyond `../art/*.jpg`, no broken images, no page scroll, and
  the two checks a viewport test misses because `overflow:hidden` on `body` hides
  both — **escape** (nothing paints outside its panel) and **collapse** (no
  region flattens). Two real bugs were caught this way and both are noted in the
  file that had them: 01's ring caption was printing underneath a damage bead,
  and 04's commander name was clipping to one line because its container was an
  inline span with nothing for the two-line clamp to clamp in — defect #5,
  reproduced by accident.

## For whoever builds the real panel

- **Test ids must survive.** `player-<pid>`, `mana-<pid>`, `pile-<pid>-<zone>`,
  `commander-<oid>`, `command-zone-<pid>`, and above all `life-<pid>`, which must
  hold the **bare number and nothing else** — `lifeOf()` in
  [e2e/helpers.ts](../../frontend/e2e/helpers.ts) does `Number(textContent)` on
  it. Every mockup here puts them on the node a click would land on.
- **Nothing in the commander subtree may carry `data-action-id`.** It is a
  gesture surface like `HandFan`; the action panel keeps sole ownership of the
  id, and `e2e/cycle3.spec.ts` and `e2e/action-panel.spec.ts` both assert it.
- **`commander_cost` is not `commander_tax`.** The mockups show `+2`, which is the
  extra generic already doubled by the engine — see the contract note in
  `api/types.ts`.
- **Whatever wins, draw four seats before believing a single-panel shot.**
  Direction 03 is the one this will have something to say about, and the README
  above says what it will say.
