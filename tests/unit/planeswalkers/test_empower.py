"""Empower Jace N: loyalty on a Jace token, which may first have to be made.

Reality Fracture's keyword action, and the reminder text printed on every card
that does it is the whole rule: *(Put N loyalty counters on a Jace token you
control. If you don't control one, first create a blue Jace planeswalker token
with "[-1]: Surveil 1" and "[-3]: Draw a card.")* Plan for All Outcomes is
the shipped witness.

Three ways to get it wrong, each a different card from the printed one:

- **Making a Jace you did not need.** `create_token` then `add_counters` puts
  a second Jace beside the one you control, so every empower would be a fresh
  planeswalker. The token is created only when you control no Jace *token* --
  an opponent's does not count, and neither does a Jace planeswalker card.
- **Countering every Jace.** The counters go on *a* Jace token. With two (a
  doubled creation), the player picks one, and the other is left at zero
  loyalty for 704.5i.
- **Letting 704.5i look too early.** The token's printed loyalty is 0. Created
  and countered inside one effect, it is never seen by a state-based action at
  zero unless nothing was put on it.

And the token is the first planeswalker token in the pool, so it is pinned here
that it works with the loyalty machinery a planeswalker card uses: both
abilities offered, a minus it cannot afford withheld, one activation a turn,
and the abilities doing what they print.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_counters import EMPOWER_TOKEN
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from tests.conftest import (
    action_for_card,
    activations,
    hand_ids,
    pass_until,
    settle,
    settle_completely,
)

JACE_CARD = "t_jace_walker"  # a Jace planeswalker *card*, loyalty 4
INSTANT = "t_plain_instant"  # {W}: you gain 1 life


def board(builder, *, mine=(), theirs=()):
    """Player 0 in their precombat main with a library to surveil and draw from.

    The Plains in hand is a land drop to make, which is what stops the
    builder's auto-pass handing an empty board's turn to player 1.
    """
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, ["plains"])
        .library(0, ["island"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def empower(game, amount, *, controller: int = 0, pick: int = 0) -> list:
    """Run ``empower`` directly, answering any choice with option ``pick``.

    Returns the decisions it raised, so a test can say whether it asked.
    """
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    gen = execute(ctx, [{"op": "empower", "amount": amount}])
    asked, send = [], None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        send = [pick]


def jace_tokens(game, pid: int = 0) -> list[int]:
    state = game.state
    return [
        oid
        for oid in state.battlefield
        if state.objects[oid].controller == pid
        and state.objects[oid].is_token
        and "Jace" in chars(state, oid).subtypes
    ]


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counter("loyalty")


class TestTheToken:
    def test_it_is_the_printed_jace(self, registry):
        """The catalog's tfra token row: a blue Jace planeswalker, loyalty 0."""
        jace = registry.get(EMPOWER_TOKEN)
        assert jace is not None and jace.is_token
        assert jace.name == "Jace"
        assert "Planeswalker" in jace.types
        assert list(jace.subtypes) == ["Jace"]
        assert sorted(jace.colors) == ["U"]
        assert jace.loyalty == 0
        assert [a.cost.loyalty for a in jace.abilities] == [-1, -3]

    def test_a_deck_list_cannot_name_it(self, registry):
        """No card is named Jace; the token must not answer for one."""
        found = registry.by_name("Jace")
        assert found is None or not found.is_token


class TestWithNoJace:
    def test_it_creates_one_with_the_counters(self, builder):
        game = board(builder)
        empower(game, {"const": 2})
        [jace] = jace_tokens(game)
        assert game.state.card(jace).id == EMPOWER_TOKEN
        assert loyalty(game, jace) == 2

    def test_it_survives_the_state_based_actions(self, builder):
        """Its printed loyalty is 0; the counters arrive in the same effect."""
        game = board(builder)
        empower(game, {"const": 1})
        settle(game)
        [jace] = jace_tokens(game)
        assert loyalty(game, jace) == 1

    def test_zero_makes_a_jace_that_dies(self, builder):
        """"Empower Jace X" with X = 0 still creates the token, with nothing on
        it, and 704.5i puts it into the graveyard (where a token ceases to
        exist)."""
        game = board(builder)
        empower(game, {"const": 0})
        assert len(jace_tokens(game)) == 1
        pass_until(game, lambda g: not jace_tokens(g))

    def test_a_negative_amount_is_zero(self, builder):
        """107.1b: a negative X is 0, never a removal."""
        game = board(builder)
        empower(game, {"const": -3})
        [jace] = jace_tokens(game)
        assert loyalty(game, jace) == 0


class TestWithAJace:
    def test_it_counters_the_one_you_control(self, builder):
        game = board(builder)
        empower(game, {"const": 2})
        [jace] = jace_tokens(game)
        empower(game, {"const": 3})
        assert jace_tokens(game) == [jace], "no second Jace"
        assert loyalty(game, jace) == 5

    def test_an_opponents_jace_is_not_yours(self, builder):
        game = board(builder)
        [theirs] = create_token(game.state, EMPOWER_TOKEN, 1)
        game.state.objects[theirs].counters["loyalty"] = 3
        empower(game, {"const": 2})
        [mine] = jace_tokens(game, 0)
        assert mine != theirs
        assert loyalty(game, mine) == 2
        assert loyalty(game, theirs) == 3

    def test_a_jace_card_is_not_a_jace_token(self, builder):
        game = board(builder, mine=[JACE_CARD])
        [card] = [o for o in game.state.battlefield if game.state.card(o).id == JACE_CARD]
        empower(game, {"const": 2})
        assert len(jace_tokens(game)) == 1
        assert loyalty(game, card) == 4

    def test_with_two_it_asks_and_counters_only_one(self, builder):
        game = board(builder)
        first, second = create_token(game.state, EMPOWER_TOKEN, 0, 2)
        for oid in (first, second):
            game.state.objects[oid].counters["loyalty"] = 1
        asked = empower(game, {"const": 2}, pick=1)
        assert [d.kind for d in asked] == [DecisionKind.CHOOSE_OBJECTS]
        assert asked[0].player == 0
        assert (loyalty(game, first), loyalty(game, second)) == (1, 3)


class TestUnderDoublingSeason:
    def test_two_jaces_one_empowered_and_the_counters_doubled(self, builder):
        """Doubling Season doubles the creation and the counters. One Jace gets
        the doubled counters; the other is left at zero and dies."""
        game = board(builder, mine=["doubling_season"])
        asked = empower(game, {"const": 2})
        assert len(asked) == 1, "two Jaces, so the player chooses"
        counters = sorted(loyalty(game, oid) for oid in jace_tokens(game))
        assert counters == [0, 4]
        pass_until(game, lambda g: len(jace_tokens(g)) == 1)
        [survivor] = jace_tokens(game)
        assert loyalty(game, survivor) == 4


class TestTheTokensLoyaltyAbilities:
    """The first planeswalker token: the machinery a planeswalker card uses
    has to reach it unchanged."""

    def jace(self, builder, amount: int):
        game = board(builder)
        empower(game, {"const": amount})
        [jace] = jace_tokens(game)
        return game, jace

    def test_both_are_offered(self, builder):
        game, jace = self.jace(builder, 3)
        assert {a.ability_index for a in activations(game, jace)} == {0, 1}

    def test_a_minus_it_cannot_afford_is_withheld(self, builder):
        game, jace = self.jace(builder, 2)
        assert {a.ability_index for a in activations(game, jace)} == {0}

    def test_minus_one_surveils(self, builder):
        game, jace = self.jace(builder, 2)
        mark = len(game.state.events)
        game.apply(activations(game, jace, 0)[0])
        assert loyalty(game, jace) == 1, "paid as the ability is activated"
        settle_completely(game)
        [looked] = [
            e for e in game.state.events[mark:] if e.type == "surveil" and e.player == 0
        ]
        assert looked.data["looked"] == 1
        assert loyalty(game, jace) == 1

    def test_minus_three_draws_and_spends_the_last_loyalty(self, builder):
        game, jace = self.jace(builder, 3)
        game.apply(activations(game, jace, 1)[0])
        settle_completely(game)
        assert hand_ids(game) == ["plains", "island"]
        assert jace_tokens(game) == [], "zero loyalty: 704.5i"

    def test_only_one_a_turn(self, builder):
        """606.3 counts the permanent, token or not."""
        game, jace = self.jace(builder, 6)
        game.apply(activations(game, jace, 0)[0])
        settle_completely(game)
        assert activations(game, jace) == []

    def test_they_are_sorcery_speed(self, registry):
        assert all(a.sorcery_speed_only for a in registry.get(EMPOWER_TOKEN).abilities)


class TestTheLoaderRefuses:
    def test_an_empower_without_an_amount(self):
        probe = CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Empower Jace 2.",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "empower"}],
            }
        )
        with pytest.raises(DslError, match="empower needs an 'amount'"):
            compile_card(probe)


class TestPlanForAllOutcomes:
    """The witness: "Whenever you cast your first noncreature spell each turn,
    empower Jace 1." The behaviour gate never casts a second spell, so the
    trigger is only covered here."""

    def cast_instant(self, game):
        game.apply(action_for_card(game, ActionKind.CAST, INSTANT))
        settle_completely(game)

    def test_the_first_noncreature_spell_makes_a_jace(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plan_for_all_outcomes", "plains", "plains"])
            .hand(0, [INSTANT, INSTANT])
            .library(0, ["island"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        self.cast_instant(game)
        [jace] = jace_tokens(game)
        assert loyalty(game, jace) == 1
        self.cast_instant(game)
        assert jace_tokens(game) == [jace]
        assert loyalty(game, jace) == 1, "the second noncreature spell does not empower"
