"""``Action.pays`` -- which permanents a cast would tap.

The mana row shows what you have; it could not show what a spell would cost you,
which is the interesting question in a turn with two plays in it.  The solver
already knew -- ``solve_payment`` returns the taps and ``_cast_options`` was
discarding them.  See docs/playtest-feedback-02.md item 4.

This is a *forecast*, not a commitment: ``costs.pay_mana`` re-solves when the
action is applied.  The tests below therefore pin agreement with the solver
rather than any particular choice of lands.
"""

from __future__ import annotations

from automtg.engine.actions import Action, PendingDecision
from automtg.engine.costs import mana_sources
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.legality import legal_actions
from automtg.engine.mana import solve_payment


def priority_to(game, pid: int = 0):
    game.state.pending_decision = PendingDecision(kind=DecisionKind.PRIORITY, player=pid)
    return game


def cast_of(game, card_id: str) -> Action:
    for action in legal_actions(game.state):
        if action.kind is not ActionKind.CAST or action.source is None:
            continue
        if game.state.objects[action.source].def_id == card_id:
            return action
    raise AssertionError(
        f"no cast for {card_id}; legal: {[a.label for a in legal_actions(game.state)]}"
    )


class TestForecast:
    def test_a_one_mana_spell_names_one_source(self, builder):
        game = priority_to(
            builder()
            .hand(0, ["llanowar_elves"])
            .battlefield(0, ["forest", "forest", "forest"])
            .build(advance=False)
        )
        assert len(cast_of(game, "llanowar_elves").pays) == 1

    def test_it_names_permanents_that_are_actually_on_the_board(self, builder):
        game = priority_to(
            builder()
            .hand(0, ["rampant_growth"])
            .battlefield(0, ["island", "forest"])
            .build(advance=False)
        )
        pays = cast_of(game, "rampant_growth").pays
        assert set(pays) <= set(game.state.battlefield)
        assert all(game.state.objects[oid].controller == 0 for oid in pays)

    def test_it_agrees_with_the_solver(self, builder):
        """The contract: this is the solver's answer, not a second opinion."""
        game = priority_to(
            builder()
            .hand(0, ["rampant_growth"])
            .battlefield(0, ["island", "island", "forest"])
            .build(advance=False)
        )
        action = cast_of(game, "rampant_growth")
        card = game.state.card(action.source)
        payment = solve_payment(
            card.mana_cost.with_x(0),
            game.state.players[0].mana_pool,
            mana_sources(game.state, 0),
        )
        assert payment is not None
        assert list(action.pays) == list(dict.fromkeys(tap[0] for tap in payment.taps))

    def test_each_source_appears_once(self, builder):
        """A land producing two mana pays twice but is one permanent to dim."""
        game = priority_to(
            builder()
            .hand(0, ["rampant_growth"])
            .battlefield(0, ["simic_growth_chamber"])
            .build(advance=False)
        )
        pays = cast_of(game, "rampant_growth").pays
        assert len(pays) == len(set(pays))


class TestPool:
    def test_floating_mana_is_not_reported(self, builder):
        """``Payment`` does not itemise pool spend, so nothing is claimed.

        The client dims source pips and says nothing about the pool. Reporting a
        pool pip here would be the guess the payload exists to avoid.
        """
        game = priority_to(
            builder().hand(0, ["llanowar_elves"]).battlefield(0, ["forest"]).build(advance=False)
        )
        game.state.players[0].mana_pool.add("G", 1)
        assert cast_of(game, "llanowar_elves").pays == ()


class TestIdentity:
    def test_pays_does_not_change_action_equality(self, builder):
        """The RL decoder rebuilds actions without a forecast; they must match.

        ``Action`` is the shared vocabulary between the HTTP layer and the action
        space, and a display field that split their identities would silently
        break the mask.
        """
        plain = Action(kind=ActionKind.CAST, source=7)
        forecast = Action(kind=ActionKind.CAST, source=7, pays=(1, 2, 3))
        assert plain == forecast
        assert plain.key() == forecast.key()

    def test_relabelling_keeps_the_forecast(self, builder):
        action = Action(kind=ActionKind.CAST, source=7, pays=(1, 2))
        assert action.with_label("Cast it").pays == (1, 2)

    def test_it_survives_serialization(self, builder):
        assert Action(kind=ActionKind.CAST, pays=(4, 5)).to_dict()["pays"] == [4, 5]


class TestNonCasts:
    def test_playing_a_land_forecasts_nothing(self, builder):
        game = priority_to(builder().hand(0, ["forest"]).build(advance=False))
        land = next(
            a for a in legal_actions(game.state) if a.kind is ActionKind.PLAY_LAND
        )
        assert land.pays == ()
