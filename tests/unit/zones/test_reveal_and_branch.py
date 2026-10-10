"""Cards that look at the top of the library and then do one of two things.

The interesting part is not the reveal; it is that the branch reads *the card
that was revealed* rather than "is there a land in my library somewhere", which
is what a naive `exists` selector would have asked and what would have made
Coiling Oracle put a land onto the battlefield roughly always.

Both branches are pinned, because the sandbox the authoring verifier uses stocks
its library with basic lands and would only ever drive one of them.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import pass_until


def play_oracle(builder, top: str):
    game = (
        builder(players=2)
        .battlefield(0, ["forest", "island"])
        .hand(0, ["coiling_oracle"])
        .library(0, [top, "swamp", "swamp"])
        .build()
    )
    revealed = game.state.players[0].library[0]
    cast = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "coiling_oracle"
    )
    game.apply(cast)
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (d := g.pending()) is not None
        and d.kind is DecisionKind.PRIORITY,
    )
    return game, revealed


class TestCoilingOracle:
    def test_a_land_goes_onto_the_battlefield(self, builder):
        game, revealed = play_oracle(builder, "mountain")
        assert game.state.objects[revealed].zone is Zone.BATTLEFIELD
        assert revealed not in game.state.players[0].hand

    def test_anything_else_goes_to_hand(self, builder):
        game, revealed = play_oracle(builder, "grizzly_bears")
        assert game.state.objects[revealed].zone is Zone.HAND
        assert revealed in game.state.players[0].hand

    def test_it_is_the_top_card_that_decides_not_the_library(self, builder):
        """A nonland on top, lands underneath: the lands must not save it.

        `{"exists": {"zone": "library", "types": ["Land"]}}` would have been true
        here, and the card would have tried to put a creature onto the
        battlefield off the top of the library.
        """
        game, revealed = play_oracle(builder, "grizzly_bears")
        assert game.state.objects[revealed].zone is Zone.HAND
        assert not [
            o for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"
        ]


class TestTheSelectorChangeItNeeded:
    """A `binding` combined with filters narrows; alone it still passes through."""

    def test_a_binding_with_no_other_keys_is_unfiltered(self, builder):
        from commanderblitz.engine.effects.context import EffectContext
        from commanderblitz.engine.effects.selectors import resolve_pool

        game = builder(players=2).battlefield(0, ["grizzly_bears"]).build()
        bear = game.state.battlefield[0]
        ctx = EffectContext(state=game.state, controller=0, bindings={"it": bear})

        assert resolve_pool(ctx, {"binding": "it"}) == [bear]
        assert resolve_pool(ctx, {"binding": "it", "types": ["Creature"]}) == [bear]
        assert resolve_pool(ctx, {"binding": "it", "types": ["Land"]}) == []
