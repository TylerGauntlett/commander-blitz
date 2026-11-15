"""Linking an exiled card to a token made in the same resolution (607.2a, 400.7).

    Timothar, Baron of Bats: "Whenever another nontoken Vampire you control
    dies, you may pay {1} and exile it. If you do, create a 1/1 black Bat
    creature token with flying. It gains 'When this token deals combat damage
    to a player, sacrifice it and return the exiled card to the battlefield
    tapped.'"

"The exiled card" is the one this resolution exiled, and the ability asking
for it is the **Bat's**, so the link has to run from the card to the Bat. The
`exile` op's ``link`` names the resolving source (Timothar), and a selector of
"cards exiled with Timothar" would let one Bat return every Vampire it ever
exiled. `link_exiled` writes the `zones.link_exiled` record with the bound
token as the exiler, so the Bat's own `exiled_with: "self"` finds its card
and no other. The link is the card's (`exiled_by`), so it outlives the Bat
being sacrificed first; and a card that left exile is a new object (400.7)
that no Bat can return.

`t_lx_baron` is Timothar without its ward; `t_lx_vampire` is a nontoken
Vampire for it to watch.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, attack_with, find_action, oids_of, only_oid, pass_until

BARON = "t_lx_baron"
VAMPIRE = "t_lx_vampire"
BAT = "bat_1_1_b_flying"


def position(builder, vampires: int = 1):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3 + [BARON] + [VAMPIRE] * vampires)
        # A land to play keeps the turn in the main phase between deaths.
        .hand(0, ["swamp"])
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    game._advance()
    return game, oids_of(game, VAMPIRE, 0)


def accept(game) -> None:
    """Settle the stack, saying yes to "you may pay {1}"."""
    for _ in range(80):
        decision = game.pending()
        if (
            not game.state.stack
            and not game.state.pending_triggers
            and (decision is None or decision.kind is DecisionKind.PRIORITY)
        ):
            return
        if decision is None:
            game._advance()
            continue
        if decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


def dies(game, oid: int) -> int:
    """Kill ``oid``, pay for the trigger, and return the Bat it made."""
    before = set(oids_of(game, BAT, 0))
    move_object(game.state, oid, Zone.GRAVEYARD)
    accept(game)
    (bat,) = set(oids_of(game, BAT, 0)) - before
    return bat


def hit(game, *bats: int) -> None:
    """Attack player 1 with ``bats``, unblocked, through combat damage."""
    for bat in bats:
        game.state.objects[bat].entered_turn = game.state.turn - 1
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for bat in bats:
        attack_with(game, bat, 1)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: g.state.step >= Step.END_OF_COMBAT
        and not g.state.stack
        and not g.state.pending_triggers,
    )


class TestTheLink:
    def test_the_card_is_exiled_with_the_bat(self, builder):
        game, (vampire,) = position(builder)
        bat = dies(game, vampire)
        card = game.state.objects[vampire]
        assert card.zone is Zone.EXILE
        assert card.exiled_by == bat

    def test_each_bat_holds_its_own_card(self, builder):
        game, (first, second) = position(builder, vampires=2)
        bat_one = dies(game, first)
        bat_two = dies(game, second)
        assert game.state.objects[first].exiled_by == bat_one
        assert game.state.objects[second].exiled_by == bat_two


class TestTheReturn:
    def test_the_bat_returns_its_card_tapped(self, builder):
        game, (vampire,) = position(builder)
        bat = dies(game, vampire)
        hit(game, bat)
        card = game.state.objects[vampire]
        assert card.zone is Zone.BATTLEFIELD
        assert card.tapped
        assert bat not in game.state.battlefield, "it sacrificed itself first"

    def test_one_bat_returns_only_its_own_card(self, builder):
        game, (first, second) = position(builder, vampires=2)
        bat_one = dies(game, first)
        dies(game, second)
        hit(game, bat_one)
        assert game.state.objects[first].zone is Zone.BATTLEFIELD
        assert game.state.objects[second].zone is Zone.EXILE

    def test_a_card_that_left_exile_does_not_come_back(self, builder):
        """400.7: returned to exile by something else, it is a new object."""
        game, (vampire,) = position(builder)
        bat = dies(game, vampire)
        move_object(game.state, vampire, Zone.GRAVEYARD)
        move_object(game.state, vampire, Zone.EXILE)
        assert game.state.objects[vampire].exiled_by is None
        hit(game, bat)
        assert game.state.objects[vampire].zone is Zone.EXILE


class TestTheLoaderRefusesHalfALink:
    @pytest.mark.parametrize(
        "effect",
        [
            {"op": "link_exiled", "to": "bat"},
            {"op": "link_exiled", "objects": {"binding": "exiled"}},
            {"op": "link_exiled", "objects": {"binding": "exiled"}, "to": ""},
        ],
    )
    def test_both_ends_are_required(self, effect):
        model = CardModel.model_validate(
            {
                "id": "t_lx_broken",
                "name": "Broken Link",
                "oracle_text": "When this creature enters, link it.",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "When this creature enters, link it.",
                        "trigger": {"event": "self_enters", "source": "self"},
                        "effects": [effect],
                    }
                ],
            }
        )
        with pytest.raises(DslError):
            compile_card(model)


def test_the_bat_is_the_printed_token(builder):
    game, (vampire,) = position(builder)
    bat = dies(game, vampire)
    assert only_oid(game, BAT, 0) == bat
