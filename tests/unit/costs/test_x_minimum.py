"""'X can't be 0': a floor under an announced X.

Rule 107.3 lets a card restrict the X its controller announces, and 601.2b
(602.2b for an activated ability) is where that announcement happens. "Kicker
{X}. X can't be 0" -- Thieving Skydiver -- puts the X in an *additional* cost,
so the X exists only on the kicked line, and that line may not be cast for
X = 0: kicked for nothing, the Skydiver would steal a mana-value-0 artifact the
printed card never can. "{X}{G}: ... X can't be 0" -- Lair of the Hydra -- is the
same floor on an activated ability, where X = 0 would animate a 0/0 land that
dies to state-based actions.

Without the floor both cards are strictly stronger than printed (an extra line
to cast or activate) and nothing on the board shows it. The claims pinned here:
the floored line is offered only while the floor is payable, the CHOOSE_X
question starts at the floor, the X reaches the enters trigger -- its effects
and its target line both -- the unkicked line is untouched, and the loader
refuses a floor with no X under it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, settle

FLOOR = "t_kicker_x_floor"
OPEN = "t_kicker_x_open"
RELIC = "t_x_floor_relic"


def casts_of(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def kicker_board(builder, card_id: str, islands: int):
    """``card_id`` in hand with ``islands`` untapped Islands: {1}{U} plus X."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * islands)
        .hand(0, [card_id])
        .library(0, ["island"] * 10)
        .build()
    )


def x_choices(game) -> list[int]:
    """The X values the pending CHOOSE_X offers (its options, not the ordinals)."""
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    return [option.value for option in decision.options]


def choose(game, x: int) -> None:
    """Answer the pending CHOOSE_X with X = ``x``; the choice is its ordinal."""
    ordinal = x_choices(game).index(x)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.choice == ordinal
        )
    )


class TestTheKickedLineIsOfferedOnlyAtTheFloor:
    def test_two_mana_offers_only_the_unkicked_line(self, builder):
        """{1}{U} is all there is: kicked for X = 0 is not a cast."""
        offered = casts_of(kicker_board(builder, FLOOR, 2), FLOOR)
        assert offered, "the unkicked spell is still castable"
        assert not any(a.kicked for a in offered)

    def test_without_the_floor_two_mana_kicks_for_zero(self, builder):
        """The contrast: the same kicker {X} with no floor is kickable at X = 0."""
        offered = casts_of(kicker_board(builder, OPEN, 2), OPEN)
        assert any(a.kicked for a in offered)

    def test_three_mana_offers_the_kicked_line(self, builder):
        offered = casts_of(kicker_board(builder, FLOOR, 3), FLOOR)
        assert any(a.kicked for a in offered)
        assert any(not a.kicked for a in offered)


class TestTheQuestionStartsAtTheFloor:
    def test_choices_run_from_one(self, builder):
        game = kicker_board(builder, FLOOR, 5)
        game.apply(next(a for a in casts_of(game, FLOOR) if a.kicked))
        assert x_choices(game) == [1, 2, 3]

    def test_the_open_kicker_offers_zero(self, builder):
        game = kicker_board(builder, OPEN, 5)
        game.apply(next(a for a in casts_of(game, OPEN) if a.kicked))
        assert x_choices(game) == [0, 1, 2, 3]

    def test_the_unkicked_line_announces_nothing(self, builder):
        """No X in the unkicked cost, so no question and no floor to meet."""
        game = kicker_board(builder, FLOOR, 5)
        game.apply(next(a for a in casts_of(game, FLOOR) if not a.kicked))
        decision = game.pending()
        assert decision is None or decision.kind is not DecisionKind.CHOOSE_X


class TestTheXReachesTheEntersTrigger:
    def test_kicked_for_two_gains_two(self, builder):
        game = kicker_board(builder, FLOOR, 5)
        life = game.state.players[0].life
        game.apply(next(a for a in casts_of(game, FLOOR) if a.kicked))
        choose(game, 2)
        settle(game)
        assert game.state.players[0].life == life + 2
        tapped = sum(1 for o in game.state.battlefield_objects(0) if o.tapped)
        assert tapped == 4, "{1}{U} plus a kicker of X = 2"

    def test_unkicked_gains_nothing(self, builder):
        game = kicker_board(builder, FLOOR, 5)
        life = game.state.players[0].life
        game.apply(next(a for a in casts_of(game, FLOOR) if not a.kicked))
        settle(game)
        assert game.state.players[0].life == life


def relic_board(builder, forests: int):
    game = builder(players=2).battlefield(0, [RELIC] + ["forest"] * forests).build()
    return game, only_oid(game, RELIC)


def activations(game, oid: int):
    return [
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    ]


class TestTheActivatedAbilityFloor:
    def test_one_forest_pays_only_x_zero_and_is_not_offered(self, builder):
        game, oid = relic_board(builder, 1)
        assert not activations(game, oid)

    def test_two_forests_offer_it(self, builder):
        game, oid = relic_board(builder, 2)
        assert activations(game, oid)

    def test_choices_run_from_one(self, builder):
        game, oid = relic_board(builder, 4)
        game.apply(activations(game, oid)[0])
        assert x_choices(game) == [1, 2, 3]

    def test_at_the_floor_it_is_not_asked(self, builder):
        """Two Forests: {G} and X = 1 is the only payable announcement."""
        game, oid = relic_board(builder, 2)
        life = game.state.players[0].life
        game.apply(activations(game, oid)[0])
        settle(game)
        assert game.state.players[0].life == life + 1


class TestTheLoaderRefusesAFloorOverNothing:
    spell = {
        "id": "t_floor_no_x",
        "name": "Floor No X",
        "types": ["Instant"],
        "mana_cost": "{1}{U}",
        "x_minimum": 1,
        "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
    }

    def test_a_spell_with_no_x(self):
        with pytest.raises(DslError, match="x_minimum"):
            compile_card(CardModel.model_validate(self.spell))

    def test_an_ability_with_no_x(self):
        payload = {
            "id": "t_floor_no_x_ability",
            "name": "Floor No X Ability",
            "types": ["Artifact"],
            "mana_cost": "{1}",
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{G}: You gain 1 life.",
                    "cost": {"mana": "{G}", "x_minimum": 1},
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
        with pytest.raises(DslError, match="x_minimum"):
            compile_card(CardModel.model_validate(payload))

    def test_an_x_kicker_loads(self):
        """Kicker {X} costs X, so it is not refused as a kicker that costs nothing."""
        payload = {
            "id": "t_x_kicker",
            "name": "X Kicker",
            "types": ["Sorcery"],
            "mana_cost": "{U}",
            "kicker": "{X}",
            "x_minimum": 1,
            "spell_effects": [
                {
                    "op": "if",
                    "condition": {"kicked": True},
                    "then": [{"op": "draw", "player": "you", "amount": {"x": True}}],
                }
            ],
        }
        assert compile_card(CardModel.model_validate(payload)).x_minimum == 1


def skydiver_board(builder):
    """Thieving Skydiver and six Islands; the opponent has a +2 Mace (mana value 2)."""
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 6)
        .battlefield(1, ["2_mace"])
        .hand(0, ["thieving_skydiver"])
        .library(0, ["island"] * 10)
        .build()
    )
    return game, only_oid(game, "2_mace")


class TestTheEntersTriggerTargetsByTheKickedX:
    """The trigger's target line reads the X the permanent was cast with.

    A trigger announces no X, so its target pool reads the `x` binding
    `triggers` writes from `cast_x`; left at 0, "mana value X or less" would
    offer only mana-value-0 artifacts whatever the kicker paid.
    """

    def kick(self, builder, x: int):
        game, mace = skydiver_board(builder)
        game.apply(next(a for a in casts_of(game, "thieving_skydiver") if a.kicked))
        choose(game, x)
        settle(game)
        return game, mace

    def test_kicked_for_two_steals_and_equips_the_mace(self, builder):
        game, mace = self.kick(builder, 2)
        skydiver = only_oid(game, "thieving_skydiver")
        assert game.state.objects[mace].controller == 0
        assert game.state.objects[mace].attached_to == skydiver

    def test_kicked_for_one_cannot_reach_it(self, builder):
        game, mace = self.kick(builder, 1)
        assert game.state.objects[mace].controller == 1
        assert game.state.objects[mace].attached_to is None
