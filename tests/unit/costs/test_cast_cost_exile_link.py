"""A spell's additional exile cost that links the card to the permanent it becomes.

    Redemptor Dreadnought: "Fallen Warrior — As an additional cost to cast this
    spell, you may exile a creature card from your graveyard. Trample. Plasma
    Incinerator — Whenever this creature attacks, if a card is exiled with it,
    it gets +X/+X until end of turn, where X is the power of the exiled card."

`additional_cost` + `additional_optional` already charged "you may exile a
creature card from your graveyard", but the card went to exile linked to
nothing, so `{"zone": "exile", "exiled_with": "self"}` on the creature found
nothing and the attack trigger never fired. `link: true` on the
`exile_from_graveyard` cost is the capability.

The rules argument is *what* the card is linked to. 607.2a: the exiled card is
linked to the permanent the spell becomes. So nothing is linked while the spell
is on the stack, a spell that is countered links nothing (it became no
permanent), and a card that left exile before the spell resolved is a new
object (400.7) that is linked to nothing. Linking at cast time to the spell's
object would have been the near miss: it reads the same on the happy path and
wrongly survives a counter, since the oid survives the move to the graveyard.

`t_dreadnought` is Redemptor Dreadnought at one mana.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import attack_with, find_action, only_oid, pass_until, pt, settle

DREADNOUGHT = "t_dreadnought"  # {G} 4/4 trample
BEAR = "t_bear"  # 2/2
GIANT = "t_big"  # 6/6


def position(builder, graveyard=(BEAR,), *, counter: bool = False):
    """The Dreadnought in hand, a Forest, and a graveyard to pay from.

    With ``counter``, the opponent holds a Counterspell and the Islands for it,
    which also keeps the spell on the stack: a seat with a play to make is not
    passed for automatically.
    """
    b = (
        builder(players=2)
        .battlefield(0, ["forest"])
        .hand(0, [DREADNOUGHT])
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    if counter:
        b = b.hand(1, ["t_counterspell"]).battlefield(1, ["island", "island"])
    game = b.build()
    (spell,) = [o for o in game.state.players[0].hand if game.state.objects[o].def_id == DREADNOUGHT]
    return game, spell


def in_graveyard(game, card_id: str) -> list[int]:
    return [
        oid for oid in game.state.players[0].graveyard if game.state.objects[oid].def_id == card_id
    ]


def cast_lines(game, spell: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == spell]


def cast(game, spell: int, exiled: int | None) -> None:
    """Cast the Dreadnought, paying the cost with ``exiled`` or declining it."""
    times = 0 if exiled is None else 1
    game.apply(next(a for a in cast_lines(game, spell) if a.additional_times == times))
    decision = game.pending()
    if (
        exiled is not None
        and decision is not None
        and decision.kind is DecisionKind.CHOOSE_OBJECTS
        and decision.context.get("purpose") == "exile_cost"
    ):
        # One candidate is chosen for the payer; a choice is asked only of two.
        index = next(i for i, o in enumerate(decision.options) if o.ref and o.ref.id == exiled)
        game.apply(
            next(
                a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index
            )
        )
        if game.pending() is decision:
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def resolve(game) -> int:
    settle(game)
    return only_oid(game, DREADNOUGHT, 0)


def attack(game, dreadnought: int) -> None:
    """Attack player 1 and let the attack trigger resolve."""
    game.state.objects[dreadnought].entered_turn = game.state.turn - 1
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, dreadnought, 1)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: g.state.step >= Step.DECLARE_BLOCKERS
        and not g.state.stack
        and not g.state.pending_triggers,
    )


class TestWhenItIsOffered:
    def test_a_creature_card_in_the_graveyard_offers_both_lines(self, builder):
        game, spell = position(builder)
        assert sorted({a.additional_times for a in cast_lines(game, spell)}) == [0, 1]

    def test_no_creature_card_offers_only_the_unpaid_line(self, builder):
        game, spell = position(builder, graveyard=("forest",))
        assert sorted({a.additional_times for a in cast_lines(game, spell)}) == [0]


class TestTheLink:
    def test_the_card_is_exiled_and_not_yet_linked_while_the_spell_is_on_the_stack(
        self, builder
    ):
        """607.2a links it to the permanent, and there is none yet."""
        game, spell = position(builder, counter=True)
        (bear,) = in_graveyard(game, BEAR)

        cast(game, spell, bear)

        assert game.state.stack, "the spell should still be on the stack"
        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[bear].exiled_by is None

    def test_the_card_is_exiled_with_the_permanent_the_spell_becomes(self, builder):
        game, spell = position(builder)
        (bear,) = in_graveyard(game, BEAR)
        cast(game, spell, bear)

        dreadnought = resolve(game)

        assert game.state.objects[bear].exiled_by == dreadnought
        assert game.state.objects[dreadnought].exiled_cards == [bear]

    def test_declining_the_cost_links_nothing(self, builder):
        game, spell = position(builder)
        (bear,) = in_graveyard(game, BEAR)
        cast(game, spell, None)

        dreadnought = resolve(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[dreadnought].exiled_cards == []

    def test_a_countered_spell_links_nothing(self, builder):
        """It became no permanent, so there is nothing for the card to be exiled with."""
        game, spell = position(builder, counter=True)
        (bear,) = in_graveyard(game, BEAR)
        cast(game, spell, bear)
        if game.pending().player == 0:
            game.apply(find_action(game, ActionKind.PASS))
        counterspell = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "t_counterspell"
        )
        game.apply(counterspell)
        settle(game)

        assert game.state.objects[spell].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[bear].exiled_by is None

    def test_a_card_that_left_exile_before_resolution_is_not_linked(self, builder):
        """400.7: back in the graveyard it is a new object, never exiled with anything."""
        game, spell = position(builder, counter=True)
        (bear,) = in_graveyard(game, BEAR)
        cast(game, spell, bear)
        move_object(game.state, bear, Zone.GRAVEYARD)

        dreadnought = resolve(game)

        assert game.state.objects[bear].exiled_by is None
        assert game.state.objects[dreadnought].exiled_cards == []


class TestPlasmaIncinerator:
    def test_it_gets_the_exiled_cards_power(self, builder):
        game, spell = position(builder, graveyard=(GIANT,))
        (giant,) = in_graveyard(game, GIANT)
        cast(game, spell, giant)
        dreadnought = resolve(game)

        attack(game, dreadnought)

        assert pt(game, dreadnought) == (10, 10)

    def test_with_nothing_exiled_it_stays_a_four_four(self, builder):
        game, spell = position(builder, graveyard=(GIANT,))
        cast(game, spell, None)
        dreadnought = resolve(game)

        attack(game, dreadnought)

        assert pt(game, dreadnought) == (4, 4)

    def test_another_card_in_exile_does_not_count(self, builder):
        """The near miss a bare `{"zone": "exile"}` would be."""
        game, spell = position(builder, graveyard=(GIANT,))
        (giant,) = in_graveyard(game, GIANT)
        move_object(game.state, giant, Zone.EXILE)
        cast(game, spell, None)
        dreadnought = resolve(game)

        attack(game, dreadnought)

        assert pt(game, dreadnought) == (4, 4)

    def test_it_wears_off_at_end_of_turn(self, builder):
        game, spell = position(builder, graveyard=(BEAR,))
        (bear,) = in_graveyard(game, BEAR)
        cast(game, spell, bear)
        dreadnought = resolve(game)
        attack(game, dreadnought)
        assert pt(game, dreadnought) == (6, 6)

        pass_until(game, lambda g: g.state.active_player == 1)

        assert pt(game, dreadnought) == (4, 4)


SPELL_MODEL = {
    "id": "t_link_guard",
    "name": "Test Link Guard",
    "oracle_text": "As an additional cost to cast this spell, exile a creature card from your graveyard.",
    "mana_cost": "{G}",
    "types": ["Creature"],
    "power": 1,
    "toughness": 1,
    "additional_cost": {"exile_from_graveyard": {"types": ["Creature"], "link": True}},
}


def _model(**changes) -> CardModel:
    card = copy.deepcopy(SPELL_MODEL)
    card.update(changes)
    return CardModel.model_validate(card)


class TestLoadTimeGuards:
    def test_a_permanent_spells_linked_cost_loads(self):
        card = compile_card(_model())
        assert card.additional_cost.exile_from_graveyard["link"] is True

    def test_an_activated_abilitys_linked_cost_loads(self):
        ability = {
            "kind": "activated",
            "text": "Exile a creature card from your graveyard: Draw a card.",
            "cost": {"exile_from_graveyard": {"types": ["Creature"], "link": True}},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
        card = compile_card(_model(additional_cost=None, abilities=[ability]))
        assert card.abilities[0].cost.exile_from_graveyard["link"] is True

    def test_an_instant_has_no_permanent_to_link_to(self):
        with pytest.raises(DslError, match="only an activated"):
            compile_card(
                _model(
                    types=["Instant"],
                    power=None,
                    toughness=None,
                    spell_effects=[{"op": "draw", "player": "you", "amount": {"const": 1}}],
                )
            )

    def test_link_must_be_true(self):
        with pytest.raises(DslError, match="true or absent"):
            compile_card(
                _model(additional_cost={"exile_from_graveyard": {"types": ["Creature"], "link": 1}})
            )
