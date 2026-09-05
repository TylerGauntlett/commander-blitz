# ADR 0006 — Colour accessibility is out of scope

**Status:** accepted

## Context

Greyscale legibility had become a hard gate on UI work here, without anyone
having decided that it should be.

It arrived as a review habit — take a screenshot, apply `filter: grayscale(1)`,
see what is left — and then grew teeth. `frontend/e2e/greyscale.spec.ts` failed
the run if a card face rendered without a type glyph. Every mockup carried a
`g`-to-desaturate key and shipped a `-grey.png` twin beside its colour shot.
Every mockup comparison table had a **Survives greyscale** row in it.
`cards.css` graded seven type fills across a luminance ladder and
`tests/palette.test.ts` asserted the spread. Roughly forty source comments
justified a styling choice by what a colour-blind player or a monochrome capture
would still receive.

By the end it was not a check, it was the deciding argument. the design record (`docs/design-record.md#board-themes`)
called the greyscale twin "the verdict" for the board direction and rejected
menu 05 on it. `docs/roadmap.md` ranked the two most urgent open UI defects as
"both greyscale failures". A criterion nobody had signed up for was vetoing
design directions.

## Decision

**Colour accessibility is not a consideration for this project.**

Concretely, UI work here does not need to:

- provide a redundant non-colour channel for anything;
- survive a `grayscale(1)` capture;
- satisfy WCAG contrast ratios or any colour-vision-deficiency criterion.

Colour may be the sole carrier of a distinction. No test, review checklist,
mockup comparison or design doc should gate on any of the above, and a review
finding whose only content is "this reads in colour alone" is not a finding.

**Plain legibility is still a gate, and it is a different thing.** The card is a
full-bleed illustration with white text on graded scrims over a crop nobody
chose, so the scrim-darkness floor in `frontend/tests/palette.test.ts` and its
resolved-value counterpart in `frontend/e2e/legibility.spec.ts` stay, as does the
frame-width floor at pod size. Those hold regardless of anyone's colour vision;
they are about text over an unknown photograph and about a ~51px card.

## Consequences

**Good.** Design choices get argued on their merits at the sizes cards actually
render, rather than against a monochrome proxy for those sizes. The removed
suite, the sixteen screenshot twins and the toggle in fifteen mockup files stop
costing maintenance. Two open defects that were stated as greyscale failures —
the `--playable` rim and the combat arrows — turned out to have real non-colour
cores (both are thin strokes over a board of illustrations) and are now stated
that way, which is a better description of what is actually wrong with them.

**Bad, and it is a real cost.** This application is meaningfully worse for
players with colour-vision deficiency, and for some of them unusable: attack
assignments and castability are now carried by hue alone with no committed
fallback. Roughly one man in twelve has some red-green deficiency, and Magic's
five colours put red and green on opposite sides of the most common one.

Reversing this decision later is expensive in a way that keeping the gate was
not. Colour accessibility is cheap to maintain incrementally and costly to
retrofit: with no test watching, every surface built from here on can quietly
acquire a colour-only encoding, and picking that apart means auditing all of
them rather than catching each regression as it lands.

## Alternatives considered

**Keep the gate.** Rejected. It was never a stated product requirement, and it
had been quietly promoted from a review habit to a veto over design directions —
which is the thing that actually prompted this decision.

**Keep it as advice, not a gate — drop the tests, keep the guidance.** Rejected.
That is roughly the state this project was already in: the greyscale check had
"no automated form" for two full playtest cycles and was treated as binding
anyway. An unenforced criterion that still appears in every design comparison
table gets treated as a requirement by the next person to read it. If it is out
of scope, it has to be out of the documents too.
