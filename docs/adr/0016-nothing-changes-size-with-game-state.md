# ADR 0016 — Nothing the player is looking at changes size because of game state

**Status:** accepted

## Context

A collapsing slot moves the board under the cursor. The viewer's empty lane used
to collapse to a strip, so playing a first creature shoved the land row down by
a card and killing it shoved the row back up — on the one mat that owns every
drop target, mid-decision. The orb's mana row appeared and vanished with the
mana, re-spacing the whole column several times a turn. An opponent's loss line
appeared as a new row, stretched every sibling mat and moved the viewer's board.
The commit button's label changed width with its count, so it re-centred under
the thumb. The hint bar echoed an unbounded string that wrapped onto a second
line, grew the foot and lifted every tool button. The opening hand's mockup
grew the selected card and closed the others around it, so the one thing
holding still was the card you were trying to read, and everything else moved.

Each of these was locally reasonable. Each put the board in motion for a reason
that was not the player's.

## Decision

**Reserve the space. A slot that can be empty is drawn at its full size, empty.**

- **The viewer's lanes are always rendered at a full card's height**, empty or
  not. That is dead space bought deliberately; what it buys is the board holding
  still. Opponents' lanes have a fixed height (`--pod-lanes-h`) and scroll
  inside it, so hiding an empty one moves nothing.
- **The pod's lane box is a function of the viewport and the seat count alone**
  — `solvePodLanesHeight` in `frontend/src/logic/zoomFit.ts` takes the table
  height, the CSS floor and a seat count, and its signature is the argument. A
  box that read any measured height would move when the hand changed the foot,
  once per card played.
- **The orb's mana panel is permanent.** It sits on a plate in `.orb__foot`
  with the zone piles, so the column's slack lives in one gap, and an empty
  panel says `—` (`orb__none` in `PlayerOrb`).
- **An opponent's seat is a fixed grid** (`--seat-h` in `frontend/src/styles/seat.css`)
  whose rows are pixels that add up to the seat, with no row that can appear.
  The loss state is a filter and a mark, and the loss reason takes the commander
  name's slot.
- **The commit label never changes width** — `Attack`, not `Attack with N`; the
  count is the number of filled rows — and `CommitDock` renders its `.commit-note`
  line in every mode, with a minimum height, so the rail's bottom never moves.
- **The opening hand's positions are computed once per resize** and take no
  selected index (`handRow` in `frontend/src/logic/openingHand.ts`); moving the
  selection touches `zFor`, one attribute and one custom property. Only the card
  you are on prints its rules; the others close the box and let the illustration
  absorb the space, so every card is the same size either way.
- **Lobby plate rows are given a height** (`--name-h`, `--meta-h` in
  `frontend/src/styles/lobby.css`), because your chair carries a field where the
  others carry a label, and a field is the taller box. A plate is read across as
  much as down.
- **`scrollbar-gutter: stable`** on every list, stack and rules box that can
  grow a scrollbar, so the bar appearing does not re-wrap the text beside it.
- **A dialog holds one width** while it has a combo in it; a label naming the
  highlighted row must not decide the panel's width.

## Consequences

- `frontend/e2e/layout.spec.ts` fails the run if any of the viewer's bands
  drifts relative to the mat over a game, and asserts the pod box is independent
  of card size. `frontend/tests/openingHand.test.ts` pins that the arch takes no
  selection, because a screenshot cannot show it. `PodLobby.stories.tsx`
  measures the row tops across all four plates.
- The asymmetry is deliberate and was measured: opponents still drop their
  empty lanes, because a permanent empty global lane wrapped their creatures
  onto a second row and pushed the viewer's board down — the opposite of the
  intent. Their lanes are height-fixed, so the drop is now a width argument only.
- Dead space is a real cost at the small viewport. It is paid where the cursor
  is and refused where it is not: the viewer's mat reserves, a seat's sheet does
  not.
- A new conditional row — a warning, a status, a count that is sometimes zero —
  is a slot, authored at its full size with an empty state. A row that mounts on
  a condition reverses this decision.

## Rejected

- **Animate the collapse** so the move is smooth. A smooth move of the drop
  target under the cursor is still a move.
- **Put the count in the label** because it is useful. It is useful; it goes on
  a line that is always rendered.
- **Solve the pod box against a measured container**, which no card size can
  move. The container's height moves with the hand. Only the viewport and the
  seat count cannot.
- **Grow the selected card** in the opening hand. It reads better in a still
  and worse in use.
