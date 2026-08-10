"""'Sacrifice it unless you...' -- the branch that makes a card a cost.

The Karoo lands are pure upside if the refusal does nothing, so the assertion
that matters is the *unhappy* path: declining, and having no Island to bounce at
all, must both leave the land in the graveyard. Gate 5 of the authoring verifier
drives the happy path (it takes every offered choice), which is exactly why the
other two are pinned here.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import pass_until


def play_the_land(game, card_id: str) -> int:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND and game.state.objects[a.source].def_id == card_id
    )
    oid = action.source
    game.apply(action)
    return oid


def answer_the_may(game, yes: bool) -> None:
    """Say yes or no to the one optional effect, then let everything settle."""
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY,
    )
    want = ActionKind.YES if yes else ActionKind.NO
    game.apply(next(a for a in game.legal_actions() if a.kind is want))
    pass_until(
        game,
        lambda g: not g.state.stack
        and (d := g.pending()) is not None
        and d.kind is DecisionKind.PRIORITY,
    )


class TestCoralAtoll:
    def test_returning_an_island_keeps_it(self, builder):
        game = builder(players=2).battlefield(0, ["island"] * 2).hand(0, ["coral_atoll"]).build()
        atoll = play_the_land(game, "coral_atoll")
        answer_the_may(game, yes=True)

        assert game.state.objects[atoll].zone is Zone.BATTLEFIELD
        assert game.state.objects[atoll].tapped, "'this land enters tapped'"
        islands = [o for o in game.state.battlefield_objects(0) if o.def_id == "island"]
        assert len(islands) == 1, "one of the two went back to hand"

    def test_declining_sacrifices_it(self, builder):
        game = builder(players=2).battlefield(0, ["island"] * 2).hand(0, ["coral_atoll"]).build()
        atoll = play_the_land(game, "coral_atoll")
        answer_the_may(game, yes=False)

        assert game.state.objects[atoll].zone is Zone.GRAVEYARD
        assert len([o for o in game.state.battlefield_objects(0) if o.def_id == "island"]) == 2

    def test_with_no_untapped_island_it_is_not_even_asked(self, builder):
        """Nothing to return means no choice to make -- and it still dies.

        Without the `exists` guard the card would offer a "may" that could be
        accepted for free, and a Karoo land that never costs anything is simply
        a better card than the one printed.
        """
        game = builder(players=2).hand(0, ["coral_atoll"]).build()
        atoll = play_the_land(game, "coral_atoll")
        pass_until(
            game,
            lambda g: not g.state.stack
            and (d := g.pending()) is not None
            and d.kind is DecisionKind.PRIORITY,
        )
        assert game.state.objects[atoll].zone is Zone.GRAVEYARD

    def test_a_tapped_island_does_not_count(self, builder):
        game = builder(players=2).battlefield(0, ["island"], tapped=True).hand(
            0, ["coral_atoll"]
        ).build()
        atoll = play_the_land(game, "coral_atoll")
        pass_until(
            game,
            lambda g: not g.state.stack
            and (d := g.pending()) is not None
            and d.kind is DecisionKind.PRIORITY,
        )
        assert game.state.objects[atoll].zone is Zone.GRAVEYARD


class TestJungleBasin:
    def test_it_wants_a_forest_not_an_island(self, builder):
        """The pair differ only in the land type, so a copy-paste slip is the risk."""
        game = builder(players=2).battlefield(0, ["island"] * 2).hand(0, ["jungle_basin"]).build()
        basin = play_the_land(game, "jungle_basin")
        pass_until(
            game,
            lambda g: not g.state.stack
            and (d := g.pending()) is not None
            and d.kind is DecisionKind.PRIORITY,
        )
        assert game.state.objects[basin].zone is Zone.GRAVEYARD, "Islands are no help here"

    def test_returning_a_forest_keeps_it(self, builder):
        game = builder(players=2).battlefield(0, ["forest"] * 2).hand(0, ["jungle_basin"]).build()
        basin = play_the_land(game, "jungle_basin")
        answer_the_may(game, yes=True)
        assert game.state.objects[basin].zone is Zone.BATTLEFIELD
