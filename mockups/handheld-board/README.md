# The handheld board, at full fidelity

Three mockups of **one Steam Deck screen** — the whole 1280×800 of it, drawn
properly — with the action rail answering a different decision in each. Open any
`.html` directly. No build, no server, no network.

```
01-attackers.html   your turn 8, combat        declare attackers
02-blockers.html    Edgar's turn 9, combat     declare blockers
03-abilities.html   your turn 8, main 1        cast, activate, and aim
_board.css          the screen: deck grid, strip, seat, plinth orb, lanes, hand, rail
_board.js           the fixture, the builders, the reader, the holds, BOARD.mount()
assert.js           the gates; BOARD_ASSERT() in any console
inline.py           splices the three masters into the three files
measure.mjs         drives all three and prints the table below
shots/              PNG of each at 1280×800
```

---

## Why this round exists

Three earlier rounds each designed one component against a **ghost** of
everything else.

[`seat/`](../seat/README.md) drew an opponent's seat at 332×96 over a sketched
board of dashed rectangles. [`rail/`](../rail/README.md) drew the action rail at
243×514 over a sketched board *and* a sketched hand. [`self/`](../self/README.md)
drew the viewer's own orb at 154×518 over ghosted lanes — it is the one that got
closest, because it drew the opponents' seats for real and asked "does this orb
belong on the same table as that seat". Each ended with a direction picked.
**No two of them were ever on the same screen**, and none could check its own
central claim:

- `seat/06-muster.html` argues that an opponent's seat should say *what have they
  got on the battlefield* — three counts, `untapped/total`, with a meter. Over a
  dashed sketch, "3 lands, 2 untapped" is unfalsifiable. There was nothing there
  to be wrong about.
- `rail/01-attackers.html` argues that the rail is the decision — a row per
  creature, a rim per staged attacker. Its rows named a Vampire deck that appears
  on no board anywhere in this repo, next to eight grey rectangles. A row saying
  "Bloodghast 2/1" beside a rectangle is not the same design as a row saying
  "Bloodghast 2/1" beside Bloodghast.

This round draws all three at full fidelity — real art, the published Scryfall
mana symbols, the actual board state out of [`handheld/_handheld.js`](../handheld/) —
on the layout `06-muster.html` sketched, and holds **the whole screen** to the
floors all three earlier rounds asked of one panel at a time.

The three files differ only in what the rail is deciding. That is `rail/`'s
question asked again with the board no longer imaginary.

---

## The measured table

`node mockups/handheld-board/measure.mjs`, at 1280×800 from `file://`:

| file | rail | reader | list | share | rows | cards | min card | min font | min hit | seats | escapes | silent clips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01-attackers | 748 | 236 | 398 | 53% | 8 | 18 | 120 | 16 | 44 | agree | 0 | 0 | yes |
| 02-blockers | 748 | 236 | 363 | 49% | 7 | 18 | 120 | 16 | 44 | agree | 0 | 0 | yes |
| 03-abilities | 748 | 236 | 398 | 53% | 8 | 18 | 120 | 16 | 44 | agree | 0 | 0 | yes |

The shipped board at the same size, for the same numbers: action list **172px**,
card width **73.6px**, 444 of 635 elements below 12px with the smallest at
**2.11px**.

---

## The five things this round changes

### 1. The rail runs the full height of the screen, and that is worth 234px

`06-muster.html`'s sketch made the rail a column from the top of the screen to
the bottom rather than a panel that stops where the hand starts. That is one
grid line, and it is the biggest number in the round.

`handheld.css:1540-1554` records what the shipped rail was doing at 514px: *"four
things want it: the stack, the card you are reading, the list of things you can
do, and the commit slab"*, with the action list measured at 41px holding 197px of
content — so **the rows the turn is actually spent in got 172 of 514**. `rail/`
answered that by exiling the stack and the card reader to holds, which got the
list to 78–86% of the column.

Running the rail to the foot makes it **748px**, which buys back exactly one of
the two exiles. This round spends it on **the card reader**, for one reason: the
reader changes with every row the cursor touches, and the stack is empty for most
of a turn.

That is a real trade and `rail/` argued the other side of it: *"a hold you have to
remember to press is not a replacement for a panel that was always visible."*
The honest next thing to try is **one region that is the stack when the stack is
not empty and the reader when it is** — they are never both urgent, and neither
earns a permanent column on its own. It is not built here because it would be a
fourth variable in a round that already has three.

The list still comes out at 363–398px, which is **more than double** the shipped
172, while also showing a panel the shipped rail only had at 152px.

### 2. The strip and the board are the same numbers, and the gate proves it

`seatsAgree` is the round's own gate. Each opponent's five counts are derived
three ways — by `musterOf()`, which the seat is drawn from; by `assert.js`,
walking the fixture again with different code; and by reading the text out of the
rendered `.perm` cells — and the file fails if any two disagree.

`seat/` could not run this check at any price. **A summary that cannot be checked
against the thing it summarises is the failure mode this whole family of
components has**, and it is why "how many lands has that seat got" was
unanswerable from the shipped strip at any density: the number was never in the
payload, so nothing could contradict it.

It pays off immediately in `02`. Edgar attacks with everything, so his creature
cell reads **0/4 untapped** and every pip in his detail cell is hollow — *they
have nothing left* — and that is exactly the fact that tells you it is safe to
block. No sentence anywhere says it.

### 3. The rail and the mat are one object in two places

Toggling a row in `01` puts `--staged` amber on that creature's face on the mat
and a ▲ on its corner. `02` does the same in `--targetable` blue. `03` does it in
`--playable` green when you aim at something of your own. One token, two
surfaces, no legend.

Two findings fell out of building it, and both are the sort that only appear when
the two halves are on one screen:

- **Every corner mark had to move to the left edge.** Later cards sit on top in a
  fanned lane, so what a lane hides is each card's right-hand fifth — which is
  where `handheld/` puts the staged ▲ and the ×2 stack count. Five creatures
  staged and not one visible mark on the mat, on the file whose entire argument
  is that the row and the card are the same object. The rim survived because a
  box-shadow goes all the way round; the marks did not.
- **A rim is a fact about a permanent, not about a picture.** The first version
  selected faces by name across the document, so the amber also landed on the
  enlarged card in the reader hold — a surface whose only job is to show what a
  card *is*.

### 4. The player orb is `self/03-plinth.html`, and this screen is where it gets checked

[`self/`](../self/README.md) drew five directions for exactly this panel, in
exactly this palette, and **plinth** is the one carried here: the commander's art
as the panel's ground, the portrait as the button that casts them, and life as a
64px dial stamped over the portrait's corner.

Its argument is the pod. `seat/06-muster.html` uses a commander's art twice on
every opponent's seat — a crisp window and a veiled ground — so three opponents
stop being three identical rectangles. The viewer is the fourth seat at that
table and the shipped client does not give them the treatment, so **a pod today
is three decks and a control panel**. Plinth is what happens when the fourth seat
gets it too.

`self/` had to argue that from a panel with ghosted lanes beside it. **Here the
three decks are drawn six pixels above**, so three of its claims stop being
arguments and become things you can look at:

| `self/` reasoned | this screen shows |
|---|---|
| a fourth seat with a portrait joins the pod | four portraits in one column of screen |
| 21px zone chips, because 72px read as bloated *beside an opponent's 20px* | both sets on screen at once |
| the crop costs 40% of the painting's width | it costs 16% here — see below |

**The crop mostly refunds itself, and nobody fixed it.** Plinth's one stated price
is that a 148×250 portrait is 0.59:1 against a 1.37:1 `art_crop`, so `cover`
scales to height and shows about 40% of the painting — *"on a commander whose art
is a wide landscape it will not be, and this is the direction that will find
out."* This layout gives the hand a 270px foot instead of the shipped 148, so the
viewer's mat is 372px rather than 534 and this column is 358 rather than 518. The
160px comes off the one elastic member, which is the portrait: **148×128 is
1.16:1, so `cover` now keeps about 84% of the width.** What it pays instead is
area — 18,944px² against plinth's 37,000, still six times a seat's window.

**One deviation, and it is the drop rule.** Plinth draws the player's name across
the top of the portrait for pod symmetry with a muster seat's head row. That is
worth 21px of a 250px picture; it is not worth 21px of a 128px one, and the case
for it is weaker here than it was there — the information strip six pixels above
names you twice, and unlike the three seats beside it there is never any doubt
whose panel this is. Dropping it returns **107px of visible art instead of 86**
for no information, and the price strip moves back to the top of the frame.

**A note on what the portrait is doing in these three files.** `cmd: 0` puts Aesi
on the battlefield, so in all three the button reads `In play`, carries no price
and is `aria-disabled` — *never* `disabled`, because a disabled control dispatches
no mouse events and the reader is driven by hover. That is the state in which
plinth's portrait is **not** a control, and it is the state a board round is most
often in. `self/`'s `cmdzone` and `unpaid` states are the ones that make it a
button; this round has no `s` walk, so both are unexercised and the code path is
kept rather than trimmed so that stays visible.

**Two facts, drawn two ways.** Whose turn it is and who holds priority are
different things: `--active` is the astral inset ring, priority is the tick on the
top edge. `02` is the file that proves they are separate — it is Edgar's turn and
yours is the decision, so the orb wears the tick and not the ring. The shipped
board runs the two together into one highlighted name.

### 5. The three files are one game, one turn apart

`03` is your main phase. `01` is your combat, four minutes later. `02` is Edgar's
turn after that — and **the three creatures that cannot block in `02` are the
three you sent in `01`**, drawn tapped on the mat, absent from the list, because
attacking taps them and none of them has vigilance.

Neither earlier round could show that. It is the whole reason declare-attackers is
a hard decision, and it is invisible unless the same board survives from one
mockup to the next. The delta between files is six lines at the top of `02`, kept
there rather than in the master so it is auditable.

Two creatures that *are* in `02`'s list: Acidic Slime and Yavimaya Elder are still
summoning-sick, and summoning sickness stops a creature attacking and tapping,
not blocking. The engine gets this right; a panel that dropped them would not.

---

## Findings that hold whichever direction wins

**1. The hand overflowed its own row and nothing said so.** Six cards at 176px is
1056px in the 947 the foot has. The fan arithmetic that keeps the board's lanes
inside their rows was written for `.lane__cards` and the hand is not one, so the
hand ran 79px past the foot and sat on top of the commit panel's first mark. The
deck is `overflow: hidden`, so the page reported no overflow at all — the only
symptom was **a button that had quietly stopped being clickable**. This is the
board round's lesson arriving a third time: where a visual property reduces to a
number, assert the number. It is `fanOverflow` now.

**2. Affordability stops being the filter on a developed board.** `rail/03` opens
with two rows dimmed because the board cannot pay for them. This board has twelve
untapped sources against a hand whose most expensive card is five, so *everything*
is castable and the `.act--broke` tone is carried and unused. That is worth more
than the demonstration would have been: on a turn-8 Commander board the whole of
the decision is **targeting**, which is the case the chip cloud is worst at and
the case the shipped panel spends its row width on the other thing.

**3. Forty-two legal targets is not a stress test, it is this table.** Beast
Within reads "destroy target permanent", and the four boards hold 21 + 7 + 8 + 6
permanents. The engine offers one `cast` action per target; a chip grid of 42
44px pills, two to a row, is over a thousand pixels of pills in a 243px column.
`rail/03` argued the drill-down against six invented targets and had to *assert*
that it scaled. Here the number is just what the board is, and it is printed on
the hint bar.

**4. The collapse is a real reduction and should be said out loud.** Those 42
objects become 25 rows because seven Forests are one row with a ×7 on it — the
same collapse `CardStack` makes on the mat. If the seven Forests differed in a way
that mattered (an Aura on one, damage marked, one of them tapped), the collapse
would be hiding it. `CardStack` has that exposure on the board today.

**5. The type line loses to the P/T when a box is too small, and that is
backwards.** The reader's first draft put "Legendary Creature — Serpent · 5/5" on
one 227px line. It ellipsised, and the half it dropped was the number. The P/T is
on the art window now, where a card keeps it.

**6. `--mat-side` is a clamp, and its floor is not its value.**
`clamp(132px, 12vw, 190px)` resolves to **154px** at 1280 wide, which is the box
`self/` measured its five directions inside. The first draft here took 132 — the
clamp's floor — which is a round quietly giving itself an easier problem than the
one whose conclusion it is carrying.

**7. Sizing a bezel to `1280 × scale` and letting the unscaled deck overflow it
puts the deck 48px right of centre.** A grid item that overflows its own declared
width is not centred by what it overflows. `seat/_seat.css`'s fixed full-viewport
bezel has no such failure mode; this folder now uses it.

---

## What is deliberately not here

- **Three cards have no art.** Gyre Strait Leviathan, Terramorphic Expanse and
  Plains render the `face__noart` plate, because `../art/` has never been asked
  for them and this folder does not touch the network. `python mockups/fetch_art.py`
  with those three names added would fill them. It is also a real state:
  `logic/cardArt.ts` returns `undefined` when the map has not been fetched and
  `null` when a printing genuinely has no art, and the two look identical on
  screen — which is its own small finding.
- **Who you attack is answered halfway.** The engine offers one action per
  (creature, defender) pair — six attackers and three opponents is eighteen
  `add_attacker` actions for this board. `01` makes the defender one shared choice
  drawn on the mat as a blue rim round the seat, which is right for the common
  case and is not the general answer. **The general answer is `03`'s drill-down**:
  tap the defender row, the list becomes the three seats, tap one, come back.
- **This board never produces a tier-3 or tier-4 block.** Edgar attacks with four
  small creatures, so every legal block in `02` is "kills it, survives" or
  "survives". The grammar carries all four tones and `rail/02` shows the other two
  on its invented board. A real board that produced a chump block is one where you
  are about to lose, and it is worth a fixture of its own.
- **The stack is empty in all three.** See point 1 above for the region it would
  have wanted.
- **The portrait's two live states are not reachable.** `self/`'s `cmdzone` and
  `unpaid` are what make it a control; this round has no `s` walk, so all three
  files sit in `In play`. See point 4.
- **The mana groups never show a spend.** `VIEWER.spend` is in the fixture and
  `manaCells` draws it, but `f.spending` is never set — that is `self/`'s
  `spending` state, reached by the same `s` walk this round does not have. It
  would be a good thing to wire to the reader: pointing at Beast Within in the
  hand and watching three mana groups show what would be left.

---

## Reading them

Every control is reachable by pointer and by ring, and every mark's name is its
`aria-label` — surfaced on hover *and* on the cursor, never as a `title`, because
a native tooltip opens on hover and on nothing else and is therefore unreachable
on a controller. The gate fails a file that grows one.

| key | |
|---|---|
| `o` | the card hold — the card you are pointing at, at 330px |
| `k` | the stack hold |
| `b` / `Esc` | close a hold |
| `r` | re-render |
| `m` | run the gate and draw every failure on the element that failed |

`m` is the one worth knowing. It prints the table's row for the file you are
looking at onto the bezel caption and outlines anything under 16px type, under
44px of target, under 96px of card, escaping the screen, scrolling without a
reserved gutter, clipping text with no ellipsis to say so, or describing a board
that is not there.
