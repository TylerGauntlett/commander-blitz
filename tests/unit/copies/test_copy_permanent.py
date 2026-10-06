"""Tokens that are copies of something already on the battlefield.

The engine's object model is already a copy model: identity is `def_id` pointing
at a `CardDef`, and `is_token` is a separate flag. So a token copy is a token
whose `def_id` is the original's — and that is not a shortcut, it is the rule.
A copy copies the *printed card*, so the counters, damage and Auras piled onto
the original must **not** come with it. That is the property worth pinning,
because the cheap wrong implementation (clone the GameObject) would carry all
three and nothing on the board would say so.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from tests.conftest import pass_until


def copies_of(game, def_id: str, pid: int = 0):
    return [
        o
        for o in game.state.battlefield_objects(pid)
        if o.def_id == def_id and o.is_token
    ]


class TestWhatACopyIs:
    def test_it_is_a_token_with_the_originals_identity(self, builder):
        from automtg.engine.effects import execute
        from automtg.engine.effects.context import EffectContext

        game = builder(players=2).battlefield(0, ["grizzly_bears"]).build()
        bear = game.state.battlefield[0]

        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        list(execute(ctx, [{"op": "copy_permanent", "objects": {"self_only": True}}]))

        made = copies_of(game, "grizzly_bears")
        assert len(made) == 1
        got = chars(game.state, made[0].oid)
        assert (got.power, got.toughness) == (2, 2)

    def test_it_copies_the_printed_card_not_the_object(self, builder):
        """Counters and damage on the original are not part of the copy."""
        from automtg.engine.effects import execute
        from automtg.engine.effects.context import EffectContext

        game = builder(players=2).battlefield(0, ["grizzly_bears"]).build()
        bear = game.state.battlefield[0]
        game.state.objects[bear].counters["+1/+1"] = 3
        game.state.objects[bear].damage = 1
        game.state.bump_chars()
        assert chars(game.state, bear).power == 5

        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        list(execute(ctx, [{"op": "copy_permanent", "objects": {"self_only": True}}]))

        copy = copies_of(game, "grizzly_bears")[0]
        assert copy.counters == {}
        assert copy.damage == 0
        assert chars(game.state, copy.oid).power == 2, "a 2/2, not a 5/5"

    def test_a_copy_of_nothing_makes_nothing(self, builder):
        from automtg.engine.effects import execute
        from automtg.engine.effects.context import EffectContext

        game = builder(players=2).battlefield(0, ["forest"]).build()
        before = len(game.state.battlefield_objects(0))
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        list(execute(ctx, [{"op": "copy_permanent", "objects": {"binding": "nobody"}}]))
        assert len(game.state.battlefield_objects(0)) == before


class TestScuteSwarm:
    """The "instead" is the whole card: one token or the other, never both."""

    def board(self, builder, lands: int):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * lands + ["scute_swarm"])
            .hand(0, ["forest"])
            .build()
        )

    def play_a_land(self, game):
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == "forest"
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

    def test_under_six_lands_it_makes_an_insect(self, builder):
        game = self.board(builder, lands=3)  # four after the drop
        self.play_a_land(game)
        assert len(copies_of(game, "insect_1_1_g")) == 1
        assert not copies_of(game, "scute_swarm"), "not a copy at four lands"

    def test_at_six_lands_it_copies_itself_instead(self, builder):
        game = self.board(builder, lands=5)  # six after the drop
        self.play_a_land(game)
        assert len(copies_of(game, "scute_swarm")) == 1
        assert not copies_of(game, "insect_1_1_g"), "'instead' means instead"

    def test_the_copies_copy_too(self, builder):
        """Each copy is a Scute Swarm, so the next land doubles the board."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 6 + ["scute_swarm"])
            .hand(0, ["forest", "forest"])
            .build()
        )
        self.play_a_land(game)
        assert len(copies_of(game, "scute_swarm")) == 1, "two Swarms now"

        # A second land, on a later turn, with two Swarms watching.
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1 and g.state.players[0].lands_played == 0)
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.PLAY_LAND
                and g.state.objects[a.source].def_id == "forest"
                for a in g.legal_actions()
            ),
        )
        self.play_a_land(game)
        assert len(copies_of(game, "scute_swarm")) == 3, "each Swarm made one"

    def test_a_copy_is_a_token_and_ceases_to_exist(self, builder):
        from automtg.engine.zones import destroy

        game = self.board(builder, lands=5)
        self.play_a_land(game)
        copy = copies_of(game, "scute_swarm")[0]
        destroy(game.state, copy.oid)
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[copy.oid].zone is not Zone.BATTLEFIELD
