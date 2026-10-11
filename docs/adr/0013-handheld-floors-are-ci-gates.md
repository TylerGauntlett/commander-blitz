# ADR 0013 — Handheld floors are CI gates

**Status:** accepted

## Context

The board rendered at a Steam Deck's panel was measured before anything was
designed for it. Most of what was on screen was below any readable size; the
smallest text was a decoration in the shape of a word. Hover was the only route
to several things, including a large number of native `title` tooltips, and
there was no cursor at all — every card was focusable and nothing drew focus.

A screenshot of that board looked fine. A reviewer already knows what the label
says, so an unreadable label reads. That is why the handheld round's first
principle was that a stated design number is measured and not eyeballed, and why
the floors it settled were taken as hard constraints before any layout was
drawn. They then turned out to decide the layout rather than decorate it.

## Decision

**Four floors, held as constants and asserted in CI at the device's viewport.
Nothing ships below them.**

The floors live in `FLOORS` in `frontend/e2e/handheldAssert.ts`: a minimum font
size for anything carrying information, a minimum box for anything focusable or
tappable, a minimum width for any card the ring can land on, and a minimum ring
width. They are asserted at every reachable state by the `handheld` Playwright
project (`frontend/playwright.config.ts`) and, from fixtures, by the
`storybook-handheld` Vitest project (`frontend/vite.config.ts`), which runs every
story tagged `handheld` at the panel's size. Both are separate projects rather
than a second viewport on the desktop ones, because the desktop numbers must not
move and would.

What the gate holds, beyond the four numbers:

- **The ring is solid.** Read the style, not only the width — `outline-width`
  with `outline-style: none` passed a width-only check.
- **At most one cursor**, and `ringLost` — the state names a stop, the stop is on
  screen, and it is not wearing the ring — never happens. Two amber rings at
  once is the one failure a controller UI may never have.
- **No native `title`.** A tooltip opens on hover and on nothing else, so on a
  controller it is information that cannot be reached. `frontend/tests/noTooltips.test.ts`
  bans the attribute; a mark's name lives on `aria-label` and `data-hint`.
- **A hit floor is a target, not a size.** The box is the floor; the ink is
  drawn smaller on a pseudo-element (`.ibtn::before` in `frontend/src/styles/lobby.css`).
  A disc grown to the floor in a row of small pips is the loudest thing on the
  plate.
- **The CSS fallback is the floor.** A `var(--x, 13px)` fallback put faces under
  the floor the moment the variable was unset; the fallback value is now the
  floor. `<small>` renders at a fraction of its parent and inherits instead.
- **Big screens spend room on content, not scale.** A wider panel draws more —
  opponents' actual creatures, a wider rail — and the floors do not move. A
  width that cannot afford the card floor does not get the mode.
- **Fits is a separate question from big enough.** `handheldAssert` also reports
  `overflowing[]` and `overBudget[]`, and `frontend/e2e/deckfit.spec.ts` asserts
  nothing scrolls, at two widths; see [ADR 0014](0014-measured-numbers-invariant-relationships.md).

## Consequences

The floors decide layout. Each of these is a floor applied, not a taste:

- **Seven readable cards do not fit on the panel at any layout**, so `OpeningHand`
  shows one card at a time and the rest follows.
- **A seat cannot hold its zone counts as targets** at the hit floor, so on an
  `OpponentSeat` the counts are marks and the seat itself is the stop; the
  seat's sheet is the route into any zone.
- **An opponent's hand is a button only when something is revealed.** The peek
  opened on a number already on the chip.
- **A new surface is authored at the floors**, not repaired to them. The old
  front door cleared the type floor by an override list; the shipped one sizes
  everything as `max(floor, …)` off a stage unit.
- **Rumble is always redundant with something visible.** It is best-effort on
  one browser and must never be the only channel.
- Do not ship a controller mode without the floors asserted in CI. Every one of
  the numbers caught something a screenshot could not.

## Rejected

- **Scale the desktop board down.** That is what was measured, and it is where
  the unreadable text came from.
- **A per-element override list** that lifts each offending size to the floor.
  The door had one. It covered every word on the screen but the wordmark, and it
  meant the surface's own stylesheet was wrong everywhere.
- **Floors as guidance.** An unenforced number in a design document is a
  requirement only until the next person needs the pixels. The floors are code,
  cited from one constant.
