# The action rail — handheld

**One column, one job.** Three files for the right rail on a 1280×800 Steam Deck
screen, for picking a direction before
[`ActionPanel.tsx`](../../frontend/src/components/game/ActionPanel.tsx) and the
rail half of [`handheld.css`](../../frontend/src/styles/handheld.css) are
touched. Open any `.html` directly — no build, no server, no network.

```
01-attackers.html   declare attackers · the shape the other two inherit
02-blockers.html    declare blockers  · one shared pool, colour as the channel
03-abilities.html   main phase        · one drill-down instead of a chip cloud
_rail.css           the bezel, the ghosted board, the palette, AND the shared
                    grammar of the rail; inlined per file
_rail.js            the shell, the two holds, the review keys; inlined per file
assert.js           the gates, as numbers; inlined per file
inline.py           splices the masters into each file; --check for CI
```

Every file boots to turn 8 of the reference board and takes four keys:

```
o       the card hold — read the focused card, full screen (Y on a pad)
k       the stack hold — what is waiting to resolve (X on a pad)
r       reset
m       run the gate and draw its failures on the elements that failed
```

**These are not five directions and a recommendation.** They are one direction
drawn three times, on the three decisions the rail actually has to answer. The
round the panel needs is not "which of these looks best" — it is "does one panel
shape survive attacking, blocking and casting", and the only way to find out is
to build all three out of the same parts and see what breaks.

So `_rail.css` carries the grammar, unlike [`../seat/_seat.css`](../seat/_seat.css),
which deliberately withheld a shared plate style because uniformity was the thing
that round was arguing about. Here uniformity is the **thesis**, and a file that
restyled the row would be disproving the claim it exists to make. A file may add
only the shape of its own list. 01 adds no CSS at all.

These are about **one column of the board**.
[`../seat/`](../seat/README.md) is an opponent's seat on the same screen,
[`../handheld/`](../handheld/README.md) the Deck board and the pad that drives
it, [`../`](../README.md) the board, [`../cards/`](../cards/README.md) the card
face, [`../menu/`](../menu/README.md) the main menu, [`../flow/`](../flow/README.md)
the lobby.

---

## The complaint, and what it measures to

> *attack with button is randomly placed (not centered and touching the items
> below it). all attack and no attack buttons are massive and do not match the
> styling of anywhere else in page. when testing on computer, the mouse
> automatically produces scroll bars in the stack and actions panels causing a
> bleeding effect. numbers are not vertically/horizontally centered in the middle
> of the squares within the action panel and the select player buttons are
> entirely too big for the space.*

Five defects. Four of them are one cause, and it is not carelessness: the 16px
type floor and the 44px hit floor — both correct, both hard-won by
[`../handheld/`](../handheld/README.md) — landing on controls whose boxes were
sized for a 304px desktop rail at 10.5px type. Every one is a specific rule.

**D1 · The slab floats free of the buttons under it.**
[`handheld.css:384-416`](../../frontend/src/styles/handheld.css#L384-L416) makes
`.foot__slab` `justify-content: flex-end` and `.commit-dock`
`align-items: flex-end`. The slab shrink-wraps its label; the alternatives row
shrink-wraps its own. Two stacked controls, two different widths, neither
anchored to the other.

**D2 · "All attack" and "No attacks" outweigh the button they serve.**
[`handheld.css:1802-1817`](../../frontend/src/styles/handheld.css#L1802-L1817)
gives `.commit-alt button` 44×44 and
[`:1989`](../../frontend/src/styles/handheld.css#L1989) gives it 16px, on top of
the `padding: 8px 10px` and `border-radius: 999px` it inherits from
[`ui.css:665`](../../frontend/src/styles/ui.css#L665). Both floors applied to a
desktop pill produce a capsule larger than the slab it is subordinate to.

**D3 · Hovering spawns scrollbars that re-wrap the panels.** `.stackpanel` and
`.acts__list` both scroll
([`handheld.css:1571-1599`](../../frontend/src/styles/handheld.css#L1571-L1599)),
and the styled `::-webkit-scrollbar` at
[`theme.css:403`](../../frontend/src/theme.css#L403) is a **classic** bar, not an
overlay — it takes 8px out of the content box the instant it appears, so every
row re-flows under the pointer.

**D4 · The numerals sit low and off-centre in their squares.** `.act__key` is a
fixed 19×19 box from [`ui.css:291-303`](../../frontend/src/styles/ui.css#L291-L303),
drawn for 10.5px type; the floor raises the type to 16px
([`handheld.css:1687`](../../frontend/src/styles/handheld.css#L1687)) and leaves
the box alone. A 16px Segoe line box is about 21px. It cannot centre inside 19.
Same shape of bug as `.pile__stack`, already documented one file over.

**D5 · One 44px capsule per opponent, inside a 44px row.** `.aim`
([`ui.css:367-375`](../../frontend/src/styles/ui.css#L367-L375)) takes 16px
([`:1692`](../../frontend/src/styles/handheld.css#L1692)) and 44×44
([`:1800`](../../frontend/src/styles/handheld.css#L1800)) but keeps its pill
padding, so each defender is a full-size button nested in a row that is itself
only as tall as one. Two opponents already wrap. **The cost scales with pod
size**, which is exactly backwards.

### And the sixth, which is the one the round is actually about

None of those five is why the panel is hard to use. This is:

`handheld.css:1540-1554` records the shipped column in its own words — *"514px on
a 1280×800 screen, and four things want it: the stack, the card you are reading,
the list of things you can do, and the commit slab"* — and the measurement that
prompted it, **the action list at 41px holding 197px of content**. The caps that
followed brought it to 172px:

| | px |
|---|---|
| preview pane | 152 |
| stack pane | 84 |
| gaps | 16 |
| action panel | 262 |
| └ the pane's own chrome | ~22 |
| └ prompt + hint line | ~68 |
| └ **the rows** | **172** |

**A third of the column is the thing the turn is spent in**, and the other two
thirds are four bordered wells competing with each other and with the board
beside them. Every direction here is judged on that fraction, and `assert.js`
fails a file that does not clear half.

---

## What all three do about it

**Reading is a hold, not a column.** Checking a card you do not know and checking
the stack are *occasional*. Neither earns 236px of permanent rail, and this app
already decided what an occasional full-screen answer looks like:
[`.oppboard`](../../frontend/src/styles/handheld.css#L1314-L1338) is fixed at
`inset: 8px`, held on R2, and its own comment says why — it *"owns the screen
while it is up, which is why it can afford a generous card size and why it is
outside the zoom solver entirely."* `.logover` is the same family. Press `o` and
`k`: the card gets 340×476 where the rail could only ever give it 152px of
height, and the stack gets the whole screen instead of an 84px scroller.

One difference from the log, and it is load-bearing: **the stack hold opens
itself.** The stack was moved into this rail because it is something you need
*mid-decision*, unlike the log — so a hold you have to remember to press is not a
replacement for a panel that was always visible. It presents whenever you take
priority with anything on it, and the hint bar carries `X Stack 2` while it is
not empty, which costs the rail nothing.

**The prompt goes.** "Declare attackers" and "Click a creature to send it" are
two lines saying what the phase ribbon is already lit for and what a list of your
untapped creatures already implies. That is this codebase's own drop rule —
*a label whose subject is still on screen* — the one that took the lane headings
and the pile words.

**The list has no pane.** The rows are already bordered rectangles; a well around
the only content in the column is a frame around a frame, and `.acts` spends 22px
of height and 20px of width on it. What keeps a surface is the commit panel,
which is then the one recessed thing in the rail and reads as the floor the
decision lands on rather than as a fourth box.

**The commit comes back off the foot, as one row of three.** There is no second
row for the slab to be misaligned against (D1 cannot recur by construction), and
the alternatives are sized by the row rather than by their own padding, so the
hit floor cannot inflate them past the thing they serve (D2).

**"All" and "None" become marks.** The house rule for a control that will not fit
its word is the compact piles' —
[*drop the word, keep the mark, put the name one input away*](../../frontend/src/styles/handheld.css#L819-L944).
Both are 44px squares carrying `aria-label`, surfaced on `:hover` and
`[data-cursor]`, so the accessible name and the visible one cannot drift. Filled
and empty of **one** shape, because that is the relationship: every legal choice,
or none of them.

**The commit label never changes width.** `Attack with 0` → `Attack with 1` →
`Attack with 10` re-centres itself every time you stage a creature — the button
moving while you aim at it. It says `Attack`. The count is already on screen as
the number of filled rows, and the disabled state is the only thing that needs to
say "you have picked nothing", which is what a disabled state is for.

---

## The three, measured

`m` in any file, or `RAIL_ASSERT()` in the console. Every number below is read
off the running page at 1280×800; nothing here is asserted by hand.

| | rail | list | **share** | rows | surfaces | scrollers | overflowing at rest |
|---|---|---|---|---|---|---|---|
| **shipped** | 514 | 172 | **33%** | 3 | 4 | 2 | — |
| 01 attackers | 514 | 440 | **86%** | 8 | 1 | 1 | 0 |
| 02 blockers | 514 | 403 | **78%** | 8 | 1 | 1 | 1 |
| 03 abilities · list | 514 | 440 | **86%** | 8 | 1 | 1 | 0 |
| 03 abilities · aiming | 514 | 440 | **86%** | — | 1 | 1 | 0 |

The shell reproduces the rail at **exactly 514px**, which is not a coincidence
and took a correction to get: the phase ribbon was drawn as a flat 40px strip and
the rail came out at 549, handing the design 35px the device does not have.
Thirteen step labels at 16px do not fit 1264px on one line — `handheld.css`
raises `.track__step-label` back to 16px rather than dropping it, so the real
ribbon **wraps**, and it is two rows. Every figure above is therefore directly
comparable with the shipped breakdown.

`surfaces` counts boxed containers — something with a border and a background of
its own that holds other elements. Four in the shipped rail, one here. A number
is not a verdict; a direction may spend a second surface on purpose to separate
the choices from the commit. What the gate forbids is spending one by accident.

### 02 is the only one that overflows, and the collapse is what pays for it

At rest, four attackers with their candidate blockers is **738px of content in a
403px list**. That is the round's one real cost and it should be stated rather
than hidden. Press `▣`:

| | content px | overflowing |
|---|---|---|
| at rest | 738 | yes |
| after `▣` | **403** | no |

Every assignment removes a group's worth of rows, so the list shrinks fastest
exactly when you are furthest through the decision. It fits before you finish.

---

## What each file argues

### 01 — Attackers *(the shape)*

A list of your creatures and a button that sends them. **This file adds no CSS.**
Everything it needs is in `_rail.css`, because `_rail.css` was designed here
first — 02 and 03 are the test of whether it generalises, and this is what it
generalises from. If a rule ever appears in `01-attackers.html`, the round has
lost its claim.

### 02 — Blockers *(one shared pool)*

Every attacker is a heading; under it, every creature that can still block it,
tinted by what that block would achieve.

**The inversion.** `ActionPanel` groups by *blocker* and lists the attackers each
could stop, on the stated argument that *"the question a defender is answering is
'what do I do with this creature'"*. That is right on a desktop rail with room
for both sides. At 243px only one of the two can be the spine, and the attackers
are the half you do not control — the fixed set, against which your creatures are
the resource.

**The pool is shared, which is the part the chip grid never modelled.** A
creature blocks one attacker; assigning it removes it from the other three
headings and folds this one shut. So the list is never showing an option that is
not really available, and you cannot stage the same blocker twice — a rule the
current surface leaves the player to remember. One piece of state in the
implementation (`blocker → attacker`), everything drawn from it; keeping it
per-group is how a shared pool stops being shared.

**Colour is the channel and the words are gone.**
[`logic/autoBlock.ts`](../../frontend/src/logic/autoBlock.ts) already ranks every
legal block into four tiers and `.verdict--1…4` already colours them — then
[`TIER_LABEL`](../../frontend/src/components/game/ActionPanel.tsx#L72-L77) spells
each out in four words on every row, so the colour was decoration standing next
to the meaning rather than carrying it. Green kills and survives, blue survives,
amber trades, red chumps.

**Colour is not the only channel, and it must not be.** Candidates are ordered
best-first, so position says the same thing; and the word comes back from
`aria-label` on hover and on the ring — the same mechanism `▣` uses. Look at the
Gatekeeper's group: every candidate red is the panel saying *there is no good
answer here* without a sentence, which is the case the four-word verdicts were
worst at, because reading "chumps, chumps, chumps" is slower than seeing it.

**"Nobody" is gone, and so is every other placeholder.** An unblocked attacker
carries a red number; a blocked one does not. There is no state left that needs
naming, and `.actgroup__none`'s *"Nothing this can block"* goes with it — a
heading with no rows under it has already said that, at no cost. The number is
hidden with `visibility`, not `display`, so a heading does not change width when
it leaves.

**The forecast is the number the step is about.** `.acts__stakes` says "12 power
incoming", which is half the question — what a player wants is where that leaves
them. `40 → 31`, updating as you assign, **red only when lethal**: taking damage
is Tuesday, and spending `--danger` on every block step spends it on nothing.

**`▣` sorts by tier across the whole board**, not heading by heading. Walking
them in order spends the Nighthawk chumping the Serra Angel before the Vampire's
group is ever considered — the greedy answer to the wrong question. It also stops
at tier 3, which is `autoBlock`'s own judgement that a chump is never worth
making on its own, inherited rather than second-guessed.

### 03 — Abilities *(one drill-down)*

**The chip cloud is D5 wearing a different hat.** The engine offers a targeted
spell once per legal target, so a Bolt with six things to point at is six `cast`
actions; `groupPlayActions` already collapses them to one row with a chip each,
because six rows drawing the same card read as six copies of it. Then the floors
land, and six 44px chips wrap to three rows inside a row that is itself 44px
tall. The cost scales with how interesting the spell is.

**A drill-down does not care how many there are.** Tapping a targeted spell turns
the list into the list of things it can hit. One state, one row height, two
targets or twenty.

**The target list says what would happen.** Same four-tier idea as 02, applied to
an effect: a filled green dot means the spell kills it, a hollow grey one means
it survives, red is a player taking the damage. So *which of these six does 3
damage actually deal with* is answered by looking rather than by arithmetic —
`autoBlock`'s argument about combat, applied to the other place a player was
being asked to do sums under time pressure. The mockup computes it from toughness
rather than hard-coding it, because the whole claim is that the client can.

**And the invariant survives, which the `<select>` version of this idea does
not.** `ActionPanel`'s header states it: every legal action is a button carrying
`data-action-id`, exactly once in the document. An `<option>` cannot carry one,
so a select needs the same deliberate carve-out `choose_x` has. Here every target
is still a real button with its own id — on a second screen rather than in a
second row — so the contract holds unchanged and `e2e/action-panel.spec.ts` does
not have to learn anything.

---

## Three findings, none of which the round went looking for

**1 · D4 exists twice.** `.glyph` in the hint bar is an 18px box at 11px type
([`board.css:1680-1693`](../../frontend/src/styles/board.css#L1680-L1693)) and the
floor raises the type to 16 without touching the box — the identical defect to
`.act__key`, one surface over, found because this round draws a hint bar. Both
need the box sized for the **line**, not the glyph. Whatever fixes one should fix
the other in the same commit.

**2 · The enlarged card has D3.**
[`cards.css:493-500`](../../frontend/src/styles/cards.css#L493-L500) gives
`.face--big .face__rules` `overflow-y: auto` — the part of the card that gives
when there is more rules text than the frame shows. It is the same classic
scrollbar, so a card whose rules run one line past the fold **re-wraps every line
of its own text** the moment the bar appears, on the one surface whose entire job
is being readable. Found by pointing this round's gutter gate at the card hold.
`scrollbar-gutter: stable` fixes it in one declaration, same as the action list.

**3 · A cost and a name do not both fit a 243px row.** At the 16px floor a
three-pip cost is 64px of about 223 usable, and with the numeral chip and the
gutters that leaves 115px for a name that wants 145. Measured on 03: three of six
rows clip, including `Vampire Nighthawk` and both ability labels. `.act__type`'s
drop already accepted truncation here on the argument that the preview draws the
whole card — but that argument was made when the preview was always on screen,
and this round moves it behind a hold. **Whoever builds 03 has to decide where
the cost goes**, and the options are a second line, dropping generic pips to a
number, or dropping the cost entirely on the grounds that an unaffordable row is
already marked. The round does not settle it.

A fourth, internal to the gate and worth recording because it nearly passed
silently: the escape check reported **18 escapes on a file with nothing wrong**,
because rows scrolled below the fold of `.list` are outside the visible box —
which is the entire point of a scroll container. Inside a scroller only the
*cross* axis is a failure (`.list` scrolls vertically, so a row wider than its box
is unreachable by any gesture); outside one, both axes count. Same lesson the
board round drew about `overflow: hidden`, arriving through the opposite door.

---

## Recommendation

**Take 01 as the base and land it in four commits, in this order.** Nothing here
needs a component rewrite — `ActionPanel` already renders one control per legal
action and already portals its dock, so this is where the dock portals *to* plus
targeted CSS.

1. **The three floor fixes, which are independent of any layout decision.**
   `scrollbar-gutter: stable` on `.acts__list`, `.stackpanel` and
   `.face--big .face__rules`; `.act__key` and `.glyph` sized for a 16px line;
   `.commit-alt button` given its own tier instead of the desktop pill. This is
   D2, D3 and D4 in one reviewable diff and it improves the shipped panel whether
   or not the rest is taken.
2. **The commit into the rail.** Delete the `.foot__slab` portal host and its
   `handheld.css` block; `.commit-dock` becomes one row of three under the list.
   D1 goes. Check `useZoomFit`'s `HANDHELD_FOOT_EXTRA` on the way — it reserves
   56px for a slab that would no longer be in the foot.
3. **The two holds.** `.oppboard` is the pattern and most of the CSS; the stack's
   auto-open on priority is the only new behaviour. Then the preview and stack
   panes leave the rail and the list takes the column.
4. **02 and 03**, as separate pieces of work with their own arguments. 02 is a
   new list shape plus one map; 03 is one piece of drill-down state.

**Do not take 02's colour-only verdicts without the hover label.** The word is
the third channel and the round only works because it is one input away — a
version that drops `TIER_LABEL` and puts nothing in its place is a different and
worse design.

---

## Notes on fidelity

- Same board state as every other round in this folder: turn 8, one opponent,
  three lanes, five in hand. The board and the fan are **ghosts** — drawn dim,
  drawn to scale, not part of the design. They are there so the height the rail
  is spending is visible rather than asserted.
- The deck is 1280×800 and **scaled**, never reflowed, so a mockup reviewed on a
  2560px monitor is still reviewed at Deck density. Font sizes are read unscaled
  and boxes are read through the scale; getting that backwards reports a 16px
  floor as 17.9 and passes type that fails on the device.
- Mana is a letter on a disc, standing in for the published Scryfall SVGs the
  client vendors to `frontend/public/symbols/`. The letters are `aria-hidden` and
  the cost is carried as real text by `.cost`'s `aria-label`, which is what
  `ManaSymbol` + `SymbolText` do — the honest line the type gate draws, not a way
  round it.
- The card in the hold is drawn with gradients rather than a bitmap. The round is
  about the rail; the crop only has to be a picture. `../art/` has the real ones.
- Each file inlines its own copy of the masters, because each must open
  standalone from `file://`. Edit `_rail.css` / `_rail.js` / `assert.js` and run
  `python inline.py`; `--check` exits 1 if any file is stale.
- Verified per file with `m` at 1280×800: PASS on all three, both of 03's states,
  and both holds. No console errors, no external network requests, no `title`
  attributes.
