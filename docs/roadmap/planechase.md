---
id: planechase
title: "Planechase: the planar deck and planeswalking"
area: play
effort: L
impact: low
why: every card that planeswalks waits on it, TARDIS and Susan Foreman in the Blast from the Past precon among them
depends_on: []
status: proposed
adr: true
---

## Today

Planechase (901) is absent. A game is built from each seat's library and
commander; nothing in `engine/state.py` holds a planar deck, a face-up plane or
phenomenon, or the planar die, and no op in the DSL planeswalks (701.31) or
makes chaos ensue (901.9). `Zone.COMMAND` exists in `engine/enums.py` for
commanders and emblems only.

The Doctor Who precons print the action on ordinary cards, outside a
Planechase game: TARDIS ("you may planeswalk"), Start the TARDIS ("Surveil 2,
then draw a card. Then you may planeswalk.") and Susan Foreman ("If you would
planeswalk, instead…"), all gapped under `planechase`
(`data/authoring/gaps/tardis.json`, `start_the_tardis.json`,
`susan_foreman.json`). Missy and the "whenever chaos ensues" cards wait on the
chaos half of the same rules.

## The change

1. The ADR first: whether a game may carry a planar deck at all, and what a
   planeswalk instruction does in a game without one. 901.1 makes Planechase a
   variant, so in a game that is not one, "planeswalk" finds no planar deck and
   does nothing; the ADR records whether that is the whole of this item.
2. A `planeswalk` op that is a recorded no-op without a planar deck, and the
   `if you would planeswalk` replacement shape for Susan Foreman, so the
   Doctor Who cards can be written faithfully for a standard Commander game.
3. Only if the ADR chooses the full variant: a planar deck per game in
   `GameState`, the face-up plane in the command zone, the planar die as a
   player action, `planeswalk` and `chaos_ensues` events, and plane cards in
   the catalog. That step is its own pull request.

It does not add plane cards to any precon, and it changes no shipped deck.

## Gate

A unit test under `tests/unit/` per step: a `planeswalk` in a game with no
planar deck leaves the state unchanged and fires no trigger; the Susan
Foreman replacement is offered only when a planeswalk would happen. With the
full variant, a server test that a game started with a planar deck rolls the
die and turns over the next plane.

## Open questions

- **Variant or no-op.** Build the full Planechase variant, or only the
  instruction's meaning in a game without a planar deck? Recommended: the
  no-op first, because every card that found this prints the action in a
  Commander precon, and the site plays Commander, not Planechase.
- **Is a no-op a card that does nothing?** `card-dsl.md` refuses "a card that
  looks implemented and does nothing". Recommended: allowed here, because the
  rules give the instruction no effect without a planar deck (901.1), and the
  ADR says so.
