# How the game client is organised

The client under `frontend/` is React and TypeScript, built with Vite, animated with
`motion`, linted by Biome. This page is the map: which folder owns which kind of
decision, and the handful of rules that every change in it has to keep. It is written
for people and agents about to edit `frontend/src`, and it tries to say each thing once.

What it does not own:

- how the suites are layered and what each gate exists to catch — [testing.md](testing.md);
- the HTTP contract, hidden information and long-polling on the wire — [api.md](api.md);
- the decisions themselves — the ADRs under [adr/](adr/), cited here by number;
- why the board looks the way it does — ADRs [0011](adr/0011-the-card-is-the-illustration.md) through [0017](adr/0017-animation-reports-state.md).

```bash
cd frontend && npm install && npm run dev      # the Vite dev server
uvicorn commanderblitz.server.app:get_app --factory --reload   # the engine beside it
```

## The one rule

**The client simulates nothing.** The server sends every legal action with an opaque id
(`LegalActionDTO` in `api/types.ts`), the client renders those ids, and a gesture echoes
exactly one of them back through `act(id)`. There is no rules code on this side, no
reconstruction of what a drag "means", and no optimistic update: every mutation returns
the new state and the board draws that. Desync is structurally impossible rather than
merely untested. [architecture.md](architecture.md) explains the single seam this
rests on, [api.md](api.md) the round trip, and ADR 0015 *Every legal action is exactly
one control* the consequence for the UI.

Three input paths funnel into the same call, and the third is load-bearing rather than a
fallback:

1. **Drag** a hand card onto a lane. `Card`'s drag-end hit-tests the `data-dropzone`
   under the pointer; `canDropOnLane` in `logic/actionMatch.ts` says yes or no, and a no
   springs the card back with nothing sent.
2. **Click** a card, then its target. What is targetable comes from the action's own
   `targets`; a click settles only the half it answers, and `uiStore.narrowTargeting`
   leaves the panel to ask the rest. Hovering or focusing a card the targeting skips
   names the reason in the foot's targeting hint (`logic/targetHint.ts`): the engine's
   own refusal from `LegalAction.untargetable` when it has one (hexproof, shroud,
   protection), else the source's printed target line. The hint quotes; it never
   decides what is legal.
3. **The action panel**, which lists every legal action as a button. That is what makes
   the game keyboard-reachable and the end-to-end specs writable.

## Folder roles

Everything lives under `frontend/src`. The rule per folder is the thing to preserve.

| Folder | Owns | Rule |
|---|---|---|
| `screens/` | one component per address; `App.tsx` is the route table | the only place that imports `react-router`, with one exception: `components/ui/UpdateBanner.tsx` calls `useMatch` to know whether the player is at the table, and `tests/renderWithRouter.tsx` exists so its test can mount it |
| `components/` | `game/`, `lobby/`, `menu/`, `ui/`, `screen/` — presentation | renders bare, with no provider around it; anything that needs a router, a query client or a session is wired in `screens/` |
| `logic/` | every decision the client makes, as pure functions over the server's view | no DOM, no React; this is what the unit tests cover |
| `state/` | `useGame.ts` and `usePod.ts` (react-query long polls), `uiStore.ts` (zustand), `useAppConfig.tsx` (`GET /api/config`), `storage.ts` and `migrate.ts`, `useHandheld.ts`, `useZoomFit.ts`, `narration.ts` | the four kinds of state below, and nothing that belongs to the server |
| `input/` | `pad.ts` and `padRead.ts` (the gamepad poll), `cursor.ts`, `stops.ts`, `groups.ts`, `nav.ts`, `ring.ts`, `inputMode.ts`, `useCursorNav.ts`, `longPress.ts`, `stickScroll.ts`, `repeat.ts`, and the `useTable*` hooks | two signals, one intent; the cursor is an attribute, never state |
| `fx/` | `scheduler.ts`, `actuators.ts`, `particles.ts`, `presets.ts`, `reducedMotion.ts` | effects run concurrently on one frame loop and never touch React state |
| `motion/` | `springs.ts` | every transition in the app, named once |
| `styles/` and `theme.css` | `theme.css` at `src/` root is the token layer; `styles/*.css` are the surfaces (`cards`, `board`, `handheld`, `phone`, `lobby`, `opening`, …) | source order is the cascade; see the Biome note under Storybook |
| `testing/` | `fixtures.ts`, `cards.ts`, `pods.ts`, `scenarios/`, `fakeGame.ts`, `mounts.tsx`, `appGeometry.ts`, `journey.ts`, `asserts.ts`, `art.ts` | shared by tests and stories, and kept out of the production bundle by `tests/imports.test.ts` |
| `desktop/` | `bridge.ts`, the typed view of what the Electron preload exposes on `window` | the only place the shell is spoken to; `logic/desktop.ts` makes the decisions (ADR 0009 *The desktop build runs its own server, and the site is for friends*) |
| `api/` | `client.ts` and `types.ts`, the fetch wrapper and the DTO mirrors | same-origin: every call goes to `/api` relative to the page, so the dev server proxies it and a deployment serves it; the pod token is attached once in `request()` and no call site can forget |
| `audio/` | `sfx.ts`, the synthesised palette | — |

`theme.css` registers its moving tokens with `@property` (`--card-w`, `--card-w-base`,
`--pod-lanes-h`, `--mat-side`, `--pod-seat-h`, `--seat-h`, …) so a transition on one
re-resolves every declaration that reads it. It also reads three attributes on `<html>`
that the rest of the stylesheets key on: `data-desktop` and `data-handheld` for the
layout, `data-input` for whether a focus ring and button glyphs are drawn.

## State: four kinds

**Server truth lives in react-query**, fetched by `useGame` and `usePod`. Both are
self-rescheduling long polls: the request carries the version last seen, the server holds
it until that number moves or its timeout lapses, and the moment an answer lands the
next request goes out. A timed-out poll is a normal response with the same version. The
mechanism is ADR 0007 *Versioned long-polling for multiplayer*; the wire detail is in
[api.md](api.md#long-polling).

`useGame` has two loops and picks by *who* it is waiting for, read from `human_seats`:
an AI seat is pumped one decision at a time (`?ai_steps=1`), so its turn is watchable;
another person is listened for, because pumping would busy-wait against their thinking.
The listener carries two cursors — the version says *when* to wake, `?since=` (the
response's `event_cursor`) says *what* is new — and `absorb` trims anything already
seen, so a pump reply and a poll reply that overlap never narrate a move twice.
`tests/useGame.test.tsx` pins the loop.

**Client-only state lives in `uiStore`** (zustand): selection, hover, targeting, staged
attacks and blocks, the open stack group, the peek, the log and settings overlays, the
viewed seat, the error banner. None of it reaches the server except as an action id.

**What persists** does so under one prefix. `state/storage.ts` owns `STORAGE_PREFIX`;
`state/migrate.ts` runs the rename of any legacy keys as a side effect of being imported,
and `main.tsx` imports it before anything else because the store reads its keys at
module evaluation. The persisted settings are narrow: playback speed, mute, the hint bar,
the input scheme preference. The player's imported library is `state/library.ts`.

**The URL carries the place; `sessionStorage` carries the identity.** ADR 0008 *Real URLs
for the client* records the shape: every screen has an address that mirrors the API
resource behind it, `App.tsx` is the route table and nothing else, `logic/routes.ts`
holds the path builders and `screenKey`, which is what the screen transition swaps on.
Two rules fall out of it:

- A link pasted into a chat must not grant a seat, so the token for a pod is in
  `sessionStorage` keyed by pod code (`usePod.storedToken`), and a game id maps to its
  pod code the moment the client learns it (`usePodSession`). Session, not local, so
  two tabs are two players — which is how `e2e/pod.spec.ts` drives two browsers.
  `setPlayerToken` is called during render, not in an effect, because a child's first
  request fires before a parent's effect runs.
- **One-way transitions `replace` rather than push**: the deal, leaving a pod, quitting
  a table. A dealt pod's lobby cannot be re-entered, so that history entry stops
  existing and Back from the table lands on the front door. Browsing pushes.

Deep links need a host that rewrites unknown paths to `index.html`; Vite does, and the
engine's `create_app(serve_client=True)` does for `frontend/dist`.

## Layout modes

There are three, and they nest: **desktop**, **handheld** (a Steam Deck's panel) and
**phone** (a handheld whose floors are too big for it). The queries are stated once as
strings in `logic/breakpoints.ts` — `HANDHELD_QUERY` and `PHONE_QUERY` — and
`styles/handheld.css` and `styles/phone.css` repeat them literally;
`tests/breakpoints.test.ts` reads the stylesheets off disk and fails if either drifts.
`state/useHandheld.ts` hands React the same answers (`useHandheld`, `usePhone`) through
`matchMedia`, because the compact layout moves components into different parents, which
CSS alone cannot do.

**An explicit attribute beats the media query.** `App.tsx` stamps `data-handheld` and
`data-phone` on `<html>` from the hooks; Storybook's `preview.tsx` stamps `data-handheld`
or `data-desktop` from its toolbar without resizing anything. Anything that moves a
*node* rather than a pixel reads `useHandheldLayout`, which honours the stamp first and
the query second, so a story reviewed as the wide board renders the wide structure.
`data-desktop` exists for Storybook alone; the running app never sets it.

What the compact layout gives up, as rules:

- **The viewer's board is the only board.** An opponent's lanes are clipped to a zero
  box, not removed. `FxLayer` anchors numerals and ghosts by looking up `[data-oid]` in
  the live DOM, so a card that is not laid out has no box to fly from; and there is
  exactly one box per `data-oid` at all times, because viewing another seat *moves* the
  node into the viewer's lane position rather than copying it. `stops.ts:visibleBox` is
  the on-screen question, and `stops.ts` and `groups.ts` filter stops with an
  ancestor-clip walk rather than by size, because a clipped card still reports a full box.
- **Lane headings go**, and `useZoomFit` passes `labels: false` to match, or the solver
  reserves room for labels that are not drawn.
- **The tool strip moves to the foot** by portal, not duplication, so every
  `data-action-id` and stop travels with it and the one-control-per-action invariant
  holds.
- **The phone tier is additive**: everything `handheld.css` says still applies, and
  `phone.css` lowers the floors and restacks the table under `data-phone`.

**How big a card is** has two layers. `logic/cardSize.ts` is proportion: one fluid
`--card-w-base` in `theme.css`, every zone a ratio of it (`CARD_SCALE`), and
`cardWidthVar` is the only way to write `--card-w` — **never emit a px literal into
`--card-w`**, because an inline pixel beats the `clamp()` on `:root` and freezes every
display at the same size; `tests/cardSize.test.ts` fails if `cardWidthVar` stops
emitting a `calc()`. `logic/zoomFit.ts` with `state/useZoomFit.ts` is absolute size:
the board, the pod and the hand each get the largest card whose wrapped rows still fit
the room they have, shelf-packed from real footprints (a tapped permanent is landscape, a
stack is one box, a host carries its auras). The scale constants are ceilings the solve
may not exceed, not sizes.

Four rules for touching the solver (ADR 0014 *Numbers are measured, relationships are
invariants, budgets are ceilings*):

- **A fit solver reads the layout and then changes it, so it may only read inputs that
  cannot move**: lane width (grid tracks, hence `scrollbar-gutter: stable`), never lane
  height. The hand solves before the board because the foot's height comes out of the
  board's. `useZoomFit`'s header carries the full argument.
- **The pod's box is a function of the viewport and the seat count alone**
  (`solvePodLanesHeight`), never of anything the card size or the hand can move; `Table`
  writes it back as `--pod-lanes-h`, so the box CSS draws is the budget the cards were
  packed into. `e2e/layout.spec.ts` states this outright.
- **Board height is not monotone in card width** — growing cards can shorten a lane by
  re-wrapping a tapped permanent — so `solveBoardCardWidth` scans rather than bisects,
  and `tests/zoomFit.test.ts` pins the counter-example.
- **Nothing the player is looking at changes size because of game state** (ADR 0016).
  The viewer's lanes render at full card height whether empty or not, the mana row has a
  reserved slot, and `e2e/layout.spec.ts` fails the run if a band of your own mat drifts
  over a game.

The board is laid out the way it is played: `LANES` in `logic/zoneGrouping.ts` is
declared front to back and `PlayerMat` renders it in that order, so the array *is* the
layout; an opponent's mat is `mirrored`, which puts the two creature bands either side of
the table's midline. Attachments are not loose cards — `attachmentsFor` pulls them out
of the lanes and `CardStack` tucks them under their host, so a host is never merged into
a stack.

## Input and the cursor

**Two signals, deliberately independent, feed one intent.** `<html data-input>` says
what the player last used — `mouse`, `keyboard` or `pad` — and decides whether the focus
ring and button glyphs are drawn; `data-handheld` says what the viewport is and decides
the layout. Neither implies the other: a desktop player who picks up a pad gets the ring
on the wide board, and a Deck with no pad gets the compact board and no glyphs.

`data-input` is **last-input-wins**, not "is a pad plugged in", because a Deck in desktop
mode has both at once. `input/inputMode.ts` throttles pointer moves and gives any key or
pad input a grace period during which a move cannot steal the mode back — the Deck's
stick and trackpads arrive as mouse events. A scheme preference (`SchemePref`:
`auto | pad | keyboard | mouse`, set from `components/ui/SchemePicker.tsx`) pins the
mode outright; `?input=` is the un-persisted escape hatch.

**The Deck sends a keyboard in some modes.** Under Steam Input's keyboard-and-mouse
template the pad is taken exclusively, `getGamepads()` is empty, and the d-pad arrives as
arrow keys. `inputMode.ts` carries a heuristic under `auto` — a streak of navigation keys
and no character key, at handheld size, is a pad — and
`components/ui/ControllerPanel.tsx` puts `padDiagnostics()` (`supported`, `secure`,
`focused`, the raw pad list) on screen with the fix for each. [steamdeck.md](steamdeck.md)
is the player-facing version.

**Never `getGamepads()[0]`.** The array is sparse and indexed by slot, so the first
non-null entry is a convincing wrong answer: Steam publishes a virtual pad beside the
real one, a wheel occupies a slot, a reconnected pad comes back higher. `input/padRead.ts`
reads *every* connected pad, OR-ing buttons and letting the hardest-pushed stick win; its
`HID` table is the fallback for a pad the browser will not call `standard`, where the
d-pad is a hat axis. `pad.ts` trusts a rAF handle only while the loop has ticked inside
`STALL_MS`, because no browser runs rAF for a hidden window and a stale handle looks
exactly like a live loop. Analog motion counts as pad input, since a held trigger has no
edges.

**The cursor is an attribute, not state.** `input/cursor.ts` holds one string and stamps
`data-cursor` on one node imperatively; no component subscribes. `Card`, `Lane`,
`PlayerOrb` render `data-stop` as a static prop derived from their own props, so a sweep
moves one attribute rather than re-rendering thirty cards. The two exceptions are
`HintBar` and the read rail, single leaves at the edge of the tree, and the rail's write
is debounced by `RAIL_SETTLE`.

**Stops are a string namespace keyed on the oid, never an index** — `stopId` in
`stops.ts`: `card:<oid>`, `orb:<pid>`, `act:<actionId>`, `pile:<pid>:<zone>`,
`lane:<pid>:<lane>`, `stack:<sid>`. The namespace says what a stop *is*, not where it
lives, which is why the ring survives a card moving hand to stack to battlefield, for
the same reason `layoutId` does. **A region is a DOM container** (`input/groups.ts`,
`GroupId`: hand, acts, stack, seats, orb, board), because `card:<oid>` is a hand card
and a board card and a stack item and a prompt option, and only the DOM can say which.
Off the board a native focusable is a stop, so a lobby button added next year is
reachable without anyone remembering this layer.

**The modal trap is hard; the region trap is soft.** `stopRoot()` says whatever is on top
owns the ring — surfaces mark themselves `data-modal-root`, and `:not([data-closing])`
keeps an exiting dialog from trapping the ring in a panel that is fading out. A region
narrows the board for comfort, so `stops.ts:escapeGroup` lets a direction with nowhere
to go inside the region leave it; the group is released before the cursor moves, because
`setCursor` resolves through the active root. The region trap applies only under
`data-input="pad"` or `"keyboard"`; a mouse player has no ring to trap.

**A commit never moves focus; the ring follows a focus holder.** `resolveCursor()` runs
after every commit so the ring lands back on a card the engine replaced, and it re-stamps
*without* focusing when something else already holds focus — otherwise a controlled input
loses its caret on every keystroke. It still focuses when the cursor genuinely moved, or
when nothing holds focus. Where a stop can hold focus (off the board) the ring follows
it; on the board a card is a `div`, so following focus would drag the ring off the card on
every engine push. `focusHolder` in `cursor.ts` is the one function that draws that line.

**Focus nudges fire on transitions, never on state.** `logic/focusGroup.ts` moves the ring
when the *decision* changes — combat to the board, an opponent's spell waiting on you to
the top of the stack, your main phase to the hand, otherwise the panel — keyed on the
pending kind, the step and `opponentTop` (the newest stack item of somebody else's while you
hold priority, so a response of your own on top of it is not a new decision). Run on every
render it would pin the ring on each state the engine pushes. The lobby's nudges follow the same rule: the
pod commits whenever anybody is choosing, and re-asserting a cursor on each would make
the rest of the screen unreachable. A block declaration is the one case where the region
depends on the layout as well as the game, so `boardCanDecide` is asked of the DOM and
passed in.

**A control that comes and goes leaves a stop behind.** Between priority windows the commit
slab has nothing to carry and becomes the idle bar; the bar is a `commit:idle` stop in the
slab's own box, so `cursor.ts:nearestTo` hands the ring from the slab to the bar and back
and a player passing repeatedly never has to walk back to it. Overlays that trap the ring
apply a choice only after they unmount: the region dial's pick (by `A` or by releasing
`L2` on a spoke) is held in `useGroupDial` and entered by `Table` once `.wheelwrap` is
gone, because `setCursor` resolves through the trap and would find nothing outside it.

**Do not advertise a button without binding it.** `HintBar` renders *from*
`NAVIGATION_HINTS` in `logic/verbs.ts` rather than restating it, and
`tests/hintsBound.test.ts` holds what the bar can say against what `pad.boundButtons()`
and the verb routing actually bind. An advertised button that does nothing teaches the
player the bar is not to be trusted, and a rendered span cannot fail a test on its own.

**`A` is a click.** `useCursorNav` dispatches `element.click()` on the focused stop; there
is no second routing table and no way for a pad to reach an action a pointer cannot.
`actionAttrs(id)` emits `data-action-id` and `data-stop` together, so "every legal action
is a button, exactly once" and "every one of them is reachable" are equal by construction
(`tests/stops.test.tsx` fails on a bare `data-action-id`). A horizontal press inside a
`[data-nav-x]` container becomes a `padnav` DOM event for the container to handle.

**Follow-up returns an ordered candidate list, not an answer.** `logic/followUp.ts`
answers "where should the ring go now that this decision has started" with candidates in
preference order, and the caller takes the first that lands — an attacker's card on a
desktop, the panel row for the same pairing where lanes are clipped. Nothing in the module
knows what a handheld is. Two questions keep it honest: `stops.ts:onScreen` for a direction
press (stepping does not scroll) and `sendableIn` for a jump (`stamp` brings its
destination into view; only a zero-box ancestor disqualifies).

**The commit control is `logic/commit.ts`**, shared rather than restated: `Table`
presses it and `logic/verbs.ts` prints its name, so the two cannot differ. Both attack
rankings share one fight model, `logic/fight.ts` (see Surfaces).

**Dispatch happens on the next frame.** `pad.ts` is a frame loop and a key is latched into
it, so a synthetic press asserted immediately is asserted against a board that has not
heard it; and `useCursorNav` is mounted by `components/screen/Screen.tsx`, not by the
table. [testing.md](testing.md) says what that means for a story.

The ring's spring (`input/ring.ts`) integrates the closed form of a damped oscillator,
exact at any `dt`, so a throttled tab resolves to "the ring is where the cursor is"
rather than going unstable; `tests/ringSpring.test.ts` holds it.

**Handheld floors are CI gates** (ADR 0013): `FLOORS` in `testing/asserts.ts` for the
story project and in `e2e/handheldAssert.ts` against a real engine — type, hit target,
card, a visible ring, one cursor, zero unreachable stops, zero `title` tooltips
(`tests/noTooltips.test.ts`; `data-hint` is the carrier). Press budgets are the fifth
gate: `testing/journey.ts` walks a journey and returns what it cost,
`Journeys.stories.tsx` holds a ceiling per journey, and `e2e/journeys-handheld.spec.ts`
walks the same ones against the server. Ceilings, never exact counts.

## Motion and effects

**Animation reports state; it never precedes or lags it** (ADR 0017). React commits the
new battlefield the instant a response lands, and nothing renders a lagged board to make
an animation line up — that would desync every `data-oid` anchor, drop target and
legality check. Narration (`logic/events.ts` turning event batches into beats,
`state/narration.ts` running the queue) plays *over* the committed state. A click while
the queue drains means "get on with it" and the thing clicked; only an in-flight request
gates input.

**Effects are concurrent, not queued.** A beat carries a list of timed effects played
together inside it, and an effect's offset is deliberately not bounded by the beat's hold,
so a turn reads as continuous rather than as slides. `tests/timing.test.ts` holds each
golden batch at or under its current cost so the queue cannot slow back down a few
milliseconds at a time.

Three primitives, one loop:

- **`fx/actuators.ts`** — the cards themselves move. A registry of imperative handles
  keyed by oid; `Card` registers on mount; `lunge`, `recoil`, `shudder`, `pulse` write
  Motion values directly, so a wide exchange drives every card without the reconciler
  hearing about it.
- **`fx/particles.ts`** with `ParticleLayer` — a pooled, capped, pure simulation on one
  canvas; `CAP` is the pool, and at the cap new emissions are **dropped**, because a
  capped effect thins out and an uncapped one becomes a slideshow at the most dramatic
  moment. Presets are in `fx/presets.ts`, coloured from the theme's signal tokens.
- **`fx/scheduler.ts`** — the one frame loop. It does not run when nothing is subscribed,
  and a ticker that returns `false` is dropped, so no effect has to remember to
  unsubscribe.

**`Card` has three motion layers, and the split is not cosmetic**: the outer node owns
*position* (`layoutId`, drag, hover lift); `.card__actor` owns transient *force* (what the
actuators push); `.card__pivot` owns *orientation* (the tap rotation). Each writes
`transform`, so sharing a node would let the last render win and untap a card the moment
it was picked up. The rim is painted on `.card__actor::after` and the staged pin is a
child of it, so both ride a lean; the `[data-oid]` box the arrows and ghosts measure
stays above and still. **`layoutId` is the oid**, which the engine preserves across zone
changes — that single fact is why a card flies from hand to stack to battlefield.
`StaticCard` exists for previews, dialogs and the lobby, where a second `layoutId` for
the same oid would animate between the two copies.

**Ghosts.** A card leaving the battlefield is gone from the DOM before its beat plays, so
`FxLayer` cannot anchor to it. `Card` posts its last box to `logic/cardRects.ts` in a
layout-effect cleanup on unmount, and `CardGhost` redraws the card from that box, holds
it long enough to read why it left, then drops it into its pile. **A card with no recorded
position draws nothing** — inventing one would put an opponent's creature in the middle
of your board on its way out. Face resolution is by oid, then by definition id (tokens
cease to exist on the way out), then a name plate. Destination comes from the event's
`to`, never from its cause ([engine-rules.md](engine-rules.md)); how it leaves is branched
on `cause` and `to`, and a bounce gets no burst because it is not a loss.

**`zone_change` narrates only when `from === "battlefield"`** — `logic/beats/exits.ts`,
`describeEvent` in `logic/labels.ts` and `logic/removals.ts` all hold the guard. Without
it every draw, mill and resolution earns a second log line, and a library-origin change
carries a card id to every seat, which would put a tutor target in the log.

**Reduced motion keeps what happened.** `App` passes `reducedMotion="user"` to
`MotionConfig`; particles, actuators and shake cannot read context, so
`fx/reducedMotion.ts` is their channel. What is dropped is how it felt; numerals,
captions, flashes and the log survive.

Combat is a collision: `logic/choreography.ts` collapses a run into declare and strike
beats, pairs hits from the `source` and `oid` each `damage_dealt` already carries, and
resolves the contact point in `FxLayer` when the beat plays, because both cards may still
be mid-flight. Only the attacking side lunges, since an actuator cancels whatever the card
was doing and a blocker would be told to lunge and recoil at once.

## Surfaces and their rules

**Cards look like cards.** The illustration is the card (ADR 0011 *The card is the
illustration*); text sits on graded scrims whose darkness `tests/palette.test.ts` and
`e2e/legibility.spec.ts` guard. Art is fetched once at build time and served by this
application (ADR 0012 *Art fetched once, served locally, never upscaled*), so the board
renders with the network unplugged; a card with no printing gets a deliberate no-art
plate. Every dimension on a face is a ratio of `--card-w`, so one component renders on
an opponent's board, in hand and in the preview with no separate styles. Card type is a
glyph and a type line, not a tint; colour identity keeps the frame. Mana symbols are the
vendored SVGs under `public/symbols/`, drawn by `ManaSymbol` on every surface that shows
notation; a code with no SVG falls back to a disc and `e2e/cycle3.spec.ts` fails the run
if any does.

**Identical permanents stack** (`logic/stacking.ts`). `stackKey` includes everything that
makes two permanents behave differently — tapped, damage, counters, sickness, attacking,
blocking, attachment, commander-ness, controller — so an untapped Forest never hides
behind a tapped one. `splitActionable` pulls out any member a legal action names, so a
stack can never bury a choice. Hidden members stay mounted, because unmounting would
destroy their `layoutId` identity.

**OpeningHand** owns the first decision. The hand is the screen; `logic/openingHand.ts`
computes the arch once per resize and takes no selected index, so moving the ring moves
nothing (`tests/openingHand.test.ts`). Only the selected card prints its rules. `A` is
bound scoped to the card stops and stands aside on the Keep plate; a card's own click
stays "select", because **a mouse click must never commit a game by clicking a card it
only wanted to read**. Both halves of a London mulligan route here through
`mulliganPhase`, which reads the engine's `purpose` tag rather than the prompt text.
`ownsDecision` in `PromptDialog.tsx` is what `ActionPanel` reads to stand down, a wider
question than `isModalDecision`; getting that split wrong renders keep and mulligan twice.

**ChoiceCombo** takes over a prompt with more than `COMBO_MIN` options
(`logic/promptFilter.ts`) when no option carries a card face. **Only the Choose button
carries an action id**, bound to the highlighted row, so the panel invariant reads one
action rather than hundreds and `e2e/full-game.spec.ts` can answer the prompt. A row's
`onFocus` is what highlights it, so the ring's landing and a mousedown both do the job;
horizontal presses page via `padnav`. On a pad or a handheld the ring **starts on the
first row, not the filter field**: a focused input deadens the arrow keys standing in for
the d-pad, and on a Steam Deck it raises the on-screen keyboard. The field is one press up.

**Attack and block helpers share `logic/fight.ts`.** `autoAttack.ts` mirrors
`autoBlock.ts` tier for tier, and both ask the same two questions of the same model —
deathtouch and first strike are modelled because they change who dies; the file says
what is not and why. A keyword modelled in one and not the other is two buttons
disagreeing about the same two cards. "All attack" stages and does not submit, so it is
safe on a hotkey; `X` commits whatever `commitmentFor` names and goes quiet rather than
reaching past a disabled "All defend".

**Hidden information in the UI** ([api.md](api.md#hidden-information) owns what is sent).
The library is never a button: `ZonePile` renders it static, and only a revealed top card
makes it readable. An opponent's hand opens as a peek that shows only `hand_revealed`
and counts what is still unaccounted for (`ZonePeek`); a `ZonePile` is a button wherever
the zone can be opened, because a decorative pile would make the graveyard unreachable
without a keyboard. Which ability a press asks for is `logic/abilities.ts`: one untargeted
ability activates, one targeted enters targeting, several open `AbilityMenu`, whose ids
stay on the panel rows. A hand card with two ways to be played asks the same way — a shock
land's two land drops, a modal double-faced card's spell and land — and `HandFan` marks it
with the green `rune--ways` badge before it is pressed.

**The lobby** (ADR 0019 *A pod is seats with symmetric readiness*). `logic/lobby.ts` holds
the predicates so they test without a DOM; `canStart` and `whyNot` answer the same
question and `tests/lobby.test.ts` asserts on both together in every case, because a
button and its explanation disagreeing is worse than neither. Seats are named by the
server after their chair; there is no name field, because typing with a controller is
the last text box a pad can get stuck in. `CommanderCard` adapts `GET /api/cards/{id}`
into the `CardView` that `CardFace` takes and puts a `podcard` class on it, which
`styles/lobby.css` re-boxes to `--card-w`, so a face-up seat and a face-down back are
the same rectangle.

**The phase ribbon** keeps every step label in the DOM whether or not its phase is
expanded, which is what keeps the marker's `layoutId` continuous across a phase boundary
and what `e2e/acceptance.spec.ts` counts.

## Two contract gotchas, and one about the dev server

Both are handled once, in `logic/labels.ts`, and should never leak further:

- `step` arrives UPPERCASE (`"DECLARE_ATTACKERS"`) while `phase` in the same payload is
  lowercase (`"precombat_main"`).
- `commander_tax` and `commander_damage_taken` have **string** keys in JSON, so a lookup
  is `[String(pid)]`.

Also: events carry the snake_case card id, not the printed name. `useGame` harvests a
`card_id -> name` map from every zone it sees so the log reads "Sol Ring", not
"sol_ring"; `prettyCardName` is the fallback.

**The dev server binds IPv4 explicitly.** `vite.config.ts` pins `host: "127.0.0.1"`.
Vite's default is `"localhost"`, which Node resolves to `::1` and binds IPv6-only — so
Playwright's health check, curl, and the engine's CORS origin list all get connection
refused against a server that is plainly running.

## Storybook conventions

[testing.md](testing.md) owns why there is a browser story project and what it gates;
this is the set of rules a story has to follow.

- **Every story declares a `mount`, and the decorator throws without one.** `bare` and
  `screen` are valid answers; they have to be answers. `src/testing/mounts.tsx` holds the
  app's own wrapper chains by class name, so every size comes out of the stylesheets
  rather than being restated. **A layer may not state a size.** It may say two things:
  grid placement (every layout container is a grid whose other tracks are filled by
  siblings the story does not render) and a value the app sets from JavaScript
  (`--card-w` on a lane, through the same `cardWidthVar`). `fill` supplies an empty
  stand-in for a sibling the component is sized against.
- **Expected sizes come from `src/testing/appGeometry.ts`**, each citing the rule it
  comes from, and `expectMountedLike` compares a rendered box against those rather than
  against the mount that produced it. Sizes derived from `vh` are asserted as
  relationships, because the preview iframe is not the window.
- **Motion runs twice.** The runner gets `reducedMotion="always"` and the browser gets
  the real springs, split by the flag `.storybook/vitest.setup.ts` sets.
  `parameters.commanderblitz.motion: "real"` opts a story back in — a hover that scales
  is a transform, so holding motion still removes the thing under test — and such a story
  waits with `settled()` from `testing/asserts.ts`, since a transform merely existing
  returns on the spring's first frame.
- **The rest of `parameters.commanderblitz`**: `ui` seeds the store, `query` pre-loads
  react-query, `art` picks the art source, `zoomLock` opts out of the pinned zoom for the
  stories that exercise the solver. Fixtures are under `src/testing/`:
  `fixtures.ts` for DTOs, `cards.ts` for a real pool, `scenarios/` for whole positions,
  `pods.ts` for lobby states, `fakeGame.ts` for a `useGame` stand-in, and `asserts.ts` for
  `expectUniqueActionIds`, the invariant most worth sharing.
- **The toolbar globals** are `input` (mouse, keyboard, pad), `handheld` (desktop or
  handheld; stamps `data-desktop` or `data-handheld`), `hints` (the hint bar, reviewed on
  because stories read it) and `art` (stub, live, none). Stub art is deterministic and
  offline; `live` needs uvicorn.
- **The a11y addon reports and does not fail** (`a11y: { test: "todo" }` in
  `preview.tsx`); ADR 0006 *Colour accessibility is out of scope* is the decision behind
  the contrast half of that. Backgrounds are disabled because `theme.css` owns the ground.
- **`tests/imports.test.ts`** fails the build if production code imports anything under
  `src/testing/`, or if a story still carries the old `frame:` key that a loosely typed
  `parameters` would let pass as a silent no-op.

Two Biome notes that are conventions rather than defects: `a11y/useSemanticElements` is
off because it pushes `role="dialog"` toward a native `<dialog>`, which cannot be driven
by an exit animation; and the stylesheets carry a file-level `noDescendingSpecificity`
suppression, because their source order *is* the cascade and reordering to satisfy the
lint would change which declaration wins.
