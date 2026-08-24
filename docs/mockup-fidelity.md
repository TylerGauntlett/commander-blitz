# Mockup fidelity

Where the running client and the mockups still differ, and which of those
differences are bugs. Two mockups are in scope: `mockups/05-planar-art.html` for
the board, and `mockups/flow/02-face-up.html` for the lobby.

The mockup is the design the client was themed against. It is not the
specification: several differences below are deliberate, made after the mockup
was drawn and for reasons the mockup could not have known about. **An audit that
files those as defects is worse than no audit**, so this file separates the two
and records the reason for every divergence. If you are about to "fix" something
here, check which section it is in first.

## Redoing the sweep

Run the client and the mockup side by side at **both** viewports the mockups were
verified at — 2560×1278 and 1600×950 (`mockups/README.md`, "Notes on fidelity") —
and walk the board region by region: phase ribbon, left rail, opponent mats, own
mat, card faces at each scale, hand fan, command zone, right rail, overlays.

Then repeat the pass at a four-player pod, where cards are ~51px. That is the size
that decides whether a signal is really carrying anything.

Where a visual property reduces to a number, measure it rather than looking at it.
`e2e/layout.spec.ts` explains why: `body { overflow: hidden }` means the page
reports `scrollHeight === clientHeight` while content visibly runs off the bottom,
so a naive overflow check passes through the exact failure it was written for.

---

## Deliberate divergences

Do not "correct" these. Each is a decision made after the mockup.

### ~~The deck picker stays inline; there is no modal catalogue~~ — reversed

**This entry is closed, and the mockup's design shipped after all.** It used to
read: the flat grid stays, because every deck tile carries
`data-testid="deck-${id}"` and roughly fourteen spec files click one on the way
in, so a modal puts a click and a wait in front of all of them for facets that
are only worth anything once there are more decks than fit on a screen.

The reasoning was sound and the conclusion expired. Multiplayer moved deck
selection *into the pod*, where a row of four large cards owns the whole screen —
so there is nowhere to put a catalogue except over the top of it. The full-screen
takeover is not a preference any more; it is the honest consequence of the
metaphor.

What the old entry was actually protecting was the test hooks, and those survived
unchanged: `deck-${id}` is still a catalogue tile, `opponents-${n}` still adds the
nth CPU, `start-game` still deals. `e2e/helpers.ts:startGame` was rewritten once
and eleven of the thirteen spec files needed no edit at all. See "Two specs did
need editing" below for the two that did.

### ~~The lobby's front door is not `01-front-door.html`~~ — superseded

**This entry is closed. The front door is `mockups/door/01-the-hand.html` now.**
It used to read: the lobby ports `mockups/flow/02-face-up.html`, whose home screen
is a fan of four card backs and two actions.

What replaced it is a main menu made of three selectable cards — Decks, Play,
Join — and the reason is the one `mockups/door/README.md` opens with: on the old
door, the one card-shaped object was a fan of four `.back` plates you could not
select, press or reach with a pad, so **the only thing on the screen that looked
like a game was the only thing that did nothing** — and what those plates were
drawn as is the hatch `cards.css` uses for a card with *no printing*, four times.
Everything you could actually use was a web control: a button, a text input, an
underlined link, walked between on a pad *through* the text field.

The actions did not change. Create a pod, join by code and browse the catalogue
are the same three things, and nothing on the door configures a game — deck,
opponents, AI difficulty — because those are decisions you make *with* the people
you are playing against. What changed is that all three are now the same kind of
object, at the same weight, in one row.

Ported at 1:1 against the mockup at 1280×800: `.door__title`, `.door__row` and
every card box measure identically, which is checked by driving both and
comparing `getBoundingClientRect`. The five divergences below are the whole list.

### The front door scales rather than being a scaled 1280×800 deck

The mockup fixes a 1280×800 deck and `transform: scale()`s it to whatever window
is open, which is right for a review surface and wrong for an application: at
1600×950 that is a blurry 1280 in a letterbox.

The shipped door is full-bleed and only the *furniture* scales, off one number —
`--du`, written by `HomeScreen` from `stageScale()` in
[`logic/doorRow.ts`](../frontend/src/logic/doorRow.ts). It is **exactly 1 at
1280×800**, which is what keeps the port pixel-identical on a Deck; it grows to
1.45 and shrinks to 0.72. Type does not follow it down — every size on the screen
is `max(16px, calc(N * var(--du)))` — because the 16px floor is a CI gate and a
card that shrank its copy would clear the layout by failing the thing the layout
is for.

That scaling also forced the drawing's one structural change. The floor sigil is
its own layer, sized in `--du` and hung off the row, rather than part of the
full-bleed ground: `preserveAspectRatio="slice"` scales the ground 2× at
2560×1440 while the cards only scale 1.45×, so the ring on the floor grew wider
than the row standing in it. The sky, the beams and the vignette still slice,
because stretching a gradient is what a gradient is for.

### The door keeps the app's focus ring, which the mockup has no concept of

In the mockup the selected card *is* the cursor: nothing else on the screen says
where you are. In the app, `[data-cursor]` draws a ring on whatever the pad is
on, everywhere, and `e2e/handheldAssert.ts` fails a run where it is missing. So
on the door the ring is drawn on top of the card's own five channels — the lift,
the scale, the rim, the sheen and the room's colour.

Kept rather than suppressed. A screen that quietly dropped the one indicator the
rest of the client is consistent about would be teaching a player that the ring
is unreliable, which is worse than a doubled affordance on one screen. It costs
nothing on a mouse: `html[data-input="mouse"]` hides the ring already, so the
default view is exactly the mockup's.

### The code field is behind the Join card, and `join-pod` names the card

This is the mockup's design, not a divergence from it, but it moves a test id and
that is worth stating plainly. `join-pod` is the **card that opens the hold** and
`join-go` is the **confirm inside it**; `pod-code` is on the field, wherever the
field is. A suite that drives `join-pod` is starting a join; one that drives
`join-go` is finishing one. `e2e/pod.spec.ts`'s `join()` helper and two of its
tests were updated for the extra press, and `browse-decks` — a test id the old
door never had, so `e2e/routing.spec.ts` was matching the string "Browse them" —
now exists on the Decks card.

One addition the mockup does not make: **an invite link opens the hold itself**.
`?join=CODE` and a cold `/pods/CODE` both land with the field on screen and
filled, because the link has already asked the question the hold exists to ask,
and burying a prefilled field behind a card somebody would have to know to press
is worse than the old door, not better.

### The cold state and the build stamp did not come across

The mockup opens on a "press any button" caption, because Chrome hides gamepads
behind a user gesture and `navigator.getGamepads()` returns four nulls until the
first press — the most honest first frame a *file://* console mockup can have.
The client has `input/inputMode.ts` and shows a controller legend only once a pad
or a key has spoken, which answers the same question without a caption every
mouse player would see and have to dismiss.

`Build 0.9 · offline` goes with it. The bottom-left corner is where a console
game puts the build, and what the client actually has to say there is the deck
count the old door's footer carried — real, and the same shape of line.

### The seat rail keeps a seed field the mockup does not have

`02-face-up.html`'s rail is lock-in, the ready track, the "why not" line and Deal.
The shipped one adds a seed input, host-only, between the lock and the spacer.

A reproducible game is the fastest way to re-examine something that went wrong,
and `full-game.spec.ts`, `playtest.spec.ts` and several others are built on it
(`getByPlaceholder("random")`). Host-only because a seed is a property of the
game, not of a seat.

### No difficulty ladder, and no persona per CPU seat

Carried over from the mockup, which is explicit about it: four named personas with
a capability row apiece is configuration for behaviour the engine does not have.
What a CPU seat can honestly differ in today is its deck and its agent, so that is
what its plate offers.

### The catalogue has no `engine: "preview"` state

The mockup's catalogue carries decks that cannot be dealt, badged `Preview`, with
their cards inert and out of the tab order. There is no analogue here: every deck
the server lists is playable, because the server lists exactly the decks it can
build a game from. An imported deck maps onto the existing `simplified` count,
which is what the mockup's `partial` badge meant.

`guild` and `short` are dropped too. A guild name is derivable from
`color_identity` in the client if it is ever wanted, and neither is worth a data
field.

### Two specs did need editing

The claim was that rewriting `startGame` alone would cover it. Two of the thirteen
spec files enter through `page.goto("/")` rather than the helper, so both needed a
one-block change:

- `deck-import.spec.ts` — the import row moved from the front door into the
  catalogue's footer, so its `beforeEach` opens the catalogue first. Same
  component, same `data-testid`s; only the box around it changed.
- `playtest.spec.ts` — two inline setup flows, one of which now shoots the door
  *and* the lobby rather than a single "menu".

`layout.spec.ts` also calls `goto("/")`, but only to read a CSS custom property
off `document.documentElement`, so it was unaffected.

### The card is a full-bleed illustration, and card type is no longer a colour

Supersedes the earlier "cards are art-first everywhere" note, which described the
arrangement this replaced. `mockups/05-planar-art.html` is no longer the reference
for the card face at all: **`mockups/cards/index.html` direction D, "Art Bleed",
is.** The illustration fills the frame and the text sits on graded scrims at the
top and bottom — head (glyph, name, then the cost on a row of its own), foot (type
line, rules where there is room, then keywords/counters/P-T).

The consequential half of this is what came *out*. Card type used to be encoded as
the colour of the card stock: an eight-step `--stock` luminance ladder plus a
matching `--type-ring` hairline, and ~200 lines of `tests/palette.test.ts`. All of
it is gone.

The reasoning, because this looks like a regression if you only read the old
tests: the ladder existed because a type line renders at 5.6px on a pod board
(docs/playtest-feedback-01.md item 4) and something had to say "creature" from
across the table. A full-bleed illustration says it **better and per card rather
than per category**. Twelve Forests are one recognisable picture; under the ladder
they were twelve copies of "one of the tan ones", which is the same scanning
problem the ladder was built to solve, one level up. Verified at pod size before
the ladder was removed, not after.

What still carries card type at that size: `.face__glyph` and `.face__type`.
Colour *identity* is a different fact and it keeps the frame
— the border and the gradient the art sits on, which on the ~4% of cards with no
printing is the whole card. A land's frame narrows to the colour it taps for, and
its produced-mana symbols go large and centre-frame.

What replaced the removed tests, so the surface is not left unguarded:

- `tests/palette.test.ts` — now asserts the art *is* full bleed (the inverse of
  its old "the art window must never cover the whole face" suite), that both
  scrims exist as gradients whose opaque ends clear a darkness floor, that the
  text carries a shadow as a second defence, and that no `.face--type-*` colour
  rule has crept back in.
- `e2e/art.spec.ts` — `the art fills the frame` replaces `the art never covers the
  type ring`; the same measurement, the opposite assertion.
- `e2e/legibility.spec.ts` — a resolved-scrim-contrast check and a frame-width
  check replace the `--type-ring` ladder walk.

Everything else about D was taken as drawn, including the parts that are easy to
skip:

- **Real mana symbols.** Scryfall's published SVGs, vendored to
  `frontend/public/symbols/` by `mockups/cards/fetch_symbols.py` and drawn by
  `ManaSymbol` everywhere mana notation appears. See `docs/frontend.md`.
- **Type sizes clamped at both ends.** The mockup names this file's predecessor
  for getting it wrong — "a floor alone is what the client does, and it is why
  the preview card looks like a zoomed board card rather than a designed one".
  `.face` now carries the mockup's `--fs-*` scale; `.face--big` restates it in
  pixels because its `--card-w` is a fiction.
- **A 1.4% frame, not 3.2%.** The old border was thick enough to read as a fourth
  band on a card meant to be an illustration. The 2px floor stays and is what
  `e2e/legibility.spec.ts` actually measures.
- **The commander is a crown inside the name**, not a `CMD` badge in a corner. At
  pod size the badge rendered at under 3px, which is not a word.
- **Supertypes come off at board size** (`shortType`): "Legendary Creature — Hu…"
  spent the whole line on the least useful word on it. The rail keeps the full
  line.
- **No hatched plate.** A card with no printing is its colour-identity gradient
  with a quiet `NO ART`, so it reads as a grey card rather than a damaged one.
- **Keywords are a chip**, not a loose run of type over an illustration.
- **A land that taps for no colour gets a neutral mark** — Terramorphic Expanse
  was the one land on the board with no centre symbol at all.

Two size-driven rules are scoped to `.mat--compact`, which is the client's
equivalent of the mockup's 60px column:

- The name clamps to **one** line. At a three-opponent pod cards are ~51px, the
  name is held at its floor, and a wrapped second line left "Indulgent
  Aristocrat" with 4px of illustration between the two scrims.
- The mana cost is **dropped entirely**. This is the mockup's strongest argument:
  a permanent on an opponent's board has already been paid for, so its cost is
  the one line on the card that cannot change a decision you are about to make —
  and at 51px it is competing for a row against the name and the type. Your own
  battlefield and your hand keep theirs, and hovering restores it either way.

Not taken: the mockup's 60px column also reduces the type line to the bare
subtype and drops it entirely when it repeats the name. With the type-colour
ladder gone, the type line and the glyph are what say what kind of card this is —
so that one stays open rather than being quietly traded away.

### No rules text on board or hand cards

### No rules text on board or hand cards

The mockup does the same, so this is not a divergence from it — but it *is* a
divergence from `docs/frontend.md`'s earlier "cards are text-only" position, and
it is worth stating plainly: at hand size a rules box renders at 6–8px, which is
not text. The rules live on the rail card, which is now big enough to hold them.

### A life dial and zone piles, not a number and chips — **half reversed**

The mockup shows life as a plain numeral with a row of mana dots, and the zones as
text chips (`Lib 84`, `Hand 4`, `GY 6`). The client uses a brass dial and stacked
piles. Predates this sweep; `e2e/acceptance.spec.ts` asserts both.

**On a handheld both halves went the mockup's way, and the reasoning that
survives is about size rather than about taste.**

- The dial is still a dial, but it is a **64px conic ring** instead of a 52px
  brass disc: at that size there is area to spare, and a ring to `--fill` says
  "34 of the 40 you started with" without adding a character. Desktop keeps the
  disc, which is a seal and deliberately not a meter.
- The piles are **chips**. The leaf stack was already reduced to its top leaf
  here, because the leaves are height a 154px column does not have — so what
  was left was five identical card-back boxes told apart by the hue of a 15px
  icon, which is one channel and it is the one `e2e/greyscale.spec.ts` takes
  away. `mockups/handheld-board/` puts the zone's own colour on the *ground*
  with one dark ink over it, and draws which of them you can press as relief: a
  lit top edge on the four that open a peek, a recessed and desaturated face on
  the library, which is hidden information and never a control.

**Two of the mockup's numbers did not survive contact.** It splits five chips
3 + 2 inside a 148px `.orb`; this column is 136px of content at 1280 and 126 at
1200, and three 44px targets with two gaps is 138. So they are two to a row.
`expectHandheldFloors` is the gate that found it, on the first run, and is why
the split is stated in `handheld.css` rather than left to look right.

### Commander damage is two arrows on an opponent's own life bar

Superseded: the orb's `.orb__cmd` plate and the seat's hatched `.tick`s and
crown chip. All three are gone.

The client used to draw commander damage twice and answer neither question a
player actually has. The viewer's orb carried a chip per opposing seat with a
meter under it — the loudest object in a 154px column — which said *how close is
each of them to killing me*. An opponent's seat carried `worstSource(seat)`,
which is the worst damage **that seat** has taken **from anybody**: in a pod
that is usually a number about two other players, and `mockups/handheld-board/`
records it as the direction's one open hole.

There are exactly two facts, they are about the same pair of people, and they
run in opposite directions. So each opponent's 40-life gauge carries two small
arrows, each parked at its own fraction of 21:

| | edge | direction | colour | what it is |
|---|---|---|---|---|
| `.cmdarrow--dealt` | top | down | `--playable` | what **your** commander has done to them |
| `.cmdarrow--taken` | bottom | up | `--attacking` | what **their** commander has done to you |

Distance travelled is progress toward lethal. Four channels and only one is
hue — edge, direction, colour, distance — so the pair survives greyscale and so
does the difference between the two. At 15 the arrow grows and takes a light
halo rather than getting redder, because `--taken` is red already and hue has
nothing left to say.

The numbers are on the gauge's `data-hint` and `aria-label` and nowhere else: a
22px row will not hold two more numerals at the 16px floor. `--dealt` is
deliberately not gold — the life fill under it is.

Zero draws nothing, unlike every other cell on the seat. The reflow argument
that keeps those at zero does not apply to an absolutely positioned mark, and
two arrows parked on the left edge at the start of every game are two marks
saying nothing.

### The commit dock is a bar of three, not a slab over two pills

`ui.css`'s dock was a full-width `.commit` slab with a `.commit-alt` row of two
outlined 12px pills under it. That spends a whole second row on the two answers
nobody presses and reads as one button with a caption.

`mockups/handheld-board/` draws the relationship the three controls actually
have — every legal choice, the decision, none of them — as **a filled and an
empty of one shape flanking the slab**, on one row, inside a `--pane-well`. All
three clear the 44px floor in the height the slab alone was taking, and the
well is what makes "this does not scroll with the list" visible rather than
merely true.

Three things came off the button with it:

- **The count.** `Attack with 0` → `Attack with 10` is a label that changes
  width, so the button re-centres under the thumb every time a creature is
  staged — which is exactly while you are aiming at it. It is `.commit-note`
  above the bar now, which is also where a block forecast wants to sit.
- **The marks' words.** The marks carry their names on `aria-label` and
  `data-hint` only. A `title` would reach the mouse and nothing else, and this
  bar is driven by a controller at least as often.
- **`.commit__key`.** The keycap chip is gone; `HintBar` already advertises the
  same binding from the foot, and Loop 8.4 is about what happens when two
  surfaces claim the same thing.

`combat-all`, `combat-skip`, `combat-confirm` and `commit` are all still the
same `data-testid`s on the same handlers. Three e2e assertions read the count
off `aria-label` rather than out of the label; `cycle3.spec.ts` reads "All
defend" the same way.

**Not taken: the mockup's hint line inside the well.** `mockups/handheld-board/`
puts `13 power · A Send` under its bar. The client has a `HintBar` spanning the
foot that renders from `NAVIGATION_HINTS`, and a second hint surface in the
rail is the exact shape of the bug Loop 8.4 found.

### Amended after playtest: the marks are drawn, and the dock never moves

Two things about this bar shipped as the mockup drew them and came back.

**`▣` and `▢` are gone.** Filled and empty of one square *is* the
relationship between "every legal choice" and "none of them", and that is an
argument you can only make in a document somebody has read. On screen they are
two squares in one box that nobody can tell apart, on a bar where one of them
ends the declaration. `components/ui/ActionIcon.tsx` draws them now — select-all
(three rows and a tick) and skip-to-end (a triangle against a bar) — following
`SeatIcon`'s pattern and its argument: **a glyph in a font is a different
picture on every machine**, and a mark that has to be *recognised* has to be
drawn. Everything else is untouched: same `data-testid`s, same handlers, same
names on `aria-label` and `data-hint`, so the three e2e assertions above and
`cycle3.spec.ts`'s "All defend" still read what they always read.

**The well was only ever the right height when it had something in it.** The
dock was always mounted and its contents were conditional, so between decisions
it collapsed to its own 18px of padding and sprang back to 66 or 90 when an
action arrived — and the bottom of the rail moved with it, every time a turn
passed. The count's row was a second mover: it existed only in combat, so
entering `declare_attackers` added 25px on top of the bar changing.
`ActionPanel` now renders the note in every mode (a non-breaking space when it
has nothing to say, `min-height: 1lh` to hold the line) and falls back to an
idle slab carrying the panel's own `.acts__dot` waiting mark — quiet, not gold,
because gold means "this is what the turn is waiting on". `.preview` above it
had already been given a fixed height for exactly this reason; `board.css`
spends four paragraphs on why. The idle slab is a `div` and not a disabled
`<button>`: there is nothing to press even in principle, it carries no
`data-action-id` and no `data-stop`, and a disabled control is a promise that it
will become pressable. `ActionPanel.stories.tsx`'s `expectStableDock` is the
gate, called from the emptiest state and the fullest one alike.

### Counted mana symbols on a plate, not a row of loose dots

Every `mockups/orb/` direction draws mana as a row of small coloured discs sitting
directly on the panel — as does `mockups/boards/`, and as the client did. Two
things were wrong with porting that faithfully, and both were in `docs/roadmap.md`
rather than in the mockups:

The dots are not mana symbols. Every other surface in the client draws Scryfall's
real ones, so the orb was the last place still using a mark nobody who plays the
game recognises. It draws them too now — which forces the second change, because a
real symbol is about twice a dot's width and a mark per mana wrapped to three rows
in a 190px column. So the panel counts (`4{G} 2{U}`) where the mockup repeats.

And the row floated. The mockups are 318px tall studies where a loose row lands
where the composition wants it; the client's orb fills its column, and
`orb__body`'s `space-between` stranded both the mana row and the commander-damage
row in the slack between the plinth and the piles — re-spacing the interior every
time either appeared or emptied. The client groups all three into `.orb__foot`, on
plates, permanently. `e2e/orb.spec.ts` measures the result, since two more plates
in that column is exactly the change that quietly breaks the 112px pod budget.

### `Auto-pass` keeps a word where the mockup uses a glyph

The mockup's tool row is bare glyphs (`⏩ ↺ ✕`). Mute, skip, undo and quit follow
it. Full control does not: it changes whether the engine stops at every priority
window, and an unlabelled icon for a mode with that consequence is a puzzle, not a
saving in space.

### An art-loading state the mockup has no concept of

A land draws its produced-mana symbols centre-frame whether or not the image map
has arrived — `.face__watermark` before, `.watermark-row` after, styled
identically because on a bleed face neither one reserves any layout. The mockup
inlines its state and never loads anything.

### The commander is a plinth in the info panel, not a card beside the hand

The mockup draws the command zone as a small card face in its own box. The client
draws a banner-cropped portrait with a name and a state strip, inside the player's
info panel, for every seat. This is the fix for defect #5 below, which is where the
reasoning lives — read that before restoring anything card-shaped here.

---

### The lobby's enlarged card keeps its 1.4 box; the preview rail's does not

`cards.css` has one `.card--big`, built for the preview rail: width-driven with
`height: 100%`, held to a fixed frame by `.rail--right .preview`. The mockup calls
this out by name and takes the other trade:

> ONE DELIBERATE DEVIATION. The app's rail card is width-driven with `height:100%`
> — it is the one card on that screen not held to 1.4. Here the aspect ratio stays,
> because a face-up seat and a face-down `.back` have to be the same rectangle: the
> moment they are not, the row stops reading as a hand and `.hand__felt` no longer
> lands under the cards' shoulders. So this takes the preview's treatment and not
> its box.

The first port dropped that block on the grounds that "the components already emit
the `.face` rules". They do — but the mockup's `.face--big` was not a copy of the
app's, it was a lobby-scoped re-derivation at a different size, and dropping it was
the bug behind two of the three defects that came back from the first hands-on pass.
`lobby.css` now carries it under `.podcard`, the class `CommanderCard` puts on every
card it renders.

The type scale comes back as ratios of `--card-w` for the same reason the mockup
gives: they *are* the rail's absolute numbers expressed as fractions of the top of
`.podhand`'s clamp (296 × .047 = 13.9 against the rail's 13.5px name), so the row
reads at the size the preview was tuned at and stays legible at the bottom of the
clamp, where an absolute scale would be half again too big.

### The dossier's card column is a fixed track, not the mockup's `auto`

The mockup writes `.dos__top { grid-template-columns: auto minmax(0, 1fr) }` and can
afford it, because its card is a fixed-width `.face`. Ours is a component, and while
it was content-sized its max-content contribution was the longest unbroken run of
oracle text — which squeezed the prose column to about twenty pixels and put a
horizontal scrollbar on the panel. The track is now `var(--card-w)`.

The card is also larger than the mockup's: `clamp(150px, 22vh, 214px)` against the
mockup's root `clamp(128px, 18vh, 176px)`. Below about 202px `--fs-tx` sits on its
8.5px floor and the ratio scale stops doing anything; the 660px panel still leaves
the prose column 394px; and the loading placeholder already renders at this size, so
the panel does not resize when the card arrives.

### The seat plate carries a name field the mockup has no counterpart for

The mockup's plate renders the name as a plain span, and its front door asks for no
name at all — its guests were scripted. The shipped app briefly had a "You are"
field on the door; **removing it restores fidelity, and adding an editable name to
your own plate deliberately breaks it.** A real pod needs somebody to be able to say
who they are, and the door is the wrong place: a name is something you say to a
table, and at the door there is not one yet.

An unnamed chair is `Player {n}`, numbered by seat. Not `"You"` — that is only true
for one reader, and a host who never renamed would have the rest of the pod reading
"Waiting on You" about somebody else.

### The lobby's stylesheet renames four classes from the mockup

`.hand`, `.rail`, `.over` and `.play` all already mean something in `board.css`
or `ui.css`, and CSS is one global document. The lobby's are `.podhand`,
`.podrail`, `.dos` and `.deal`.

The lobby and the table are never on screen together, so nothing would visibly
break today — which is exactly the argument for renaming rather than relying on
it. A stylesheet that only works because two screens happen never to coexist is
one import-order change away from a very confusing bug.

`.btn` and `.tabular` are *not* redefined at all: `ui.css` and `theme.css` own
them, and `lobby.css` adds only the `--wide` and `--live` modifiers.

## Open defects

Ranked by severity. None of these block anything; they are the queue.

### 1. The `--playable` rim is easy to miss — medium

- **Mockup**: same design, so it inherits the same problem.
- **App**: `.card--playable::after` is a green rim plus glow (`frontend/src/styles/cards.css`).
- **Why it matters**: it is a hairline against a hand of full-bleed illustrations,
  several of which have green in them. "Which of these can I actually play right
  now" is the most urgent question the hand has to answer, and it is answered by
  the quietest mark on the card.
- **Partly mitigated**: castable cards are now also rows in the action panel, which
  is a second channel and a much louder one.
- **Fix direction**: give the rim more weight, or strengthen the dimming applied to
  unplayable cards so the distinction is a difference in brightness across the whole
  hand rather than a line around one card.

### 2. Combat arrows are hard to pick out — medium

- **App**: `CombatArrows.tsx` draws `--attacking` red lines over the board.
- **Why it matters**: they are thin strokes over a board of illustrations, and who
  is attacking whom is the single most important fact on screen during combat.
- **Fix direction**: more stroke weight, or a dash pattern, or an outline that
  separates the line from whatever art is under it.

### 3. The tools are visible but unreachable while a dialog is open — medium

- **App**: `.prompt-backdrop` is `position: fixed; inset: 0` at `--z-modal`
  (`frontend/src/styles/ui.css`), so it swallows clicks aimed at the tools footer
  underneath it.
- **Why it matters**: the speed control is most wanted exactly when narration is
  running into a decision, and that is precisely when it cannot be pressed. The
  panel keeps rendering the footer, which makes it look available.
- **Note**: pre-existing — the old `.bar` was equally covered. The mockup has no
  modal at all, so it does not address this. `e2e/action-panel.spec.ts` works around
  it by answering the mulligan first, with a comment pointing here.
- **Fix direction**: either lift the tools above the backdrop, or dim them while a
  modal owns the screen so they stop advertising themselves.

### 4. The preview can pin itself to a stale card — medium

- **App**: `CardPreview` renders through `AnimatePresence mode="wait"` keyed on the
  hovered oid, and `hoveredOid` is only ever cleared by an element's own
  `onMouseLeave` / motion `onHoverEnd`.
- **Symptom**: the rail arrives at a decision still showing a card from earlier in
  the turn, and in that state hovering something new does not swap it — where from
  an *empty* rail the same hover works first time. Reproduced repeatedly while
  wiring hover into the action panel: hovering a blocker group header reads the
  right creature when the rail is idle and does nothing when it is not.
- **Why it matters**: the rail is the only place rules text lives now, so a rail
  showing the wrong card is worse than one showing none. It also means "point at a
  row to read it" is unreliable exactly when you have been reading other cards.
- **Suspected cause**: `hoveredOid` outliving the element that set it — a hand card
  hovered and then cast unmounts without ever firing a leave — combined with
  `mode="wait"`, which will not mount the incoming card until the outgoing one has
  finished exiting.
- **Fix direction**: clear `hoveredOid` when the element that owns it unmounts, and
  re-check whether `mode="wait"` is still earning its place; a card-to-card swap
  does not obviously need the outgoing one to finish first.
- **Test status**: `e2e/action-panel.spec.ts` asserts the panel's hover wiring
  structurally for the blocker list rather than behaviourally, with a comment
  pointing here. The play-mode hover is asserted end to end and passes.
- **Partly closed by the orb rebuild** — still open for everything else. The
  commander plinth now clears `hoveredOid` on unmount when it still owns it
  (guarded, so it cannot blank a hover that has already moved), and
  `frontend/tests/commandZone.test.tsx` asserts both halves. `Card.tsx` and
  `HandFan.tsx` are the ones that matter for the symptom above and are untouched,
  as is `mode="wait"`. The panel also has a test file now
  (`frontend/tests/cardPreview.test.tsx`), so the "no coverage" half of this entry
  no longer holds.
- **Adjacent bug, fixed**: `findCard` did not search `state.stack`, so a spell
  mid-cast resolved to nothing. That is the beat the commander plinth is
  deliberately still drawing (`commandersOf` has searched the stack since it was
  written), so hovering a commander you had just cast blanked the rail. Both
  functions search the stack first now; `frontend/tests/zoneGrouping.test.ts`
  pins the ordering.

### The focus ring cannot see a transform on a descendant — low

- **App**: `input/ring.ts`'s `ringTargetFor` walks *ancestors* accumulating
  rotation and scale, which is why the hand fan works — its rotation is on
  `.hand__lift`, above the card. The tap rotation is on `.card__pivot` and the
  staged-attacker lean is on `.card__actor`, both *below* the node the ring is
  drawn around, so `degrees` stays 0 and the ring is the axis-aligned envelope.
- **Why it matters**: only for a pad or keyboard player. `handheld.css` hides
  `#ring` and the `[data-cursor]` outline for the mouse, so the `::after` rim is
  the whole of the selection glow there — and that half is fixed (see above:
  the rim moved onto `.card__actor`, inside both transforms).
- **Fix direction**: a descendant walk, or having the actuators publish their
  held transform where the ring can read it. Needs its own gate either way.
- **Test status**: none. `Card.StagedAndTapped` pins the rim's half of this and
  says nothing about the ring.

### 5. The command-zone card is cramped — **resolved**, by not drawing a card

- **Was**: `.cmdslot { --card-w: clamp(74px, 4.2vw, 100px) }`, matched by the app. At
  1600×950 that resolved to ~74px, and with the art band taking `1/1.4` of the width
  the name clipped to "Aesi, Tyra…" and the type line to "Legendary Creatur…". The
  commander is the card you cast most often in the format and it was the least
  legible thing on screen.
- **Fix**: the mockup's own direction — "give it a larger scale" — could not work.
  A card face has six things to fit and the column that holds it is a hard 190px, so
  every pixel of extra width is a pixel of extra height in a column that also has to
  carry a life dial, a mana row and five zone piles.
  So it stopped being a card. `CommandZone` now renders a **plinth** inside the
  player's info panel (`docs/roadmap.md`, "Improve Commander Placement"): a 2:1
  banner crop of the art, the name on its own line at the full column width, and a
  state strip. Rules text and the type line were never legible at this size anyway
  and are one hover away in the preview rail, which is the surface rebuilt to hold
  them.
- **Bonus**: the plinth's state is carried on a word, the art's brightness, and a
  glyph — three channels rather than one line of colour. That makes it the first
  interaction affordance on the board that does *not* fail defect #1 below.
- **Guards**: `e2e/cycle3.spec.ts` asserts the name is not clipped
  (`scrollWidth <= clientWidth`); `tests/playerOrb.test.tsx` covers the state table.

### 6. Card type and keyword lines sit on their pixel floor — low

- **App**: `.face__type` and `.face__kwline` measure exactly 8.5px on opponent mats
  at both viewports, i.e. the `max()` floor is doing the work and the ratio has been
  overridden.
- **Why it matters**: no headroom left. A four-player pod shrinks
  `opponentCardScale` to 0.58 and the floor is already binding at one opponent, so
  the text does not get smaller — the art band gives up height instead, and past
  some point that band stops being worth drawing.
- **Fix direction**: check the 3-opponent layout before shrinking anything else, and
  consider dropping the type line entirely on the smallest scale rather than
  rendering it at the floor.

### 7. Phase step labels are abbreviated where the ribbon now has room — low

- **Mockup**: `Begin · Declare attackers · Blockers · First strike · Damage · End`.
- **App**: `Combat · Attack · Block · 1st Strike · Damage · End Cbt`
  (`STEP_SHORT` in `frontend/src/logic/labels.ts`).
- **Why it matters**: the abbreviations were chosen when the live phase pill was
  content-sized and cramped. It is now a fixed six-column grid roughly 960px wide at
  1600×950, so the full labels would fit and read better.

### 8. The action panel's empty state leaves a large dead area — low, and larger

- **App**: `.acts__list` is `flex: 1 1 auto` with a 74px floor, so it fills the panel
  even when it holds one italic line ("Nothing can block.").
- **Why it matters**: cosmetic. The floor is load-bearing — `e2e/layout.spec.ts`
  measures it, because on a short viewport this list is the first thing a flex
  parent flattens to zero — so this is a trade, not simply a bug.
- **The handheld round made it bigger, deliberately.** The rail runs the full
  height of the screen now, so the list is 392px at 1280×800 rather than 172 —
  which is the point of the change and also means an empty list is 392px of
  nothing. `mockups/handheld-board/README.md` names the honest answer and does
  not build it: **one region that is the stack when the stack is not empty and
  the reader when it is**, because they are never both urgent and neither earns
  a permanent column. The stack now floats over the board instead, which is a
  different answer to the same observation and leaves this one open.

### 9. The viewer's mat side column has more whitespace than the mockup's — low

- **Mockup**: a compact side column — name, life, mana dots, zone chips.
- **App**: the dial and pile bars leave noticeable dead space beneath them at
  1600×950.
- **Why it matters**: purely density. It costs the lanes horizontal room they could
  use.

### 10. Eliminating an opponent moves the viewer's whole board down — **resolved**

- **What happened**: a dead player's orb grew a `.orb__loss` line. The opponent row
  is `align-items: stretch`, so *every* mat grew to match and the viewer's board —
  and every drop target on it — shifted down. Measured at 19px at 1600×950.
- **What resolved it**: an opponent is an `OpponentSeat` now, and a seat is a
  stated `--seat-h` grid whose four rows are pixels that add up to 96. It has no
  row that can appear, so there is nothing for a stretched sibling to match. The
  loss state is a filter and an absolutely positioned mark (`.seat--out`,
  `.seat__out`), neither of which takes layout.
- **Not the fix that was proposed.** The entry suggested reserving the loss
  line's height whether or not a player has lost. Making the whole panel a fixed
  grid is the same idea one level up, and it also closes the general case: any
  future conditional row on a seat has the same problem, and now there is
  nowhere to put one without saying so.

---

## Closed in the lobby's first hands-on pass

Three defects came back from actually opening a pod, and two of them were one bug.

- **Seat cards were four different heights** — `.card--big` reverting to content
  sizing with no container frame. `e2e/pod.spec.ts` now asserts all four
  `.slot__card` boxes share width, **height and top**, and that `h / w ≈ 1.4`. Width
  alone passed even with the bug, because `.slot` has a definite width; height is the
  assertion that bites.
- **The dossier's card blew out its grid**, same root cause plus the `auto` track.
  Guarded by an assertion that `.dos__body` does not scroll sideways *and* that
  `.dos__col` clears 300px — the overflow check alone would also pass if the panel
  merely clipped.
- **The name field was on the door.** Now on your own plate, with a server route that
  did not exist (`PATCH /pods/{code}/seat` takes a `name`).

Two things fell out while tracing them:

- `.slot__card[data-act] { cursor: pointer }` had never once been visible:
  `.card--static { cursor: default }` sits on the child that fills the slot.
- `--card-r` is declared at `:root` and a `var()` inside a custom property is
  substituted *where it is declared*, so the whole document rounded cards at the
  board's ~5px however wide they were drawn. `.podhand` and `.dos__top` re-derive it,
  which is what makes a `.back` and a face round alike.

## Closed in this pass

Recorded so the next sweep does not re-derive them. All four came from playtest
feedback against the shipped client.

- **The phase ribbon resized on every phase change.** `.track__steps` had
  `overflow-x: auto` over `flex: 0 0 auto` children, so the live phase's steps grew
  the row past the bar and scrolled the already-played phases out of view;
  `.ph--now` was `flex: 1 1 auto`, so the pill was sized by however many steps its
  phase had. Now a three-column grid with `flex: 1 1 0` on the live pill and a fixed
  six-column step track. Measured: the ribbon is 49px tall and all five phases are
  in view at both viewports.
- **Hand cards rendered rules text at 6–8px.** Cards went art-first, the rules moved
  to the rail, and every remaining line got a pixel floor. Measured: nothing on any
  card renders below 8.5px.
- **The rail preview clipped its rules text.** It scaled the portrait card up, so the
  rules box stayed squeezed by the card's own 1.4 aspect. It is now `.face--big`,
  width-driven and as tall as its text needs. Measured: 286×312 with 12px rules and
  no clipping.
- **Three panels where the mockup has one.** `ActionBar` and `CombatPanel` merged
  into `ActionPanel`; the tools became its footer; the amber wash came off the panel
  and moved onto the selected rows; the commit alternates got a real outline.
  Measured: the right rail has exactly three children, and the panel's background
  matches the stack pane opposite it.
