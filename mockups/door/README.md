# The front door, as a game menu

Five interactive mockups of **one Steam Deck screen** — the whole 1280×800 of
it — turning the front door from a web page into a main menu made of three
selectable cards. Open any `.html` directly. No build, no server, no network.

```
01-the-hand.html      a hand you hold        · the room takes the card's colour
02-the-cut.html       a deck you cut         · the name goes up the spine
03-the-table.html     the board at rest      · the pod, before anybody sits
04-the-launcher.html  the control            · the card carries live state
05-the-lantern.html   a lit room             · the selected card lights the art
_door.css             the stage, the card plate, the row, the sheen, the floors
_door.js              the three cards, the pad, the spring, `poseOf`, `DOOR.mount()`
_art.js               the drawn ground, card frame and illustrations (01 only)
assert.js             the gates; `DOOR_ASSERT()` in any console
inline.py             splices the masters into the five
measure.mjs           the layout table below, in all three selections
drive.mjs             presses things; the second table below
shots/                PNG of each at 1280×800, in all three selections
```

All five do the same things, so the comparison is about design and not about
capability:

- open on a **"press any button"** state, because Chrome hides gamepads until
  one is pressed and pretending otherwise is the first thing a console menu can
  lie about
- move the selection with **a real pad**, a stick, the arrow keys or the mouse
- **refuse at the ends of the row**, visibly and with rumble
- **press** the selected card, which commits visibly and does nothing else
- take a **pod code**, in five different places — four on the screen, and 01
  behind a dialog that opens when you press Join

---

## What is wrong with the front door today

Four things, in the order they cost the most.

**1. Nothing on it is a game object.** The screen's one card-shaped thing is a
fan of four `.back` plates at
[HomeScreen.tsx:78-87](../../frontend/src/components/lobby/HomeScreen.tsx#L78-L87),
and it is decoration — you cannot select it, press it, or reach it with a pad.
Everything you *can* use is a web control: a button, a text input, an underlined
link. **The only thing on the screen that looks like a game is the only thing
that does nothing.** And what those four plates are drawn as is the hatch
`cards.css` uses for a card with *no printing* — a placeholder, four times.

**2. It clears the handheld type floor by override list, not by design.**
[handheld.css:1978-2116](../../frontend/src/styles/handheld.css#L1978-L2116) is a
*generated* block of 144 selectors forced to `font-size: 16px`, and its own
comment calls that "the honest size of the problem". **Eight of the door's own
are in it** — every piece of text on the screen except the hero wordmark:

| | authored | at the Deck |
|---|---|---|
| `.brand__sub`, `.or`, `.door__cap` | 11px | 16px |
| `.link` | 11.5px | 16px |
| `.join__go` | 13px | 16px |
| `.join__in` | 14px | 16px |
| `.brand__mark`, `.hero__line` | 15px | 16px |

Two of its controls are dragged up to the 44px target floor the same way. **The
door is written at 11–15px and repaired at the Deck** — `handheld.spec.ts`
asserts the floor on `/`, and what clears it is the override list rather than the
stylesheet the door is written in.

**3. Its geometry is keyed to a window it no longer has.** `.fan` is
`min(clamp(104px, 15vh, 148px), 27vw)`
([lobby.css:263](../../frontend/src/styles/lobby.css#L263)) and `.hero__mark` is
`min(clamp(38px, 6.2vh, 66px), 8.6vw)`, with a phone breakpoint below. On a panel
that is always 1280×800 every one of those terms resolves to one number.

**4. The most important control is the least reachable.** "Create a pod" is a
`.big` in the middle, the pod code sits beside it, and "Browse them" is an 11px
underlined link in the footer — three actions at three weights, and on a pad you
walk between them *through a text input*.

---

## The brief, and the one place it contradicts itself

Three selectable cards — **Play, Join, Decks** — drawn in the grammar of those
four placeholders, sliding apart from the selected one and stacking on the far
side, with **the middle card selected by default**.

Those last two only agree one way. A menu whose default selection is not its
default action has picked the wrong default, so **Play is the middle card** and
the list order is what gives. Decks goes left, which keeps the shipped door's own
Play-then-Join adjacency and puts the least-committing thing furthest from the
commit. Flipping the row is `CARDS.reverse()`.

---

## The row is one number

Everything on screen is derived from `s`, where the selection currently is in
card-index space, which a spring moves between 0, 1 and 2. No keyframes and no
discrete states — a card mid-flight is at a real position rather than at a tween
between two poses, which is what makes the numbers below measurable at all.

```
d = i - s
x      (i-1)*STEP + sign(d) * (PUSH*min(|d|,1) - BUNCH*max(0,|d|-1))
rot    clamp(d, -1.6, 1.6) * ARC
y      DROOP*min(|d|,1.6) - LIFT*max(0, 1-|d|)
scale  1 + RAISE*max(0, 1-|d|)
z      100 - round(|d|*10)
lean   clamp((|d| - 0.45) / 0.60)      how far the name has travelled to its edge
ink    1 - clamp((|d| - 1) / 0.60)     how much of the card is worth printing on
```

`ARC`, the push-away and the parabolic droop are
[HandFan.tsx:36-83](../../frontend/src/components/game/HandFan.tsx#L36-L83)'s,
because the app already has this mechanic on the board and it is already tuned.
**The `BUNCH` term is the brief's stacking, and it is the only new arithmetic** —
`PUSH` alone spreads the row evenly, which is a fan; subtracting `BUNCH` past one
place pulls the far card back *over* its neighbour.

The spring is stated in time rather than in stiffness, which is
[ring.ts:18-35](../../frontend/src/input/ring.ts#L18-L35)'s rule: **w 22, z 0.82**
covers 98% of the gap in 179ms — eleven frames at 60Hz — overshoots 2.8px, and is
permanently inside 2px at 294ms.

---

## What the gates measure

`measure.mjs` walks every file through all three selections and prints this.

| file | label | ink | spill | row | margin | traverse | frames | settle | over | default | card | font | hit | esc | clip | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01-the-hand | clear | 0% | 0 | 819 | 230 | 179 | 11 | 294 | 2.8 | Play | 200 | 16 | 200 | 0 | 0 | **yes** |
| 02-the-cut | clear | 0% | 0 | 819 | 230 | 179 | 11 | 294 | 2.8 | Play | 200 | 16 | 200 | 0 | 0 | **yes** |
| 03-the-table | clear | 0% | 0 | 819 | 230 | 179 | 11 | 294 | 2.8 | Play | 200 | 16 | 44 | 0 | 0 | **yes** |
| 04-the-launcher | clear | 0% | 0 | 768 | 256 | 179 | 11 | 294 | 2.8 | Play | 200 | 16 | 44 | 0 | 0 | **yes** |
| 05-the-lantern | clear | 0% | 0 | 819 | 230 | 179 | 11 | 294 | 2.8 | Play | 200 | 16 | 200 | 0 | 0 | **yes** |

`drive.mjs` presses things instead of measuring them.

| file | cold | default | move | 2 taps | wall | press | hover | code | type | join | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 01-the-hand | up→gone | Play | yes | two | holds | yes | yes | **hold** | safe | reads | **yes** |
| 02-the-cut | up→gone | Play | yes | two | holds | yes | yes | inline | safe | reads | **yes** |
| 03-the-table | up→gone | Play | yes | two | holds | yes | yes | inline | safe | reads | **yes** |
| 04-the-launcher | up→gone | Play | yes | two | holds | yes | yes | inline | safe | reads | **yes** |
| 05-the-lantern | up→gone | Play | yes | two | holds | yes | yes | inline | safe | reads | **yes** |

### The gates this round added, and what each one caught

Four are inherited unchanged — the 16px type floor, the 44px target floor, the
96px card floor and the escape check, from [`../handheld/`](../handheld/README.md)
and [`../handheld-board/`](../handheld-board/README.md). These five are new, and
**every one of them failed a file that looked entirely correct**.

**`labelClear` — the thesis gate.** The brief asks two cards to overlap, and
overlap's failure mode is a card covering the one thing that says what the card
under it *is*. Nothing else here can see it: the covered card is the right size,
in the right place, in the right font, fully on the stage, and unreadable. Caught
it at 54%, then again at 15% after the first fix.

**`inkClear` — everything else on the card.** `labelClear` guards the name and
only the name. 04 passed it with its live state line sliced down the middle by
the plate in front of it. A sentence running under a covering card does not read
as hidden, it reads as **truncated** — a cut line looks like a bug in the copy.

**`cardSpill` — text falling off its own card.** The escape check measures
against the deck and skips the row, because a tilted card's bounding box grazes
the stage edge. That left a hole one level down and two files fell into it: a
specificity collision pulled 04's selected title half off its plate, where
`overflow: hidden` ate it (the screen read "ECKS"), and 01's copy — written for a
panel and put on a 200px card — ran out of the bottom of it seven times over.

**`slideReads` — an animation needs a floor as well as a ceiling.** This is the
one worth reading twice; see below.

**`rowFits`** — the row is laid out by `poseOf` rather than declared, and its
widest state is not the one it opens on. `.deck` is `overflow: hidden`, so a row
that runs off the stage reports no page overflow at all.

---

## The animation gate rewarded the failure it existed to prevent

The screen was reported as **jerky** while every number in this folder said it was
fine. Both halves of that are worth keeping.

The gate asked one question: is a hop permanently within 2px of its target inside
180ms, the moment a held direction fires again. The spring that passed it — `w
38, z 0.62`, a 169ms settle — did this, sampled per frame:

```
0.85  0.55  0.27  0.07  -0.04  -0.08  -0.08  -0.05  -0.03  -0.01 ...
```

**It crossed the entire row in four frames and then rang for fourteen more**, 21px
each way. A cut, followed by a wobble. And 169 < 180, so it passed.

A one-sided ceiling on a duration is satisfied most cheaply by making the
animation violent. Three numbers now, from `DOOR.springProfile()`:

| | | why |
|---|---|---|
| `traverseMs` | ≥ 100 | fewer than six frames is a cut, not a move |
| `settleMs` | ≤ 320 | past a third of a second a menu is making you wait |
| `overshootPx` | ≤ 8 | a big overshoot after a fast traverse **is** the jitter |

All five now traverse in **179ms / 11 frames** and overshoot **2.8px**, which is a
card settling onto a table rather than being thrown at one.

### Four more things were snapping, and none of them was the spring

Sampling every card's label every frame across all six moves found single-frame
teleports of **20% of a card's width on 01, 03 and 05, 35% on 02, and 50% on
04** — four times per move. The cards were sliding perfectly smoothly and the
writing on them was jumping about.

Each was a property with no in-between, and each is now a fraction of `s`:

- **the name's centre-to-edge jump** — a `data-side` attribute that flipped at
  half a place. It is a `lean` ramp now, and the offset is measured, not guessed:
  `paint()` reads where each label naturally sits before it has moved anything.
- **02's spine** — `writing-mode: vertical-rl` behind a class, which is ninety
  degrees in one frame. It is a `spin` fraction composed into the same transform,
  so the name rolls onto its side as the pile closes.
- **04's title alignment** — flipping at 1.05 places, on a plate whose body was
  still fully visible. It is tied to `data-covered` now, which turns at 1.45,
  where the body has already faded.
- **the flip** — see 01 below. It was the largest of the four and the last to go.

Worst single-frame movement is now **0.0–4.5%** of a card.

### And the frame rate: `will-change` on the backdrop was the cost

05 was the only file dropping frames — a median of **33ms** against 16.7 flat
everywhere else, with a worst of 83. Removing `.wall` restored it, so the
`blur(26px)` was plainly the cost.

The obvious fixes both failed. Blurring a quarter-size layer and scaling it 4× —
a sixteenth of the pixels — changed nothing; nor did 3px instead of 26. **What
fixed it was deleting `will-change: transform`.** Promoting the filtered element
to its own compositor layer is what made it slow: left in the parent's layer the
blur is rasterised once and reused, because nothing about the wall changes while
a card slides in front of it.

That is the opposite of the usual advice and worth writing down. `will-change` is
a promise that a thing is *about to change*. On the three slots, which move every
frame, it is right and they keep it. On a static backdrop it throws away the one
optimisation that was already working.

---

## Three findings that hold whichever direction wins

### 1. The stack depth is set by the longest label

Of two cards on the same side of the selection the nearer is drawn on top, so
what is left of the further one is a strip `STEP - BUNCH` wide. **Its name has to
fit in that strip** or it cannot be read at any alignment. Arithmetic, not taste:

| | sliver | widest label | fits |
|---|---|---|---|
| 01, 03, 04, 05 (`BUNCH` 112) | 136–139px | 88–95px | yes, with 44px |
| the first pass (`BUNCH` 140) | 108px | 102px | **no** — 16px of inset did not fit in the 6 that were left |
| 02, with a spine (`BUNCH` 178) | 73px | 26px turned | yes, easily |

Which is why 02's vertical name is worth more than it looks: **a spine label is
about 26px wide whatever it says**, so the constraint stops binding.

### 2. A stacked card's name must sit on its outer edge

A centred label is half-covered in exactly the state the brief asks for. Each
name therefore travels to the edge facing *away* from the selection — the only
part guaranteed to be uncovered, and what a fanned hand does anyway.

It costs 04 the one piece of its own grammar it most wanted: a launcher tile's
title goes at its top left, and a tile stacked to the right is covered *from* the
left. **That is a cost of the stack, not of the skin.**

### 3. The stack costs a card everything except its name

One place from the selection a card is on top of everything. Two places and it is
under its own neighbour, so anything below the name has to go — `.ink` fades it
out with the card. The corollary is the useful half: **a direction whose idea
lives in the body of the card is a direction the stack argues against**, which is
most of 04's case against itself.

### And four for whoever builds it

- **A text field inside a card makes the card a bad button.** The field has to
  stop its own click reaching the card, or focusing it to type would submit it.
  In 04 it sat in the plate's centre — exactly where a pointer aims — and
  clicking `join-pod` did nothing at all. `drive.mjs` exists because nothing that
  measures a still could have seen that.
- **A hold has to give focus back.** `PAD` ignores keys aimed at an input,
  because `d` is "right" and BRAMBLE has a `d` in it. Hide a dialog while its
  field still holds focus and every key after that lands on an invisible input:
  the row stops responding and nothing on screen says why.
- **Escape is never text.** The same input guard swallowed Escape, so a player
  who opened the join dialog and changed their mind had no way out but the mouse.
- **Two taps inside a frame are two presses.** The keyboard fallback merged them,
  and a driver had been *relying* on the drop — it pressed left twice, asserted
  the row moved one place, and passed. Counting keydowns rather than latching a
  boolean fixes both that and a re-press arriving before the release is observed.

---

## The five, compared

| | 01 The Hand | 02 The Cut | 03 The Table | 04 The Launcher | 05 The Lantern |
|---|---|---|---|---|---|
| **Metaphor** | a hand you hold | a deck you cut | the board at rest | a launcher | a lit room |
| **Ground** | **drawn hall, retinted** | flat | board anatomy | flat | blurred real art |
| **Card face** | frame + illustration | printed back | name and verb | plate, live state | back over a crop |
| **Unselected pair** | tilt away, overlap | **close to a pile** | tilt, overlap | slide flat, overlap | tilt, overlap |
| **The far card reads** | on its outer edge | **up its spine** | outer edge | outer edge | outer edge |
| **Pod code** | **a dialog on press** | in the ledger | in the strip | on the plate | under the row |
| **Tune it moves** | none | `BUNCH` 112→178 | none | `ARC`→0, `RAISE`→0.05 | none |
| **Says what a pod IS** | no | no | **yes** | no | no |
| **Port cost to React** | medium | medium | medium | **low** | high |

### 01 — The Hand *(recommended, and the one taken forward)*

*The menu is a hand of cards and you are already holding it.* Three cards, the
one you are on lifted and lit, the other two tilted away and stacked.

**The room takes the selected card's colour.** This is 05's idea brought here
because it was the best thing in the round, and drawn art does it better than a
photograph can: 05 could only wash a colour *over* its crop, which is why its
tint had nothing left to say once it had said which card was selected. Here the
line itself is recoloured — the floor sigil is `stroke: var(--lit)` — so the room
is not tinted, it *is* that colour, and the wash on top is free to be doing
something else. Decks makes the hall cold and green; Play warm; Join violet.

**The art is drawn, and that is not a compromise.** Everything else in this folder
works around one constraint: `art_crop` is 626×457 and there is nothing sharper
to fetch, so any field over ~780px is a deliberate blur. A front door has no card
on it yet, so it has nothing to be a crop *of* — and putting Edgar Markov behind
"Play" says the game is about Edgar Markov. A vector ground is exact at 1280×800
and exact again at 2560, and it is the only kind of asset that can be inlined into
a file that must open from `file://`. See [`_art.js`](_art.js): a hall with beams
and a sigil cut into the floor, a printed card frame, and one illustration per
card drawing **what that card does** — a table with four seats, a door somebody
left open, a shelf of decks.

**Three things this pass removed.**

*The flip.* The selected card used to turn face-up. Reported as disorienting, and
that is the right word: the row is built on one continuous number and every other
quantity on it is a smooth function of `s`, but a card turning over is a fourth
kind of change, it is the largest, and it swaps what the card *says* halfway
through. Two of three cards changed identity on every move and the eye had to
re-find which was which. The fix is not to slow it down — a menu of three things
should not hide two of them. All three are face-up now; selection is carried by
the lift, the scale, the rim, the sheen and the room's colour, and all five of
those are continuous.

*The code field.* It filled the Join card, which made one of three cards a form —
two illustrations and a text input is a menu with a widget stuck in it, and the
widget is where your eye goes. It is a dialog that opens when you press Join,
which is also the truer flow: the code is the next question, not a thing waiting
on screen whether or not you have one.

*`Last pod BRAMBLE-4821`.* A session starts here, so resuming is not something
this screen does and a line implying it is a promise the flow does not keep.

**And the wordmark stopped appearing twice.** The first pass had it small at the
top left and again at 44px in the middle, with "Play a pod against the engine, or
against friends" under it — a landing page, telling somebody who has already
launched the game what the game is, in the largest type on the screen. The mark
appears once now, which is [`Mark.tsx`](../../frontend/src/components/lobby/Mark.tsx)'s
own stated rule; the pitch is gone, because three cards already say what can be
done here and each says it in a verb; and the menu is the biggest object on the
screen. What is left at the edges is what a console game puts there — the build,
and what the buttons do.

### 02 — The Cut

*The two cards you did not pick are still in the deck.* The pile closes to a 73px
sliver and **the far card's name is printed up its spine**, because that is what a
deck box does and a 73px sliver is a spine.

**Stacking is the affordance rather than the leftover.** In 01 the overlap is what
is left over after two cards move; here it is the point, and the spine is what
makes it affordable. Second: **expand in place** — what the selected card offers
unfolds into the ledger below, in the room the pile leaves. A modal exists to stop
you losing your place, and you cannot lose your place in a row of three.

### 03 — The Table

*The door is the board before the board.* The information strip along the top, the
pod in the middle, the three cards down where the hand goes. Pressing Play changes
the contents of a rectangle rather than the application.

**The stealable idea is the empty pod** — four seat plates, one yours and three
dashed, so the screen says what a Commander pod *is* before you have chosen
anything. No other direction tells a first-time player that four seats is a rule
rather than a setting.

**It also produced the round's sharpest structural finding.** The board gives that
strip 34px and defends the number, and the defence holds because everything in it
is text. Put a control in it and 34px stops being enough by exactly the 44px
target floor. The first pass used `min-height: 30px`, looked perfectly correct,
and the gate failed it. The strip is 56px here and the play region lost 22.
**Worth knowing before somebody puts a control in the shipped strip.**

### 04 — The Launcher

*A main menu is a launcher; make it an excellent one.* Here to be the control, the
way [`../menu/04-ink-dossier`](../menu/README.md) and
[`../flow/04-three-steps`](../flow/README.md) were. It takes the row and the
stacking and refuses everything else: no tilt, no card back, no atmosphere.

**The plate carries live state** — *Last pod BRAMBLE-4821 · 2 min ago*, *Codes look
like BRAMBLE-4821*, *6 in the catalogue · 2 yours*. On a console that matters more
than on a desktop: the machine has been asleep, and the first question on waking
it is what you were in the middle of. None of it is invented.

It loses the "feels like a game" test on purpose, and **it also loses the argument
with its own idea, twice**: the stack takes the live line off any card more than
one place out, and the field in the tile cost it the tile's own press.

### 05 — The Lantern

*The most atmospheric surface in the app.* Full-bleed art blurred 26px under three
crisp cards, and the selected card lights the room. Bound by the constraint the
folder inherits from [`../menu/README.md`](../menu/README.md): `art_crop` is
626×457, so a 1280px ground is a 2.05× upscale and is soft on purpose.

**Its verdict is the one [`../menu/05-planar-gate`](../menu/README.md) came back
with, and it is why 01 took the idea and not the direction: the tint is already
spent.** It is carrying "which card is selected", so it has nothing left for
hovered, pressed or unavailable — one channel, several jobs. Drawing the ground
instead is what gets the channel back.

---

## Recommendation

**Take 01.** It is the direction the round converged on, and it has already
absorbed the best of 05 — the lit room — without paying 05's price for it.

Three things are still worth porting into it:

1. **The spine** (from 02). A vertical name on a card more than one place out. It
   is a strictly better answer than the outer-edge travel to the same problem, and
   it removes the constraint that currently bounds `BUNCH`.
2. **The empty pod** (from 03). Four seat plates above the row. The only thing in
   the round that explains the game, and it reuses `.back--open`.
3. **The live lines** (from 04), on the card face rather than the back — *6 in the
   catalogue · 2 yours* under Decks. Three facts the client already holds. The ink
   finding says where they can go and where they cannot.

**Do not** put a text field in the middle of a card without re-running
`drive.mjs`; do not put a control in the board's 34px information strip without
growing it first; and do not put `will-change` on a static backdrop.

---

## Notes on fidelity

- **The tokens are the app's**, byte-for-byte out of
  [theme.css](../../frontend/src/theme.css) and
  [handheld.css](../../frontend/src/styles/handheld.css). The card plate is
  [lobby.css:23-57](../../frontend/src/styles/lobby.css#L23-L57) ported, the sheen
  is [handheld.css:1347-1398](../../frontend/src/styles/handheld.css#L1347-L1398),
  the logo is [Mark.tsx](../../frontend/src/components/lobby/Mark.tsx) inlined, and
  the pad layer is lifted whole from
  [`../handheld/_handheld.js`](../handheld/README.md).
- **The pad is real.** `navigator.getGamepads()` is `[SecureContext]` and
  `file://` is a potentially-trustworthy origin, so it works — but Chrome hides
  pads behind a user gesture and returns four nulls until the first press. Hence
  the cold state, which `drive.mjs` checks is up at load and gone after one key.
- **Four test ids must survive the port** and every file puts them where a click
  lands: `home` on the deck, plus `create-pod`, `join-pod` and `browse-decks`.
  `assert.js` fails a file that loses one. `pod-code` is on the field wherever
  that direction puts it; in 01 the dialog's confirm is `join-go`, because
  `join-pod` stays on the card that opens it.
- **Reduced motion takes the texture and leaves the facts** — the sheen and the
  motes stop, the selection still moves, and every gate still passes. Verified
  with Chromium in `reducedMotion: "reduce"`.
- **The loop stops when it settles.** This is a battery-powered seven-inch
  computer and the menu is the screen a Deck sits on longest. Same rule as
  [ring.ts:10-13](../../frontend/src/input/ring.ts#L10-L13).
- **No backticks inside `_art.js`'s templates.** Every asset there is a template
  literal, so a backtick anywhere inside one — including in an SVG comment
  quoting a CSS property, which is how it happened twice — ends the string and
  the file stops parsing, with a `SyntaxError` naming a word nowhere near the
  cause.
- Each file inlines its own copy of the masters, because each must open standalone
  from `file://`. `python inline.py --check` fails if any has drifted.
- Verified per file at **1280×800** from `file://`: no console errors, no external
  requests, no broken images, no `title` attributes (a pad can never open a native
  tooltip), no duplicate test ids, nothing under either floor, nothing off the
  stage and nothing off its own card.
- 05 requests only local `../art/*.jpg`; 01's art is inline and requests nothing.
