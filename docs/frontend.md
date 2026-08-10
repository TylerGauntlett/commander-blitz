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
├── state/       uiStore.ts (zustand), useGame.ts (react-query), narration.ts,
│                useImages.ts, useCardBase.ts, useZoomFit.ts
├── logic/       zoneGrouping, actionMatch, labels, stacking, cardStyle, events,
│                cardArt, cardSize, cardStackGeometry, zoomFit, zones
├── motion/      springs.ts                 - every transition in the app
├── styles/      cards.css, board.css, ui.css  (+ src/theme.css for tokens)
└── components/
    ├── game/    Table, PlayerMat, Lane, CardStack, Card, CardFace, HandFan,
    │            PlayerOrb, PhaseTrack, CombatPanel, CombatArrows, ActionBar,
    │            PromptDialog, StackPanel, CardPreview, FxLayer, EventTicker,
    │            ZonePeek, GameOverScreen
    └── menu/    NewGameScreen
```

`logic/` holds every decision the client makes, as pure functions over the server's
view. That is what the unit tests cover; components stay presentational.

## Where things sit on screen

A ribbon across the top, three columns, and the hand along the foot.

- **Top** — the phase ribbon: five phases as pills, and only the live one expands
  into its steps. All thirteen step labels stay in the DOM regardless, which is
  both what `e2e/smoke.spec.ts` counts and what keeps the marker's `layoutId`
  animation continuous across a phase boundary.
- **Left rail** — the stack, and the event log.
- **Middle** — opponents on a row that sizes to its content, then your own mat. Each
  mat's first column is that player's info panel (`PlayerOrb`): their commander,
  their life dial, their mana, their zone piles. The board itself is two *bands*
  — see below. Card size is **solved against the space each area actually has**
  rather than fixed: see "How big a card is" below.
- **Right rail** — the card preview, then **combat**, then the tool strip. Combat
  moved here from a full-width banner under the board: the decision now sits
  directly under the card you are reading rather than as far from it as the
  layout allows, and the foot belongs to the hand alone. Whichever surface owns a
  decision renders its action ids and the bar stands down (`standDown`), so a
  prompt is never printed twice.
- **Foot** — the hand, and nothing else. Your commander used to sit to its left; it
  is the hero of your info panel now, drawn as a plinth rather than a card. See
  `CommandZone` and `docs/mockup-fidelity.md` defect #5.

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

Three things about it are worth knowing before touching it:

- **A fit solver reads the layout and then changes it**, so only measurements that
  cannot move are allowed as inputs: lane *width* (grid tracks, hence
  `scrollbar-gutter: stable`), never lane *height*. The hand solves before the board
  because `.table__foot` is an `auto` row taking its height out of the board's, and
  the pod's lane box is pinned so `.play`'s `fit-content(58%)` row cannot depend on
  the pod card size it is being used to solve. `useZoomFit`'s header has the full
  argument.
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

Both the mana panel and the commander-damage panel are **permanent**. They were
conditional rows in `orb__body`'s `space-between` slack, so they floated in the
middle of the column and re-spaced the whole interior each time one appeared or
emptied — several times a turn. They sit on a plate with the zone piles in
`.orb__foot` now, which puts all the slack in one gap under the plinth. An empty
mana panel says `—`; a commander-damage chip exists for every other seat from turn
one, at zero, carrying the seat and a meter of its progress toward 21.

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

## Watching the opponents

`GameSession.drive_ai()` normally runs every AI seat until a human must decide, so one
response can contain three whole turns and the board simply snaps. The client asks for
`?ai_steps=1` instead, which bounds the server to a single AI decision per call, and
pumps: when a response comes back with no legal actions and the game is not over, the
opponents still owe decisions.

`logic/events.ts` turns each batch of events into timed **beats** — floating damage
numerals anchored to the struck permanent, life tickers, spotlights on the card being
cast, turn banners, screen shake. `state/narration.ts` runs the queue; input is gated
while it drains, with a Skip button and a 1x / 2x / instant speed control.

The pump waits for the queue, so the animation of one decision finishes before the next
is requested. A stall guard stops the loop if the engine ever fails to progress.

## State

- **Server state** — react-query. The engine is authoritative and every mutation returns
  the new state, so there are no optimistic updates. There is no background polling; the
  only loop is the AI pump described above.
- **UI state** — zustand: selection, hover, targeting, staged combat, the open stack, the
  zone modal, animation speed, the error banner. None of it reaches the server except as
  an action id.

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
npm test                 # vitest: pure logic + components
npm run build            # tsc --noEmit && vite build
npm run lint             # biome check .
npx playwright test      # end-to-end against the real engine
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
[roadmap.md](roadmap.md), "All Card Support"), that file is its only coverage.

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

## Not built

WebSockets (the AI pump is enough for one local player), deck building,
multiplayer over a network, and mobile layout.
