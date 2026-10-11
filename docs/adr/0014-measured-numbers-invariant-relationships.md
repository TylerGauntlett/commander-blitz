# ADR 0014 — Numbers are measured, relationships are invariants, budgets are ceilings

**Status:** accepted

## Context

An assertion about content passes happily through a layout failure. Text can
render at a fraction of a readable size and still be found by its label; a panel
can flatten to zero height and still contain its buttons; `overflow: hidden` on
the body makes a page report that nothing scrolls while content runs under the
foot. Every one of these happened here, and in each case the suite was green and
a screenshot looked right.

The design rounds met the same problem from the other side and wrote their own
gates, and several of those gates were wrong in instructive ways: a one-sided
ceiling on an animation's settle time was satisfied by making the animation
violent; a tolerance of one pixel in an overflow check approved a visible
ellipsis; a uniformity gate proved only that the noise was evenly spaced.

When the layout later moved on purpose, the desktop suite's numbers had to move
with it, and the question of which assertions may move and which may not needed
an answer that was not "whichever ones fail".

## Decision

**A stated design number is asserted, never eyeballed — and the suite
distinguishes three kinds of assertion, each with its own rule for change.**

- **A relationship is an invariant.** Nothing under the foot; no panel
  flattens; action ids are unique; the bands run creatures, globals, lands; the
  dial overlaps the portrait; the viewer's bands do not drift as permanents come
  and go. These stay byte-identical across any layout change and must keep
  passing. **A failing relationship assertion is a regression, never a new
  baseline.** `frontend/e2e/layout.spec.ts` is mostly this kind.
- **A bare number is a measurement.** A change may move desktop geometry. When
  it does, each bare number is re-taken once, in one commit, with the old value,
  the new value and a one-line reason in the diff. An assertion whose surface
  stopped existing is rewritten, not re-taken.
- **A budget is a ceiling.** Press budgets per journey (`frontend/src/testing/journey.ts`,
  asserted by `frontend/src/components/game/Journeys.stories.tsx` and against a
  real engine by `frontend/e2e/journeys-handheld.spec.ts`) are `<=`, never exact:
  an exact count fails on an improvement, which is the wrong direction to be
  strict in. Timing goldens in `frontend/tests/timing.test.ts` are the same
  shape, held against both the pre-work numbers and the current ones so a
  hundred milliseconds of drift at a time fails rather than rots.
- **An animation gate has a floor and a ceiling.** The front door's spring was
  gated on a minimum traverse (fewer than a few frames is a cut), a maximum
  settle and a maximum overshoot, because the ceiling alone rewarded the failure
  it existed to prevent.
- **"Fits" and "big enough" are two questions.** The floors answer the second
  (see [ADR 0013](0013-handheld-floors-are-ci-gates.md)). `frontend/e2e/deckfit.spec.ts`
  answers the first by asserting `scrollHeight === clientHeight` on every
  container in a played-in game, and runs at two handheld widths because enough
  findings appeared at exactly one of them that they are not interchangeable.

How to measure, so the number means what it says:

- Measure the element, not the class name, and measure after the render.
- Inside a scroll container only the cross axis is an escape; outside one both
  axes are. Check the last lane's bottom against the foot's top, not the mat's.
- Read font sizes unscaled and boxes through the stage scale; backwards, a
  floor passes type that fails on the device.
- `getBoundingClientRect` of a rotated element is its axis-aligned box.
- A clipped element still reports its own full box; walk the ancestors.
- No tolerance in an overflow check: `text-overflow` fires at the first pixel.

## Consequences

- A screenshot is not evidence for anything these gates cover. The two bugs the
  card round's gates caught — a face that collapsed inside an auto-height card
  and left a band of empty stock, and a name band compressed to one line —
  both looked like padding.
- Deliberate geometry changes cost a commit of re-taken numbers. That is the
  price of being able to tell a decision from a regression in the diff.
- A new number on a surface comes with its assertion, or it is not a design
  number, it is a guess.
- Two viewports double the fit gate's run time. Accepted; see the finding above.

## Rejected

- **Snapshot everything and accept whatever changes.** A snapshot cannot tell a
  moved number from a broken relationship; it makes every failure a new baseline.
- **Exact press counts.** A journey that gets shorter would fail.
- **Tolerances to absorb rounding.** A tolerance in an overflow check is a
  licence for an ellipsis. Rounding is handled by what is measured, not by
  widening what passes.
- **A single viewport for the fit gate**, on the grounds that the width
  difference is small. It was the width difference that found the bugs.
