"""Ancient Greenwarden: land triggers fire twice.

"That ability triggers an additional time" is a second copy on the stack, not a
doubled effect, and the difference is observable -- anything else that wants to
happen in between still can. It is queued twice for that reason.

The scope matters as much as the doubling: *lands* entering, *your* permanents.
A general "double every trigger" would be a much larger claim than the card
makes, and each of the three ways to get it wrong is pinned below.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind
from tests.conftest import pass_until


def play_a_land(game, card_id: str = "forest") -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def saprolings(game, pid: int = 0) -> int:
    return sum(1 for o in game.state.battlefield_objects(pid) if o.def_id == "saproling_1_1_g")


class TestLandfallFiresTwice:
    """Sporemound is the readable case: one token per trigger, so count them."""

    def test_one_land_makes_two_triggers(self, builder):
        def tokens_after_a_land(with_warden: bool) -> int:
            board = ["sporemound"] + (["ancient_greenwarden"] if with_warden else [])
            game = builder(players=2).battlefield(0, board).hand(0, ["forest"]).build()
            play_a_land(game)
            return saprolings(game)

        assert tokens_after_a_land(with_warden=False) == 1
        assert tokens_after_a_land(with_warden=True) == 2

    def test_a_nonland_permanent_does_not_double(self, builder):
        """The card says "a land entering", and only that."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 6 + ["impact_tremors", "ancient_greenwarden"])
            .hand(0, ["grizzly_bears"])
            .build()
        )
        before = game.state.players[1].life
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "grizzly_bears"
        )
        game.apply(cast)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert before - game.state.players[1].life == 1, "one damage, not two"

    def test_it_does_not_double_an_opponents_triggers(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["ancient_greenwarden"])
            .battlefield(1, ["sporemound"])
            .hand(1, ["forest"])
            .build()
        )
        # Hand the turn over so the opponent can play their land.
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.PLAY_LAND
                and g.state.objects[a.source].def_id == "forest"
                for a in g.legal_actions()
            ),
        )
        play_a_land(game)
        assert saprolings(game, 1) == 1, "'a permanent you control'"
