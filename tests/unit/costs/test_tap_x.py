"""An activated-ability cost of "Tap X untapped <permanents>" (601.2b, 107.3).

    Hazel of the Rootbloom: "{T}, Pay 2 life, Tap X untapped tokens you
    control: Add X mana in any combination of colors."

107.3 lets a cost's number be X, and 601.2b (applied to abilities by 602.2b,
and to mana abilities by 605.3a) has the controller announce it as the ability
is activated, before any cost is paid. A cost is paid only by doing all of it
(601.2h), so X can be no more than the matching untapped permanents -- and a
permanent tapped for the same cost's {T} is not one of them: Hazel's ruling is
that a token Hazel cannot pay both. The ability's effects read the same X back,
here the size of a mana ability's yield.

Without this, `tap_permanents` takes only a count the card fixes or crew's
power sum, so "Tap X untapped tokens" had no spelling. `tap_x` is
`sacrifice_x`'s selector over `tap_permanents`' pool: `costs.cost_x_ceiling`
bounds X for `Game._activate`, `Game._activate_mana` and legality alike, and a
mana ability that takes X is activated by hand -- never by the payment solver,
its cost not being tap-only -- so `_activate_mana` asks X, pays, and then asks
the division of X among the colours.

Witness: Hazel of the Rootbloom. `t_tx_hazel`, `t_tx_green`, `t_tx_engine` and
`t_tx_tapper` are its shapes.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import solver_taps
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, oids_of, only_oid, settle

HAZEL = "t_tx_hazel"  # "{T}, Tap X untapped tokens: Add X mana in any combination of colors."
GREEN = "t_tx_green"  # "Tap X untapped tokens: Add X {G}."
ENGINE = "t_tx_engine"  # "{1}, Tap X untapped tokens: You gain X life."
TAPPER = "t_tx_tapper"  # "{T}, Tap X untapped creatures: You gain X life." -- a creature
SPLIT = ["W", "U", "B", "R", "G"]
SQUIRREL = "squirrel_1_1_g"


def position(builder, source: str = HAZEL, *, mine=(SQUIRREL,) * 3):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 2 + [source] + list(mine))
        # A land to play keeps the main phase from passing itself: a window
        # holding only mana abilities is auto-passed.
        .hand(0, ["swamp"])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    # The builder places a token's card, not a token; mark the Squirrels as
    # what a token-making effect would have made.
    for oid in oids_of(game, SQUIRREL, 0):
        game.state.objects[oid].is_token = True
    return game, only_oid(game, source, 0)


def choose_x(game, x: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    game.apply(find_action(game, ActionKind.CHOOSE, choice=x))


def tap_these(game, oids) -> None:
    """Answer the cost's pick with exactly these permanents; a forced pick asks nothing."""
    decision = game.pending()
    if decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        return
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(find_action(game, ActionKind.CHOOSE, choice=index))
    if game.pending() is decision:
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def divide(game, colors: str) -> None:
    """Answer the one-mana-at-a-time colour choice, in order."""
    for color in colors:
        assert game.pending().kind is DecisionKind.CHOOSE_MODE
        game.apply(find_action(game, ActionKind.CHOOSE, choice=SPLIT.index(color)))


def pool(game) -> dict[str, int]:
    return {k: v for k, v in game.state.players[0].mana_pool.to_dict().items() if v}


def tapped(game, card_id: str) -> list[int]:
    return [oid for oid in oids_of(game, card_id, 0) if game.state.objects[oid].tapped]


class TestAManaAbilityThatTakesX:
    def test_it_is_offered_by_hand_as_one_row(self, builder):
        """Not the solver's -- its cost is not tap-only -- and one row, because
        the yield is asked once X is known."""
        game, hazel = position(builder)
        ability = game.state.card(hazel).abilities[0]
        assert not solver_taps(ability)
        assert [a.mana_option for a in activations(game, hazel)] == [None]

    def test_activating_it_asks_for_x_up_to_the_untapped_tokens(self, builder):
        game, hazel = position(builder)
        game.apply(activations(game, hazel)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context["max_x"] == 3

    @pytest.mark.parametrize(("x", "colors"), [(1, "G"), (3, "WUG")])
    def test_x_tokens_are_tapped_and_x_mana_is_divided(self, builder, x, colors):
        """Parametrised because a constant passes any single case; "WUG" is
        the combination no single colour can make."""
        game, hazel = position(builder)
        picked = oids_of(game, SQUIRREL, 0)[:x]
        game.apply(activations(game, hazel)[0])
        choose_x(game, x)
        tap_these(game, picked)
        assert sorted(tapped(game, SQUIRREL)) == sorted(picked)
        assert game.state.objects[hazel].tapped
        divide(game, colors)
        assert pool(game) == {c: colors.count(c) for c in colors}
        assert not game.state.stack

    def test_x_can_be_zero(self, builder):
        """107.3: zero is a legal announcement, so the ability is on offer with
        no token, taps only Hazel, and makes no mana."""
        game, hazel = position(builder, mine=())
        game.apply(activations(game, hazel)[0])
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        assert game.state.objects[hazel].tapped
        assert pool(game) == {}

    def test_choosing_zero_with_tokens_taps_none(self, builder):
        game, hazel = position(builder)
        game.apply(activations(game, hazel)[0])
        choose_x(game, 0)
        assert tapped(game, SQUIRREL) == []
        assert pool(game) == {}

    def test_a_one_colour_yield_reads_x_as_its_amount(self, builder):
        game, green = position(builder, GREEN)
        game.apply(activations(game, green)[0])
        choose_x(game, 2)
        tap_these(game, oids_of(game, SQUIRREL, 0)[:2])
        assert pool(game) == {"G": 2}


class TestOnlyUntappedMatchingPermanentsCount:
    def test_a_tapped_token_and_a_nontoken_are_not_fodder(self, builder):
        game, hazel = position(builder, mine=(SQUIRREL,) * 3 + ("grizzly_bears",))
        game.state.objects[oids_of(game, SQUIRREL, 0)[0]].tapped = True
        game.apply(activations(game, hazel)[0])
        assert game.pending().context["max_x"] == 2

    def test_the_source_tapped_for_its_own_tap_symbol_is_not_counted_twice(self, builder):
        """The tapper is a creature tapping X untapped creatures and itself for
        {T}: two others make the ceiling two, not three, and X = 2 is payable."""
        game, tapper = position(builder, TAPPER, mine=("grizzly_bears",) * 2)
        life = game.state.players[0].life
        game.apply(activations(game, tapper)[0])
        assert game.pending().context["max_x"] == 2
        choose_x(game, 2)
        assert len(tapped(game, "grizzly_bears")) == 2
        settle(game)
        assert game.state.players[0].life == life + 2


class TestAnAbilityOnTheStackReadsX:
    @pytest.mark.parametrize("x", [0, 2])
    def test_the_effect_reads_the_announced_x(self, builder, x):
        game, engine = position(builder, ENGINE)
        life = game.state.players[0].life
        game.apply(activations(game, engine)[0])
        choose_x(game, x)
        tap_these(game, oids_of(game, SQUIRREL, 0)[:x])
        assert len(tapped(game, SQUIRREL)) == x
        settle(game)
        assert game.state.players[0].life == life + x

    def test_it_reads_as_tap_x(self, registry):
        assert registry.get(ENGINE).abilities[0].cost.describe() == (
            "{1}, Tap X untapped permanents"
        )


class TestTheLoaderChecksIt:
    def _card(self, cost: dict, *, mana: bool = False) -> CardModel:
        if mana:
            ability = {
                "kind": "activated",
                "text": "Tap X untapped tokens you control: Add X {G}.",
                "is_mana_ability": True,
                "cost": cost,
                "effects": [{"op": "add_mana", "mana": "{G}", "amount": {"x": True}}],
            }
        else:
            ability = {
                "kind": "activated",
                "text": "Tap X untapped tokens you control: You gain X life.",
                "cost": cost,
                "effects": [{"op": "gain_life", "player": "you", "amount": {"x": True}}],
            }
        return CardModel.model_validate(
            {
                "id": "t_tx_bad",
                "name": "Test Bad Tap X",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": ability["text"],
                "abilities": [ability],
            }
        )

    def test_a_selector_is_the_form(self):
        compile_card(self._card({"tap_x": {"is_token": True}}))
        compile_card(self._card({"tap_x": {"is_token": True}}, mana=True))

    @pytest.mark.parametrize("key", ["count", "total_power", "as", "tapped"])
    def test_x_is_the_count_and_untapped_is_implied(self, key):
        with pytest.raises(DslError, match=f"'{key}' may not be set"):
            compile_card(self._card({"tap_x": {"is_token": True, key: 2}}))

    def test_a_malformed_selector_is_refused(self):
        with pytest.raises(DslError, match="tap_x"):
            compile_card(self._card({"tap_x": {"token": True}}))

    def test_not_beside_a_fixed_tap_cost(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(
                self._card({"tap_x": {"is_token": True}, "tap_permanents": {"count": 1}})
            )

    @pytest.mark.parametrize(
        "second", [{"mana": "{X}"}, {"discard_x": True}, {"sacrifice_x": {"is_token": True}}]
    )
    def test_not_beside_a_second_x(self, second):
        with pytest.raises(DslError, match="second X"):
            compile_card(self._card({"tap_x": {"is_token": True}, **second}))

    def test_a_mana_ability_reads_x_only_when_its_cost_takes_x(self):
        with pytest.raises(DslError, match="no X"):
            compile_card(self._card({"tap": True}, mana=True))
