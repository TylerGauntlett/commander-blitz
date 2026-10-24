# ADR 0025 — A phone is a layout mode and touch is an input mode

**Status:** accepted

## Context

The client had three layouts that nested. A phone was a handheld whose
floors were too big for it: `<html>` carried `data-handheld` and
`data-phone` together, everything `styles/handheld.css` said about the
Deck applied, and `styles/phone.css` lowered the floors and restacked the
table on top. `tests/breakpoints.test.ts` asserted the nesting outright: a
phone size was always a handheld size, "because the tier is additive".

The nesting made the cheap thing easy and the right thing invisible. A rule
written under `[data-handheld]` for the Deck landed on every phone with no
one deciding it should, so the phone layout was whatever the Deck's rules
left behind after `phone.css` had pushed back. The floors, the press
budgets and the legibility spec were measured at the Deck's panel; there
was no phone story global and no phone Playwright project, so nothing
failed when a phone layout broke.

Input had the same shape. `input/inputMode.ts` knew mouse, keyboard and
pad, and a finger arrived as a mouse: `pointerdown` wrote `mouse` whatever
its `pointerType`. Every way to read a card was hover (a pointer) or `Y`
and the ring (a pad), and a phone has neither.

## Decision

**The layout is one of three peers.** `logic/breakpoints.ts:layoutModeForSize`
returns `desktop`, `handheld` or `phone`, and the phone query is asked first,
so a size is exactly one mode. `App.tsx` stamps it as `<html data-layout>`;
Storybook stamps it from the viewport global. React reads it through
`state/useHandheld.ts:useLayoutMode`, which honours the stamp before the
query, as `useHandheldLayout` did.

**What the compact modes share is named for what it is.** The structural
rules both small screens use (the viewer's board as the only board, seats
as orbs, the tool strip in the foot) are keyed on `data-compact`, which
`App.tsx` stamps for `handheld` and `phone` alike. A rule that belongs to one
mode is keyed on `[data-layout="handheld"]` or `[data-layout="phone"]`.
`data-handheld` and `data-phone` no longer exist, so a Deck rule cannot
reach a phone by accident: whoever writes one has to say which.

**Floors are per mode, in one table.** `logic/floors.ts:FLOORS` holds the
type, card and hit floors for `handheld` and `phone`, and both the story
asserts (`testing/asserts.ts`) and the e2e gate (`e2e/handheldAssert.ts`)
read the row for the mode the page is in. The phone row's type and card
floors are the ones `styles/phone.css` and `logic/cardSize.ts` already
solved to; its hit floor is a thumb's.

**Touch is a fourth input mode.** A `pointerdown` whose `pointerType` is
`touch` writes `touch`, last input wins, and a pointer move made by a finger
cannot write `mouse`. The Settings card offers `touch` as a scheme a player
can pin. Under touch nothing draws a ring, a glyph or the hint bar, and a
tap does what a click does. A tap on a card with nothing to do selects it,
so its "why not" can be read; a tap on the selected card, or a long press on
any card, opens the full card view.

**On a phone the action panel is the sheet.** The targeting hint and the
"why not" of a hand card are portalled into it, so they are said where the
thumb already is. A portal moves the one node, so
[ADR 0015](0015-every-legal-action-is-one-control.md) holds: every legal
action is still one control, exactly once.

**Devices are named, not measured.** `testing/devices.ts` names the phones
the gates run on by their Playwright descriptors, and holds by hand the one
Playwright does not ship, built from the maker's published screen. The
Playwright config and the Storybook viewport global both read it, so a
story and an e2e spec on "the iPhone 15" are on the same size.

## Consequences

- **A rule under `[data-compact]`** reaches both small screens and is the
  place for structure; a rule about a floor, a token or a budget there is a
  rule written for one mode and applied to two.
- **Bringing back nesting** (a phone stamping the handheld mode as well)
  would pass every Deck rule to every phone again. `tests/breakpoints.test.ts`
  asserts every size has exactly one mode.
- **The phone has its own gates**: the floors per viewport in the
  `storybook-phone` project and the `phone` e2e project, tap budgets in place
  of press budgets, and no horizontal scroll. A phone layout that breaks
  fails CI.
- **Touch never draws a ring.** The ring exists to say where a cursor with
  no pointer is; a finger is its own pointer. The e2e gate asks for a ring
  only under `pad` and `keyboard`.
- **A tap is still a click.** The select-first rule applies only to a card a
  tap could do nothing with, so playing a land is one tap on a phone as it is
  one click on a desktop.

## Rejected

- **Squeezing the handheld layout further.** It is what `phone.css` was, and
  every Deck rule it did not know to override was a phone bug in waiting.
- **A second component tree for phones.** The board's structure is the same
  idea at every size; a fork would put the one-control rule in two places.
- **Treating touch as mouse.** A finger cannot hover, so every read that
  hover offered was unreachable, and a "why not" that only appears on hover
  was never said on a phone at all.
- **Pixel sizes in the stories and specs.** A size with no device behind it
  drifts from the phones people hold; a descriptor names the device.
