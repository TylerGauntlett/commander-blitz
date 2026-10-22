---
id: phone-modality
title: A phone modality
area: play
effort: L
impact: high
why: a phone is the one device every player always has, and today the site breaks on it
depends_on: [selection-model]
status: proposed
---

## Today

Phone is a tier under handheld, not a mode: `phone.css` lowers the
handheld floors and restacks the table under `data-phone`, and everything
else assumes the Deck ([client.md](../client.md#layout-modes)). The input layer
knows mouse, keyboard and pad, and every way to *read* a card is one of them:
hover for a pointer, `Y` or the ring for a pad. Drag is a pointer gesture
over drop zones sized for one. The floors, the press budgets and the
legibility spec are measured at the Deck's panel in landscape, there is no
phone story global and no phone Playwright project, so nothing fails when a
phone layout breaks, which is why it does.

## The change

**Phone is a fourth layout mode and touch is a fourth input mode**, each a
peer of the three that exist rather than a squeeze of the handheld one.

- **Layout, portrait first.** The viewer's mat is the board and the
  opponents are a strip of orbs that open a seat on a tap, which the
  compact layout's "the viewer's board is the only board" rule already
  allows. The hand is a drawer and the action panel is a bottom sheet, so
  the commit control is always under the thumb. Safe-area insets are
  tokens in `theme.css`. The zoom-fit solver gets portrait inputs and keeps
  its one rule, that it reads only what cannot move
  ([ADR 0014](../adr/0014-measured-numbers-invariant-relationships.md)), and
  nothing changes size with game state ([ADR 0016](../adr/0016-nothing-changes-size-with-game-state.md))
  holds on a screen where that is most tempting to break. Landscape is a
  second layout of the same mode, not the handheld layout.
- **Touch, as `data-input="touch"`.** There is no hover, so a tap selects
  and a second tap or a long press reads (`input/longPress.ts` exists for
  the pad and gets a second caller); the targeting hint and the "why not"
  reasons move into the sheet; no ring is drawn and no glyphs. Drop zones
  grow under a finger. The invariant of
  [ADR 0015](../adr/0015-every-legal-action-is-one-control.md) is untouched,
  because the sheet is the panel: every legal action is still one control,
  exactly once. A hit-target floor for a thumb joins the floors.
- **Stories per device.** The Storybook toolbar's handheld
  on/off becomes a viewport global: desktop, the Deck, and a matrix of
  popular phones named by Playwright's device descriptors rather than by
  pixel counts, each in portrait and landscape.
- **A `phone` Playwright project** on the same descriptors, walking the
  handheld journeys with tap budgets in place of press budgets, and one
  full game on each device.

Do it after the selection audit, not before: touch is one more column in
that audit's table, and a sheet built on surfaces that are about to be
unified would be built twice.

## Gate

The floors of [ADR 0013](../adr/0013-handheld-floors-are-ci-gates.md)
asserted per viewport in the story project and in the `phone` e2e project;
the legibility spec per viewport; `tests/breakpoints.test.ts` holding the
new query to its stylesheet as it holds the two today; no horizontal
scroll, every stop reachable by tap, and every decision answerable from the
sheet, each as an e2e assertion on each device.
