# Design record

The findings of the design rounds that were carried out as static HTML mockups
under `mockups/`. That tree was removed on 2026-09-05: nothing consumed it at
runtime, and it weighed 108 MB. What it established -- the numbers, the rules,
the directions chosen and the reasons the other directions lost -- is kept here
as prose. The shipped client cites this file wherever a number or a decision
came from a round.

Twelve rounds, in the order they happened. Each section says what the round
explored, which direction was taken and why, and every concrete number and rule
it settled that code might cite. Where a README's own wording was crisp it is
kept; the narrative is compressed. A final section carries over the fidelity
findings that were still open when `docs/mockup-fidelity.md` stopped being
maintained against a live mockup.

Every round shared one board state -- **turn 8 of the reference screenshot, at
declare-attackers, thirty permanents, the same hand and life totals** -- so that
a difference on screen was a difference in design rather than content. Every
round's files opened standalone from `file://` with no build, server or network,
which is why each inlined its own copy of the shared masters (`inline.py
--check` failed a file that drifted) and why mana symbols were `<img>` rather
than fetched.

---

## Gates and measurement

Principles that every round after the first inherited, and that the client's
`e2e/handheldAssert.ts`, `e2e/layout.spec.ts` and the Storybook gates are
ported from.

- **A stated design number is measured, not eyeballed.** Where a visual
  property reduces to a number, assert the number: an assertion about content
  passes happily through a layout failure, and 2.11px text looked fine in
  every screenshot of the board for months.
- **`overflow: hidden` on `body` hides layout failure completely** -- the page
  reports `scrollHeight === clientHeight` while content runs under the foot.
  Two checks a naive overflow test misses: **escape / last-lane spill** (a
  child wider than its block paints over the next sibling; measure the last
  `.lane`'s `bottom` against the foot's `top`, not the mat, which is stretched
  to its grid row) and **collapse** (assert a scrolling region still has a
  height; at 950px the action list flattened to 0 in three of five board
  mockups). Measure the element, not the class name.
- **Inside a scroll container only the cross axis is an escape**; outside one,
  both axes count. A gate that ignored this reported 18 escapes on a clean file.
- **Font sizes are read unscaled and boxes through the stage scale**; backwards,
  a 16px floor reads as 17.9 and passes type that fails on the device.
- **A `+1` tolerance in an overflow check approves a visible ellipsis** --
  `text-overflow` fires the moment `scrollWidth` exceeds `clientWidth` at all.
- **`getBoundingClientRect().width` of a rotated element is its axis-aligned
  box, not its width** (a 176px card measured as 202). A clip check asked of
  `overflow: visible` boxes counts hover labels in `scrollWidth`. `* {
  box-sizing }` does not match pseudo-elements.
- **Measure after the render, not during.** A cursor resolved before markup was
  inserted named nothing on the first frame; a coach mark built inside the
  template string queried the previous render's DOM.
- **A one-sided ceiling on an animation duration is satisfied most cheaply by
  making the animation violent.** Animation gates need a floor as well as a
  ceiling (see [Door](#door)).
- **A uniformity gate cannot see redundancy and cannot see one component
  shouting at its neighbour.** Both have to be noticed (see [Self](#self)).
- **No native `title` tooltips.** A tooltip opens on hover and on nothing else,
  so on a controller it is information that cannot be reached. The client had
  45 and has none; every handheld-era gate fails a file that grows one. A
  mark's name lives on `aria-label`, surfaced on hover and on the cursor.
- **The handheld floors**: nothing carrying information under **16px**; nothing
  focusable or tappable under **44x44**; no card the cursor can land on under
  **96px** wide (`CARD_FLOOR`); focus ring **3px solid** (read the style, not
  only the width -- `outline-width: 3px` with `outline-style: none` passed a
  width-only gate); never more than one cursor; `ringLost` -- the state names a
  stop, the stop is on screen, and it is not wearing the cursor -- is never
  intentional.
- **Verification viewports**: the desktop rounds were verified at **2560x1278
  and 1600x950**; every handheld round at **1280x800** from `file://`. Every
  file: no console errors, no external network requests, no broken images.
- Colour accessibility is out of scope by ADR 0006; the 16px floor is a
  legibility gate, which that ADR keeps in scope.

---

## Board themes

Five static mockups of one board state (`01-arcane-slate`, `02-candlelit-table`,
`03-neon-arena`, `04-ink-and-signal`, `05-planar-art`), for picking a direction
before any component was touched.

**What was wrong with the board it replaced**, in cost order: **the table was
green, and green was already taken** (`--felt-0: #0a1410` under a `--playable:
#5ce08a` rim and a green Forest tone -- every mockup started by making the
table neutral); **every control had the same weight** (one `.btn` for "Attack
with 0", "Quit", "Undo" and the speed toggle alike -- all five split controls
into **three tiers**: one large non-rectangular commit button, contextual
choices, a demoted utility strip); **activated abilities had no presence on
the card** (`Table.onBoardCard` already routed a click to `activate` actions;
all five put a rune on the card and a popover behind it); **two thirds of the
screen was dead** (`.play` gave opponents `1.25fr` permanently; every mockup
sized the opponent row to its content); and **`--card-w` was hard-coded at
104px** -- all five used `clamp()` **keyed off viewport height, not width**,
because the binding constraint on a 1600x950 laptop is vertical and the
shipped `--hand-scale` only ever shrank the hand, so the board was what
spilled.

**The five.** 01 Arcane Slate (graphite + brass, hex "priority stone", 13 phase
ticks collapsed to 5 with only the live one expanded) was recommended as the
base because it kept every structural class name. 02 Candlelit contributed
**zones as furniture** -- piles whose height is the count -- and **life as a
brass dial**. 03 Neon Arena contributed the **strike band** (declared attackers
stand in a lit band between the boards, one "at Edgar Markov" plate replacing
five "Attack p1 with ..." sentences) and the **mana meter**: the opponent's lands
as `R x2 open, W/B x1 tapped`, listing one entry **per source, not per symbol**
-- Scoured Barrens makes W *or* B and counting it twice claims mana that does
not exist. 04 Ink & Signal spent hue on exactly two things, mana and interaction
state, and grouped **actions under the card that offers them**. 05 Planar put
real art on the board and showed that at 110px it costs the board its type
encoding.

**What was actually built.** Mockup 05 was taken, art and all -- against the
recommendation, and deliberately -- and the card face then went further, to
direction D of the [Cards](#cards) round. The argument that settled it: a
luminance ladder tells you a card is one of eight categories; a picture tells
you which card it is. Twelve Forests under the ladder were twelve copies of
"one of the tan ones". Also taken: the neutral indigo ground, fluid
height-keyed `--card-w`, the opponent row sizing to content, the three button
tiers, the ability rune, the five-phase ribbon, and from 02 the life dial and
the zone piles. The strike band and the grouped-by-source list were not built.

**Ability rune caveat.** The server can express an *available* ability but not
an unaffordable one -- `legality.py`'s `unplayable_reason` covers hand cards
only -- so a greyed "you can't afford this" state needs a new field.

**Card art pipeline.** The Moxfield route in the original card-catalog proposal
was tested leg by leg: `api2.moxfield.com/v2/cards/search` answers a scripted
client with a **Cloudflare 403**; `assets.moxfield.net` serves the whole card,
not the art, and only by an id the blocked search returns.
`api.scryfall.com/cards/named?exact=` is open, keyless, and returns
`image_uris.art_crop` (~40-100 KB each; tokens resolve too). Architecture kept
-- fetch once, store in the repo, skip if present, no service running anywhere
-- with the lookup swapped to Scryfall. **Coverage: 133 of 138 non-token cards
across both decks.** The five that do not resolve are custom names (`Gyre
Strait Leviathan`, `Surge of Growth`, `Tidal Broodmaster`, `Wave of Growth`,
`Whelming Tide`), so an art pipeline needs a text-frame fallback for **~4% of
cards**. 21 crops for the reference board came to 1.4 MB. The shipped client
draws from a Scryfall bulk dump (`docs/card-catalog.md`).

**Fixture notes.** `Sunlit Barrens` in the original screenshot is Scoured
Barrens. One of the eight Forests was swapped for a **Terramorphic Expanse**,
because nothing else on that board has a non-mana activated ability
(`engine/legality.py` never offers mana abilities as actions) and its `{T},
Sacrifice:` is a real `activate` at that step.

**Standing warning.** Do not put art on the board without checking a
four-player pod at ~51px cards; that is the size that decides whether a signal
is carrying anything.

---

## Cards

Five directions for the card face (`index.html`), drawn at **the four widths the
client uses -- 60px (a 3-opponent mat), 104px (your battlefield), 146px (the
hand) and 286px (the preview rail)** -- so a direction that only works enlarged
is visibly one that only works enlarged.

**Three complaints**, in cost order: the title bar was a three-item flex row so
`Aesi, Tyrant of Gyre Strait` lost the width fight with its own cost and clipped
to "Aesi, Tyra..."; mana costs were invented letter-on-a-disc pips; and every
land was the same tan rectangle at the same luminance, on a board that is
roughly forty percent lands.

**Two decisions all five shared**, which hold whichever direction is taken:

- **A name wraps rather than truncating** -- two lines wherever there is room;
  truncation only at 60px, where a second line costs a quarter of the card's
  height. The name band must not be left at `flex-shrink: 1`, or the art
  compresses it back to one line at 104 and 146.
- **The 60px mat card drops the mana cost entirely.** A permanent on an
  opponent's board has already been paid for; its cost is the one line that
  cannot change a decision you are about to make. Also at 60px, the type line
  is suppressed when it would only repeat the name (a Forest's subtype *is* its
  name).

**The five.** A Modern Frame (best enlarged, worst at 60px -- three raised
bands plus a footer eats the art to a sliver; its rarity gem is drawn hollow
because `CardView` carries no rarity). B Banded (nothing reflows between sizes;
cheapest port). C Cost Rail (cost on a vertical rail down the left edge, so a
name cannot collide with a cost at any width; its land widens the rail into a
coloured spine -- the best land at 60px; highest port cost because `.face`
becomes a row). D Art Bleed (art fills the frame, text on graded scrims top and
bottom; most attractive, least dense). E Tactical (designed at 60px and scaled
up unchanged; its land is the symbol and almost nothing else).

**The recommendation was C's cost rail and E's land on B's band structure.
What shipped was D**, "Art Bleed", because the game looking good in a
screenshot was accepted as a real goal and the type-ladder objection was
settled the other way (see [Board themes](#board-themes)). Everything else
about D was taken as drawn: real mana symbols; type sizes clamped at both ends
(`--fs-*` scale on `.face`; `.face--big` restates it in pixels because its
`--card-w` is a fiction); a **1.4% frame, not 3.2%**, with a 2px floor; the
commander as a crown inside the name rather than a `CMD` badge that rendered
under 3px at pod size; supertypes dropped at board size (`shortType`); no
hatched plate for a card with no printing (a colour-identity gradient with a
quiet `NO ART`); keywords as a chip; a neutral centre mark for a land that taps
for no colour. Two 60px rules are scoped to `.mat--compact`: the name clamps to
**one** line, and the mana cost is **dropped**. Not taken: reducing the type
line to the bare subtype, because with the ladder gone the type line and glyph
are what say what kind of card this is.

**What the ladder cost.** None of the five preserved card type as a luminance
ladder (0.58 -> 0.92 relative luminance across seven type fills). Its removal
took ~200 lines of `tests/palette.test.ts` with it. What replaced the guards:
`palette.test.ts` asserts the art *is* full bleed, that both scrims are
gradients whose opaque ends clear a darkness floor, that text carries a shadow,
and that no `.face--type-*` colour rule has crept back; `e2e/art.spec.ts`'s
"the art fills the frame"; `e2e/legibility.spec.ts`'s resolved-scrim-contrast
and frame-width checks.

**Mana symbols.** `fetch_symbols.py` made one call to
`api.scryfall.com/symbology` and downloaded the **28 symbols this game can
produce -- WUBRG + C, generic 0-16, X, and tap, untap, snow, energy -- 93 KB**.
Hybrid and phyrexian were deliberately excluded because the engine rejects
those costs at load. Fetch once, store in the repo, skip on re-run. The SVGs
ship fully coloured, so nothing is recoloured through `currentColor`; they are
vendored to `frontend/public/symbols/` and `ManaSymbol` draws them everywhere.
A real symbol is a *shape* -- a tree, a droplet, a skull -- so colour identity
reads at a glance and reads on a tapped card, which a horizontal text
watermark does not.

**The sample set** was eleven cards picked to break layouts: Aesi (longest name
against a 3-symbol cost), Gyre Strait Leviathan (no printing, and the widest
cost at 7 pips), Terramorphic Expanse (a land producing no colour with a real
activated ability -- all five answered it with the same neutral grey mark),
Acidic Slime (counters, damage, keyword and summoning sickness at once),
Explosive Vegetation (longest rules text, no P/T), plus Sol Ring and Beast
Within because the board had no artifact and no instant.

**Verified** at both desktop viewports across 11 cards x 5 directions x four
toggles: no clipped rules on any enlarged card, no truncated name above 60px,
nothing under **8.5px** -- the floor already binding on the client at one
opponent. Two bugs the gates caught: `.face { height: 100% }` inside an
`auto`-height card collapsed the face and left a band of empty stock under the
textbox (it looks like padding; it is not); and the name band's default
`flex-shrink`. The 60px column was an inspection tool, not a gate.

---

## Menu

Five interactive directions for the new-game screen (`01-command-table`,
`02-deck-rack`, `03-pod-lobby`, `04-ink-dossier`, `05-planar-gate`). Each picked
decks, opened a dossier (closing on x, outside click and Escape), set
difficulty per seat, imported from Moxfield (fail then succeed), opened a chair
to another player, and pressed Play, which committed visibly and did nothing
else -- the rule for every interactive mockup after it.

**What was wrong**: the menu was the last green surface in an indigo app (and
its 46px `--gold` title the only place gold was a display face rather than a
control tier); a 100-card deck rendered as forty words in a 250px box while
the deck files' `substitutions` went undisplayed; Opponents, AI and Seed had
equal weight; the AI toggle leaked `heuristic | random`; and nothing could say
where a deck came from.

**Direction taken.** 01 Command Table as the base -- the setup screen as the
board before the board, with a **seat strip** instead of an opponent count --
with four ports: the comparison matrix's five 1-4 ratings as filled/hollow
segments (from 04), the back of the box on the tile (from 02), the persona seat
(from 03), and the tint on the hero panel only (from 05). 03's idea that **a
seat is the unit** -- a seat has a `kind` -- is what survived into every later
round. 05's verdict, repeated for every later tint: the tint is already spent
saying which deck is selected, so it has nothing left for hover or an open
chair -- one channel, four jobs.

**Art resolution is a hard ceiling and a layout constraint.** Every Scryfall
variant was measured:

| variant | size | what it is |
|---|---|---|
| `art_crop` / `art` | **626x457** | the art alone -- the ceiling |
| `large` | 672x936 | whole card |
| `png` | 745x1040 | whole card; art band ~655px |
| `border_crop` | 480x680 | whole card |

The rule: **never render a crop above ~1.25x native (about 780px wide).** Any
field bigger than that is blurred on purpose and carries no detail; something
crisp sits on top at or below 1x. This applies to every surface in the app.

**Difficulty**: four tiers, because tier 1 is the `random` agent and tier 3 is
`heuristic`, each lighting a cumulative prefix of three capability lamps
(combat math, removal & targeting, mana & sequencing): **Goldfish** "Plays
solitaire" (ooo), **Apprentice** "Knows the basics" (*oo, default), **Duelist**
"Plays to win" (**o), **Archmage** "Plays around you" (***). Apprentice and
Archmage do not exist in the engine and would map to `heuristic`. The shipped
client dropped the ladder: what a CPU seat can honestly differ in is its deck
and its agent (see [Flow](#flow)).

**Rooms**: one new idea, a seat kind -- `cpu`, `open` (an empty chair holding
the room code), `human` (`ready` is whether they have locked in). No
single-player/multiplayer fork. "Fill empty chairs with CPU" is one toggle
covering the partial pod and backfill. A human's dossier is sealed until they
lock in, drawn as the no-printing hatch plate. A preview deck can be chosen but
not dealt and never sits in an opponent's chair.

**For the port**: `new-game`, `deck-<id>`, `opponents-<n>` and `start-game`
must survive on the node a click lands on (in 04 the name cell, because a
`display: contents` row has no box). Deleting the seed field breaks
`e2e/helpers.ts`'s `getByPlaceholder("random")`. The engine already takes one
`agent` per seat. Escape and collapse checks caught three real bugs; a grid
item's default `min-width: auto` was the cause of one.

---

## Flow

Five interactive mockups of the whole path from launch to shuffle, under the
working name **Snap Keep** (this round only; the rename did not ship).
`01-front-door`, `02-face-up`, `03-command-rail`, `04-three-steps`,
`05-the-room`, over an eleven-point contract every file drove end to end: home,
create or join by code, fill a chair (add a CPU or invite, never behind a mode
switch), a scripted guest joins and locks in, copy code and invite link,
browse a 24-deck catalogue (search, colour identity, source, four sorts), open
a dossier, import from Moxfield (garbage then a link), lock in and unlock,
adjust a seat, Start which refuses until every seat is resolved *and* you are
locked in.

**The four holes the menu round left**: no front door; creating a pod was not
an act; a catalogue of four is a list but twenty-four is a problem; and only
the *other* player locked in -- so in every direction **readiness is
symmetric**: you lock in like everybody else, and Start is the pod completing.
The seat model gained `empty` (no chair at all; a two- or three-player pod is a
legal pod).

**Direction taken.** 01 Front Door was recommended (one surface, overlays, the
readiness strip); **02 Face Up is what the lobby was ported from.** 02 draws
setup as four cards on a table -- face-down until somebody chooses, face-up
once they have, stamped once they cannot take it back -- with lock-in as a
physical act louder than unlock, and face-down as one picture for three facts
(empty chair, undecided player, sealed list). It is the one file with no
difficulty ladder: it lets you change a CPU's **deck** instead, which is the
thing a seat can honestly differ in, and that is what shipped. Its seat face is
the preview-rail `.face--big` re-derived for the lobby, keeping the 1.4 aspect
so a face-up seat and a face-down `.back` are the same rectangle -- the one
deliberate deviation from the app's width-driven rail card, now `.podcard` in
`lobby.css`, with the type scale as ratios of `--card-w` (296 x .047 = 13.9
against the rail's 13.5px name). Four classes were renamed for the port
(`.podhand`, `.podrail`, `.dos`, `.deal`) because `.hand`, `.rail`, `.over`
and `.play` already meant something in `board.css`/`ui.css`.

**Portable ideas from the others**: 04's comparison matrix (five ratings over
shared columns, read straight down); 03's pod summary that never leaves the
screen (as a strip, not a 300px rail); 05's tint on the pod backdrop only, if it
drives nothing but the wash.

**Catalogue states**: `playable` (the engine can deal it), `preview` (in the
catalogue, not dealable -- Gishath and Yuriko, chosen on mechanics the engine
cannot express), `partial` (an import whose unsupported cards were dropped;
maps onto the client's `simplified` count). Twenty of the twenty-four
commanders were chosen for colour spread; their ratings are authored editorial
judgement and their `curve` is **null**, because a curve is a count of a list
that does not exist and inventing one would be the single lie on the screen.
The shipped client has no `preview` state (the server lists exactly the decks
it can deal) and dropped `guild` and `short`.

**Art ceiling bit harder here**: 03's seat panels were capped at a 1440px board
because an uncapped half-stage panel at 2560 is 845px, a 1.35x upscale.

**Bugs the escape check found**: a seat x 8px off its card, a selection ring
at `inset: -5px`, a 104px colours column against The Ur-Dragon's five pips,
and a six-pip cost pushing `.face__head` past the card until `.face__name` got
`min-width: 0`.

**For the port**: seven test ids -- `new-game`, `deck-<id>`, `opponents-<n>`
(on the "Add a CPU" control of an empty chair, `n` being the count that click
produces), `start-game`, `create-pod`, `join-pod`, `lock-in`. The seat rail
kept a host-only seed field the mockup lacks, because reproducible games are
what `full-game.spec.ts` and `playtest.spec.ts` run on. `DeckImport` follows
`_flow.js`'s `CUSTOM` brief: **"The error state matters more than the happy
path, because it is the state the real feature will spend its life in."**

---

## Orb

Five directions for the player panel on the desktop **190px column**, which
gets roughly **341px of height at 1600x950** (`01-astrolabe`, `02-docket`,
`03-plinth`, `04-ink-and-signal`, `05-totem`). Not interactive; one state with
every conditional channel on at once (your turn *and* priority, commander in
the zone with `+2` tax, two opponents past commander damage with one at 16,
exile non-empty, a hovered spell tapping two lands, library 41 against
graveyard 12).

**What was wrong**: six visual languages in one column; commander damage -- the
only stat with a known maximum -- drawn as a bare number; the component
maintained twice (`.orb--compact`); and four seats that looked identical while
the one asset that tells them apart, the commander's art, was drawn at 80px.

**Measured**: 01 Astrolabe 256x460 (does not fit; a 21-notch damage arc);
02 Docket full width x 104 (returns 190px to the board; most expensive port);
**03 Plinth 190x318** (the art as the ground, the life dial stamped over the
portrait's lower right, costing the overlap instead of a row); 04 Ink & Signal
150x434 (one track, two scales: 21 segments for damage, 9 for zones because
`pileLeaves` is one leaf per nine); 05 Totem 96x356 (a proportional zone pole;
Lib 41 a 38px band, CMD 1 a 14px sliver).

**Direction taken: 03 Plinth, with the height of 01 and without the tint.**
Three departures from the mockup, each found by measuring the built panel:

1. **The panel fills its column** -- `.orb` is `flex: 1` and `.orb__body`
   spreads with `space-between`: 190x353 at 1600x950 and 190x475 at 2560x1278.
2. **No colour-identity tint.** `.orb__wash` and `.orb__veil` shipped;
   `.orb__tint` did not. The veil is unconditionally dark, so dropping the tint
   cost nothing but the tint; seats are told apart by portrait alone, which is
   what survives `e2e/greyscale.spec.ts`.
3. **The seal reserves its overhang instead of indenting the caption**
   (`.cmdplinth__frame` carries a `margin-bottom` of the overhang; at 2560x1278
   the disc clamps to 76px of a 156px portrait).

Two more: `.orb--compact`'s piles must not wrap (they did at 112px; the binding
constraint was the labels -- "Hand" beat a 20px stack -- retuned to fit five
with ~5px spare); and **the plinth was unhoverable** because it rendered
`disabled`, and a disabled control dispatches no mouse events, so "the full
card is one hover away" was false for every commander you could not cast. It is
`aria-disabled` with the click gated in the handler. `findCard` also learned to
search the stack.

**Plinth's art ceiling**: the wash renders the 626x457 crop at 190px (0.30x) and
the window at 160px (0.26x); nothing is upscaled. Do not port the wash to
anything wider than ~780px.

**Later superseded by [Self](#self) and [Handheld board](#handheld-board)**:
the 21-notch damage gauge (port item 1) was closed rather than built -- the
viewer's panel stopped drawing commander damage at all; the seat-shaped
component that would kill `.orb--compact` turned out to need 74px rather than a
seat's 96; and mana became counted symbols on a plate (`4{G} 2{U}`) rather than
the loose dots every orb direction drew, because a real symbol is twice a
dot's width and a mark per mana wrapped to three rows in 190px. The three foot
rows were grouped into `.orb__foot` on plates so the interior stops re-spacing
whenever mana empties; `e2e/orb.spec.ts` measures it against the **112px pod
budget**.

**Rules that hold**: the library is not a button (hidden information; a control
that does nothing when clicked is worse than no control); the mana slot keeps
its line whether or not it has pips, because a collapsing slot moves the board
under the cursor; nothing in the commander subtree may carry `data-action-id`;
`commander_cost` is not `commander_tax` (the `+2` shown is the extra generic
already doubled by the engine); `life-<pid>` holds the bare number and nothing
else because `lifeOf()` does `Number(textContent)`; draw four seats before
believing a single-panel shot.

---

## Handheld

Six interactive mockups of a Steam Deck board driven by a real `Gamepad` API
build with a keyboard fallback. `01-focus-ring`, `02-verb-wheel`,
`03-one-zone`, `04-the-reel`, `05-glass-pointer` were the argument;
**`06-one-thumb` was the answer**, held to reaching everything the web client
reaches. Every file was exactly one 1280x800 screen scaled to the window with
the scale printed on the bezel, because a 1280 design judged in a 2560 window
is judged at half the angular size, in the direction that flatters it.

**The measurement the round was built on.** The shipped board at 1280x800 put
**444 of 635 rendered elements below 12px, the smallest at 2.11px**. A Deck is
a 7-inch panel at 40-50cm; 2.11px is a decoration in the shape of a word.
Also: **41.9% of the screen was rail** (`232px minmax(0,1fr) 304px` -- 536 hard
pixels of 1280, with only three `@media` rules in the client); hover was the
only route to five things (the preview rail, the dim-card reason, the ability
popover, fanning a stack, and **45 native `title` tooltips**); and there was no
cursor -- zero `:focus-visible` rules with every card `tabIndex={0}`.

**The floors** -- 16px type, 44x44 targets, 96px cards, a 3px solid ring --
were taken as hard constraints and turned out to decide the layout rather than
decorate it. ADR 0002's flat action space means a controller UI loses no
capability: every legal action is already a control with `data-action-id`,
exactly once.

**Three things decided once for all five**: B is back everywhere and never
quits from the top level; View is the log/zones/scoreboard, Menu is the system;
the commit control is one shaped slab saying the one thing the turn waits on.

**The five**: 01 Focus Ring (noun first; its ring is 06's ring; `nav()` scores
candidates by distance along the pressed axis plus punished perpendicular
drift, `PERP = 2.4`); 02 Verb Wheel (eight verbs in eight fixed places; a
Commander priority window can hold forty actions so it always costs a
shortlist; the one place a wheel is genuinely better is colour identity, which
is radial); 03 One Zone (bumpers swap which zone owns the screen; **158px is
the width at which a card renders its own name at the 16px floor** -- 5 of 7
creature names fit; its spine summary `8 creatures - 8 untapped - 20 power - 1
flier` is worth stealing anywhere); 04 The Reel (draw what the engine is: one
question per `PendingDecision`, one entry per legal target tuple; gives up the
board); 05 Glass Pointer (the control: the Deck already has a trackpad;
magnetism snaps to the nearest interactive thing within 40px and draws a line
to what it caught; wins on presses and loses on seconds).

The headline metric -- cast Beast Within at Falkenrath Noble -- was defined
three ways (presses, seconds, mode switches) because a single number would hand
the win to 05. **The seconds column was never filled: nobody has held a Deck**,
and a keyboard makes every scheme feel equally fine.

**06 takes**: 01's ring drawn from state; 02's wheel demoted to a shortcut for
things not on the board; 03's spine summary; 04's reel for all eleven decision
kinds (the switch is a denylist, like `PromptDialog`'s, so an unknown kind
arrives working); 05's pointer live on every screen so trackpad, touch and
mouse are one code path. The thesis: **you can play the whole game with the
left thumb and A**; everything else is a shortcut to something the thumb could
already reach.

**Rules that came out of driving it** (the friction log and four passes):

- **FILL IS FOCUS.** A control is an outline until the ring is on it, then it
  fills. Tier lives on the edge (gold commit, green confirm, red danger), never
  on the fill. Priority is the dot, and only the dot -- two amber rings at once
  is the one failure a controller UI may never have.
- **The cursor is state, not `:focus`.** Stamp `[data-cursor]` from state and
  draw the ring from that; after anything rebuilds markup, re-derive it
  (`ringLost`). The ring went out on the commit slab and the pad stopped
  working, invisibly to any pointer.
- **A real focus trap**: whatever overlay is on top owns the ring. The shipped
  client had five `aria-modal` dialogs with no trap.
- `<small>` renders at 0.83em and broke the floor eight times on one screen
  (`small { font-size: inherit }`); a `var(--face-fs, 13px)` fallback put faces
  under the floor in three files -- **the fallback is now the floor**. A cost
  is one word: `display: inline-flex; white-space: nowrap`.
- An opponent's seat carried ten facts in 330px; it now carries the three that
  decide an attack -- can they block it, can they answer it, is it worth it.
- **The ask leads** (`Declare attackers -- 3 staged, 3 more can go`, on the line
  above your own board; one function feeds the ask line, the slab and the
  foot's verb); the rail owns identity and carries combat math (*"Unblocked it
  deals 7 to Edgar Markov -- that is 18 life left"*); the foot is verbs only.
  Stack edges are drawn always. Review instruments live on the bezel.
- **Declare blockers**: their attackers lead, each a row; your creatures are
  assigned *into* rows; an unblockable attacker's row carries no slots.
- **The stick repeat is a ramp off magnitude**: first repeat 360ms at a nudge
  to 180ms at a shove, then 155ms to 46ms, x0.72 over a seven-step run. A
  d-pad and the keyboard stand at the middle. These four constants are
  reasoned, not measured -- the round's one open tuning.
- **The ring is a spring, not a transition**, written as the closed form of a
  damped oscillator (the naive integrator overshoots 1.6px at 60fps and 4.5px
  at 144fps and goes unstable at large `dt`). Tuned in time: **w 36, z 0.78 --
  142ms settle, 2.0% overshoot, within 2px in 117ms** on a 200px hop,
  identical at 30, 60 and 144fps; the loop stops itself when it settles. A hop
  further than **420px** starts its travel from that far out along its line,
  because settle time is distance-independent and 1000px in 140ms strobes.
- **The cursor is instant; the detail waits for you to stop.** A step 40ms
  after the last is part of a sweep, so the reader dims and waits ~110ms; a
  twelve-step sweep rebuilds it twice, not twelve times.
- A cursor move is not a board change. Under **4x CPU throttling** (a Deck APU
  proxy) a full render was 28.2ms and a held direction ran at **18.5fps**;
  rebuilding only the rail and foot, keyed on what they draw, gave 10.5ms and
  **59.7fps**. **For a React port: the cursor wants to live as an attribute on
  one element, not as state thirty components read.**
- **Feedback beats** -- anticipation, strike (a ghost moves; the real card
  never does), impact (burst, shake scaled to the hit, rumble, numeral), settle
  -- attackers staggered **110ms** apart, the whole budget under a second.
  State changes first and the animation only reports it; effects live in a
  sibling layer a re-render cannot delete; every beat goes through `beat()`
  and any button skips it (131ms instead of 900). **Motion is a setting**:
  full / swift (55%) / reduced, measured 1030 / 578 / 5ms -- a real toggle is
  the only way the reduced path ever runs.
- **Who you attack**: `A` stages at the default seat, `X` re-aims; **the default
  is the seat closest to dying** (life dominates, commander damage breaks
  ties). Arrows go per seat; the commit names them (`-> Edgar 5, Duelist 8`).
- Manual mana reuses targeting (a x7 Forest is seven taps; B backs out without
  losing the spell). Undo is one snapshot per action, capped at twenty,
  cleared when the turn passes. Coach marks: one at a time, only the
  non-obvious, tied to the moment, dismissed by doing, never again. Sound is a
  specification of seventeen cues placed at their beats (`ui.move` the
  most-played and quietest; denial distinct and paired with rumble; mute never
  changes what happens); **rumble is always redundant with something visible.**
- Lane order is the client's: creatures forward on the combat line, lands next
  to the hand, opponents mirrored. The opening hand's answers are deliberately
  not cards. The stack resolves top-first and `A` on a lower item refuses.
- **Big screens spend room on content, not scale**: at >= 1500 wide the
  opponent seats draw their actual creatures and the rail widens 262 -> 336;
  at >= 1800 board cards step 104 -> 124; at >= 1100 tall lanes get their own
  rows. Two custom properties (`--card-w-board`, `--rail-w`) carry it. The 96px
  floor does not move; a width that cannot afford it does not get the mode.

**Hardware**: `file://` is a secure context so `getGamepads()` works, but Chrome
returns four nulls until the first press -- hence every handheld file opens on
"press any button". The Deck reports a standard 17-button pad; **the back grips
L4/R4/L5/R5 are not exposed** (recommended Steam Input defaults: L4 = back,
R4 = commit); trackpads and gyro arrive as mouse events; rumble is Chrome-only.
Open: how a Vite app reaches a Deck at all (desktop browser or a non-Steam
wrapper), and portrait/phone (390px), where only the reel survives.

**Rejected**: direct-bind (hand cards as ABXY; collapses at five cards) and
dual-cursor (needs both thumbs for one act and loses cancel).

**Port order recommended and largely followed**: ring bound to state; focus
trap; kill the 45 tooltips; real symbols everywhere; fluid rails; the reel for
`PendingDecision`; the spine summary; then the four fluidity items. **Do not
ship a controller mode without the 16px floor asserted in CI.**

---

## Seat

Five directions plus a synthesis for **an opponent's seat on the handheld
board** (`01-dogtag`, `02-vitals`, `03-plinth-strip`, `04-meters`,
`05-seat-card`, `06-muster`), reviewed at all three pod densities and five seat
states (`rest`, `active`, `targetable`, `out`, `noart`). The complaint: the
threat line was a sentence, commander damage floated, and the padding was
inconsistent -- which measured to **seven distinct paddings and at least four
gutters** on one compact seat, each locally reasonable. So `padKinds`,
`gapKinds` and `boxKinds` became gates; every direction reports 2-3 / 1-4
against the shipped 7 / 4.

**The arithmetic.** At 1280x800 the play column is `1280 - 12 - 8 - 243 =
1017px`. A seat gets **1017x96 at one opponent, 503x96 at two, 332x84 at
three**, and has to hold fifteen facts, four of them 44x44 zone targets: five
targets at 44px is **220px of a 332px seat**. The shipped layout answered by
deleting commander damage from the second opponent on.

**Three findings that belong to no direction**:

1. **An opponent's hand is a button only when `hand_revealed` is non-empty.**
   `types.ts` sends `hand: null` for every seat but the viewer, so the peek
   opened on "Hidden -- 4 cards", the number already on the chip. The library's
   own rule applied to the zone beside it. Five targets become three: **88px of
   a 332px seat, and why the seats fit at all.**
2. **Every count lost its label at 16px and nothing replaced it**, so every
   zone mark is a **shape**: a headstone is a graveyard, a fan of three cards a
   hand, a face-down card a library, a dashed outline exile, a star the command
   zone, a crown commander damage. `aria-hidden` SVG with the name on the
   cell's `aria-label`.
3. **None of the five showed board state; they showed zone counts.** Lands were
   not in the payload at all, and `threat.other` (artifacts and enchantments)
   was in it and rendered by nothing -- `logic/threat.ts`'s own behaviour. "How
   many lands and enchantments have they got" was unanswerable from the strip
   at any density. This produced 06.

**Why the five failed** (each passes the gates; each fails on something else):
01 Dogtag -- one cell, one gutter, one radius (44px height, 4px gap, 8px
corner, 4px padding); the best duel seat at **1017x54**, but at three opponents
fifteen ~48px cells wrap to three rows and stand **150px, 66px over budget**.
02 Vitals -- life and per-source damage as one block, the seat as one stop,
**74px at every density**, but it spends the portrait and four seats are told
apart by name. 03 Plinth Strip -- the art as the ground, creatures as **pips**
(filled untapped, outlined tapped, a clipped corner flies), one reserved damage
chip; 74px; but `noart` takes the whole identity with it and at 332px the
marks cover the picture. 04 Meters -- every number a fraction; the **lethal
gauge** (life fills from the left, commander damage closes from the right, one
tick per source at its fraction of 21; when they touch the seat is dead); but a
meter row cannot go under 18px with a 16px numeral, so 90px, and the loosest
uniformity numbers. 05 Seat Card -- one 300px card at every density, hands back
**717px at one opponent** (407 at two, 97 at three), but a 52x88 portrait
column shows a vertical slice of a landscape crop and it costs 12px at three.

**Direction taken: 06 Muster, 332x96 at every density** -- 05's fixed card at
the width `handheld.css` already gave a seat at three opponents, 04's lethal
gauge with 02's one tick per source, 03's pips and art-as-ground, 01's
discipline (**2 paddings, 1 gutter**, three cell geometries differing only in
height). Its row: three cells of one kind -- `[land] 2/3  [creature] 2/4
[gem] 1` -- **untapped / total with a 3px meter along the cell's bottom edge**,
at the same x on every seat so three opponents compare down a column. A meter
rather than a pip run because a pip run cannot do lands (eight is the honest
cap and a Commander board passes eight lands by turn eight). The first version
filled the cell to the fraction with a rule at the boundary, which at two
thirds of a 62px cell landed exactly on the slash in `2/3`. The fourth cell is
the detail: 03's pips plus total power, the only place a creature is an
individual.

**What the row cost**: 96px will not hold four rows one of which is 44 tall
(18 + 22 + 44 is 84 of the 81 that four rows and three gutters leave), so **the
zone counts are marks, not targets**, with the seat sheet as the route into any
of them; the seat is itself a stop, 332x96, the largest target in the round.
The picture: a **72x43 window** keeps the crop's full width and trims top and
bottom, in two thirds of 05's area; the art appears twice on purpose -- the
window as a picture, the ground under a heavy veil as colour identity -- so
`noart` costs a picture, not an identity. Moving the counts into their own row
gave the commander's name ~190px instead of 110: the first seat where *Isperia,
Supreme Judge* fits whole at three opponents. **06 clips nothing at any
density.**

**Seat as a stated 96px design.** The shipped `OpponentSeat` is a `--seat-h`
grid whose rows are pixels that add up to 96, with no row that can appear; the
loss state is a filter and an absolutely positioned mark. That is what closed
fidelity defect #10 (an appearing loss line stretched every sibling mat and
moved the viewer's board 19px). In every direction `out` originally grew a row
and overflowed; all now put the loss reason in the commander name's slot so
the seat does not change size while somebody is looking at it.

**Port order** (do all three findings regardless): hand as button only when
revealed; threat line to marks (`threatClause()` text to `aria-label`); one
reserved damage chip showing the worst source filled to its fraction of 21
(per-source detail in the R2 sheet); one cell one gutter one radius; **lands,
tapped lands and noncreature permanents -- not layout work, `logic/threat.ts`
and `types.ts` must count and carry them first** (the tapped half is a sum over
a field that already exists); the lethal gauge on its own schedule; the fixed
card last because it deletes the three `:has()` density branches.

**Rules**: `spine-<pid>` needs a decision, not a rename; nothing in the seat
carries `data-action-id` (a seat that takes the player-target action routes
through `onSelect`); the card cannot be a `<button>` because the marks inside
it are; **the opponents' row stays capped** (`fit-content(58%)` is load-bearing;
an uncapped row was the handheld layout's largest defect); draw all three
densities before believing a single-seat shot -- two opponents fell through the
gap between branches once already. Fixture values chosen, not read: seat 3 at
16 commander damage (past the warn threshold of 15), seat 2 at 3, Marco's
`revealed: 2`. Five bugs only the gates found, among them a priority tick that
drew 6px outside its seat under `overflow: hidden` and a 40px zone mark holding
35px of content in 32px of box; the rest are in
[Gates and measurement](#gates-and-measurement).

---

## Rail

One direction drawn three times: the right rail at **243x514** on the handheld
board, answering declare-attackers (`01-attackers`), declare-blockers
(`02-blockers`) and the main phase (`03-abilities`) out of the same parts.
The shared master carried the grammar and a file could add only the shape of
its own list; 01 added no CSS at all. The question was whether one panel shape
survives all three decisions.

**The complaint measured to five defects, four of them one cause** -- the 16px
and 44px floors landing on controls sized for a 304px desktop rail at 10.5px:
D1 the slab floated free of the buttons under it (`flex-end` on two stacked
controls of different widths); D2 "All attack"/"No attacks" outgrew the slab
(44x44 plus pill padding); D3 hovering spawned **classic** scrollbars that took
8px from the content box and re-wrapped every row; D4 numerals off-centre in
19x19 boxes drawn for 10.5px type (a 16px Segoe line box is ~21px);
D5 one 44px capsule per opponent inside a 44px row, wrapping at two opponents
-- a cost that scales with pod size, backwards.

**The sixth, which the round was about**: of the rail's **514px**, the rows the
turn is actually spent in got **172** -- preview pane 152, stack pane 84, gaps
16, action panel 262 of which ~22 chrome and ~68 prompt and hint. A third of
the column. So the gate was **`listShare`**, failing a file under half.

**What all three do**: reading is a hold, not a column (the card hold gives
the card **340x476**; the stack hold gets the whole screen; `.oppboard`'s
`inset: 8px` was the pattern); **the stack hold opens itself** whenever you
take priority with anything on it and the hint bar carries `X Stack 2`; the
prompt goes (a label whose subject is still on screen); the list has no pane
(a well around the only content is a frame around a frame, 22px of height and
20px of width); the commit comes back off the foot **as one row of three**, so
D1 cannot recur and D2 cannot inflate; "All" and "None" are 44px marks --
filled and empty of one shape -- with `aria-label`; **the commit label never
changes width** (`Attack`, not `Attack with N`; the count is the number of
filled rows).

**Measured at 1280x800**: shipped 172/514 = 33%, 3 rows, 4 surfaces, 2
scrollers; **01 440px = 86%**, 8 rows, 1 surface; **02 403px = 78%**; **03
440px = 86%** in both states. The shell reproduced the rail at exactly 514
only after a correction: thirteen step labels at 16px do not fit 1264px, so the
real phase ribbon **wraps to two rows**, and a flat 40px strip had handed the
design 35px the device does not have.

**02's cost**: at rest four attackers with candidate blockers is **738px of
content in a 403px list**; after `[all]` it is 403 and fits before you finish.
Its inversion: attackers are the spine (the fixed set you do not control), your
creatures the resource, and the pool is shared -- assigning a blocker removes
it from every other heading. Colour is the channel (green kills and survives,
blue survives, amber trades, red chumps) with position and the hover label as
the second and third channels; **do not take colour-only verdicts without the
label**. The forecast is `40 -> 31`, **red only when lethal**. `[all]` sorts by
tier across the whole board and stops at tier 3, `autoBlock`'s own judgement
that a chump is never worth making on its own.

**03's drill-down**: tapping a targeted spell turns the list into its targets
-- one state, one row height, two targets or twenty -- with a filled green dot
for "kills it", hollow grey for "survives", red for a player. Every target
stays a real button with its own `data-action-id`, so the exactly-once
invariant holds and `e2e/action-panel.spec.ts` learns nothing.

**Three findings that hold regardless**: D4 exists twice -- the hint bar's
`.glyph` is an 18px box at 11px type with the same defect as `.act__key`; the
enlarged card's `.face--big .face__rules` has D3 and re-wraps its own text
when the bar appears (`scrollbar-gutter: stable`); and **a mana cost and a card
name do not both fit a 243px row at the 16px floor** -- a three-pip cost is
64px of ~223 usable, leaving 115px for a name that wants 145, so three of six
rows on 03 clipped. Whoever builds 03 has to decide where the cost goes (a
second line, generic pips to a number, or drop it since an unaffordable row is
already marked).

**Recommended in four commits**: the floor fixes (`scrollbar-gutter: stable`
on the list, stack and rules; `.act__key` and `.glyph` sized for a 16px line;
a tier for the alternates); the commit into the rail (delete the `.foot__slab`
host; check `useZoomFit`'s `HANDHELD_FOOT_EXTRA`, which reserved 56px for a
slab no longer in the foot); the two holds; then 02 and 03 separately.

---

## Self

Five directions for **the viewer's own orb on the handheld**, drawn in the
palette the seat round settled, with three real muster seats above it and
ghosted lanes beside -- because the question was not "is this orb good" but
"does it belong on the same table as that seat, and is it saying anything the
seat already says". `01-ledger`, `02-banner`, `03-plinth`, `04-dial`,
`05-console`, at three densities and seven states (`rest`, `priority`,
`spending`, `cmdzone`, `unpaid`, `out`, `noart`).

**The box, measured**: play column 1017; viewer's mat `634 - 96 - 4 = 534`;
`--mat-side: clamp(132px, 12vw, 190px)` = **154 at 1280**. **The orb is 154x518
and the lanes beside it are 841x518.**

**The round became one about subtraction.** The first pass drew everything the
shipped orb draws and passed every gate while still busy, because a uniformity
gate only proves the noise is evenly spaced. Two channels came off, the two
largest:

1. **The viewer's commander damage** (~70px of 518, the loudest thing on the
   panel). The pod already draws it on the opponents' seats six pixels above.
   The stated cost: a seat draws `worstSource`, the worst that seat has taken
   from anyone, so what *you* have taken was on nobody's panel -- and the
   cheap fix is not to put it back but to flip the seat's chip to "damage they
   have dealt to you". (The shipped client did exactly that: two arrows on
   each opponent's life gauge, `.cmdarrow--dealt` and `.cmdarrow--taken`.)
2. **The board counts.** Yours is 841x518 of lanes beside the panel.

**Ten cells where there were nineteen** (eight in `unpaid`). What survives:
name, turn ring and priority tick; the commander portrait, **which is the
button that casts it**; life as one number; mana by kind with what a hovered
spell would take; the five zones as a seat's chip inside a 44px target. **The
reduced orb does not vary with how many opponents are at the table**, which
removes the last reason `.orb--compact` and its `:has()` branches exist.

**The portrait's three states are drawn, never implied**: on the battlefield
-- plain edge, `In play`, no price; in the command zone and payable --
`--playable` rim, the cost with `+2`, green `Ready`; in the zone and unpayable
-- `--staged` rim, the same price, amber `Need 8`. Castable and affordable are
two different things (`{4}{G}{U}` plus two tax is eight against three open).
`aria-disabled`, never `disabled`; the cost belongs on the button.

**Findings**:

1. **The target is bigger than the ink.** The first pass grew the zone chips to
   68-72px because the room existed; beside identical 20px chips on the seats
   above that was a component shouting at its neighbour. **The chip is a seat's,
   to the pixel (20-21px); the button around it is 44 and transparent.** Which
   ones you can press is drawn as relief -- a lit top edge on the four that
   open a peek, a recessed face on the library -- with identical fills, so it
   survives greyscale.
2. **A uniformity gate cannot see redundancy and cannot see shouting.**
   `padKinds` 2, `gapKinds` 1, `boxKinds` 3 against the shipped seven and four,
   and still wrong twice.
3. **Three crops of one 1.37:1 painting**: 02 banner 92x68 (~100% of the
   width); 05 console 148x74 (100%, trimmed); 01 ledger 148x170 (~64%); 04 dial
   148x130 (~83%); **03 plinth 148x250 (~40%, the largest picture, heaviest
   crop)** -- the direction's one stated price.
4. `[data-name]::after` is spoken for by the hover label (including
   `opacity: 0`), and a blanket `.dial > *` rule turned the donut's hole solid.

**The five**: 01 Ledger (the seats' cells; a 148x170 portrait and a 100px life
cell with a 48px numeral; cheapest port); 02 Banner (**999x74** -- five facts
need one line, not a column; returns the 154px column and its gutter, **ten
cards per lane become twelve**; reaches `logic/zoomFit.ts`); 03 Plinth (the art
as the ground under muster's veil, a 148x250 portrait, the life dial stamped
over its lower right with the overhang reserved); 04 Dial (life as a 148px
ring, the full column width; a dial cannot be compared across seats the way a
bar can); 05 Console (mana one group per row at 44px, life the smallest thing
at 30px). 04 and 05 are the two ends of one question -- do not take both.

All 50 measured rows pass; `minHitPx` is 44 everywhere; the only clip is the
loss line in `out` and the commander's name in 02's `unpaid`, never a count.

**Recommendation**: 01, and take 02's question seriously -- the column was
sized for fifteen things and there are five. Then the portrait's three-state
button; the 21px chip inside the 44px button (do not do it by growing the
chip); 03's life seal if the identity claim is wanted. **What shipped is 03's
plinth**, verified on the whole screen in [Handheld board](#handheld-board).

`lifeLabel` is deliberately separate from the seats' `gaugeLabel`, so the
accessible name never describes something the sighted reader cannot see.

---

## Handheld board

Three mockups of **the whole 1280x800 screen at full fidelity** --
`01-attackers` (your turn 8, combat), `02-blockers` (Edgar's turn 9),
`03-abilities` (your turn 8, main 1) -- putting the seat round's muster seat,
the self round's plinth orb and the rail round's panel on one deck with real
art, real symbols and the real board state, on the layout muster sketched. The
three are **one game, one turn apart**: the three creatures that cannot block
in 02 are the three sent in 01, tapped on the mat and absent from the list.
Acidic Slime and Yavimaya Elder are summoning-sick and *can* block, which the
engine gets right.

**Why**: every earlier round designed one component against a ghost and could
not check its own claim. "3 lands, 2 untapped" over a dashed sketch is
unfalsifiable. So the round's own gate is **`seatsAgree`**: each opponent's five
counts derived three independent ways -- by `musterOf()`, by `assert.js`
walking the fixture with different code, and by reading the rendered `.perm`
cells -- must match. A summary that cannot be checked against the thing it
summarises is the failure mode this whole family of components has.

**Measured at 1280x800**:

| file | rail | reader | list | share | rows | min card | min font | min hit |
|---|---|---|---|---|---|---|---|---|
| 01-attackers | 748 | 236 | 398 | 53% | 8 | 120 | 16 | 44 |
| 02-blockers | 748 | 236 | 363 | 49% | 7 | 120 | 16 | 44 |
| 03-abilities | 748 | 236 | 398 | 53% | 8 | 120 | 16 | 44 |

Shipped at the same size: action list 172px, card width 73.6px, 444 of 635
elements below 12px, smallest 2.11px.

**The five things the round changed**:

1. **The rail runs the full height of the screen: 514 -> 748px**, worth 234px
   from one grid line. That buys back exactly one of the rail round's two
   exiles, spent on **the card reader (236px)** because it changes with every
   row the cursor touches while the stack is empty for most of a turn. The
   list still comes out at **363-398px**, more than double the shipped 172 --
   seven or eight rows without scrolling. The honest next thing, not built:
   **one region that is the stack when the stack is not empty and the reader
   when it is.**
2. **The strip and the board are the same numbers.** In 02 Edgar attacks with
   everything, so his creature cell reads `0/4 untapped` and every pip is
   hollow -- the fact that says it is safe to block, with no sentence.
3. **The rail and the mat are one object in two places.** Toggling a row puts
   `--staged` amber on the creature's face and a mark on its corner; blockers
   in `--targetable` blue; aiming at your own permanent in `--playable` green.
   Two findings: **every corner mark had to move to the left edge**, because a
   fanned lane hides each card's right-hand fifth; and **a rim is a fact about
   a permanent, not a picture** -- selecting by name also lit the enlarged card
   in the reader hold.
4. **The player orb is the self round's plinth, checked here.** The layout
   gives the hand a **270px foot instead of the shipped 148** (0.34 of an 800px
   screen), so the viewer's mat is **372 rather than 534** and the orb column
   **358 rather than 518**. The 160px comes off the one elastic member, the
   portrait: **148x128 is 1.16:1, so `cover` keeps ~84% of the painting's
   width** instead of plinth's 40% -- 18,944px<sup>2</sup> against 37,000,
   still six times a seat's window. One deviation: the player's name is
   dropped from across the top of the portrait (21px of a 128px picture is not
   worth what it was of a 250px one; the strip above names you twice), which
   returns **107px of visible art instead of 86**. Whose turn and who holds
   priority are two facts drawn two ways -- `--active` is the inset ring,
   priority the tick on the top edge -- and 02 proves they are separate.
5. One game across three files, above.

**Findings that hold**:

1. **The hand overflowed its own row by 79px and nothing said so.** Six cards
   at 176px is 1056px in the 947 the foot has; the deck is `overflow: hidden`;
   the only symptom was a commit button that had quietly stopped being
   clickable. It is `fanOverflow` now.
2. **Affordability stops being the filter on a developed board.** Twelve
   untapped sources against a hand whose most expensive card is five; the
   whole decision is targeting.
3. **Forty-two legal targets is not a stress test, it is this table** (Beast
   Within against 21 + 7 + 8 + 6 permanents; a chip grid of 42 44px pills is
   over a thousand pixels in a 243px column).
4. Those 42 collapse to **25 rows** because seven Forests are one row with x7
   -- the same collapse `CardStack` makes, with the same exposure if the
   Forests differ in a way that matters.
5. The type line loses to the P/T when a box is too small, and that is
   backwards; the P/T goes on the art window, where a card keeps it.
6. **`--mat-side` is a clamp and its floor is not its value**: 154px at 1280,
   not the 132 floor a first draft took.
7. Sizing a bezel to `1280 x scale` and letting the unscaled deck overflow it
   puts the deck 48px right of centre; use a fixed full-viewport bezel.

**Other numbers**: the card hold shows the pointed-at card at **330px**; the
commit dock is a filled and an empty of one shape flanking the slab on one row
inside a well, all three clearing 44px in the height the slab alone took, with
the count on a `.commit-note` line above the bar so the button never
re-centres under the thumb; the hint line inside the well was *not* taken
(`HintBar` already owns that). Later amended after playtest: the two squares
were unreadable on screen and are drawn glyphs in `ActionIcon.tsx`, and the
dock renders its note in every mode so the rail's bottom never moves.

**Deliberately not here**: who you attack is answered halfway (one shared
defender as a blue rim round the seat; the general answer is the rail's
drill-down); no tier-3 or tier-4 block; an empty stack; the portrait's
`cmdzone`/`unpaid` states and the mana spend preview unexercised;
`logic/cardArt.ts`'s `undefined` (not fetched yet) and `null` (no printing)
look identical on screen.

---

## Door

Five interactive mockups of the front door as a Steam Deck main menu:
**three selectable cards -- Decks, Play, Join -- sliding apart from the selected
one and stacking on the far side**, driven by the pad build lifted whole from
the handheld round. `01-the-hand`, `02-the-cut`, `03-the-table`,
`04-the-launcher`, `05-the-lantern`. All open on "press any button", move with
a pad, stick, arrows or mouse, refuse at the ends of the row with rumble, press
visibly, and take a pod code.

**What was wrong**: the one card-shaped thing on the old door was a fan of four
`.back` plates you could not select -- **the only thing that looked like a game
was the only thing that did nothing**, drawn as the no-printing hatch four
times. The door cleared the type floor by override list, not design: **eight of
its own text sizes** (11 / 11.5 / 13 / 14 / 15px) were in `handheld.css`'s
generated 144-selector `font-size: 16px` block -- every word on the screen bar
the wordmark. Its geometry was keyed to a window it no longer has. And the most
important control was the least reachable: three actions at three weights,
walked between on a pad *through* a text input. This is the first surface
authored **at** the 16px and 44px floors rather than repaired to them.

**The brief contradicted itself once**: "the middle card selected by default"
and a given list order. A menu whose default selection is not its default
action has picked the wrong default, so **Play is the middle card**, Decks
left, Join right.

**The row is one number.** Everything derives from `s`, the selection in
card-index space, moved by a spring between 0, 1 and 2, with `d = i - s`:

```
x      (i-1)*STEP + sign(d) * (PUSH*min(|d|,1) - BUNCH*max(0,|d|-1))
rot    clamp(d, -1.6, 1.6) * ARC
y      DROOP*min(|d|,1.6) - LIFT*max(0, 1-|d|)
scale  1 + RAISE*max(0, 1-|d|)
z      100 - round(|d|*10)
lean   clamp((|d| - 0.45) / 0.60)     how far the name has travelled to its edge
ink    1 - clamp((|d| - 1) / 0.60)    how much of the card is worth printing on
```

`ARC`, the push-away and the droop are `HandFan.tsx`'s. **`BUNCH` is the only
new arithmetic** -- `PUSH` alone is a fan; subtracting `BUNCH` past one place
pulls the far card back over its neighbour. **The spring is w 22, z 0.82: 98%
of the gap in 179ms (eleven frames), 2.8px overshoot, permanently inside 2px at
294ms.**

**The gates**, all five of which failed a file that looked correct:
`labelClear` (a card covering the name of the card under it; caught at 54% then
15%); `inkClear` (04's live state line sliced by the plate in front -- a cut
line reads as truncated copy); `cardSpill` (a specificity collision pulled 04's
title half off its plate so the screen read "ECKS"; 01's panel copy ran off a
200px card seven times over); `slideReads`; `rowFits` (the row's widest state is
not the one it opens on, and `.deck` is `overflow: hidden`). Measured: row
819px (04: 768), margin 230 (04: 256), card 200, font 16, hit 200 (03/04: 44),
0 escapes, 0 clips, all five PASS.

**The animation gate rewarded the failure it existed to prevent.** A spring of
`w 38, z 0.62` settled in 169ms -- under the 180ms ceiling -- by crossing the
row in four frames and ringing for fourteen more, 21px each way. So three
numbers from `springProfile()`: **`traverseMs >= 100`** (fewer than six frames
is a cut), **`settleMs <= 320`** (past a third of a second a menu is making you
wait), **`overshootPx <= 8`**. Four more things snapped and none was the
spring: single-frame label teleports of 20-50% of a card, each a property with
no in-between (a `data-side` flip, 02's `writing-mode`, 04's alignment flip, the
face-up flip), each now a fraction of `s`; worst single-frame movement is now
**0.0-4.5%** of a card. And **`will-change: transform` on a static blurred
backdrop was the frame-rate cost** -- 05 ran at a 33ms median with a
`blur(26px)` wall, a quarter-size layer and a 3px blur changed nothing, and
deleting the promotion fixed it, because an un-promoted blur is rasterised once
and reused. Keep it on the moving slots; never on a static backdrop.

**Three findings that hold whichever direction wins**:

1. **The stack depth is set by the longest label.** What is left of the further
   card is a strip `STEP - BUNCH` wide and its name has to fit it: `BUNCH` 112
   leaves a 136-139px sliver against 88-95px labels (fits with 44px spare);
   the first pass at `BUNCH` 140 left 108 against 102 and 16px of inset did not
   fit in the 6 remaining; 02's spine at `BUNCH` 178 leaves 73 against a 26px
   turned label; 01 at `BUNCH` 96 leaves 155 against 88. **A spine label is
   about 26px wide whatever it says**, so the constraint stops binding.
2. **A stacked card's name must sit on its outer edge -- or the stack must
   open.** It costs 04 the left-aligned tile title it most wanted. 01 pays the
   other way: with `steady` set, its type stays printed on the plate and the
   pile opens (`BUNCH` 112 -> 96; `labelClear` priced it at 13% covered at 112,
   4% at 104, zero at 100). The remaining +/-4px is the card's own 7.2 degrees
   of tilt.
3. **The stack costs a card everything except its name**, so a direction whose
   idea lives in the body of the card is one the stack argues against.

**Four for whoever builds it**: a text field inside a card makes the card a
bad button (04's `join-pod` did nothing at all -- `drive.mjs` exists because no
still could see that); a hold has to give focus back or every key lands on an
invisible input; Escape is never text; two taps inside a frame are two presses
(count keydowns, do not latch a boolean).

**Direction taken: 01 The Hand.** The room takes the selected card's colour --
05's idea done with drawn art, so the floor sigil's line *is* `--lit` rather
than a wash over a photograph (Decks cold green, Play warm, Join violet). **The
art is drawn, and that is not a compromise**: a front door has no card to be a
crop of, a vector ground is exact at 1280 and 2560, and it is the only asset
that inlines into `file://`. Three things removed in the round: the face-up
flip (a fourth kind of change that swapped what a card *says* mid-move;
selection is carried by lift, scale, rim, sheen and room colour, all
continuous); the code field in the Join card (a dialog on press -- the code is
the next question); and `Last pod BRAMBLE-4821` (a promise the flow does not
keep). The wordmark appears once, per `Mark.tsx`'s rule; the pitch line is
gone; what is left at the edges is what a console puts there.

**The others**: 02 The Cut (the pile closes to a 73px sliver and the far name
goes up its spine; expand in place, because you cannot lose your place in a
row of three); 03 The Table (the empty pod -- four seat plates, one yours and
three dashed -- the only thing in the round that says four seats is a rule;
and **a control in the board's 34px information strip needs 56px**, the 44px
floor costing the play region 22); 04 The Launcher (live state on the plate;
loses the argument with its own idea twice); 05 The Lantern (626x457 art at a
2.05x upscale, soft on purpose; the tint already spent on selection). Still
worth porting into 01: 02's spine on a card more than one place out, 03's
empty pod above the row, 04's live lines on the card face.

**Port notes**: test ids `home` on the deck, `create-pod`, `join-pod` (the
card that opens the hold), `join-go` (the confirm inside it), `pod-code` on the
field wherever it is (`browse-decks` came and went; the catalogue is reached
from a seat). Reduced motion stops the sheen and the motes and the selection
still moves; the loop stops when it settles. What the shipped door changed: it
is full-bleed and only the furniture scales, off `--du` from `stageScale()`
(exactly 1 at 1280x800, 0.72 to 1.45); every size is `max(16px, calc(N *
var(--du)))`; the floor sigil is its own layer sized in `--du`; the app's focus
ring is kept on top of the card's five channels; an invite link opens the hold
itself; the cold caption and build stamp did not come across.

---

## Mulligan

Five interactive mockups of **the first decision of every game** as a game
screen instead of a dialog: `01-the-deal`, `02-the-read`, `03-the-table`,
`04-the-cut`, `05-the-second-question`. Same seven cards (an opening seven for
Aesi: three lands, one a tapland, Sol Ring, a two-drop that ramps, a five-drop
that pays off -- **keepable, deliberately**), real oracle text from
`data/catalog/cards.sqlite`, and a pod where three seats have already answered.

**What was wrong**: `PromptDialog` drew "Keep this hand?" as a centred
rectangle with an 18px title and two identical grey buttons over the hand,
with a *gradient* backdrop whose comment admits "a flat dim over the whole
viewport hid the one thing the player has to look at". Behind it the hand was
`clamp(68px, 9.2vh, 96px)` = **73.6px**, where rules text is 8.5px. Neither
option was drawn as anything (`rowsFor` only draws a face for an option with a
ref); the count in the engine's own prompt string (`Mulligan? (N taken)`) was
thrown away for a constant; and the London mulligan's two questions went
through the same dialog looking like unrelated rooms.

**The round's real answer, from `probe.mjs`**, which binary-searched a real
card in a real browser for the narrowest width at which it prints its own
name, cost, type line and rules text at the 16px floor:

| card | oracle | TEXT | CARD |
|---|---|---|---|
| Sol Ring | 16ch | 120px | 161px |
| Forest | 15ch | 172px | 172px |
| Sakura-Tribe Elder | 124ch | 218px | 247px |
| Island | 15ch | 170px | 170px |
| Tatyova, Benthic Druid | 79ch | **296px** | **296px** |
| Thornwood Falls | 85ch | 182px | 249px |
| Explosive Vegetation | 103ch | 215px | 231px |

**Widest card 296px; seven of those flush is 2072px against a 1280px panel.**
Seven cards tiled across 1280 are 182px each, under what four of the seven
need. **Seven readable cards do not fit on a Steam Deck, at any layout, at any
overlap.** For four of the seven the binding constraint is the name row, not
the rules box. The desktop preview card cannot be borrowed either: `.face--big`
is `--fs-nm: 13.5px`, `--fs-tp: 11px`, `--fs-tx: 12px`, four under the floor,
which is why `CardPreview` already swaps the node on a handheld. The client
found the same wall from the other side: a prompt showing a whole hand at 264px
came to 668px of overflow and settled at 180 where the rules box "degrades
honestly".

**So every direction shows one card at a time, and how is the comparison.**
02-05 raise it over the room on Y with a **0.55 scrim and no blur** -- the
raise is not a modal, because the screen behind it *is* the question. On Y in
all four because 05's second question already needs X for confirm. 04 (the
library as a switch on the d-pad, so the hand walks on L1/R1) had the heaviest
overlap (102px of every 172px card) and had to grow selection before it could
raise.

**01 The Deal does not raise anything, and is what shipped as `OpeningHand`.**
Three passes: seven 176px faces with a one-line reader (told you nothing);
the selected card grown to 296 with the others closing up (the row re-centred
on every move, so the one thing holding still was the card you were reading
and everything around it moved); and **all seven at 296x414, every position
written once at mount and never recomputed** -- moving the selection touches
`z-index`, one attribute and one custom property. What pays for it is **144px
of pitch**, so every card not on top shows half of itself. **Only the card you
are on prints its rules**; the box is closed on the other six and the
illustration absorbs the space (`.ffull__art` is the only flexing member), so
every card is the same 296x414 either way. **The stack falls away from the
selection in both directions, `z-index: 100 - |i - on|`**; a one-directional
fan buries the right-hand neighbour to a four-pixel stripe.

**Measured**: 01 296px card, 0 of 7 names cut, 152px neighbour overlap; 02
178px, 3 of 7 cut, 14px gap; 03 168px, 3 cut, 6px; 04 172px, 3 cut, 102px
covered; 05 164px, 3 cut, 12px gap. At the floor a name needs up to 238px with
its cost beside it.

**Findings**: `hidden` is a UA default and an author `display: flex` outranks
it; **a card face cannot have a type row smaller than its name at a 16px
floor** (0.94 of the head is 15.04px), so hierarchy is carried by weight and
opacity and the small face prints a type *word*; the full card must not repeat
the type line its small sibling puts in the foot (Sol Ring read "Artifact",
rules, "Artifact"); **a fan is wider than its row** -- a card rotated theta
about a pivot below it swings out by `(pivot - h/2) * sin theta` and widens its
box by `h/2 * sin theta` on top, so 1.2 degrees per step swung a 296px card
44px against a 48px margin; an overlap wider than ~20px deletes the mana cost
of six of seven cards; `justify-self`, not `align-self`, on a grid child you
want left ("Kept 7" as a 260px pill). The `+1` tolerance and the rotated-rect
lessons in [Gates and measurement](#gates-and-measurement) were found here.

**Driving**: d-pad/stick or arrows to move; Y (or I) reads in full (01 needs
nothing); A keeps; B mulligans or backs out. `shoot.mjs` ran at **1306x840**
because `STAGE.fit` sizes the deck to `(innerWidth - 26) / 1280`.

**Where it lands**: `mulligan` joins `PromptDialog`'s `HANDLED_ELSEWHERE`
denylist and gets its own surface reading `pending.context.hand`,
`mulligans_taken` and `has_kept_hand` -- no engine change. The full card is
the one piece of real client work: not `variant="big"` resized but that card's
parts re-cut at 16px with the **illustration** as the flexing member. The
shipped `OpeningHand` uses `StaticCard variant="detail"` -- the app's own
full-bleed card at the same 296x414 -- rather than the mockup's banded
`.face--full`, and `styles/opening.css` lets the foot's scrim grow over the art
to fit the rules. Consequences, none a defect: a basic land shows no reminder
text; rules are 12.5px on a desktop and 16px on a handheld. 05 additionally
wants the bottoming prompt (`choose_objects` with `source_name == "Mulligan"`)
routed to the same surface.

---

## Open fidelity findings

Carried over from `docs/mockup-fidelity.md`'s queue as it stood when the
mockups were removed. Resolved entries (#5, the cramped command-zone card, by
the plinth; #10, an eliminated opponent shifting the viewer's board, by the
fixed 96px seat grid) are omitted. None of these blocks anything.

**#1 The `--playable` rim is easy to miss -- medium, a bug.**
`.card--playable::after` is a green rim plus glow: a hairline against a hand of
full-bleed illustrations, several of which have green in them, answering the
most urgent question the hand has. Partly mitigated -- castable cards are also
rows in the action panel. Fix direction: more rim weight, or stronger dimming
of unplayable cards so the distinction is a brightness difference across the
whole hand.

**#2 Combat arrows are hard to pick out -- medium, a bug.** `CombatArrows.tsx`
draws thin `--attacking` red strokes over a board of illustrations, and who is
attacking whom is the most important fact on screen during combat. Fix
direction: stroke weight, a dash pattern, or an outline separating the line
from the art under it.

**#3 The tools are visible but unreachable while a dialog is open -- medium, a
pre-existing bug.** `.prompt-backdrop` is `position: fixed; inset: 0` at
`--z-modal` and swallows clicks aimed at the tools footer, which keeps
rendering and looks available -- exactly when the speed control is most wanted.
The mockup had no modal. `e2e/action-panel.spec.ts` works around it by
answering the mulligan first. Fix direction: lift the tools above the backdrop,
or dim them while a modal owns the screen.

**#4 The preview can pin itself to a stale card -- medium, a bug, partly
closed.** `CardPreview` renders through `AnimatePresence mode="wait"` keyed on
the hovered oid, and `hoveredOid` is only cleared by an element's own leave
handler -- a hand card hovered and then cast unmounts without firing one, so
the rail shows an earlier card and a new hover does not swap it. The commander
plinth now clears `hoveredOid` on unmount when it still owns it and `findCard`
searches the stack; `Card.tsx`, `HandFan.tsx` and `mode="wait"` are untouched
and are where the symptom lives. The blocker-list hover is asserted
structurally, not behaviourally.

**The focus ring cannot see a transform on a descendant -- low, a bug.**
`ringTargetFor` walks *ancestors* accumulating rotation and scale (the hand fan
works because its rotation is on `.hand__lift`, above the card), but the tap
rotation is on `.card__pivot` and the staged lean on `.card__actor`, below the
ring's node, so the ring is the axis-aligned envelope. Pad and keyboard only;
the `::after` rim half is fixed (it moved onto `.card__actor`). Fix direction:
a descendant walk, or the actuators publishing their held transform. Untested.

**#6 Card type and keyword lines sit on their pixel floor -- low, a trade.**
`.face__type` and `.face__kwline` measure exactly 8.5px on opponent mats at
both desktop viewports: the `max()` floor is doing the work. A four-player pod
shrinks `opponentCardScale` to 0.58 with no headroom, so the art band gives up
height instead. Fix direction: check the 3-opponent layout before shrinking
anything else; consider dropping the type line entirely at the smallest scale.

**#7 Phase step labels are abbreviated where the ribbon now has room -- low.**
The mockup reads `Begin - Declare attackers - Blockers - First strike - Damage
- End`; `STEP_SHORT` in `logic/labels.ts` reads `Combat - Attack - Block - 1st
Strike - Damage - End Cbt`. The abbreviations were chosen when the live pill
was content-sized; the ribbon is now a fixed six-column grid ~960px wide at
1600x950, so the full labels would fit.

**#8 The action panel's empty state leaves a large dead area -- low, and
deliberately larger.** `.acts__list` is `flex: 1 1 auto` with a 74px floor that
`e2e/layout.spec.ts` measures (the first thing a flex parent flattens on a
short viewport), so it fills the panel even holding one italic line. The
handheld board round made the list 392px at 1280x800 rather than 172, which is
the point of the change and means an empty list is 392px of nothing. The
honest answer, named and not built: **one region that is the stack when the
stack is not empty and the reader when it is.** The stack floats over the board
instead, which leaves this open.

**#9 The viewer's mat side column has more whitespace than the mockup's --
low, density only.** The dial and pile bars leave dead space beneath them at
1600x950, costing the lanes horizontal room.

**Also recorded as a real gap, out of scope rather than fine**: a card whose
only text is keywords (Serra Angel: `keywords: ["flying", "vigilance"]`, no
`oracle_text`) renders nothing in its foot under `variant="detail"`, which
shows the keyword chip line only when it is not showing rules. It applies
equally to the stack and the zone peek; `OpeningHand.stories.tsx` pins it so a
future fix is deliberate.
