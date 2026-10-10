# ADR 0015 — Every legal action is exactly one control

**Status:** accepted

[ADR 0002](0002-flat-action-space.md) is the engine's side: legality enumerates a
flat list of actions with opaque ids. This ADR is the client invariant that list
makes possible.

## Context

The server sends `LegalActionDTO`s with opaque ids and the client echoes one
back. The client never reconstructs a rules operation from a gesture, so desync
is structurally impossible: a gesture *selects* a legal action, it never *is*
one. That was the most important thing about the client from the start.

Two things tested it. First, the controller work: a pad has to reach everything
a pointer reaches, and a second routing table for "what A does on this kind of
stop" would drift from the pointer's. Second, a bug where the foot drew its own
list of remaining actions for a half-settled targeting while the panel drew the
same ids — two controls, one id — which escaped CI only because no shipped card
reached the branch, and manual mana reached it immediately.

## Decision

**Each legal action id is rendered once, as one control carrying
`data-action-id`, and every input path ends by activating that control.**

- **Three paths, one sink.** Drag a hand card onto a lane; click a card then its
  target; press the control in the panel. All three funnel into `act(id)`. The
  panel is load-bearing, not a fallback: it is what makes the game
  keyboard-reachable and the Playwright specs writable.
- **A click can answer half a question.** Picking a target narrows the selection
  to whatever still matches (`uiStore.narrowTargeting`) and the panel asks the
  rest. The foot says where to look; it does not render ids of its own.
- **A pad reaches nothing a pointer cannot.** `A` is `element.click()` on the
  focused stop (`frontend/src/input/useCursorNav.ts`), with no branch per stop
  kind. `X` commits the decision from wherever the ring is by clicking the
  control the panel already rendered (`frontend/src/logic/commit.ts`); the
  controls that stage rather than post — all attack, the attack slab — have no
  id and are pressed, not sent.
- **An id is emitted with its stop.** `actionAttrs(id)` in
  `frontend/src/input/stops.ts` returns both attributes, so "every legal action
  is a button, exactly once" and "every one of them is reachable" are equal by
  construction. `frontend/tests/stops.test.tsx` fails the build on a bare
  `data-action-id`.
- **The one exception is `choose_x`.** The engine offers every value the board
  can pay as a separate action. The panel draws a stepper (`XStepper`) and only
  the selected value carries an id. Nothing is duplicated and there is always at
  least one control, which is what the full-game spec depends on. The same shape
  answers a long `choose_type`: one Choose button carries the id for the
  highlighted row.
- **Surfaces that do not own the decision stand down.** `ownsDecision` in
  `PromptDialog.tsx` is what `ActionPanel` reads (its `standDown` prop); getting
  the split wrong renders keep and mulligan twice. A seat that takes the
  player-target action routes through `onSelect` and carries no id; nothing in
  the commander subtree carries one.
- **A portal moves a node, never duplicates one.** The tool strip is the same
  node in the foot that it was in the rail, so its ids, test ids and stops
  travel with it.

## Consequences

- `frontend/e2e/full-game.spec.ts` drives whole games by always clicking a legal
  action. If any decision kind has no surface in the UI the loop runs out of
  buttons and the spec fails, which is the bug most worth catching. A new
  `DecisionKind` arrives working through the panel's denylist switch, and gets a
  nicer surface later.
- `expectUniqueActionIds` in `frontend/src/testing/asserts.ts` is the invariant
  most worth sharing between stories and specs; `clarity.spec.ts` holds it
  across a whole game.
- A new input — a trackpad gesture, a voice command, a shortcut key — is wired
  by finding the control and clicking it. Adding a fourth path that posts an id
  directly is how the invariant breaks.
- Drag is a shortcut. A drop the server did not offer springs back and sends
  nothing. Nothing is decided by geometry.

## Rejected

- **The client constructs actions** from a gesture and the server validates.
  Every desync bug in every card game client is this.
- **A per-stop routing table for the pad.** It would be a second answer to "what
  does activating this do", and the two answers would diverge on the first stop
  somebody forgot.
- **A hidden panel when a richer gesture exists.** The panel is the gate's
  surface and the keyboard's; it is never hidden, only stood down by the surface
  that owns the decision.
- **A second control for the same id in a second place** (the foot's old
  `choice-list`), on the grounds that it is closer to the thumb. Closer is a
  layout problem; one id, one control.
