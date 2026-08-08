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
│                useImages.ts, useCardBase.ts
├── logic/       zoneGrouping, actionMatch, labels, stacking, cardStyle, events,
│                cardArt, cardSize, zones
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
  their life dial, their mana, their zone piles.
- **Right rail** — the card preview, then **combat**, then the tool strip. Combat
  moved here from a full-width banner under the board: the decision now sits
  directly under the card you are reading rather than as far from it as the
  layout allows, and the foot belongs to the hand alone. Whichever surface owns a
  decision renders its action ids and the bar stands down (`standDown`), so a
  prompt is never printed twice.
- **Foot** — the hand, and nothing else. Your commander used to sit to its left; it
  is the hero of your info panel now, drawn as a plinth rather than a card. See
  `CommandZone` and `docs/mockup-fidelity.md` defect #5.

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
recognisable picture rather than twelve of "the tan ones". What carries type
without colour now is the glyph and the type line, and `e2e/greyscale.spec.ts`
fails the run if either is missing or unrendered on any face. The full reasoning
and the list of tests that changed is in
[mockup-fidelity.md](mockup-fidelity.md) -- read it before re-adding a type tint.

**Colour identity is a different fact and it keeps the frame**: the border, and the
gradient the art sits on, which on the ~4% of cards with no printing is the whole
card. A land's frame narrows to the colour it taps for and its produced-mana
symbols go large and centre-frame, so a lane of lands reads without reading a name.

Text over an unknown illustration is the one thing here that can fail silently, so
it is guarded by number: `tests/palette.test.ts` asserts both scrims are gradients
whose opaque ends clear a darkness floor, and `e2e/greyscale.spec.ts` asserts the
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

144 unit and component tests: lane assignment, seat rotation, stat and counter rendering,
mana pip splitting, action matching, target disambiguation, stack keying and splitting,
event-to-beat mapping, card-type tones and glyphs, the mana row and the unplayable-card
hint, and — via `@testing-library/react` — the card face, the action bar and every
decision kind the prompt dialog has to cover.

The Playwright suite boots uvicorn and vite itself and plays the real UI:

- `smoke.spec.ts` — deal, mulligan, hand renders, play a land, hover preview, reach combat.
- `full-game.spec.ts` — drive a 2-player game to a result by always clicking a legal
  action, plus a 4-player pod. **If any decision kind has no surface in the UI the loop
  runs out of buttons and the spec fails**, which is the bug most worth catching.
- `stacking.spec.ts` — duplicate lands collapse to one counted stack and fan out on hover.
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
