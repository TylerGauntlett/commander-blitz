"""Restrictions judged on the whole declaration: "can't attack or block alone".

    Toby, Beastie Befriender — "When Toby enters, create a 4/4 white Beast
                                creature token with 'This token can't attack or
                                block alone.'"

Rules 508.1c and 509.1b: attack and block *restrictions* are checked against the
declaration once it is complete, not against each creature as it is picked. That
is the whole content of the word **alone** — the same creature, on the same
board, is legal beside a second attacker and illegal by itself, so there is
nothing to refuse at the moment it is chosen.

Every prohibition the engine had before this was the other shape. `cant_attack`
and `cant_block` take one oid and answer yes/no with no view of the rest of the
declaration (`characteristics.attack_forbidden`), so writing the token with
either would have printed a Beast that can *never* attack or block — strictly
stronger than the card, and invisible on screen. `block_restriction`'s
`require_all` is the one whole-declaration check that existed, and it asks a
different question from the attacker's side. On the attack side there was no
whole-declaration hook at all: `blocks_valid` had no `attacks_valid` counterpart
until this.

So the two claims worth testing are (a) that the restriction bites on the
finished declaration and nowhere earlier, and (b) that it is not an absolute
prohibition wearing a costume.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import (
    attack_alone_forbidden,
    attack_forbidden,
    block_alone_forbidden,
    block_forbidden,
)
from automtg.engine.combat import attacks_valid, blocks_valid
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from automtg.engine.zones import destroy
from tests.conftest import find_action, oids_of, only_oid, pass_until

#: Toby's Beast: 4/4 white, "This token can't attack or block alone."
TOKEN = "beast_4_4_w_alone"
BEAR = "t_bear"


def finish_actions(game) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION]


def add_actions(game, kind: ActionKind) -> list:
    return [a for a in game.legal_actions() if a.kind is kind]


def to_attackers(game) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )


def attack_with(game, oid: int, defender: int = 1) -> None:
    game.apply(
        find_action(
            game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(defender),)
        )
    )


def block_with(game, blocker: int, attacker: int) -> None:
    game.apply(
        find_action(
            game, ActionKind.ADD_BLOCKER, source=blocker, targets=(TargetRef.obj(attacker),)
        )
    )


def attack_position(builder, *, friends: tuple[str, ...] = ()):
    """``(game, token_oid)`` with the active player at declare attackers.

    ``friends`` are the other creatures on the token's own side — the company
    the restriction is about, so a test that passes none is asking what happens
    when there is nobody to attack alongside.
    """
    game = (
        builder(players=2)
        .battlefield(0, [TOKEN, *friends])
        .battlefield(1, [BEAR])
        .build()
    )
    to_attackers(game)
    return game, oids_of(game, TOKEN, 0)[0]


def block_position(builder, *, friends: tuple[str, ...] = ()):
    """``(game, token_oid, attacker_oid)`` with a bear attacking into the token."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR])
        .battlefield(1, [TOKEN, *friends])
        .build()
    )
    to_attackers(game)
    attacker = only_oid(game, BEAR, 0)
    attack_with(game, attacker)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, oids_of(game, TOKEN, 1)[0], attacker


class TestItIsNotAnAbsoluteProhibition:
    """The near miss the gap record was filed over: `cant_attack` would have
    stopped the Beast attacking at all."""

    def test_the_alone_statics_are_read_off_the_token(self, builder):
        game, oid = attack_position(builder)
        assert attack_alone_forbidden(game.state, oid)
        assert block_alone_forbidden(game.state, oid)

    def test_the_absolute_prohibitions_stay_false(self, builder):
        game, oid = attack_position(builder)
        assert not attack_forbidden(game.state, oid), (
            "`cant_attack` is absolute; a creature that can't attack alone can attack"
        )
        assert not block_forbidden(game.state, oid)

    def test_it_is_still_offered_as_an_attacker(self, builder):
        """Nothing is refused when the creature is picked — the restriction is
        about the declaration, and a one-creature declaration is not finished
        yet."""
        game, oid = attack_position(builder)
        assert [a for a in add_actions(game, ActionKind.ADD_ATTACKER) if a.source == oid]

    def test_an_ordinary_creature_is_unaffected(self, builder):
        game, _ = attack_position(builder, friends=(BEAR,))
        assert not attack_alone_forbidden(game.state, only_oid(game, BEAR, 0))
        assert not block_alone_forbidden(game.state, only_oid(game, BEAR, 0))


class TestItCannotAttackAlone:
    def test_alone_the_declaration_cannot_be_finished(self, builder):
        game, oid = attack_position(builder, friends=(BEAR,))
        attack_with(game, oid)
        assert not attacks_valid(game.state, 0)
        assert finish_actions(game) == [], (
            "'Done attacking' is the only lever legality has, exactly as it is "
            "for menace on the blocking side"
        )
        assert add_actions(game, ActionKind.ADD_ATTACKER), "the way out is a second attacker"

    def test_with_one_other_attacker_it_is_allowed(self, builder):
        game, oid = attack_position(builder, friends=(BEAR,))
        attack_with(game, oid)
        attack_with(game, only_oid(game, BEAR, 0))
        assert attacks_valid(game.state, 0)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.objects[oid].tapped, "it attacked, so it tapped"

    def test_two_of_them_together_are_each_other_s_company(self, builder):
        """Neither is alone, which is what the printed word says — a rule that
        counted *unrestricted* attackers would refuse this."""
        game, oid = attack_position(builder, friends=(TOKEN,))
        other = next(o for o in oids_of(game, TOKEN, 0) if o != oid)
        attack_with(game, oid)
        attack_with(game, other)
        assert attacks_valid(game.state, 0)
        assert finish_actions(game)

    def test_with_nothing_else_able_the_attack_is_retracted(self, builder):
        """The deadlock escape. Nothing can be added and the declaration is
        illegal, so "Done" comes back and the attack that was never legal is
        dropped — "it doesn't attack" is exactly what the rules produce."""
        game, oid = attack_position(builder)
        attack_with(game, oid)
        assert not attacks_valid(game.state, 0)
        assert add_actions(game, ActionKind.ADD_ATTACKER) == []
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert not game.state.objects[oid].tapped, "a dropped attacker never tapped"
        assert game.state.players[1].life == game.state.players[0].life, (
            "and it dealt no combat damage"
        )

    def test_the_other_attacker_leaving_mid_declaration_invalidates_it(self, builder):
        """506.4: a creature that has left is not an attacking creature, so it
        is not company either. Read live rather than remembered from the moment
        the second attack was declared."""
        game, oid = attack_position(builder, friends=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        attack_with(game, oid)
        attack_with(game, bear)
        assert attacks_valid(game.state, 0)

        destroy(game.state, bear)
        assert not attacks_valid(game.state, 0)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert not game.state.objects[oid].tapped, "left alone, it is dropped from the attack"


class TestItCannotBlockAlone:
    def test_alone_the_declaration_cannot_be_finished(self, builder):
        game, oid, attacker = block_position(builder, friends=(BEAR,))
        block_with(game, oid, attacker)
        assert not blocks_valid(game.state, 1)
        assert finish_actions(game) == []
        assert add_actions(game, ActionKind.ADD_BLOCKER), "the way out is a second blocker"

    def test_with_one_other_blocker_it_is_allowed(self, builder):
        game, oid, attacker = block_position(builder, friends=(BEAR,))
        block_with(game, oid, attacker)
        block_with(game, only_oid(game, BEAR, 1), attacker)
        assert blocks_valid(game.state, 1)
        assert finish_actions(game)

    def test_the_second_blocker_need_not_be_blocking_the_same_attacker(self, builder):
        """Which is why this lives in `blocks_valid` and not in `can_block`:
        "alone" counts the player's whole declaration, not one attacker's."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR])
            .battlefield(1, [TOKEN, BEAR])
            .build()
        )
        to_attackers(game)
        first, second = oids_of(game, BEAR, 0)
        attack_with(game, first)
        attack_with(game, second)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        token = oids_of(game, TOKEN, 1)[0]
        block_with(game, token, first)
        assert not blocks_valid(game.state, 1)
        block_with(game, only_oid(game, BEAR, 1), second)
        assert blocks_valid(game.state, 1)

    def test_with_nothing_else_able_the_block_is_retracted(self, builder):
        game, oid, attacker = block_position(builder)
        block_with(game, oid, attacker)
        assert not blocks_valid(game.state, 1)
        assert add_actions(game, ActionKind.ADD_BLOCKER) == []
        life = game.state.players[1].life
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert game.state.players[1].life == life - 2, (
            "the block was never legal, so the bear was unblocked"
        )

    def test_the_other_blocker_leaving_mid_declaration_invalidates_it(self, builder):
        game, oid, attacker = block_position(builder, friends=(BEAR,))
        friend = only_oid(game, BEAR, 1)
        block_with(game, oid, attacker)
        block_with(game, friend, attacker)
        assert blocks_valid(game.state, 1)

        destroy(game.state, friend)
        assert not blocks_valid(game.state, 1)
        # Held across the apply: finishing runs the rest of the turn, and
        # `state.combat` is cleared at the next untap step. The `CombatState`
        # itself is what the declaration was recorded in.
        combat = game.state.combat
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert oid not in combat.blockers, "left alone, its block is dropped"


class TestTheTokenAndTheLoader:
    def test_toby_s_beast_exists_and_carries_both_halves(self, registry):
        card = registry.get(TOKEN)
        assert (card.power, card.toughness) == (4, 4)
        assert card.colors == frozenset({"W"})
        assert "Beast" in card.subtypes and card.is_token
        effects = {(a.static or {}).get("effect") for a in card.abilities if a.is_static}
        assert effects == {"cant_attack_alone", "cant_block_alone"}

    @pytest.mark.parametrize("effect", ["cant_attack_alone", "cant_block_alone"])
    def test_a_static_with_no_filter_is_refused(self, effect):
        """It would load clean, print on the card and restrict nobody:
        `_matches` reads a missing filter as matching nothing."""
        with pytest.raises(DslError, match="needs an 'affects' filter"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{W}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [{"kind": "static", "text": "x", "effect": effect}],
                    }
                )
            )
