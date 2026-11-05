"""An activated-ability cost of "Discard X cards" (601.2b, 107.3).

    Gix, Yawgmoth Praetor: "{4}{B}{B}{B}, Discard X cards: Exile the top X cards
    of target opponent's library. ..."

107.3 lets a cost's number be X, and 601.2b (applied to abilities by 602.2b)
has the controller announce it as the ability is activated, before targets and
before any cost is paid. A cost is paid only by doing all of it (601.2h), and
there is no rule that lets a player discard cards they do not have, so X can be
no more than the cards in hand the cost may take. The cards go as the cost,
chosen by the payer, and the ability's effects read the same X back.

What was wrong without this: `cost.discard` is a number the card fixes, so a
printed "Discard X cards" had no spelling. `x_value` fills an ``{X}`` in a mana
cost, `pay_life_x` is the announced X for life on a spell's additional cost, and
`loyalty_x` is a planeswalker's -X; none of them discards. The new flag reuses
`loyalty_x`'s path: `Game._activate` announces X through `ask_x` with the
discard pool as the ceiling, `costs.can_pay` and `costs.pay` read the announced
X, and `legality._ability_aims` offers one activation per X when the targets read
it.

Witness: Gix, Yawgmoth Praetor. `t_dx_engine`, `t_dx_lands` and `t_dx_aimer`
are its shapes.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, only_oid, settle

ENGINE = "t_dx_engine"  # "{1}, Discard X cards: You gain X life."
LANDS = "t_dx_lands"  # "Discard X land cards: You gain X life."
AIMER = "t_dx_aimer"  # "Discard X cards: Destroy target artifact with mana value X."


def position(builder, source: str = ENGINE, *, hand=("grizzly_bears",) * 3, theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 2 + [source])
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, source, 0)


def choose_x(game, x: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def discard_these(game, oids) -> None:
    """Answer the cost's pick with exactly these cards from hand.

    A pick whose pool is exactly the count is forced and asks nothing, so the
    whole hand needs no answer.
    """
    decision = game.pending()
    if decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        return
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
    if game.pending() is decision:
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def hand(game) -> list[int]:
    return list(game.state.players[0].hand)


class TestXIsAnnouncedAndPaidInCards:
    def test_activating_it_asks_for_x(self, builder):
        game, engine = position(builder)
        game.apply(activations(game, engine)[0])
        assert game.pending().kind is DecisionKind.CHOOSE_X

    def test_the_ceiling_is_the_cards_in_hand(self, builder):
        """601.2h: a discard of cards that are not there cannot be paid."""
        game, engine = position(builder)
        game.apply(activations(game, engine)[0])
        assert game.pending().context["max_x"] == 3

    @pytest.mark.parametrize("x", [1, 3])
    def test_x_cards_are_discarded_and_the_effect_reads_x(self, builder, x):
        """Parametrised because a constant passes any single case."""
        game, engine = position(builder)
        life = game.state.players[0].life
        picked = hand(game)[:x]
        game.apply(activations(game, engine)[0])
        choose_x(game, x)
        discard_these(game, picked)
        assert all(game.state.objects[oid].zone is Zone.GRAVEYARD for oid in picked)
        assert len(hand(game)) == 3 - x
        settle(game)
        assert game.state.players[0].life == life + x

    def test_the_payer_picks_which_cards(self, builder):
        game, engine = position(builder)
        keep, *_ = hand(game)
        game.apply(activations(game, engine)[0])
        choose_x(game, 2)
        discard_these(game, [oid for oid in hand(game) if oid != keep])
        assert hand(game) == [keep]

    def test_x_can_be_zero_with_an_empty_hand(self, builder):
        """107.3: zero is a legal announcement, so the ability is on offer with
        nothing in hand, asks nothing, discards nothing and reads 0."""
        game, engine = position(builder, hand=())
        life = game.state.players[0].life
        game.apply(activations(game, engine)[0])
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        settle(game)
        assert game.state.players[0].life == life

    def test_the_mana_half_is_still_paid(self, builder):
        game, engine = position(builder)
        game.apply(activations(game, engine)[0])
        choose_x(game, 1)
        discard_these(game, hand(game)[:1])
        tapped = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "swamp" and o.tapped
        ]
        assert len(tapped) == 1

    def test_it_reads_as_discard_x(self, registry):
        assert registry.get(ENGINE).abilities[0].cost.describe() == "{1}, Discard X"


class TestTheSelectorNarrowsTheCeiling:
    def test_only_matching_cards_count(self, builder):
        game, lands = position(builder, LANDS, hand=("swamp", "swamp", "grizzly_bears"))
        game.apply(activations(game, lands)[0])
        assert game.pending().context["max_x"] == 2

    def test_only_matching_cards_are_offered(self, builder):
        game, lands = position(builder, LANDS, hand=("swamp", "swamp", "grizzly_bears"))
        game.apply(activations(game, lands)[0])
        choose_x(game, 1)
        decision = game.pending()
        offered = {game.state.objects[o.ref.id].def_id for o in decision.options if o.ref}
        assert offered == {"swamp"}


class TestTargetsThatReadX:
    """601.2b announces X before 601.2c chooses targets, so the number rides on
    the activation and each offer carries the targets legal at that X."""

    def test_one_offer_per_x_each_with_its_own_target(self, builder):
        game, aimer = position(builder, AIMER, theirs=["t_xdt_one", "t_xdt_two", "t_xdt_three"])
        offered = {
            (a.x, game.state.objects[a.targets[0].id].def_id) for a in activations(game, aimer)
        }
        assert offered == {(1, "t_xdt_one"), (2, "t_xdt_two"), (3, "t_xdt_three")}

    def test_no_x_above_the_hand(self, builder):
        """A mana value 3 artifact with two cards in hand is not a legal aim."""
        game, aimer = position(
            builder, AIMER, hand=("grizzly_bears",) * 2, theirs=["t_xdt_one", "t_xdt_three"]
        )
        assert {a.x for a in activations(game, aimer)} == {1}

    def test_the_announced_x_is_paid_without_asking_again(self, builder):
        game, aimer = position(builder, AIMER, theirs=["t_xdt_two", "t_xdt_three"])
        three = only_oid(game, "t_xdt_three", 1)
        game.apply(next(a for a in activations(game, aimer) if a.x == 3))
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        discard_these(game, hand(game))
        assert not hand(game)
        settle(game)
        assert game.state.objects[three].zone is Zone.GRAVEYARD


class TestTheLoaderChecksIt:
    def _card(self, cost: dict, kind: str = "activated") -> CardModel:
        ability = {
            "kind": kind,
            "text": "Discard X cards: You gain X life.",
            "cost": cost,
            "effects": [{"op": "gain_life", "player": "you", "amount": {"x": True}}],
        }
        return CardModel.model_validate(
            {
                "id": "t_dx_bad",
                "name": "Test Bad Discard X",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": "Discard X cards: You gain X life.",
                "abilities": [ability],
            }
        )

    def test_the_flag_alone_is_the_form(self):
        compile_card(self._card({"discard_x": True}))

    def test_not_beside_a_fixed_discard(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card({"discard_x": True, "discard": 1}))

    def test_not_beside_a_mana_x(self):
        with pytest.raises(DslError, match="second X"):
            compile_card(self._card({"discard_x": True, "mana": "{X}"}))

    def test_a_selector_rides_on_it(self):
        compile_card(self._card({"discard_x": True, "discard_selector": {"types": ["Land"]}}))

    def test_not_on_a_spells_additional_cost(self):
        with pytest.raises(DslError, match="activated ability"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_dx_bad_spell",
                        "name": "Test Bad Discard X Spell",
                        "mana_cost": "{B}",
                        "types": ["Sorcery"],
                        "oracle_text": (
                            "As an additional cost to cast this spell, discard X cards.\n"
                            "You gain X life."
                        ),
                        "additional_cost": {"discard_x": True},
                        "spell_effects": [
                            {"op": "gain_life", "player": "you", "amount": {"x": True}}
                        ],
                    }
                )
            )
