"""A variable loyalty cost: "-X" (606.4, 107.3).

    Sorin, Grim Nemesis: "-X: Sorin deals X damage to target creature or
    planeswalker and you gain X life."

606.4 makes a loyalty ability's cost "put or remove the indicated number of
loyalty counters", and 107.3 lets that number be X: the controller announces it
as the ability is activated (601.2b, via 606.2 → 602.2b) and it can be no more
than the loyalty the planeswalker has, because a cost that removes counters
that are not there cannot be paid.

What was wrong without this: `cost.loyalty` is a signed integer, so a printed
-X had no spelling at all. The two substitutes are both wrong. `x_value` fills
an ``{X}`` in a *mana* cost, and the ability would cost mana and no loyalty.
`remove_counters` takes counters off, but it is not a loyalty cost -- the
ability would lose 606.3 (one loyalty ability per permanent per turn), the
forced sorcery timing the loader applies to every loyalty ability, and
Teferi's permission, all of which ask ``cost.loyalty is not None``. So the new
key compiles to ``loyalty: 0`` plus a flag, and every one of those readers keeps
working unchanged; only `costs.can_pay` and `costs.pay` read the announced X.

The announcement comes before the targets when the targets read X -- Tamiyo,
Compleated Sage's "target nonland permanent card with mana value X" -- the same
one-activation-per-X shape `legality._ability_aims` already uses for a mana X.

Witnesses: Ashiok, Nightmare Weaver; Kasmina, Enigma Sage; Sorin, Grim Nemesis;
Tamiyo, Compleated Sage. `t_lx_walker` and `t_lx_aimer` are their two shapes.
"""

from __future__ import annotations

import pytest

from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import only_oid, pass_until, settle

WALKER = "t_lx_walker"  # loyalty 4; "+1: gain 2 life", "-X: gain X life"
AIMER = "t_lx_aimer"  # loyalty 4; "-X: destroy target artifact with mana value X"


def position(builder, walker: str = WALKER, *, theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3 + [walker])
        .battlefield(1, list(theirs))
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, walker, 0)


def activations(game, oid: int) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid
    ]


def minus_x(game, oid: int):
    return next(a for a in activations(game, oid) if a.ability_index == 1)


def choose(game, x: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


class TestXIsAnnouncedAndPaidInLoyalty:
    def test_activating_it_asks_for_x(self, builder):
        game, walker = position(builder)
        game.apply(minus_x(game, walker))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context.get("loyalty_cost") is True

    def test_the_ceiling_is_the_loyalty_there_is(self, builder):
        """606.4: a cost that removes counters that are not there cannot be
        paid, so the largest X on offer is the loyalty, and not one more."""
        game, walker = position(builder)
        game.apply(minus_x(game, walker))
        assert game.pending().context["max_x"] == 4

    @pytest.mark.parametrize("x", [1, 3])
    def test_x_counters_come_off_and_the_effect_reads_x(self, builder, x):
        """Parametrised because a constant passes any single case."""
        game, walker = position(builder)
        life = game.state.players[0].life
        game.apply(minus_x(game, walker))
        choose(game, x)
        assert game.state.objects[walker].counter("loyalty") == 4 - x
        settle(game)
        assert game.state.players[0].life == life + x

    def test_x_can_be_zero(self, builder):
        """107.3: zero is a legal announcement. Nothing comes off, nothing is
        gained, and it still spends the turn's loyalty ability."""
        game, walker = position(builder)
        life = game.state.players[0].life
        game.apply(minus_x(game, walker))
        choose(game, 0)
        settle(game)
        assert game.state.objects[walker].counter("loyalty") == 4
        assert game.state.players[0].life == life
        assert not activations(game, walker)

    def test_all_of_it_kills_the_walker_and_still_resolves(self, builder):
        """The boundary: X equal to the loyalty is payable, the walker goes to
        the graveyard as a state-based action (704.5i), and the ability -- which
        is independent of its source once on the stack -- still resolves."""
        game, walker = position(builder)
        life = game.state.players[0].life
        game.apply(minus_x(game, walker))
        choose(game, 4)
        settle(game)
        assert game.state.objects[walker].zone is not Zone.BATTLEFIELD
        assert game.state.players[0].life == life + 4


class TestItIsStillALoyaltyAbility:
    """The reason for a flag rather than `remove_counters`."""

    def test_one_loyalty_ability_a_turn(self, builder):
        """606.3: after the -X, the +1 is not on offer either."""
        game, walker = position(builder)
        game.apply(minus_x(game, walker))
        choose(game, 1)
        settle(game)
        assert not activations(game, walker)

    def test_after_the_plus_the_minus_is_not_offered(self, builder):
        game, walker = position(builder)
        game.apply(next(a for a in activations(game, walker) if a.ability_index == 0))
        settle(game)
        assert not activations(game, walker)

    def test_it_is_sorcery_speed(self, registry):
        """Applied by the loader to every loyalty ability, and this one never
        writes a `loyalty` number."""
        minus = registry.get(WALKER).abilities[1]
        assert minus.sorcery_speed_only
        assert minus.cost.loyalty == 0 and minus.cost.loyalty_x

    def test_not_on_an_opponents_turn(self, builder):
        game, walker = position(builder)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.UPKEEP)
        assert not activations(game, walker)

    def test_it_reads_as_minus_x(self, registry):
        assert registry.get(WALKER).abilities[1].cost.describe() == "-X"


class TestTargetsThatReadX:
    """Tamiyo's shape: 601.2b announces X before 601.2c chooses targets, so the
    number rides on the activation and each offer carries the targets legal
    at that X."""

    def test_one_offer_per_x_each_with_its_own_target(self, builder):
        game, aimer = position(
            builder, AIMER, theirs=["t_xdt_one", "t_xdt_two", "t_xdt_three"]
        )
        offered = {
            (a.x, game.state.objects[a.targets[0].id].def_id)
            for a in activations(game, aimer)
        }
        assert offered == {(1, "t_xdt_one"), (2, "t_xdt_two"), (3, "t_xdt_three")}

    def test_no_x_above_the_loyalty(self, builder):
        """A mana value 3 artifact with only two loyalty is not a legal aim."""
        game, aimer = position(builder, AIMER, theirs=["t_xdt_one", "t_xdt_three"])
        game.state.objects[aimer].counters["loyalty"] = 2
        offered = {a.x for a in activations(game, aimer)}
        assert offered == {1}

    def test_the_announced_x_is_paid_without_asking_again(self, builder):
        game, aimer = position(builder, AIMER, theirs=["t_xdt_two", "t_xdt_three"])
        three = only_oid(game, "t_xdt_three", 1)
        game.apply(next(a for a in activations(game, aimer) if a.x == 3))
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        assert game.state.objects[aimer].counter("loyalty") == 1
        settle(game)
        assert game.state.objects[three].zone is Zone.GRAVEYARD


class TestTheHeuristicKeepsTheWalker:
    """`choose_x` otherwise takes the maximum, which for a -X is the one answer
    that always kills the planeswalker."""

    def test_it_spends_all_but_one(self, builder):
        game, walker = position(builder)
        game.apply(minus_x(game, walker))
        action = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert action.choice == 3

    def test_with_one_loyalty_it_says_zero(self, builder):
        """The boundary: all-but-one of one is nothing."""
        game, walker = position(builder)
        game.state.objects[walker].counters["loyalty"] = 1
        game.apply(minus_x(game, walker))
        action = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert action.choice == 0


class TestTheLoaderChecksIt:
    def _card(self, cost: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_lx_bad",
                "name": "Test Bad X Walker",
                "mana_cost": "{2}{B}",
                "types": ["Planeswalker"],
                "loyalty": 3,
                "oracle_text": "-X: You gain X life.",
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "-X: You gain X life.",
                        "cost": cost,
                        "effects": [
                            {"op": "gain_life", "player": "you", "amount": {"x": True}}
                        ],
                    }
                ],
            }
        )

    def test_the_flag_alone_is_the_form(self):
        compile_card(self._card({"loyalty_x": True}))

    def test_not_beside_a_fixed_loyalty(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card({"loyalty_x": True, "loyalty": -2}))

    def test_not_beside_a_mana_x(self):
        with pytest.raises(DslError, match="second X"):
            compile_card(self._card({"loyalty_x": True, "mana": "{X}"}))
