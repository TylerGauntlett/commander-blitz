---
id: draw-replacement-effects
title: A draw replaced by something other than more draws
area: cards
effort: M
impact: low
why: Abundance in the Tyranid Swarm precon and every 'if you would draw a card, instead…' card wait on it
depends_on: []
status: proposed
---

## Today

Every draw goes through `replacements._draw_one`, which offers the draw's
replacements one at a time (616.1): the Narset cap, dredge
(`replacements._dredge`), the empty-library `replace_empty_draw` static
(`player_statics.empty_draw_replacements`, which may carry `effects` run inside
the draw, Out of the Tombs), and the `replace_draw` static
(`player_statics.draw_replacements`), which reads only a `draw_multiplier` and
turns one draw into that many. Nothing replaces a draw from a non-empty
library with effects of its own. [rules-coverage.md](../rules-coverage.md#not-implemented)
lists it under "A general replacement system": "replacements that do
something other than draw more" are engine work, not a card key.

So Abundance ("If you would draw a card, you may instead choose land or
nonland and reveal cards from the top of your library until you reveal a card
of the chosen kind…"), the card in the Tyranid Swarm precon that found it, has
no expression. Its gap record is `data/authoring/gaps/abundance.json`
(capability `draw_replacement_effects`).

## The change

1. `replace_draw` accepts `effects` in place of `draw_multiplier`, with an
   optional `may` ("you may instead"): the effects run inside the draw, the way
   `_replace_empty_draw` runs Out of the Tombs', and the draw does not happen,
   so `cards_drawn_this_turn` is not bumped and miracle is not offered.
2. `_draw_one` offers an effects replacement in the same pass as dredge, before
   the doublers, so the affected player's 616.1 choice between them is asked
   over the sources (the `ask_objects` pattern `_replace_empty_draw` uses); a
   declined `may` falls through to the next replacement and then the draw.
3. The loader refuses `effects` beside `draw_multiplier` on one static.
4. Harvest Abundance with `/author-cards`, then one wave over the catalog's
   other "If you would draw a card, … instead" cards the change reaches.

It does not build the general replacement system (616) the rules-coverage
line names: no event object and no "replaced by" chain, only one more named
hook on the draw.

## Gate

A unit test under `tests/unit/players/` for the replaced draw: the effects
run and no card is drawn, a declined `may` draws normally, the replacement
applies once per draw (614.5) when two cards are drawn, and the choice between
it and dredge is offered. Abundance passes the six authoring gates in
`tests/cards`.
