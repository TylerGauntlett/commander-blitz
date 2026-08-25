# The game client

React 18 + TypeScript, built with Vite, animated with [`motion`](https://motion.dev)
(framer-motion), formatted and linted by Biome. Runs under `bun` or `npm`.

```bash
cd frontend
npm install && npm run dev        # http://127.0.0.1:5173
```

with the engine running alongside:

```bash
uvicorn automtg.server.app:get_app --factory --reload
```

The previous text-tile playtest client is archived verbatim at `legacy-frontend/` for
comparison. Nothing builds or imports it.

The board is themed against `mockups/05-planar-art.html`. Where the two still differ
— and which of those differences are defects rather than decisions — is tracked in
[mockup-fidelity.md](mockup-fidelity.md).

## Layout

```
frontend/src/
├── api/         client.ts, types.ts        - fetch wrapper and DTO mirrors
├── state/       uiStore.ts (zustand), useGame.ts (react-query), usePod.ts,
│                usePodSession.ts, narration.ts, useImages.ts, useCardBase.ts,
│                useZoomFit.ts
├── logic/       zoneGrouping, actionMatch, labels, stacking, cardStyle, events,
│                cardArt, cardSize, cardStackGeometry, zoomFit, zones, routes
├── motion/      springs.ts                 - every transition in the app
├── screens/     HomeRoute, PodRoute, GameRoute, DecksRoute, DeckDossierRoute,
│                NotFound                   - one per address; App.tsx is the table
├── styles/      cards.css, board.css, ui.css  (+ src/theme.css for tokens)
└── components/
    ├── game/    Table, PlayerMat, Lane, CardStack, Card, CardFace, HandFan,
    │            PlayerOrb, PhaseTrack, CombatPanel, CombatArrows, ActionBar,
    │            PromptDialog, StackPanel, CardPreview, FxLayer, EventTicker,
    │            ZonePeek, GameOverScreen
    ├── lobby/   HomeScreen, doorArt, PodLobby, PodSeat, DeckCatalog,
    │            DeckDossier, InviteDialog, CommanderCard, CardBack, ReadyTrack
    ├── screen/  Screen                     - the per-route motion wrapper
    └── menu/    DeckImport
```

Nothing under `components/` imports react-router. That is what keeps every
presentational unit test able to render bare, with no providers around it — the
wiring that needs a router is in `screens/`, and the wiring is what the routing
tests are about.

`logic/` holds every decision the client makes, as pure functions over the server's
view. That is what the unit tests cover; components stay presentational.

## Where things sit on screen

A ribbon across the top, **two** columns, and the hand under the left one.

- **Top** — the phase ribbon: five phases as pills, and only the live one expands
  into its steps. All thirteen step labels stay in the DOM regardless, which is
  both what `e2e/acceptance.spec.ts` counts and what keeps the marker's
  `layoutId` animation continuous across a phase boundary. Whose turn it is and
  who holds *priority* are two chips, because they are two facts — and the case
  that matters most, somebody else's turn and your decision, is exactly the one
  a single chip cannot say.
- **Middle** — opponents on a row that sizes to its content, then your own mat.
  Your mat's first column is your info panel (`PlayerOrb`): commander, life dial,
  mana, zone piles — on a handheld the same markup skinned as
  `mockups/handheld-board/`'s plinth. **An opponent's is an `OpponentSeat`** — a 332x96 summary of
  what they have on the battlefield, because none of an orb's controls is yours
  on somebody else's seat and a pod was three control panels for controls nobody
  could press. Card size is **solved against the space each area actually has**
  rather than fixed: see "How big a card is" below.
- **Right rail** — the card you are reading, the panel of things you can do, and
  the commit dock. **It runs the full height of the screen**, which is the single
  biggest thing about this layout: it used to stop where the hand started, 514px
  at 1280x800, of which the action list got 172.
  `mockups/handheld-board/measure.mjs` measures the same rail at 748 when it runs
  to the bottom edge instead, and the list at 363-398. Whichever surface owns a
  decision renders its action ids and the other stands down (`standDown`), so a
  prompt is never printed twice.
- **Foot** — the hand, and nothing else, **inside the board's column** rather
  than spanning the screen. That is what lets the rail reach the bottom. Your
  commander used to sit to the hand's left; it is the hero of your info panel
  now, drawn as a plinth rather than a card. See `CommandZone` and
  `docs/mockup-fidelity.md` defect #5.

**There is no left rail, at any size.** It held two things and neither earned a
permanent 232px column. The log is reference you consult rather than something
you watch, so it comes up on **View** as an overlay. The stack is urgent exactly
when it is non-empty and absent the rest of the time, so it floats over the
top-left of the board and grows down over your own panel as it deepens —
`StackPanel` already drew that pile, it simply drew it inside a rail. What the
retired column buys is 232px of board, which is most of what the foot costs by
moving inside it.

## The board is laid out the way it is played

Each mat's battlefield is two bands, and which comes first depends on whose mat it
is:

```
OPPONENT   │ LANDS                     │  ← their edge
           │ CREATURES   │ GLOBAL A/E  │
═══════════╪═════════════╪═════════════╡  ← combat is declared across here
           │ CREATURES   │ GLOBAL A/E  │
YOU        │ LANDS                     │  ← your edge, above the hand
```

Three facts, none of them cosmetic:

**Your lands are the row nearest you.** They used to be the row furthest away, which
is the opposite of how anybody arranges a table. `LANES` in `logic/zoneGrouping.ts`
is declared front to back and `PlayerMat` renders it in that order, so the array *is*
the layout.

**An opponent's mat is mirrored** (`PlayerMat`'s `mirrored` prop, set from `Table`).
Their lands sit against their own edge of the screen, which puts the two creature
bands next to each other with the table's midline between them — combat then reads
as a line rather than as a diagonal past a wall of mana.

**Creatures and the global artifacts and enchantments share the front band**, split
2:1 because that is where the cards accumulate. They stay two separate drop targets;
only the row is shared. Planeswalkers ride with the creatures, since they are what
combat is pointed at.

**The viewer's lanes are always rendered, at a full card's height, empty or not.**
That is dead space bought deliberately, and what it buys is the board holding still.
An empty lane used to collapse to a 30px strip, so playing your first creature shoved
your land row down by a whole card and killing it shoved the row back up — under the
cursor, mid-decision, on the one mat that owns every drop target. The orb's mana row
did the same a second time, several times a turn, which is why it now sits in a
reserved slot (`.orb__manaslot`) rather than appearing and vanishing with the mana.

**Opponents still drop their empty lanes**, and that asymmetry was measured rather
than assumed. Three opponents leave each compact mat about 158px of lane width
against a 51px card, so the front band's 2:1 split gives creatures room for one card
per row: an always-present, usually-empty global lane wrapped an opponent's creatures
onto a second row and pushed the viewer's board down the screen — the opposite of the
intent. That is now purely a width argument: their *lanes* have a fixed height
(`--pod-lanes-h`) and scroll inside it, so hiding an empty one no longer moves
anything. What cannot change is the spacing *within* your own mat, which is the gap a
card actually jumps across, and `e2e/layout.spec.ts` fails the run if any of your
bands drifts more than a few pixels of rounding relative to your mat over a game.

## How big a card is

Two layers, and they answer different questions.

**`logic/cardSize.ts` — proportion.** One fluid `--card-w-base` in `theme.css`, and
every zone is a *ratio* of it (`CARD_SCALE`). This replaced nine hard-coded pixel
constants written straight into inline `--card-w` styles, which is why a 2560px
display used to show exactly the same small cards a 1366px one did: an inline style
beats a `clamp()` on `:root`. **Never emit a px literal into `--card-w`** — that is
what `cardWidthVar` is for, and `tests/cardSize.test.ts` fails if it stops emitting a
`calc()`.

**`logic/zoomFit.ts` + `state/useZoomFit.ts` — absolute size.** The board, the pod and
the hand each get the largest card whose *wrapped rows still fit the space they
actually have*. The solver shelf-packs real footprints (a tapped permanent is
landscape; a stack of basics is one box; a host carries its auras), so it is exact
rather than an estimate. `CARD_SCALE.own`, `CARD_SCALE.hand` and `opponentCardScale`
are still here but they are now **ceilings the solve may not exceed**, not sizes.

Four things about it are worth knowing before touching it:

- **A fit solver reads the layout and then changes it**, so only measurements that
  cannot move are allowed as inputs: lane *width* (grid tracks, hence
  `scrollbar-gutter: stable`), never lane *height*. The hand solves before the board
  because `.table__foot` is an `auto` row taking its height out of the board's, and
  the pod's lane box is pinned so `.play`'s `fit-content(58%)` row cannot depend on
  the pod card size it is being used to solve. `useZoomFit`'s header has the full
  argument.
- **The pod's box is count-aware**, and the difference was a third of an opponent's
  card. `--pod-lanes-h` used to *be* the budget, and it is `clamp(140px, 15vh,
  220px)` — measured at 1600×950 against a **four-seat** pod where nothing fits at
  any size and the viewer deliberately wins. That is the right answer to the
  question it was asked. It was then applied at every seat count, and a compact
  two-band mat costs `2.8·cw + 36` — so 142px could not hold even the 52px floor,
  `solveBoardCardWidth` fell through its scan, and a 1v1 rendered its opponent at
  `MIN_CARD_W` next to half an empty table. `solvePodLanesHeight` takes the clamp
  as a **floor** and raises it to a share of the viewport: 0.20 of `tableH` at one
  opponent, 0.16 at two, **nothing at three or more**, capped at 320px. `Table`
  writes the answer back out as `--pod-lanes-h`, so the box CSS draws is the budget
  the cards were packed into. `share(3+) = 0` is what keeps `deckfit.spec.ts`,
  `cycle3.spec.ts`'s `rowClipped` guard and `legibility.spec.ts`'s 50.7px
  measurement byte-identical, and the shares below that are priced against
  `layout.spec.ts`'s "the zoom uses the room a big display has", which wants the
  viewer at `MAX_CARD_W` on a 2560×1278 panel with about 105px of slack to spare.
- **The pod box must be a function of the viewport alone — a stronger rule than
  "independent of the card size".** `layout.spec.ts` states it outright, and it is
  easy to break while believing you have not: the first cut of the fix above solved
  against `.play`'s *measured* height, which no card size can move, and it was still
  wrong. `.table__body`'s second row is the foot, and the foot's height moves with
  the hand — so playing a card would resize the foot, resize `.play`, resize the pod
  box, and translate the viewer's whole board, once per card played. No gate pins
  that directly: "the viewer's bands do not move" measures *inside* the mat, not the
  mat's own height. `solvePodLanesHeight` takes `tableH`, the CSS floor and a seat
  count, and its signature is the argument.
- **The board height is not monotone in card width.** A tapped permanent is shorter
  but wider, so growing the cards can push a tall card onto the next row and leave a
  short row behind, making a lane *shorter*. The solver scans downward rather than
  bisecting for exactly this reason; `tests/zoomFit.test.ts` pins the counter-example
  so nobody re-optimises it into a binary search.
- **The orb columns, not the cards, own the vertical space.** At 1600×950 your
  `.mat__side` is 330px against 299px of lanes, and the compact orb is 297px — 627 of
  the 649px play area is furniture, and the mana row grows as lands are played. That
  is why the zoom gains 36% at 2560×1278 and about 2% at 1600×950. Making that column
  fluid is the change that would unlock the common viewport; see `docs/roadmap.md`.

Zoom changes animate off one `--card-w` transition. `--card-w` is a registered
`@property` of type `<length>`, so interpolating it re-resolves every declaration that
reads it — the card box, the border, all five `--fs-*`, `--pip`, both lane
`min-height`s. Nothing had to be rewritten as a `calc()` to become animatable.

`e2e` can pin the whole system with `startGame(page, { zoomLock: true })`, which is
also the path jsdom takes, so component tests render the geometry they were written
against.

Auras and Equipment are not loose cards. `attachmentsFor` pulls anything with an
`attached_to` on the same mat out of the lanes, and `CardStack` draws it tucked under
its host, offset far enough that its title bar stays readable and clickable. A host
is therefore never merged into a stack — see the note in `logic/stacking.ts`.

The one thing the reference layout has that this does not is the zone piles beside
the lands. They stay in the orb, where they already have a labelled home: graveyard
and exile are consulted rarely enough that the board is a better use of the width.

## Dragging is a shortcut, not a rule

Still the most important thing about this client:

> **A gesture selects a legal action. It is never a rules operation.**

The server sends `LegalActionDTO`s with opaque ids and the client echoes one back. It
never reconstructs an action, so desync is structurally impossible. Three input paths
all funnel into the same `act(id)`:

1. **Drag** a hand card onto a lane. `Card`'s drag-end hit-tests `data-dropzone` under
   the pointer; if `canDropOnLane` says no, the card springs back and nothing is sent.
2. **Click** a card, then click its target. `TargetLayer` highlighting comes from the
   server's own `action.targets`, so the client never decides what is targetable.
3. **The action bar**, which always lists every legal action as a button.

Path 3 is load-bearing, not a fallback: it is what makes the game keyboard-reachable
and what makes the Playwright specs writable.

**A click can answer more than one question.** Picking a target settles only the
target. Into the Roil aimed at a creature is still two legal actions — kicked
and unkicked — and `Table` used to take the first, which `legality` emits
unkicked, so the kicked cast could not be reached by any gesture at all. Path 2
now *narrows* the selection to whatever still matches (`uiStore.narrowTargeting`)
and lets path 3 ask the rest. The foot says "Pick how, in the panel" once the
target half is settled.

That is also why the foot no longer renders the remaining actions itself. It
used to draw a `choice-list` of `data-action-id` buttons for exactly this case,
while `ActionPanel` drew the same ids — two controls, one id, which is what the
panel's invariant forbids. It escaped CI only because no shipped card could
reach the branch; manual mana reaches it immediately.

**One exception to "every legal action is a button": `choose_x`.** `ask_x`
offers every value from 0 to whatever the board can pay for, so a Fireball on
ten mana is eleven actions differing by a number. The panel draws a stepper and
only the *selected* value carries an id. "Exactly once" still holds — nothing is
duplicated, and there is always at least one button, which is what
`e2e/full-game.spec.ts` actually depends on.

**Two settings live in the tool strip**, both words rather than glyphs because
both change how the game plays: `Auto-pass / Full control`, and `Auto mana /
Manual mana`. The second decides whether mana abilities are actions at all.

Keyboard: `Space` pass, `Enter` confirm, `Esc` cancel targeting, `1-9` play the nth card
in hand, `U` undo. Any key skips the narration while it is playing.

## Cards look like cards

**The illustration is the card.** It fills the frame, and the text sits on graded
scrims at the top and bottom: head (type glyph, name, then the mana cost on a row
of its own) and foot (type line, `oracle_text` where there is room, then keywords,
counters and P/T). This is direction D, "Art Bleed", of `mockups/cards/index.html`.
Everything is still proportioned 5:7 except the enlarged preview card.

The art is served by this application, never by a third party -- the build script
downloads each crop once and the API serves the bytes, so the board renders with
the network unplugged. Five cards in `data/cards/` are original designs with no
printing anywhere, and those get a deliberate "no art" plate rather than a broken
image. See [card-catalog.md](card-catalog.md).

**Card type is no longer a colour, and that was deliberate.** It used to be: an
eight-step luminance ladder on the card stock plus a matching ring, because a type
line renders at 5.6px on a pod board. A full-bleed illustration does that job
better and does it *per card* rather than per category -- twelve Forests are one
recognisable picture rather than twelve of "the tan ones". What carries type at
pod size now is the glyph and the type line. The full reasoning
and the list of tests that changed is in
[mockup-fidelity.md](mockup-fidelity.md) -- read it before re-adding a type tint.

**Colour identity is a different fact and it keeps the frame**: the border, and the
gradient the art sits on, which on the ~4% of cards with no printing is the whole
card. A land's frame narrows to the colour it taps for and its produced-mana
symbols go large and centre-frame, so a lane of lands reads without reading a name.

**Mana symbols are the real ones.** Scryfall publishes every card symbol as SVG
from an open endpoint; `mockups/cards/fetch_symbols.py` pulls them and they are
vendored into `frontend/public/symbols/`, under the same architecture as the card
art — fetch once, store in the repo, skip on re-run, nothing running anywhere at
render time. `ManaSymbol` draws them, and every surface that shows mana notation
goes through it: the cost row, rules text and action labels (`SymbolText`), the
commander plinth, the action panel and the deck picker. They were a letter on a
coloured disc, which is a mark nobody who plays the game recognises.

A code with no SVG falls back to that disc rather than a broken image. Nothing in
a real game reaches it — the engine rejects hybrid and phyrexian costs at load
time and generic never passes 16 — and `e2e/cycle3.spec.ts` fails the run if
anything does, which is the signal that `fetch_symbols.py`'s `WANTED` has fallen
behind.

The player orb's mana panel used to be the exception — 9px discs coloured by
`--mana-*`, on the argument that showing mana you *have* is a different idea from
showing a cost you *owe* and would read worse for borrowing the same mark. That
was wrong twice over: the mark a player recognises is the mark, whichever
direction the mana is flowing, and it left one surface in the client still using
the letter-on-a-disc the rest of it had abandoned.

What the discs really bought was **repetition** — at 9px a mark per mana is cheap,
and at symbol width ten untapped lands wrapped to three rows in a 190px column.
So the panel counts instead of repeating: one chip per *kind* of mana, `4{G}
2{U}`, which is also how a player says it out loud. `manaGroups` in `logic/mana.ts`
does the collapsing; `manaRow` still produces a pip per mana underneath it,
because the forecast is per-source.

Two cases the count has to carry that a repeated mark carried for free:

- **A choice of two** is the published hybrid — a land reading "Add {G} or {U}" is
  one `{G/U}`, which is exactly "one mana, either colour". Three or more has no
  printed mark and falls back to the five-way split disc (`.mana-grp__any`), not
  to `pip--text`: reaching the text fallback means a symbol is *missing*, and
  `e2e/cycle3.spec.ts` fails the run when anything does.
- **The spend forecast** was pips hollowing out one by one. A chip shows what would
  be left beside a faint `−n` for what goes, so `2 −2` answers "and what will that
  leave me with" the way the hollow pips did. Which sources those are is still the
  engine's solved payment and never arithmetic here.

The mana panel is **permanent**. It was a conditional row in `orb__body`'s
`space-between` slack, so it floated in the middle of the column and re-spaced
the whole interior each time it appeared or emptied — several times a turn. It
sits on a plate with the zone piles in `.orb__foot` now, which puts all the
slack in one gap under the plinth. An empty mana panel says `—`.

**Commander damage is not on this panel.** It used to be a second plate here —
one chip per opposing seat with a meter of its progress toward 21 — which
answered "how close is each of them to killing me" and nothing about the other
direction, at the cost of the loudest object in the column. Both directions are
two small arrows on each opponent's own life gauge now (`OpponentSeat`, and
`docs/mockup-fidelity.md` for the whole argument).

On a handheld this whole column is re-skinned to `mockups/handheld-board/`'s
plinth: a 148x128 portrait rather than a 2:1 banner, a 64px conic life ring
rather than a 52px brass seal, and the five zones as coloured chips rather than
leaf stacks. Markup is identical either way — it is CSS in `handheld.css` and
nothing else.

Text over an unknown illustration is the one thing here that can fail silently, so
it is guarded by number: `tests/palette.test.ts` asserts both scrims are gradients
whose opaque ends clear a darkness floor, and `e2e/legibility.spec.ts` asserts the
same against the *rendered* board, where a `theme.css` override would show up and a
CSS parse would not.

Every dimension is a ratio of `--card-w`, which the containing zone sets. One component
therefore renders at 82px on an opponent's board, 146px in hand and 236px in the preview
panel with no separate styles.

`Card` has **two motion layers, and the split is not cosmetic**:

- **outer** — `layoutId`, `drag`, hover lift. Owns *position*.
- **inner** — the 90° tap rotation. Owns *orientation*.

Both would otherwise write `transform` on the same node and the last render would win:
a tapped creature would untap itself the moment you picked it up.

`layoutId` is keyed on the object id, which **the engine preserves across zone changes**.
That single fact is what makes a card fly from hand to stack to battlefield rather than
vanishing and reappearing. `StaticCard` exists for previews and dialogs, where a second
`layoutId` for the same oid would make framer animate between the two.

## Identical permanents stack

`logic/stacking.ts` collapses interchangeable permanents into one pile with a `×N` badge.
The rule that matters: **a stack hides its members**, so `stackKey` includes everything
that makes two permanents behave differently — tapped, damage, counters, summoning
sickness, attacking, blocking, attachment, commander-ness, controller. An untapped
Forest never hides behind a tapped one.

`splitActionable` then pulls out any member a legal action names, so stacking can never
bury a choice. Every member stays mounted even when hidden behind the top card —
unmounting on hover would destroy each card's `layoutId` identity.

## The first decision of every game has its own screen

`PromptDialog` used to draw the mulligan: a centred rectangle, an 18px title, and two
identical grey `.opt` buttons over a hand at `--card-w-base` — **73.6px** on a Deck, where
`.face`'s rules text resolves to 8.5px and is dropped. `ui.css:934-951` is the admission
that this was wrong. That backdrop is a *gradient* rather than a flat dim, and its comment
says why: *"a flat dim over the whole viewport hid the one thing the player has to look
at"*. A workaround for a modal that should not have been in front of the hand.

`OpeningHand` is `mockups/mulligan/01-the-deal.html` ported. The hand IS the screen —
seven cards at the size their own rules text needs — and the answers are face buttons.

**296px is the number the whole thing is built on.** `mockups/mulligan/probe.mjs`
binary-searches a real card in a real browser for the narrowest width at which it can
print its own name, cost, type line and rules at the 16px floor. Seven of those laid flush
is 2072px against a 1280px panel, so a hand you can read *all at once* is not available at
any layout. One card at a time is, and the rest follows from that.

**Nothing moves when the selection does.** `logic/openingHand.ts` computes the arch once
per resize and takes no selected index at all — moving the ring touches `z-index`, one
attribute and one custom property. The mockup's second pass grew the selected card and
closed the others around it, which meant re-centring the row on every press: the one thing
holding still was the card you were trying to read. `tests/openingHand.test.ts` is what
stops that coming back, because a screenshot cannot show it.

**Only the card you are on prints its rules.** Seven open rules boxes at 144px of pitch is
six columns of type sliced down the middle by the card in front. The box closes on the
others and the illustration takes the space, so the card is the same size either way.
`styles/opening.css` also un-does two of `handheld.css`'s blanket rules for this surface
only — the rules box takes its content's height rather than fading, and the type line
comes back — on the same grounds the existing exemptions for `.opt--card` and
`.peek__slot` are made: these are the surfaces whose whole job is reading one card, and
this one has 296px to do it in.

**It scales, where the mockup does not.** `stageUnit` is `stageScale` (the door's, exactly
1.0 at 1280x800) capped by what the stage's *width* can hold, so a tall narrow window
shrinks the arch instead of running it off both sides. Type does not follow it down: every
size on the sheet is `max(16px, ...)`.

**Both halves of a London mulligan, in one room.** The engine asks twice — keep or
mulligan, then put N on the bottom — and those used to look nothing like each other,
because the first carries no object refs and the second does. `mulliganPhase` routes both
here, and it reads the `purpose` tag the engine stamps on the bottoming decision rather
than pattern-matching its prompt. `engine/serialize.py` now also sends `mulligans_taken`,
which had lived on `Player` since London mulligans landed and reached no client; it is the
lamps.

**`A` keeps the hand from a card.** `A` is `el.click()` on the focused stop app-wide and
that is not overridable, so a card's own click stays "select" — a mouse must never commit
a game by clicking a card it only wanted to read. The surface binds `A` scoped to card
stops, and stands aside when the ring is on the Keep plate so the answer is not given
twice. `B` mulligans. `verbs.ts` has a branch for both, because `b: "Back"` is true on a
board and false here.

Two surfaces own decisions now, so `ownsDecision` is what `ActionPanel` reads to stand
down — a wider question than `isModalDecision`, which the dialog still uses to decide
whether to open. Getting that split wrong renders `keep` and `mulligan` twice.

## A decision too long to draw as buttons

`PromptDialog` draws one button per legal action, which is right for a modal
spell or a sacrifice — and wrong for `choose_type`, where the engine asks "choose a
creature type" by listing every subtype in the loaded pool: 199 in this repo's decks, up
to 400 (`MAX_TYPE_CHOICES`) in a full one. That prompt was a wall of buttons nobody could
read with a mouse, and it was strictly *worse* with a controller: the ring focuses with
`preventScroll` and `candidatesIn` drops any stop an ancestor has clipped, so every option
past the fold of the scroller was unreachable rather than merely awkward.

Above `COMBO_MIN` (12) options, and only when no option carries a card face,
`ChoiceCombo` takes over: a filter field over one vertical A–Z list, with a Choose button
in a rail beside it. A card-bearing prompt keeps its grid of faces however long it is —
choosing what to sacrifice should look like looking at your board, and a face is not a
combobox row.

Three things about it are load-bearing:

- **The rows select; only the Choose button acts.** It is the one control in the dialog
  carrying `data-action-id`, bound to whatever row is highlighted, so the panel's
  invariant reads 1 action rather than 199 — and `full-game.spec.ts`, which drives a whole
  game by clicking legal actions, answers the prompt with the first type rather than
  stalling on a decision with no clickable surface. The first visible row starts
  highlighted for exactly that reason.
- **`onFocus` on a row is what highlights it.** `cursor.stamp` focuses the stop the ring
  lands on, so walking the ring down the list moves the highlight and relabels the button
  — no second pad listener to keep in step with `useCursorNav`. The rail sits to the
  *right* of the list so a right press reaches Choose from any row; underneath, it would
  be four hundred rows away.
- **The fold always cuts a row in half.** `.combo__list` is sized at eight and a half rows
  of *pitch* (row + gap, plus its padding), because a whole number of rows leaves the next
  one clipped to nothing — and a stop clipped to nothing is a wall the ring cannot cross
  with three hundred options still beneath it. `ChooseTypeOnPad` measures the straddle
  rather than trusting the arithmetic.

Typing filters (`logic/promptFilter.ts`: fold case and diacritics, AND across terms, rank
exact → prefix → substring so `Enter` commits Elf and not Elf Warrior). The field is not
autofocused in pad mode: a focused `<input>` deadens the arrow keys that stand in for the
d-pad, since both `pad.ts:isTyping` and `Table.tsx` bail while one holds focus.

## The lobby

Three screens before the table, ported from `mockups/flow/02-face-up.html` —
except the front door, which is `mockups/door/01-the-hand.html`:

| File | What it is |
|---|---|
| `components/lobby/HomeScreen.tsx` | The front door: a menu of three cards — Settings, Play, Join |
| `components/lobby/doorArt.tsx` | The door's drawn hall, card frame and three illustrations |
| `logic/doorRow.ts` | The row's arithmetic: one number in, three poses out |
| `components/lobby/PodLobby.tsx` | Four seats as a hand of cards, and the rail under them |
| `components/lobby/PodSeat.tsx` | One seat: the card, the stamp, the plate, the per-kind actions |
| `components/lobby/DeckCatalog.tsx` | Full-screen takeover: search, colour filter, source, sort, the import row |
| `components/lobby/DeckDossier.tsx` | The right-hand overlay: ratings, strategy, signature cards, curve |
| `components/lobby/InviteDialog.tsx` | The pod code and a link, each with its own copy confirmation |
| `components/lobby/CardBack.tsx` | One picture for "you do not get to know this yet" |
| `components/lobby/ReadyTrack.tsx` | Four segments, filling as each card turns face up |

The mockup's central idea is that **setting up a game is not configuration, it is four
people committing one after another** — so a commitment is drawn as a card turning over,
and locking in is a wax stamp rather than a checkbox. The asymmetry is deliberate:
`.lock--on` (unlock) is quieter than `.lock` (lock in), because committing should feel
heavier than reconsidering when three other people are waiting on it.

**A face-down card is one object for three different facts.** An empty chair, a player who
has not chosen, and a player whose list is sealed are all "you do not get to know this
yet". The menu round drew those as a dashed box, a hatch plate and an italic caption; one
object says it better and says it once.

**The card face is the real component.** `CommanderCard` adapts `GET /api/cards/{id}` into
the `CardView` shape `CardFace` takes, so the commander you turn over in the lobby is the
same object the table will put in your preview rail. The mockup carries its own port of
`cards.css` because it has no components; `styles/lobby.css` deliberately does not.

`logic/lobby.ts` holds the predicates, so they can be tested without a DOM. The pair worth
being careful about is `canStart` and `whyNot`: they answer the same question, and a screen
whose button and explanation disagree is worse than one with neither. `tests/lobby.test.ts`
asserts on both together in every case.

### Hearing about somebody else's move

`state/usePod.ts` is a **self-rescheduling long poll**. It asks for the pod with the
version it last saw; the server blocks until that number moves or ~25 s elapse; the moment
the answer lands it asks again. A timed-out poll is a 200 with the same version, which is
indistinguishable from a slow one. See
[adr/0007-versioned-long-polling.md](adr/0007-versioned-long-polling.md).

The same mechanism reaches the table. `useGame` now has two loops and picks between them
by *who* it is waiting for, using `human_seats` from the state response:

- **An AI seat** — the pump, unchanged. `?ai_steps=1` and one decision at a time, so its
  turn is watchable.
- **Another person** — `?since_version=`, and block. There is nothing to pump; the server
  is not going to move that seat, a person is. Pumping here would be a busy-wait against
  somebody's thinking time.

### Identity

A `player_token`, issued once at create or join, sent as `X-Player-Token`. `api/client.ts`
attaches it in `request()`, so no call site had to change and none can forget.

It lives in `sessionStorage` keyed by pod code. **Session, not local**, deliberately: two
tabs on one machine are then two different players, which is exactly how this gets tested
by hand — and how `e2e/pod.spec.ts` drives two browser contexts against one server.

That is also the whole reconnect story. A refreshed tab hands the token back, the server
returns the seat it already had, and nothing else happens.

Your *name* is a different thing and lives somewhere else: on your own seat plate, as
the only editable field on any plate. The front door briefly asked for one and should
not have — a name is something you say to a table, and at the door there is not one
yet. `SeatName` in `PodSeat.tsx` keeps a local draft and commits on blur and Enter: the
pod re-renders on every long-poll return, so a controlled field would reset itself
mid-word, and a PATCH per keystroke would bump the pod's version for every letter and
wake three other browsers out of their polls to be told you are still typing.

### Four plates, one row

A plate is read *across* as much as down — whose seat, which deck, what colours — and
that only holds while the same line is at the same height in all four slots. The name
field above is exactly what broke it: your chair carries a **field** where the other
three carry a label, and a field is the taller box. `.plate` is a grid, so every row
under it inherited the difference and the deck names, the mana and the buttons all
stepped down on your seat alone — 6px on the desktop plate, 23px on the handheld one,
where the hit floor raises every control to 44px.

So the two rows whose content differs by seat are **given** a height rather than taking
one from whatever is in them: `--name-h` and `--meta-h` in `lobby.css`, restated once
for the handheld floor. `PodLobby.stories.tsx` measures the row tops across all four
slots at both sizes.

The same floor caught the details glyph. `min-height: 44px` with no `min-width` turned a
17px circle into a 17x44 pill, and giving it the other half is no better — a 44px disc
in a row of 14px mana pips is the loudest object on the plate. **A hit floor is a target,
not a size**: the circle is drawn on `.ibtn::before` at 22px and only the box is 44.

### One card, two boxes

`cards.css`'s `.card--big` is the **preview rail's** card — width-driven, `height:
100%`, and it only holds a shape because `.rail--right .preview` gives it a fixed
frame. The lobby has no such container, so the same rule collapses to content sizing
and every seat card comes out as tall as its own rules text.

So `CommanderCard` puts a `podcard` class on every card it renders, and `lobby.css`
re-boxes it to `var(--card-w)` × 1.4 — `.card`'s own box. A face-up seat and a
face-down `.back` have to be the same rectangle, or the row stops reading as a hand
and `.podhand__felt` no longer lands under the cards' shoulders. The type scale comes
back as ratios of `--card-w` at the same time, because `.face--big` pins `--card-w:
150px` *on the face*, where no ancestor can beat it, and a 296px card was otherwise
drawing 150px chrome. See `docs/mockup-fidelity.md`.

## Watching the opponents

`GameSession.drive_ai()` normally runs every AI seat until a human must decide, so one
response can contain three whole turns and the board simply snaps. The client asks for
`?ai_steps=1` instead, which bounds the server to a single AI decision per call, and
pumps: when a response comes back with no legal actions and the game is not over, the
opponents still owe decisions.

`logic/events.ts` turns each batch of events into timed **beats** — floating damage
numerals anchored to the struck permanent, life tickers, spotlights on the card being
cast, turn banners, screen shake, cards leaving the battlefield. `state/narration.ts`
runs the queue.

A click while the queue is draining means "get on with it" **and** the thing that was
clicked. It used to mean only the first — `gateInput` skipped the queue and threw the
gesture away — so for a second or two after every action the board ignored you, which
is what made playing it feel like it needed spamming. Only a genuine in-flight request
gates input now. Skip empties the queue *and* puts the board back at rest, because the
physical effects below run on their own clocks past the end of the beat that started
them.

### Effects are concurrent, not queued

The queue plays one beat at a time and holds for its `hold`, which is the right shape
for a turn banner and the wrong shape for a fight. A three-attacker exchange used to be
nine consecutive beats — a 520ms banner, three 160ms flashes, a 420ms pause, then a
340ms numeral per hit. **3.3 seconds**, during which the board was frozen, and in which
nothing moved: the creatures involved sat perfectly still the whole time.

`Beat.fx` is a list of `TimedFx`, each stamped with an `at` offset and played
*concurrently* inside one beat. `at` is deliberately not bounded by `hold` — effects
outlive the queue, exactly as a floating numeral already did, which is what makes a turn
read as continuous rather than as a sequence of slides.

That is the whole reason the board can get more physical without getting slower. Every
golden batch in `tests/timing.test.ts` is now faster than it was:

| batch | before | after |
|---|---|---|
| three-attacker exchange | 3300ms | 1954ms |
| six-permanent wrath | 1700ms | 1520ms |
| a quiet ramp turn | 3530ms | 2840ms |
| nine Grapeshot copies | 5540ms | 2180ms |

`tests/timing.test.ts` is the guardrail rather than the promise: it asserts against both
the pre-work numbers and the current ones, so drifting a hundred milliseconds back at a
time fails a test instead of slowly rotting.

### Three effect primitives

**`fx/actuators.ts` — the cards themselves move.** A registry of imperative handles keyed
by oid; `Card` registers one on mount. `lunge`, `recoil`, `shudder`, `pulse`. Nothing here
renders: they write Motion values directly, so a four-way exchange drives eight cards at
sixty frames a second without the reconciler hearing about it. `Card` grew a *third*
motion layer for this — outer owns position, `.card__actor` owns transient force, the
pivot owns the tap rotation — for the same reason the first two were split.

**`fx/particles.ts` + `ParticleLayer.tsx` — explosions.** A pooled, capped, pure
simulation drawn to one canvas. Pure because an explosion is a physics question and every
part of it is answerable by stepping the field, with no rendering context in the test.
Presets in `fx/presets.ts`: `impact`, `explode`, `shatter`, `dissolve`, `dust`, `motes`,
`heal`, coloured from the theme's own signal tokens. `burst()` is importable from
anywhere, because an effect is thrown from wherever the thing happened.

At the cap, new emissions are **dropped rather than the pool grown** — a capped effect
that thins out keeps its frame rate, an uncapped one turns into a slideshow at exactly
the moment the game is most dramatic.

**`fx/scheduler.ts` — one frame loop.** There were two before (screen shake, the combat
arrow settle burst) and this would have made four. It does not run when nothing is
subscribed, and a ticker that returns `false` is dropped, so no effect has to remember to
unsubscribe itself.

`useScreenShake` writes Motion values through that loop. It used to call `setState` every
frame, re-rendering the whole board subtree sixty times a second for the duration of every
shake — at precisely the busiest moment — and each offset had to wait for a React commit
to reach the DOM, which is why it read as mush rather than as an impact.

### Combat is a collision

`logic/choreography.ts` collapses each combat run into two beats. **Declare**: attackers
surge toward the player they declared against, staggered so a wide board reads as a line
advancing; blockers move to intercept. **Strike**: everything lunges at 0ms, everything
connects at 140ms — sparks at each point of contact, numerals thrown off *those* points
rather than off the cards, defenders knocked backwards, the screen kicked in proportion to
what got through.

Pairing needs no engine change: every combat `damage_dealt` already carries `source` and
either `oid` or `to: "player"`, and that *is* the pairing.

Two constraints worth keeping:

- **Only the attacking side lunges.** A blocker in a trade both deals and takes damage, so
  it would be told to lunge *and* to recoil — and an actuator cancels whatever the card was
  already doing, so the recoil would fire at contact and snap the card back from full
  extension. One side moves; the other gets moved.
- **A hit lands at `between`, not on either card.** Resolved in `FxLayer` when the beat
  plays, because both cards may still be mid-flight from a layout animation and there is no
  earlier moment at which the point they meet is knowable.

Non-combat damage collapses the same way, which is why nine Grapeshot copies cost 520ms
instead of three seconds of the board counting to one, nine times.

### Reduced motion

`App` passes `reducedMotion="user"` to `MotionConfig` — Motion's default is `never`, so
the app ignored the setting entirely before. Particles, actuators and shake cannot read
React context, so `fx/reducedMotion.ts` is the channel they use instead. What is dropped
is "how it felt"; what survives is "what happened" — numerals, captions, flashes, the log.

Storybook sets the override alongside its `MotionConfig`, and has to: headless Chromium
reports `prefers-reduced-motion: reduce`, so without it every particle story would render
an empty canvas.

### Cards leaving the battlefield

Permanents used to simply stop being drawn. There was a `dies` beat carrying a `toll`
and a danger flash, and **it never once drew anything**: `FxLayer` resolves anchors by
looking up `[data-oid]` in the live DOM when the beat plays, and a card being destroyed
is by definition a card the board has stopped rendering. `useGame.absorb` commits the
new state and *then* pushes the beats, so the element is always already gone.

So a departure is a **ghost**: the card redrawn over the top from its last known box,
held long enough to read a caption saying why it left, then dropped into its pile.

**Why not `AnimatePresence` on the lane**, which would be the idiomatic answer. The
exit would fire at the wrong time and it cannot be fixed locally — React commits the
new battlefield the instant the response lands, while the queue may still be on a
spotlight from three beats ago, so the card would fly to the graveyard before the
narration said what killed it. Syncing them means rendering a *lagged* battlefield,
which contradicts "the engine is authoritative, no optimistic updates" and desyncs
every `data-oid` anchor, drop target and legality check in the app. Three smaller
reasons: `CardStack` is an in-flow flex item, so a deferred unmount holds its slot and
the lane reflows *after* the animation rather than during it; `narration.skip()`
cancels an overlay in one line and cannot cancel a framer exit mid-layout; and a dying
commander goes to the command zone, which *does* render a card, so a deferred
`layoutId` would collide — the exact bug `Card.tsx`'s `StaticCard` comment describes.

The pieces:

- **`logic/cardRects.ts`** — oid → last known viewport box. `Card` posts its own on
  unmount, in a `useLayoutEffect` **cleanup with empty deps**: React runs that cleanup
  before it detaches the node, which is the whole mechanism. Cleanup-only rather than
  also-on-commit because measuring every card on every render is ~40 forced synchronous
  reflows per server response, continuously, to refresh a number one card per departure
  reads. Zero-sized rects are rejected, which is what makes jsdom unmounts harmless.
- **`Beat.exits`** — *plural*. A wrath emits one `zone_change` per permanent and a beat
  each would stall the board for six seconds, so `beatsFor` groups each **consecutive
  run** into one beat and `FxLayer` staggers the ghosts inside it. Consecutive, not
  global: "death, trigger, death" stays two beats or the second death lands on screen
  before the trigger that caused it. `Beat.hold` is sublinear — 420ms for one, capped at
  820ms for a wipe — and the ghosts keep flying after the queue has moved on.
- **`CardGhost`** — presentational; it is handed two points and a caption. Renders
  `CardFace` directly, not `StaticCard`, whose own `initial`/`animate` fades it *in* on
  mount. Graveyard darkens, exile bleaches and glows, a bounce keeps its colour: whether
  a creature can be recurred is the question a player is asking as it goes.
- **Destination comes from `data.to`, never from the cause** — see `docs/engine-rules.md`.
- **Face resolution is `findCard` by oid, then `findCardByDefId`, then a name plate.**
  The middle step is load-bearing: **tokens cease to exist** on the way out, so they are
  in no zone by the time the beat plays, and token deaths are a large share of every
  Commander game.
- **A card with no recorded position draws nothing.** Deliberate — the alternative is
  inventing one, and the board's centre would put an opponent's creature in the middle
  of the viewer's own board on its way out.
- **How it leaves is branched on `cause` and `to`.** Both have been on `ExitFx` since
  ghosts were built and until now only picked a caption and a tint, so a creature burned
  down, a creature sacrificed and a creature exiled all performed the same polite little
  arc. Destroyed is thrown out of its slot with an `explode` burst; sacrificed collapses
  inward; exiled rises and comes apart into `dissolve` motes; countered shatters. A
  **bounce gets nothing** on purpose — it is the one departure that is not a loss, and a
  burst would make returning a creature to hand look like losing it.

The reason outlives the animation in two places: `describeEvent`'s `zone_change` case
puts the same sentence in the Log permanently, and `logic/removals.ts` folds the log
into oid → phrase for the notes under each card in the graveyard/exile modal.

`zone_change` narrates **only when `from === "battlefield"`**, which is doing two jobs:
without it every draw, mill, discard and resolution earns a second log line, and a
library-origin zone change carries a card id to every seat, so narrating one would put
an opponent's tutor target in the log.

There was a 0.5x / 1x / instant speed control beside it and it is gone. It took a
third of the tool strip's width on a fixed 304px rail, which is what pushed the quit
button off the end — and a per-player animation speed is a confusing thing to offer in
a game other people are waiting on, since it changes only *your* playback while the
board moves on at everyone else's. The value still exists, still read from storage so
`e2e/helpers.ts` can force `instant`; there is simply no way to set it from inside the
game.

The pump waits for the queue, so the animation of one decision finishes before the next
is requested. A stall guard stops the loop if the engine ever fails to progress.

## State

- **Server state** — react-query. The engine is authoritative and every mutation returns
  the new state, so there are no optimistic updates. There is still no *background
  polling*: the two loops are the AI pump and the long poll above, and both only run while
  the client is genuinely waiting for somebody.
- **Routing** — react-router v7, declarative. See [The URL](#the-url) below.
- **UI state** — zustand: selection, hover, targeting, staged combat, the open stack, the
  zone modal, the error banner. None of it reaches the server except as
  an action id.

## The URL

Every screen has an address, and they are shaped like the API resources behind them —
`/pods/:code` beside `/api/pods/{code}` — so there is one naming rule here rather than
two that disagree by an `s`.

| Path | Screen |
|---|---|
| `/` | the front door. `?join=CODE` prefills the code field *and opens the hold it lives in* |
| `/pods/:code` | the lobby, when this tab holds a token for that pod |
| `/games/:gameId` | "Dealing…" until the seat resolves, then the table |
| `/decks` | the catalogue, browsing for nobody |
| `/decks/:deckId` | a dossier over it — a *nested* route, so the catalogue stays mounted and its filters survive |
| anything else | a 404 screen. `/pod/GYRE-8412` is one letter from a real invite link, and a silent redirect home reads as "your invite was rejected" |

`App.tsx` is the route table and nothing else; each screen's wiring lives in `screens/`.
`logic/routes.ts` holds the path builders and `screenKey`, which is what `AnimatePresence`
swaps on — it names the *screen*, not the path, which is why both `/decks` paths share one.

**The URL carries the place; `sessionStorage` carries the identity.** A link gets pasted
into a group chat, so arriving at one must not be what grants a seat. `usePodSession`
derives a `PodSession` from the two: `/pods/CODE` plus a stored `automtg.pod.<CODE>`
token. A tab with no token is redirected to `/?join=CODE`, the join flow that already
existed — one click, not none.

A table is keyed by game id but identity is keyed by pod code, so a second key,
`automtg.game.<id>` → pod code, is written the moment a client learns the game id. That
is what lets a reload at `/games/:id` find its own token. **Reloading at the table and
coming back to your seat is new** — before, a refresh mid-game dropped you at the door.

`setPlayerToken` is called during *render* in `usePodSession`, not in an effect. `usePod`
and `useGame` fire their first request from an effect in a child, and a child's effect
runs before its parent's — a token armed in an effect arrives one round trip late, so
the opening request of every deep link would go out unauthenticated.

**One-way transitions `replace` rather than push**: the deal, leaving a pod, quitting a
table. This is the answer to the objection the no-router design was built on. A pod that
has dealt is `in_game` and its lobby cannot be re-entered, so that history entry stops
existing. After a full session the stack is `["/", "/games/G"]` — Back from the table
lands on the front door, never on a dead lobby. Browsing pushes, because browsing is what
Back is for.

Back from a lobby to `/` leaves your chair held on the server, exactly as closing the tab
does; returning to `/pods/CODE` recovers it. "Leave the pod" is still the way to free one.

**Deep links need a host that rewrites unknown paths to `index.html`.** Vite does it in
`dev` and `preview`; `create_app(serve_client=True)` — which is what `get_app()` uses —
serves `frontend/dist` with a catch-all for a real deployment. Any other static host
needs the rewrite configured or every address but `/` will 404.

## Two contract gotchas

Both are handled once, in `logic/labels.ts`, and should never leak further:

- `step` arrives UPPERCASE (`"DECLARE_ATTACKERS"`) while `phase` in the same payload is
  lowercase (`"precombat_main"`).
- `commander_tax` and `commander_damage_taken` have **string** keys in JSON.

Also: events carry the snake_case card id, not the printed name. `useGame` harvests a
`card_id -> name` map from every zone it sees so the log reads "Sol Ring", not
"sol_ring"; `prettyCardName` is the fallback.

## Dev server binds IPv4 explicitly

`vite.config.ts` pins `host: "127.0.0.1"`. Vite's default is `"localhost"`, which Node 17+
resolves to `::1` and binds IPv6-only — so Playwright's health check, curl, and the
engine's CORS origin list all get connection refused against a server that is plainly
running.

## Testing

```bash
npm test                 # vitest: pure logic + components, in jsdom
npm run test:stories     # vitest: every story, in a real Chromium
npm run test:all         # both projects
npm run storybook        # the browsable version, port 6006
npm run build            # tsc --noEmit && vite build
npm run lint             # biome check .
npx playwright test      # end-to-end against the real engine
npx playwright test e2e/pod.spec.ts   # two browser contexts, one server
```

374 unit and component tests: lane assignment and band order, attachment resolution,
seat rotation, stat and counter rendering, mana pip splitting, action matching, target
disambiguation, stack keying and splitting, event-to-beat mapping, card-type tones and
glyphs, the mana row and the unplayable-card hint, and — via `@testing-library/react` —
the card face, the action bar, the player mat and every decision kind the prompt dialog
has to cover.

`tests/playerMat.test.tsx` carries more weight than most: the tucked-attachment path is
real and unit-tested, but **neither shipped precon contains an Aura or an Equipment**, so
no game and no e2e spec can currently reach it. Until the card catalogue grows (see
[roadmap.md](roadmap.md), "All Card Support"), that file and
`PlayerMat.stories.tsx`'s `WithAttachments` are its only coverage.

### Storybook

Every component in `game/`, `lobby/` and `menu/` has stories, and they run as tests in
a real Chromium via `@storybook/addon-vitest` — a second vitest project alongside the
jsdom one, so `npm test` still means what it always meant.

The reason for a browser rather than jsdom is the reason most of this document exists:
the board's measurements come out of the cascade. jsdom has no `ResizeObserver`, does
not implement `@property`, and returns zeros from every `getBoundingClientRect`, so
`CombatArrows`, `HandFan`'s slot arithmetic, `CardStack`'s fan and `FxLayer`'s anchors
were previously reachable only by an e2e run against a live engine. A story reaches
the same position from a fixture in milliseconds.

The harness lives in `.storybook/preview.tsx` and handles four things once, each of
which a component of this app needs before it renders honestly on its own: the global
stylesheets exist, the zustand store is pristine, motion behaves, and — the one that
matters most — the component is **where the app puts it**.

### Mounts

A story that draws a component bare, or in a generic full-height box, is not testing the
component; it is testing a different design wearing the same class names. `PlayerOrb`
declares no width at all, and in the game it is whatever `.mat__side`'s 190px grid column
gives it — so full-bleed across a canvas it looked nothing like itself, and for a while
twelve stories were like that.

`src/testing/mounts.tsx` holds the app's own wrapper chains, by class name, so every size
comes out of the app's stylesheets rather than being restated. **A layer may not state a
size.** It may say exactly two things for itself:

- **Grid placement.** Every layout container here is a grid whose tracks are filled by
  siblings a story does not render, so a lone child auto-places into track 1.
  `.table__body` is `232px | 1fr | 304px`, and a right rail that forgot `gridColumn: 3`
  renders at 232px — silently, and looking entirely plausible. That trap is why this is a
  file rather than a convention.
- **A value the app sets from JavaScript.** `--card-w` on a lane is the only one, because
  `Lane.tsx` writes it inline; the mount calls the same `cardWidthVar`.

A third mechanism, `fill`, supplies an empty stand-in for a *sibling* whose box the
component is sized against — the action panel's whole design is about the rail being short,
and it is short because the card preview is above it.

Declaring `mount` is mandatory and the decorator throws without one. `bare` and `screen`
are valid answers; they just have to be answers, because a default is exactly how twelve
stories ended up in the wrong place. `tests/imports.test.ts` fails the build if any story
still carries the old `frame:` key, which `parameters` being loosely typed would otherwise
let pass as a silent no-op.

`src/testing/appGeometry.ts` holds the app's stated sizes — the 304px rail, the 190px mat
column — each citing the rule it comes from, and `expectMountedLike` compares a rendered
box against *those* rather than against the mount that produced it, which would be
circular. Sizes derived from `vh` are asserted as relationships instead: the preview iframe
is not the window, and `theme.css` has a media query keyed on viewport height.

### Motion, twice

The runner gets `reducedMotion="always"` and the browser gets the app's real springs, split
by a flag set in `.storybook/vitest.setup.ts`. Holding motion still for both meant the hand
fan's lift and every `layoutId` cross-fade simply did not happen when you opened Storybook
to look at them, which is a visual suite that cannot show you the visuals.

`parameters.automtg.motion: "real"` opts a story back in, and a few need it: a hover that
*scales* is a transform, so `reducedMotion` removes the thing under test. That is not
hypothetical — the story asserting the commit slab stays inside its rail passed against the
bug, because the scale it was measuring had been configured away. Stories that run with
real motion use `settled()` from `asserts.ts`, since waiting for a transform to merely
exist returns on the spring's first frame.

The rest of `parameters.automtg`: `ui` seeds the store, `query` pre-loads react-query so a
lobby story paints its loaded state immediately, `art` picks the card art, `zoomLock` opts
out of the pinned zoom for the two stories that exercise the solver. Fixtures are in
`src/testing/` — `fixtures.ts` for the DTOs, `cards.ts` for a real card pool,
`scenarios.ts` for whole positions, `pods.ts` for lobby states, and `asserts.ts` for
`expectUniqueActionIds`, which is the invariant most worth sharing.

Card art defaults to a deterministic offline stub keyed off the card id. Switch the
toolbar to "live" with uvicorn running to eyeball the board against real illustrations.

The Playwright suite boots uvicorn and vite itself and plays the real UI:

- `smoke.spec.ts` — deal, mulligan, hand renders, play a land, hover preview, reach combat.
- `full-game.spec.ts` — drive a 2-player game to a result by always clicking a legal
  action, plus a 4-player pod. **If any decision kind has no surface in the UI the loop
  runs out of buttons and the spec fails**, which is the bug most worth catching.
- `stacking.spec.ts` — duplicate lands collapse to one counted stack and fan out on hover.
- `layout.spec.ts` — the measurements no content assertion can make: nothing runs under
  the hand, no panel collapses to zero, cards scale with the viewport, each player's
  lands are the band nearest *them*, and no band drifts as permanents enter and leave.
  Both band orders render fine and a jumping board renders fine, so a flipped `LANES`,
  a dropped `mirrored` prop and a re-collapsed empty lane are each only visible as a
  comparison of two numbers.
- `clarity.spec.ts` — the information surfaces from
  [playtest-feedback-02.md](playtest-feedback-02.md): the mana pip row agrees with its own
  summary, a dimmed hand card explains itself in a sentence, card types render distinct
  tones and glyphs, no two rendered actions share an id across a whole game, no hand card
  hangs below the viewport, and `g` opens the graveyard.
- `playtest.spec.ts` — screenshot capture, skipped unless `PLAYTEST=1`.

`biome.json` turns off `a11y/useSemanticElements`: it pushes `role="dialog"` towards the
native `<dialog>` element, which needs an imperative `showModal()` and cannot be driven by
`AnimatePresence` exit animations.

## Playing with a controller

The client is playable end to end on a gamepad, at a Steam Deck's 1280x800. Two
signals drive it and they are **deliberately independent**:

| signal | comes from | decides |
|---|---|---|
| `<html data-input="mouse\|keyboard\|pad">` | the last input actually used | whether the focus ring and the button glyphs are drawn |
| `<html data-handheld>` | the viewport, via `logic/breakpoints.ts` | the compact layout |

So a desktop player who picks up a controller gets the ring and the glyphs on
the unchanged three-column board, and a Deck user with no pad gets the compact
board and no glyphs. Neither implies the other.

`data-input` is **last-input-wins** rather than "is a pad plugged in", because a
Deck in desktop mode has both attached at once. `pointermove` is throttled to one
write per 200ms so a mouse resting on a desk cannot steal the mode back
mid-navigation, and a *move* additionally loses outright to any key or pad input
in the last 1500ms — the Deck's right stick and trackpads arrive as mouse events,
so without that grace a thumb resting on the device it is built into hid the
ring, the glyphs and the hint bar mid-game.

### The Deck sends a keyboard, not a gamepad

In **gaming mode** Steam Input applies a controller layout to every non-Steam
shortcut, recognises browsers, and picks a keyboard-and-mouse template for them.
Under that template Steam takes the pad exclusively and publishes no gamepad at
all: `getGamepads()` is empty while the d-pad arrives as arrow keys and A arrives
as Enter. Every signal above says `keyboard`, and the hint bar tells a player
holding a controller to press Enter and Esc.

Three things answer that, and `docs/steamdeck.md` is the player-facing version:

- **A scheme preference.** `auto | pad | keyboard | mouse`, persisted, set from
  the front door's **Settings** card or in-game from the settings menu (both
  render `components/ui/SchemePicker.tsx`, so they cannot drift). Anything but
  `auto` pins `data-input` outright. `?input=pad` is the un-persisted escape
  hatch.
- **A heuristic under `auto`.** A session that has produced three navigation keys
  and *not one character key*, at handheld viewport size, is treated as a pad.
  The viewport gate is the safety: a desktop keyboard user arrowing around a menu
  must never be told to press "A". A single character key disqualifies it
  permanently — somebody who typed has a keyboard.
- **A diagnosis.** `padDiagnostics()` already computed `supported`/`secure`/
  `focused`, and was dev-only behind `window.__AUTOMTG_RING` — no use to somebody
  on a Deck with no devtools. `components/ui/ControllerPanel.tsx` puts it on
  screen with the fix for each cause. Note **secure context first**: the Gamepad
  API does not exist over plain http to anything but localhost, so a Deck pointed
  at a LAN dev server has no `getGamepads` to fail and no Steam-side fix helps.

Analog motion counts as pad input as well as button edges, because a *held*
trigger produces no edges at all for as long as it lasts.

### The region trap is soft

`L1`/`R1`/`L2` step between the board's five regions, and a region traps the ring
inside itself so a thumb-flick cannot throw it across the screen. That trap was a
**one-way door** on any controller missing a shoulder button — which is exactly
what a Deck in gaming mode is. A region is entered automatically, so the first
direction press of the game locked the ring in one region for the rest of it.

So `stops.ts:escapeGroup` makes it soft: a direction with somewhere to go inside
the region is the region's, a direction with nowhere to go **leaves** it. The
whole board is now reachable from the d-pad alone. Two things make that safe:

- **The modal trap stays hard.** A group narrows the board for comfort; a modal
  narrows it for correctness, and only the first may give way at its edge.
- **The group is released before the cursor moves.** `setCursor` resolves through
  `activeRoot()`, which is still the region being left — so without
  `setGroup(null)` first, the escape target is not findable and the ring silently
  does not move. Every unit test passed while that was broken, because they call
  `escapeGroup` directly; `e2e/pad.spec.ts` is what caught it.

The dial also has a **Regions** button in the foot now, because holding `L2` was
the only way to open it.

### Reading the pad: never `getGamepads()[0]`

`navigator.getGamepads()` is **sparse and indexed by slot**, so the nulls in it
are empty slots rather than padding to trim. "The first non-null entry" is a
convincing wrong answer to "which pad is the player holding", and on an ordinary
Windows desktop it is wrong often: Steam publishes a virtual pad beside the
physical one, a wheel or a flight stick occupies a slot, and a controller that
reconnects comes back at a higher index.

Read that way the held pad is never looked at, every button comes back neutral,
the mode never leaves `mouse`, and **nothing at all happens** — which is
indistinguishable from the polling loop being dead, and sends the next person to
debug the loop. So `input/pad.ts` reads *every* connected pad, OR-ing the buttons
and letting the stick pushed hardest win. An idle second device costs nothing and
cannot shadow the real one.

Two more things a real pad does that a synthetic one does not:

- **`mapping` is not always `"standard"`.** The W3C indices in `buttons.ts` mean
  something only when the browser says so. When it cannot vouch for a pad — an
  Xbox pad over Bluetooth that XInput did not claim, most third-party pads — it
  hands over the raw HID report order instead, where the d-pad is a **hat axis**
  rather than buttons 12–15 and the face buttons sit at 0/1/3/4 with gaps. `HID`
  in `pad.ts` is that fallback; without it such a pad has no working directions
  at all.
- **A rAF handle is not proof the loop is alive.** No browser runs rAF for a
  hidden, minimised or occluded window, so a handle taken just before the window
  went away outlives the loop that owns it. `wake()` trusts a handle only while
  the loop has ticked inside `STALL_MS`, which is what lets it recover a stalled
  loop instead of returning early from the one call that exists to do so.

### When the controller does nothing, ask the browser first

`window.__AUTOMTG_RING.pad()` reports `supported`, `secure`, `focused` and the
raw `pads` list beside the loop's own state, because the three commonest
failures are not in this code and all three look identical from inside it — an
empty `pads`:

- the Gamepad API is **secure-context only**, so the app served over plain http
  to anything but localhost has no `getGamepads` at all (`supported: false`);
- no browser hands out a pad until it has seen a button pressed **while the page
  was focused** (`focused: false`);
- on Windows a running Steam client with a desktop layout bound to the
  controller swallows it before any browser sees it (`pads: []` while the pad is
  plainly working elsewhere).

### The cursor is an attribute, not state

> The cursor wants to live as an attribute on ONE element, not as state thirty
> components read.

This is the single most important thing in `input/`. A cursor in zustand that
every `Card` subscribes to re-renders all thirty on every step of a sweep, which
the design round measured at **18.5fps under a 4x CPU throttle** against 59.7fps
for moving one attribute. The React version of the mistake looks nothing like
the vanilla one and arrives at the same number.

So `input/cursor.ts` holds one string, stamps `data-cursor` on one node
imperatively, and **no component subscribes**. `Card`, `Lane`, `PlayerOrb` and
the rest render `data-stop` as a static prop derived from their own props. The
two exceptions are `HintBar` and the read rail, both single leaves at the edge
of the tree, and the rail's write is debounced by `RAIL_SETTLE` so a twelve-step
sweep costs two rebuilds rather than twelve.

**Stops are a string namespace, never an index** — `card:<oid>`, `orb:<pid>`,
`act:<actionId>`, `tool:<name>`, `pile:<pid>:<zone>`, `lane:<pid>:<lane>`. Keyed
on the oid, so the ring survives a card moving from hand to stack to
battlefield, for the same reason `layoutId` does.

Outside the board, a **native focusable is a stop**. The lobby declares none:
everything interactive there is already a control, and the fallback means a
button added next year is reachable without anybody remembering this layer
exists.

### The cursor may not take focus off you

`stamp()` calls `.focus()` so assistive tech follows the same object the ring is
on. `resolveCursor()` runs after **every commit** — that is what puts the ring
back on a card the engine has just replaced. Put those two together on a screen
made of text fields and you get the bug a player reports as *"the seed box only
takes one digit"*: a controlled input commits on every keystroke, so the resolve
re-focused the first control on the screen and the caret left the field.

Two rules, and both halves are needed:

- **A commit is not a request to move focus.** `resolveCursor` re-stamps without
  focusing when something else already holds it. It still focuses when the
  cursor genuinely *moved* — a dialog opening over the board must take focus
  with it, or the trap is only a picture of one — and when nothing holds focus
  at all, which is the case it exists for.
- **Where a stop can hold focus, the ring follows it.** Off the board the cursor
  and DOM focus are two names for one thing, so clicking into a field moves the
  ring there rather than leaving it on a button nobody is using. Deliberately
  *not* "follow focus" in general: a board card is a div and cannot hold focus,
  so there the focused element is merely whatever was pressed last, and
  following it would drag the ring off the card on every engine push.
  `focusHolder` is the one function that draws that line.

### Two rules that keep it honest

**`A` is a click.** Not "A does what a click does" — `useCursorNav` dispatches
`element.click()` on the focused stop. There is no second routing table, no
branch per stop kind, and no way for a pad to reach an action a pointer cannot.

**Every `data-action-id` is emitted with its stop.** `actionAttrs(id)` returns
both, so `ActionPanel`'s "every legal action is a button, exactly once" and the
ring's "every one of them is reachable" are equal *by construction*.
`tests/stops.test.tsx` fails the build if a bare `data-action-id` reappears.

### The focus trap

`stopRoot()` is nine lines and every consumer asks it: whatever is on top owns
the ring. Six surfaces mark themselves `data-modal-root`. The half worth knowing
is `:not([data-closing])` — every dialog animates out through `AnimatePresence`,
so an *exiting* one is still in the DOM and would trap the ring in a panel that
is fading away.

### The ring's spring

`input/ring.ts` integrates the **closed form of a damped oscillator**, not
`v += (k*dx - d*v)*dt`. The naive one is frame-rate dependent — the same spring
overshoots 1.6px at 60fps and 4.5px at 144fps — and goes unstable at large `dt`,
which is exactly what a throttled tab hands you. The closed form is exact at any
`dt` and resolves a dropped second to "the ring is where the cursor is".

`w 36, z 0.78` is 142ms of settling and 2% of overshoot. `longHop` shortens
anything past 420px, because a spring's settling time is distance-independent —
a 1000px zone jump would otherwise fly at ~13,000 px/s and strobe.

### The floors, and why they are a CI gate

> Do not ship a controller mode without the 16px floor asserted in CI.

`e2e/handheldAssert.ts` runs at 1280x800 in its own Playwright project and
asserts: **16px** on anything carrying information, **96px** on any card the
ring can land on, **44px** on any control, a ring at least 3px *and not
`outline-style: none`*, at most one cursor, zero unreachable stops, zero
`title` tooltips.

Every one of those numbers caught something real. The full record is in
[handheld-playtest.md](handheld-playtest.md); the short version is that the app
had **123 elements under the floor at 6.5px, 142 native tooltips, and a card
floor being missed by a card the ring could sit on** — none of which is visible
in a screenshot, because a reviewer already knows what the label says.

`title` is banned outright (`tests/noTooltips.test.ts`): it opens on hover and
on nothing else, so on a controller it is information that cannot be reached.
The 43 sites became `data-hint`. It is the app's accessible-name and
description carrier now rather than a second thing on screen: the hint bar used
to echo it off the focused element and no longer does, because the string was
the one unbounded item in that row and wrapped it onto a second line, growing
the foot and lifting every tool button mid-decision. The bar names buttons; an
element says what it is through `aria-label` and `data-hint`.

### What the compact layout gives up

Most of what this section used to describe is now simply the layout: the left
rail is retired at every size, and an opponent is an `OpponentSeat` on a desktop
too. What is still handheld-only is **their lanes**.

An opponent's cards are clipped to `height: 0` at 1280x800, because three boards
and the viewer's will not fit at the 52px card floor — which is the observation
this whole round is built on. Clipped and not removed, and that is load-bearing:
`FxLayer` anchors damage numerals and exit ghosts by looking up `[data-oid]` in
the live DOM, so a card that is not laid out has no box to fly from. It is also
why `input/stops.ts` and `input/groups.ts` filter stops with an ancestor-clip
walk rather than by size: **a clipped card still reports its own full box**, and
without the walk the ring could land on one nobody can see. It could, for
several rounds, and `handheldAssert`'s `unreachable` agreed the board was fine
because it called the same unfiltered function.

Their board is two presses away and the difference is worth knowing. **`R2`
held** is the glance — "is it safe to attack into that", which is a second and
an answer. **Pressing their seat** is a place: you go and stand at it, their
lanes are drawn where yours were, your own panel stays beside them (life and
open mana are most of what you assess a threat against), and `B` or the strip's
own button brings you home. The node MOVES rather than being copied, so there is
exactly one box per `data-oid` at all times — two would give `FxLayer`'s
`querySelector` a choice it has no way to make correctly.

**The lane headings go.** "CREATURES", "GLOBAL ARTIFACTS & ENCHANTMENTS",
"LANDS" name three things drawn directly beneath them. Dropping them buys the
front band a line of height and the lands band a 74px column —
`state/useZoomFit.ts` passes `labels: false` to match, and it has to: hiding
them in CSS alone would leave the solver reserving room for them.

**The tool strip lives in the foot**, portalled out of the right rail by
`ActionPanel` into a host `Table` renders. Portalled and not duplicated: it is
the same node, so every `data-action-id`, `data-testid` and ring stop travels
with it, and the panel's one-control-per-action invariant holds. At the 44px hit
floor the five controls wrap to three rows in a 200px column; the foot's row is
1017px and they are one line.

**The commit slab stayed in the rail.** It was portalled into the foot for the
same reason, and the reason stopped holding when the rail gained 234px — under
the list it commits is where the thing that ends a decision belongs.

**The card reader is a landscape window, not a small card.** A 243px rail holds
a card frame 116px across, which is smaller than the board card it is meant to
be helping you read, with `cover` throwing away most of the painting to get
there. `art_crop` is 626x457, so a 227x84 window keeps the full width for a
third of the height, and the 78px it hands back is what the rules text is made
of. The P/T is stamped on the picture, because the first draft put it on the
type line and the line ellipsised away the number.

### Jumping around the board

Directional navigation crosses a 96px seat strip, three lanes, a fanned hand and
a 243px rail one card at a time. `docs/handheld-playtest.md` Loop 1 records
walking the board as "a bad way to ask can you reach everything": reachable and
reachable-in-under-a-second are different properties, and only the second is
playable.

`L1`/`R1` step between five regions — hand, actions, opponents, you, board — and
trap the ring inside the one it is in. **A region is a container, not a stop-id
prefix**, because `card:<oid>` is a hand card AND a board card AND a stack item
AND a prompt option: the namespace says what a stop *is* rather than where it
lives, which is the whole reason the ring survives a permanent changing zone.
Only the DOM can answer this. See `input/groups.ts`.

The trap is subordinate to the modal one: `stopRoot` returning anything but the
board means something is on top and owns the ring outright. It is also scoped to
`html[data-input="pad"|"keyboard"]` — a mouse player has no ring, and trapping a
desktop keyboard user inside a region is a regression nobody asked for.

**Holding `L2`** opens a dial that jumps straight to a region. On the trigger and
not on a shoulder, and that is not a preference: `pad.ts` reports presses and has
no release event for a shoulder, so a hold there is a timer with nothing to
cancel it. A trigger is analog and `onFrame` reports its position every frame,
which is the channel the `R2` reader already uses. The dial carries
`className="wheelwrap"` — the trap has preferred that class over every other
candidate since it was written, with nothing in the repo ever rendering one.

**The ring moves itself when the decision changes** (`logic/focusGroup.ts`):
combat to the board, your main phase to the hand, otherwise the panel. Keyed on
the pending kind and the step ONLY — run on every render it would drag the ring
back each time the engine pushed a state, several times a second while an AI
plays. It says nothing at all when the decision is not yours, when a dialog owns
it, or when passing is the only thing to say.

**`Y` reads the card the ring is on** at 330px, and on a seat it reads that
seat's commander — in Commander the deck is the commander.

> **Do not advertise a button without binding it.** `HintBar` printed `L1 Zone`
> and `L2 Menu` from its first draft and `verbsFor` returns `Y Read` on every
> card stop, and for several rounds **nothing in the app listened for any of the
> three**. An advertised button that does nothing teaches the player that the bar
> is not to be trusted, and nothing in the suite could see it, because the bar
> renders spans and a span cannot fail to work. `HintBar` renders *from*
> `NAVIGATION_HINTS` now rather than restating it, and a story compares what the
> bar can say against `pad.boundButtons()`.

### Everything on screen at once

A Deck is held at one angle in two hands. There is no second position, so a
board you have to scroll is a board whose bottom half does not exist — and that
is a stronger claim than the floors make. Three tokens carry it:

| token | what it bounds |
|---|---|
| `--pod-seat-h` | one opponent's whole seat, orb and all |
| `--hand-lift` | how far a hovered hand card rises, and the room reserved for it |
| `--mat-side` | the viewer's info column |

`e2e/deckfit.spec.ts` is the gate, and it is a separate project because it runs
at **1200x800 as well as 1280x800**: same height, ~36px less rail, and enough
findings appeared at exactly one of the two widths that they are not
interchangeable. It asserts `scrollHeight === clientHeight` on every container
in a game played in to turn six, two-player and four-seat.

`e2e/handheldAssert.ts` gained `overflowing[]` and `overBudget[]` for the same
reason. The floors it already checked answer "is this big enough"; neither of
them can answer "and does it still fit", which is how a 220px opponent seat
holding an empty board passed every gate in the suite. See
`docs/handheld-playtest.md` Loop 6.

### Not built

Rumble is best-effort — `vibrationActuator` is Chrome-only, so every rumble is
redundant with something visible. The four back grips (L4/R4/L5/R5) are
deliberately unused: Steam Input maps them before the page sees anything.
Whether Game Mode passes the pad to a non-Steam browser shortcut at all is the
one thing here that cannot be verified without the hardware.

## Not built

WebSockets — multiplayer uses versioned long-polling instead, and
[adr/0007](adr/0007-versioned-long-polling.md) records why. Deck building, spectating a
pod you are not in, chat, and mobile layout.
