# Keep or mulligan, as a game screen

Five interactive mockups of **the first decision of every game** — the whole
1280×800 of it — turning "Keep this hand?" from a centred rectangle with two
grey buttons into something a Steam Deck asks you. Open any `.html` directly.
No build, no server, no network.

```
01-the-deal.html              there is no dialog       · seven whole cards, a still arch
02-the-read.html              the game already knows   · a read, and two unequal tiers
03-the-table.html             four people, one question· the answer rides your seat
04-the-cut.html               the library is an object · a switch, not two buttons
05-the-second-question.html   a mulligan is two asks   · one room answers both
_mull.css                     the stage, both card faces, the raise, the floors
_mull.js                      the hand, the pod, the pad, `STAGE`, `MULL_ASSERT`
shoot.mjs                     the PNGs below, and the gates, in every state
measure.mjs                   how wide the cards are, and what gets cut
probe.mjs                     how wide they would have to be — the round's real answer
shots/                        PNG of each at 1280×800, plus every alternate state
```

All five do the same things, so the comparison is about design and not about
capability:

- draw **the same seven cards**, the same commander and the same pod, from
  `_mull.js` — a difference on screen is a difference in design
- carry **the real oracle text**, pulled from `data/catalog/cards.sqlite`
- open on a **"press any button"** state, because Chrome hides gamepads until
  one is pressed and pretending otherwise is the first thing a console screen
  can lie about
- take **a real pad**, a stick, the arrow keys or the mouse
- **refuse** at the ends of a row, visibly and with rumble
- let you **read any card in full**, by four different mechanisms — see below
- **commit** visibly and do nothing else — `../menu/README.md`'s rule for every
  interactive mockup in this folder
- clear the **16px type floor and the 44px target floor** by being written at
  them, checked in the page by `MULL_ASSERT()`

---

## The position

The same one in all five, and it is real rather than a sketch: an opening seven
for **Aesi, Tyrant of Gyre Strait**, with three lands (one a tapland), Sol Ring,
a two-drop that ramps and a five-drop that pays off. Every cost, type line,
power and rules text is the catalogue's. Three of the four seats have already
answered — Vessa kept seven, Ord went to six, Nim is still deciding — because
`_opening_sequence` asks the seats in order and that is what the table actually
looks like when the question reaches you.

The hand is **keepable, deliberately**. A position whose answer is obvious is
the one that shows whether the design is carrying the decision or decorating it.

---

## What is wrong with this screen today

Six things, in the order they cost the most.

**1. It is an operating-system dialog, and it is the first frame of the game.**
`PromptDialog` puts a 14px-radius panel in the centre of the viewport with an
18px title and a row of `.opt` buttons
([ui.css:954-1033](../../frontend/src/styles/ui.css#L954-L1033)). Every
non-priority decision goes through it, which is the right call for six of them
and wrong for the one a player meets before they have been taught anything.

**2. The hand is behind the question that is about the hand.** The backdrop is
the admission. It is not a flat dim, it is a **gradient** that fades out toward
the bottom of the screen ([ui.css:941-951](../../frontend/src/styles/ui.css#L941-L951)),
with a comment saying exactly why: *"a flat dim over the whole viewport hid the
one thing the player has to look at"*. And behind it the hand is drawn at
`--card-w-base: clamp(68px, 9.2vh, 96px)`
([theme.css:289](../../frontend/src/theme.css#L289)) — **73.6px** at 800px of
panel height.

**3. You cannot read any of the cards.** This is the one that decides the round,
and it is not really a mulligan problem — it is what a 73.6px card is. `.face`'s
rules text is `clamp(8.5px, card-w × 0.053, 12.5px)`
([cards.css:161](../../frontend/src/styles/cards.css#L161)), so at 73.6px it is
**8.5px**, which the handheld build then floors to 16 and drops as not fitting.
"Sakura-Tribe Elder" is not information unless you already know it blocks once
and fetches a land. See the whole section below.

**4. Neither option is drawn as anything.** `rowsFor` renders an option as a
card when it refers to an object; the mulligan decision's two options are
`DecisionOption(label="Mulligan", value=True)` and its opposite
([game.py:1156-1159](../../src/automtg/engine/game.py#L1156-L1159)) — no `ref`,
no target. So the one decision whose entire subject is a set of cards renders as
two bare labels, in identical rectangles, at the same weight. The engine even
attaches the hand to the decision (`context={"hand": [...]}`) and nothing reads
it.

**5. Every number that decides the answer is already on the wire.** How many
lands. Whether both of your commander's colours are represented. What you can
cast, and when. How many mulligans you have taken — which the engine puts *in
the decision's own prompt string*, `f"Mulligan? ({player.mulligans_taken} taken)"`
([game.py:1155](../../src/automtg/engine/game.py#L1155)) — and which the client
throws away, printing the constant `"Keep this hand?"` from
[labels.ts:103](../../frontend/src/logic/labels.ts#L103) instead.

**6. It is two questions, answered in two unrelated rooms.** A London mulligan
is keep-or-mulligan *and then* put N on the bottom
([game.py:1173-1187](../../src/automtg/engine/game.py#L1173-L1187)). Both go
through `PromptDialog` and they do not look like the same moment: the first has
no refs so it renders two labels in a narrow box, the second has refs so the
same component renders `.opt--card` faces in a wide one. No transition, no
heading that connects them, the same generic title bar.

---

## How wide a readable card is

The question this round was rebuilt around: **can the fanned hand just use the
full-size card the desktop preview already draws?**

Two answers, and the first is no for a reason that has nothing to do with taste.

**The desktop preview card is written under the Deck's floor.** `.face--big` is
the one face in the client allowed absolute type sizes, and they are
`--fs-nm: 13.5px`, `--fs-tp: 11px`, `--fs-tx: 12px`
([cards.css:459-470](../../frontend/src/styles/cards.css#L459-L470)). Twelve-pixel
rules text is 4px under the 16px floor, so that card cannot be lifted onto a
handheld as it stands — and the client already says so twice.
[handheld.css:490-495](../../frontend/src/styles/handheld.css#L490-L495)
re-floors the whole `--fs-*` scale at 16, and `CardPreview` swaps the node
entirely on a handheld rather than scaling it, for a stated reason: at 243px of
rail *"a card frame at that width is 116px across — SMALLER than the board card
it is supposed to be helping you read"*.

**And re-cut at the floor, seven of them do not fit.** `probe.mjs` binary-searches
a real card in a real browser for the narrowest width at which it can print its
own name, cost, type line and rules text at 16px:

```
card                      oracle  TEXT    CARD
Sol Ring                  16ch    120px   161px
Forest                    15ch    172px   172px
Sakura-Tribe Elder        124ch   218px   247px
Island                    15ch    170px   170px
Tatyova, Benthic Druid    79ch    296px   296px
Thornwood Falls           85ch    182px   249px
Explosive Vegetation      103ch   215px   231px

  widest TEXT:                296px      (everything readable, art may be nothing)
  widest CARD:                296px      (...and a third of the height still picture)
  seven at CARD, flush:       2072px
  the panel:                  1280px
```

**2072px of card against a 1280px panel.** Seven cards tiled edge to edge across
1280 are 182px each, which is under what four of these seven need. So a screen
showing seven readable cards at once is not available at any layout, at any
overlap, on this hardware. The client found the same wall from the other side:
[handheld.css:1455-1476](../../frontend/src/styles/handheld.css#L1455-L1476)
records a prompt that had to show a whole hand at 264px coming to **668px of
overflow**, and settling at 180px where the rules box "degrades honestly".

Two things worth noticing in that table. **For four of the seven the binding
constraint is the name row, not the rules box** — Tatyova needs 296px because
"Tatyova, Benthic Druid" plus `{3}{G}{U}` needs 296px, and its rules text would
have fitted at 240. And **Sol Ring's whole card fits in 161px**, so this is not
a uniform cost: it is one or two cards per hand that set the number.

---

## So: one card at a time, four ways

Every direction can now show any card in full. They do it differently, and that
is the comparison.

| | mechanism | costs | in the shots |
|---|---|---|---|
| **01** | the card you are on IS a full card, in the arch | no button, but half of every other card | `01-the-deal-*.png` |
| **02** | raised over the panel on **Y** | a button, and the read stays on screen | `02-the-read-raised.png` |
| **03** | raised over the table on **Y** | a button; the pod stays legible behind it | `03-the-table-raised.png` |
| **04** | raised, and it had to grow a selection first | a button *and* both shoulders | `04-the-cut-raised.png` |
| **05** | raised, and it keeps its `Bottom` tag | a button, on the screen with the fullest grammar | `05-the-second-question-raised.png` |

**The raise is not a modal**, and that is not pedantry. `.prompt-backdrop` dims
to `rgb(6 5 16 / 0.82)` and blurs, because a dialog is asking a question and the
screen behind it is not part of the question. `.raise` scrims to **0.55 with no
blur**, because here the screen behind it *is* the question — the other six
cards, the pod, the switch. You are meant to keep reading the room with a card
up.

**It is on Y in all four**, and the button is chosen by the one file that cannot
have X: 05's second question already needs a confirm alongside a toggle and a
re-mulligan. Four directions raising on X plus one on Y is worse than five that
agree.

**04 is where this bit hardest.** It was the only direction with no reader of
any kind *and* the heaviest overlap — `measure.mjs` says its fan covers 102px of
every 172px card — so it had to grow per-card selection before it could have a
raise at all. And its d-pad is the switch, so the hand walks on **L1/R1**. That
is the cost of spending left and right on a control, and it is the direction's
own idea that put it there.

---

## 01, in three passes

The one direction that does not raise anything, because it is the one with room
to keep the whole card in the row. It took three passes to get there and both
corrections are the interesting part.

**First pass** — seven 176px faces and a one-line reader under them. It showed
you seven cards and told you nothing about what any of them did.

**Second pass** — the selected card grew to 296 and the other six closed up
around it. Correct in a still, wrong in the hand: the row has to be re-centred
whenever the selection moves, so walking the hand slid all seven cards sideways
six times. **The one thing holding still was the card you were trying to read,
and everything you were reading it against moved underneath it.**

**Third pass** — all seven are 296×414. Every position is written once at mount
and never recomputed; moving the selection touches `z-index`, one attribute and
one custom property, and no geometry at all. What pays for it is 144px of pitch,
so every card that is not on top shows half of itself.

Two details fell out of that:

- **Only the card you are on prints its rules.** Seven open rules boxes at this
  pitch is six sliced columns of type competing with the one sentence that
  matters. The box is closed on the other six and the illustration absorbs the
  space — `.ffull__art` is the card's only flexing member — so the card is the
  same 296×414 either way.
- **The stack falls away from the selection in both directions**, `z-index:
  100 - |i - on|`. A one-directional fan with the selected card lifted to the
  top buries its right-hand neighbour completely: covered on the left by the
  296px card in front of it and on the right by the next one along, what
  survives is a four-pixel stripe.

---

## The measurements

`node mockups/mulligan/measure.mjs`.

| file | card | names cut | neighbour covers |
|---|---|---|---|
| 01 the deal | 296px | 0 of 7 | 152px |
| 02 the read | 178px | 3 of 7 | 14px **gap** |
| 03 the table | 168px | 3 of 7 | 6px |
| 04 the cut | 172px | 3 of 7 | 102px |
| 05 the second question | 164px | 3 of 7 | 12px **gap** |

The four small-card directions all cut the same three names at four different
widths, which is the same wall the probe measures from the other side: at the
16px floor a name needs up to 238px with its cost beside it, and none of them
has it. They answer it with the raise. 01 answers it by not having a small card
at all -- it is the only row in the round where nothing is cut -- and pays 152px
of overlap for it.

---

## Findings that hold whichever direction wins

**1. A `+1` tolerance in an overflow check is the difference between "fits" and
"one ellipsis".** `text-overflow` fires the moment `scrollWidth` exceeds
`clientWidth` by anything, so `<= clientWidth + 1` approves a line that visibly
has an ellipsis on it. `probe.mjs` returned 295px for Tatyova on exactly that
margin — 292 against 291 — and the raised card in all four files read
"Legendary Creature — Merfolk Dru…". Found by looking at a screenshot of
something a measurement had already passed.

**2. `hidden` is a user-agent default and `display: flex` outranks it.** The
cold caption is retired by `el.hidden = true`, which works through
`[hidden] { display: none }` in the UA sheet — an author rule at any specificity
beats it. The caption stayed on screen through every press with `hidden` sitting
in the DOM saying otherwise, and it took a screenshot to notice because the DOM
inspector reads exactly as intended.

**3. A card face cannot have a type row smaller than its name at a 16px floor**,
because the smaller of two sizes is by definition under the floor.
`../handheld-board/_board.css:1131` sets the type row at 0.94 of the head, which
at the floor is **15.04px**. The hierarchy has to be carried by weight and
opacity instead — and the consequence is that the small face's foot costs as
much width as its head, so it prints a type *word* rather than the type line.

**4. The full card must not repeat the type line its small sibling puts in the
foot.** The small face's foot *is* its type line, because there is nowhere else;
the full card already printed the whole printed line above the rules box. Sharing
the markup gave Sol Ring a card reading "Artifact", its rules, then "Artifact"
again. `cards.css:523-526` makes the same call on `.face--big`.

**5. A fan is wider than its row.** A card rotated θ about a pivot below it
swings out by `(pivot − h/2)·sin θ` *and* widens its own box by `h/2·sin θ` on
top. 01's third pass put a 296px card's top corner 715px from its pivot, so
1.2°/step swung it 44px against a 48px margin — both end cards came to rest 4px
from the bezel, inside the stage so the gate passed and visibly jammed so the
screenshot did not.

**6. An overlap wider than the mana cost deletes the mana cost.** The cost is
the rightmost thing in the head, so a fan hiding more than about 20px of each
small card hides the cost of six of the seven.

**7. `getBoundingClientRect().width` of a rotated element is its axis-aligned
box, not its width.** `measure.mjs`'s first table reported 01's 176px card as
202 and 04's 172 as 220, and only 05 — which does not rotate — was right.

**8. `justify-self`, not `align-self`, on a grid child you want left.** A grid's
default `stretch` is on the inline axis, so `align-self: start` left every state
chip in 03 filling its whole column — "Kept 7" as a 260px pill.

---

## Driving them

| | pad | keyboard |
|---|---|---|
| move | d-pad, left stick | arrows, WASD |
| **read the card in full** | **Y** (01 needs nothing) | **I** |
| keep / confirm | A | Enter, J |
| mulligan / back | B | Backspace, K, Esc |
| 05: confirm the picks | X | U |
| 04: pick a card to read | L1 / R1 | Q / E |
| 04: throw the switch | left / right | ← → |

`MULL_ASSERT()` in any file's console runs its three gates — every text node at
or over 16px, every `[data-hit]` at 44×44, and nothing outside the stage.
`GOTO("raised")` raises a card in 02–05; `GOTO("bottom")` / `GOTO("bottom2")` in
05, `GOTO("cut")` in 04, `GOTO("tatyova")` in 01.

`node mockups/mulligan/shoot.mjs` shoots all five plus every alternate state at
1280×800 and fails on any gate. The viewport is 1306×840, not 1280×800:
`STAGE.fit` sizes the deck to `(innerWidth − 26) / 1280`, so those are the
numbers at which the scale is exactly 1 and the PNG is the panel pixel for
pixel.

---

## Where this would land

`PromptDialog` is generic on purpose and should stay generic — seven decision
kinds go through it today and this is one of the seven. The change is that
**`mulligan` joins `HANDLED_ELSEWHERE`**
([PromptDialog.tsx:36-46](../../frontend/src/components/game/PromptDialog.tsx#L36-L46)),
the way `priority`, `declare_attackers`, `declare_blockers` and `choose_x`
already have, and gets its own surface — exactly what that denylist is for, and
exactly what the comment already in it describes. `isModalDecision` then stands
the action bar down for free.

The surface reads what is already on the wire: `pending.context.hand`,
`player.mulligans_taken` and `has_kept_hand` per seat, and `oracle_text` off the
`CardView` the prompt already carries. Nothing here needs an engine change.

The full card is the one piece of real client work. It is not `variant="big"`
resized — that variant's type scale is absolute and under the floor — it is that
card's parts re-cut at 16px with the **illustration** as the flexing member
rather than the rules box. `.face--full` in `_mull.css` is the sketch of it, and
the reason it inverts `cards.css:510-521`'s choice is stated there: in a rail
the card is a fixed height and the rules give; on a mulligan screen the card is
drawn at the size its rules need and the picture gives.

05 additionally wants the bottoming prompt (`choose_objects` with
`source_name == "Mulligan"`) routed to the same surface rather than back to the
generic dialog, which is one condition, not a feature.
