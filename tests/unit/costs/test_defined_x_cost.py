"""An activated ability whose X the *card* fixes, not the player.

Rule 601.2b announces X: the player casting a spell chooses it, and 602.2b puts
an activated ability's costs through the same steps. But an ability whose own
text says what X is never asks -- "{X}, {T}: Create a token that's a copy of the
exiled card. **X is the mana value of that card**" (Soul Foundry). The number is
read off the board at the moment the ability is activated.

Without `cost.x_value` the DSL could only write that line as `{"mana": "{X}"}`,
which is an *announced* X: the player says zero and copies an imprinted
Griselbrand for nothing. That is not an approximation of Soul Foundry, it is a
strictly better card -- and `tests/data/defined_x.cards.json` ships it as
`t_naive_foundry` precisely so `TestWhyTheFieldExists` can assert what the
difference is. It exists because the authoring gates cannot see this: the
verifier's sandbox never activates an activated ability, so both spellings
"pass all 6 gates" and only this file tells them apart.

`t_imprint_foundry` is the shape Soul Foundry needs: an imprint trigger that
exiles a creature card with a link back to the artifact, and an activated
ability whose cost prices itself off whatever is sitting under that link.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import exile
from tests.conftest import find_action, only_oid

#: A creature's mana value is the price of copying it, so the tests name cards
#: by what they cost: `t_bear` is {1}{G}, `t_big` is {5}{G}, `t_free_thopter` is
#: the {0} boundary.
BEAR_MV = 2
BIG_MV = 6


def foundry_imprinting(
    builder, imprinted: str, *, lands: int, foundry: str = "t_imprint_foundry"
):
    """A foundry with ``imprinted`` exiled under it, and ``lands`` untapped Forests.

    The exile is done by hand rather than by casting the artifact, because the
    board has to be *exact*: what is being asserted is which activations are
    offered at which amount of mana, and a cast would tap some of it. It is
    precisely what `ops_removal.op_exile` does for an `until_leaves` exile -- move
    the card and record the link -- and `TestTheImprintTheCardActuallyMakes`
    drives the printed trigger to prove the two agree.
    """
    game = (
        builder(players=2)
        .battlefield(0, [foundry] + ["forest"] * lands)
        .hand(0, [imprinted])
        .build()
    )
    oid = only_oid(game, foundry)
    card = game.state.players[0].hand[0]
    exile(game.state, card, by=oid)
    game.state.objects[card].exiled_by = oid
    return game, oid


def offered(game, oid: int) -> bool:
    """Is the foundry's ability in the legal action list right now?"""
    return any(
        a.kind is ActionKind.ACTIVATE and a.source == oid for a in game.legal_actions()
    )


def untapped_forests(game) -> int:
    return sum(
        1
        for obj in game.state.battlefield_objects(0)
        if obj.def_id == "forest" and not obj.tapped
    )


def token_ids(game) -> list[str]:
    return [obj.def_id for obj in game.state.battlefield_objects(0) if obj.is_token]


def activate(game, oid: int, limit: int = 20) -> list[DecisionKind]:
    """Activate the ability, let it resolve, and report every question asked."""
    game.apply(find_action(game, ActionKind.ACTIVATE, source=oid))
    asked: list[DecisionKind] = []
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        asked.append(decision.kind)
        if decision.kind is DecisionKind.PRIORITY:
            game.apply(find_action(game, ActionKind.PASS))
        else:
            game.apply(game.legal_actions()[0])
        if not game.state.stack:
            break
    return asked


class TestXIsWhatTheAbilitySays:
    def test_the_player_is_never_asked(self, builder):
        """601.2b's announcement is the player's choice, and this card made it."""
        game, oid = foundry_imprinting(builder, "t_bear", lands=3)
        asked = activate(game, oid)
        assert DecisionKind.CHOOSE_X not in asked, (
            "a defined X is read off the board, not announced -- asking would let "
            "the player say zero"
        )

    def test_it_charges_the_imprinted_card_s_mana_value(self, builder):
        game, oid = foundry_imprinting(builder, "t_bear", lands=3)
        activate(game, oid)
        assert untapped_forests(game) == 3 - BEAR_MV

    def test_the_copy_is_made(self, builder):
        """The other half of the line, so the price is a price *for* something."""
        game, oid = foundry_imprinting(builder, "t_bear", lands=3)
        activate(game, oid)
        assert token_ids(game) == ["t_bear"]

    def test_a_free_creature_makes_a_free_activation(self, builder):
        """The X = 0 boundary. Zero is a real defined X, not "no defined X"."""
        game, oid = foundry_imprinting(builder, "t_free_thopter", lands=0)
        assert offered(game, oid)
        activate(game, oid)
        assert token_ids(game) == ["t_free_thopter"]

    def test_nothing_imprinted_is_x_zero_and_copies_nothing(self, builder):
        """Soul Foundry with no imprint: activatable for {0}, and it does nothing.

        An empty `exiled_with` pool sums to 0, which is the same answer a table
        gives -- "X is the mana value of that card" names no card, so it is zero
        and the copy has nothing to copy.
        """
        game = builder(players=2).battlefield(0, ["t_imprint_foundry"]).build()
        oid = only_oid(game, "t_imprint_foundry")
        assert offered(game, oid)
        activate(game, oid)
        assert token_ids(game) == []


class TestItIsOfferedOnlyWhenPayable:
    """The whole point of pricing it in legality: an ability nobody can pay for
    is not on the list, so it can never be activated at a cheaper X."""

    def test_exactly_enough_mana_is_offered(self, builder):
        game, oid = foundry_imprinting(builder, "t_bear", lands=BEAR_MV)
        assert offered(game, oid)

    def test_one_mana_short_is_not(self, builder):
        game, oid = foundry_imprinting(builder, "t_bear", lands=BEAR_MV - 1)
        assert not offered(game, oid), (
            "priced at the announced floor of X = 0 this would be offered, and "
            "copying a two-drop for free is a different card"
        )

    def test_a_six_drop_costs_six(self, builder):
        game, oid = foundry_imprinting(builder, "t_big", lands=BIG_MV - 1)
        assert not offered(game, oid)

    def test_and_is_offered_at_six(self, builder):
        game, oid = foundry_imprinting(builder, "t_big", lands=BIG_MV)
        assert offered(game, oid)

    def test_a_tapped_board_offers_nothing(self, builder):
        """The mana has to be *available*, not merely on the battlefield."""
        game, oid = foundry_imprinting(builder, "t_bear", lands=BEAR_MV)
        for obj in game.state.battlefield_objects(0):
            if obj.def_id == "forest":
                obj.tapped = True
        assert not offered(game, oid)


class TestItRepricesWhenTheImprintChanges:
    """The price is read when the ability is activated, not when the card loads."""

    def test_losing_the_imprint_drops_the_price_to_nothing(self, builder):
        """The link is what the cost reads, so cutting it re-prices the ability."""
        game, oid = foundry_imprinting(builder, "t_bear", lands=BEAR_MV)
        assert offered(game, oid)

        imprinted = next(o for o in game.state.objects.values() if o.exiled_by == oid)
        imprinted.exiled_by = None
        for obj in game.state.battlefield_objects(0):
            if obj.def_id == "forest":
                obj.tapped = True
        assert offered(game, oid), "with nothing imprinted X is 0, and {0} is payable"

    def test_a_bigger_imprint_prices_the_same_board_out(self, builder):
        """Two forests pay for a Bear and not for a six-drop, on one board."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_imprint_foundry"] + ["forest"] * BEAR_MV)
            .hand(0, ["t_bear", "t_big"])
            .build()
        )
        oid = only_oid(game, "t_imprint_foundry")
        bear, big = game.state.players[0].hand[0], game.state.players[0].hand[1]

        exile(game.state, bear, by=oid)
        game.state.objects[bear].exiled_by = oid
        assert offered(game, oid)

        game.state.objects[bear].exiled_by = None
        exile(game.state, big, by=oid)
        game.state.objects[big].exiled_by = oid
        assert not offered(game, oid), "the same two forests do not pay for a {5}{G}"


class TestTheImprintTheCardActuallyMakes:
    def test_casting_it_and_imprinting_prices_the_ability(self, builder):
        """The printed path end to end: the link the cost reads is the one the
        trigger writes, and nothing in between had to be arranged by hand."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 8)
            .hand(0, ["t_imprint_foundry", "t_big"])
            .build()
        )
        game.apply(find_action(game, ActionKind.CAST))
        for _ in range(12):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.MAY:
                game.apply(find_action(game, ActionKind.YES))
                break
            game.apply(find_action(game, ActionKind.PASS))

        oid = only_oid(game, "t_imprint_foundry")
        imprinted = [
            obj
            for obj in game.state.objects.values()
            if obj.zone is Zone.EXILE and obj.exiled_by == oid
        ]
        assert [obj.def_id for obj in imprinted] == ["t_big"]
        # Five Forests are left after a {3} artifact, and a {5}{G} costs six.
        assert untapped_forests(game) == 5
        assert not offered(game, oid)


class TestWhyTheFieldExists:
    """`t_naive_foundry` is the same card with `x_value` left off -- the only
    thing the DSL could write before this run. It is strictly better than the
    printed card, and both spellings pass every authoring gate."""

    def test_without_it_the_ability_is_free(self, builder):
        game, oid = foundry_imprinting(
            builder, "t_bear", lands=0, foundry="t_naive_foundry"
        )
        assert offered(game, oid), "an announced X has a floor of zero"
        activate(game, oid)
        assert token_ids(game) == ["t_bear"], "copied a two-drop for no mana at all"

    def test_and_the_player_is_the_one_who_chooses(self, builder):
        game, oid = foundry_imprinting(
            builder, "t_bear", lands=3, foundry="t_naive_foundry"
        )
        assert DecisionKind.CHOOSE_X in activate(game, oid)


class TestTheLoaderRefusesWhatItCannotHonour:
    """`x_value` is read by `costs.ability_mana` and by nothing else. Every cost
    node it cannot reach refuses it at load time rather than dropping it."""

    @staticmethod
    def _card(**extra):
        base = {
            "id": "t_x_value_probe",
            "name": "X Value Probe",
            "mana_cost": "{2}",
            "types": ["Artifact"],
        }
        base.update(extra)
        return CardModel.model_validate(base)

    @staticmethod
    def _ability(cost, kind="activated"):
        ability = {
            "kind": kind,
            "text": "probe",
            "cost": cost,
            "effects": [{"op": "draw", "player": "you"}],
        }
        if kind == "triggered":
            ability["trigger"] = {"event": "self_enters", "source": "self"}
        return ability

    def test_it_loads_on_an_activated_ability(self):
        compile_card(
            self._card(
                abilities=[
                    self._ability(
                        {"mana": "{X}", "tap": True, "x_value": {"const": 1}}
                    )
                ]
            )
        )

    def test_it_needs_an_x_to_fill_in(self):
        with pytest.raises(DslError, match="no '\\{X\\}'"):
            compile_card(
                self._card(
                    abilities=[
                        self._ability({"mana": "{2}", "x_value": {"const": 1}})
                    ]
                )
            )

    def test_a_triggered_ability_is_refused(self):
        with pytest.raises(DslError, match="activated ability's cost"):
            compile_card(
                self._card(
                    abilities=[
                        self._ability(
                            {"mana": "{X}", "x_value": {"const": 1}}, kind="triggered"
                        )
                    ]
                )
            )

    def test_an_additional_cost_is_refused(self):
        """A spell's additional mana is folded into its price, never priced by
        `ability_mana`, so an `x_value` there would load and do nothing."""
        with pytest.raises(DslError, match="activated ability's cost"):
            compile_card(
                self._card(
                    types=["Sorcery"],
                    additional_cost={"mana": "{X}", "x_value": {"const": 1}},
                    spell_effects=[{"op": "draw", "player": "you"}],
                )
            )

    def test_an_optional_payment_is_refused(self):
        with pytest.raises(DslError, match="not to an optional payment"):
            compile_card(
                self._card(
                    types=["Sorcery"],
                    spell_effects=[
                        {
                            "op": "may",
                            "pay": {"mana": "{X}", "x_value": {"const": 1}},
                            "effects": [{"op": "draw", "player": "you"}],
                        }
                    ],
                )
            )

    def test_a_bad_value_expression_is_a_load_error(self):
        with pytest.raises(DslError, match="unknown value keys"):
            compile_card(
                self._card(
                    abilities=[
                        self._ability({"mana": "{X}", "x_value": {"nonsense": 1}})
                    ]
                )
            )
