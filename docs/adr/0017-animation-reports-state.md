# ADR 0017 — Animation reports state; it never precedes or lags it

**Status:** accepted

## Context

The engine is authoritative and every mutation returns the new state, so there
are no optimistic updates; the client renders what the server said. Narration
sits on top of that: `logic/events.ts` turns each batch of events into timed
beats — numerals, spotlights, turn banners, shake, departures — and
`state/narration.ts` plays the queue.

Two failure shapes pressed on that arrangement. A `dies` beat that never once
drew anything, because it looked up the card's element after the board had
already stopped rendering it. And a combat exchange that played as a slideshow:
nine consecutive beats, each holding the board, during which nothing on the
board moved. The obvious fix for the first — let the battlefield lag so exits
can line up with the narration — would have broken everything else.

## Decision

**New state commits first. Animation is narration over a board that has
already changed, drawn in a layer the board cannot delete.**

- **State first, then beats.** `useGame.absorb` commits the response and then
  pushes its beats. The pump waits for the queue before requesting the next
  decision, so one decision's narration finishes before the next arrives.
- **Effects live in a sibling layer** (`FxLayer`, `ParticleLayer`) that a
  re-render cannot unmount, anchored by looking up `[data-oid]` in the live DOM
  when the beat plays. A card you cannot see is its owner's seat: a hidden end
  resolves to the seat's element, deduped, or draws nothing.
- **A departing permanent is a ghost, not an exit animation.** `Card` posts its
  box on unmount (`frontend/src/logic/cardRects.ts`); `CardGhost` is redrawn
  from that last box, held long enough to read why it left, and dropped into its
  pile. A wrath's departures are grouped per consecutive run (`Beat.exits`) and
  staggered inside one beat. A card with no recorded box draws nothing rather
  than inventing a position.
- **Effects inside a beat are concurrent** (`Beat.fx`, each with an `at`
  offset) and may outlive the beat's hold. The queue serialises *beats*; it does
  not serialise motion. A fight is one lunge and one contact, not a sequence.
- **Any input skips, and the gesture still counts.** A click while the queue is
  draining empties the queue, puts the board at rest, and does what was clicked.
  Only a genuine in-flight request gates input.
- **Motion is a setting.** `MotionConfig` honours the user's preference, and
  `frontend/src/fx/reducedMotion.ts` carries it to the particles, actuators and
  shake that cannot read context. Reduced motion drops "how it felt" and keeps
  "what happened": numerals, captions, flashes, the log.
- **No per-player playback speed control.** The value exists so
  `e2e/helpers.ts` can force `instant`; there is no way to set it in a game
  other people are waiting on.
- **One frame loop** (`frontend/src/fx/scheduler.ts`); actuators write motion
  values directly and never `setState` per frame; the particle pool is capped
  and drops new emissions at the cap rather than growing.

## Consequences

- Every `data-oid` anchor, drop target and legality check reads one board, the
  current one. A ghost is a picture; it has no id, takes no drops and is not a
  stop.
- The reason a card left outlives the animation in the log and in the notes
  under the graveyard and exile modals, so skipping loses nothing a player needs.
- `frontend/tests/timing.test.ts` holds every golden batch to both its old and
  current duration, so concurrency cannot quietly regress to a queue.
- Face resolution for a ghost goes by oid, then by card definition, then a name
  plate — tokens cease to exist on the way out and are in no zone when the beat
  plays, and token deaths are a large share of every game.
- A new effect is thrown from wherever the thing happened (`burst()` is
  importable anywhere) and registered with the scheduler; it must not assume the
  element it was aimed at still exists.

## Rejected

- **A lagged battlefield that syncs exits with narration** (`AnimatePresence`
  on the lane, or deferring the commit). The exit would fire while the queue is
  still on a beat from three events ago, so the card would fly before the
  narration said what killed it; fixing that means rendering a board the engine
  did not send, which desyncs every anchor, drop target and legality check in
  the app, holds a flex slot through the animation, cannot be cancelled by
  `skip()`, and collides on `layoutId` when a commander dies into a zone that
  does render a card.
- **Queue every effect** so the sequence reads clearly. It read as a slideshow
  in which nothing moved.
- **A playback speed control.** It changes only your playback while the table
  moves on at everyone else's.
- **Swallow the gesture on skip.** The board ignored the player for a second
  after every action, which is what made it feel like it needed spamming.
