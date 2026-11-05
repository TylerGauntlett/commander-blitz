# ADR 0028 — A short handheld lays out at the Deck's height

**Status:** accepted

## Context

The handheld layout is written in CSS pixels against a Steam Deck's panel.
The floors in `logic/floors.ts`, the card floor in `logic/cardSize.ts`, the
seat strip, the tool row and the hand's reserve in `state/useZoomFit.ts` are
all stated in px, and together they need the Deck's height to fit. The
handheld query (`logic/breakpoints.ts:HANDHELD_QUERY`) also takes in screens
much shorter than that: everything taller than the phone query, such as a
tablet or an unfolded phone held sideways.

On those screens the fixed pieces kept their size and the viewer's own row
was what gave. The seat panel and the lanes were clipped under the hand,
and nothing failed, because every handheld gate ran at the Deck's size.

## Decision

**A screen in the handheld band that is shorter than the Deck is laid out at
the Deck's height and scaled to fit, through the viewport tag.**
`logic/viewportScale.ts` decides: the scale is the screen's height over
`HANDHELD_DESIGN_H` for a handheld-band size below it, and 1 for every other
size. `state/viewportFit.ts`, imported by `main.tsx` before the first render,
writes the tag with an explicit width and puts the natural tag back whenever
the screen changes under it, so the scale is always solved from the screen's
real size.

The floors stay as they are. A touch device's CSS pixel is physically larger
than a Deck's, so the Deck's layout drawn a little smaller on one is still at
least as large in the hand as on a Deck.

## Consequences

- **The Deck, a desktop and every phone are untouched.** Their tag is the
  one `index.html` ships, and `tests/viewportScale.test.ts` holds that.
- **Only engines that read the viewport tag are fixed.** Mobile Safari and
  mobile Chrome do. A desktop browser ignores the tag, `viewportFit` notices
  that the height did not move and stops, and a desktop window that small is
  the player's to zoom.
- **Measurements stay in one space.** Under a viewport scale, `innerHeight`,
  every element box, every media query and every pointer coordinate are in
  the same CSS pixels, so the fit solver, the drop hit-test and the effect
  anchors need no change.
- **The gate is `e2e/deckfit.spec.ts`**, which runs a mobile engine at two
  sizes shorter than the Deck and asks for the design height and no
  scroller.

## Rejected

- **Lower floors below the Deck's height.** This would draw a worse Deck on
  a screen that is physically larger, and every px literal across the
  handheld sheets would have to scale with it.
- **CSS `zoom` on the root.** The engines disagree about what element boxes
  and pointer coordinates report under it, and the fit solver, the drag
  hit-test and the effect anchors all mix the two.
- **Sending those screens to the phone layout.** They are not phones. The
  phone layout is written for 600px wide, and on these screens it would
  give up the board the Deck layout can show.
