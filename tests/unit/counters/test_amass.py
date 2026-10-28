"""Amass [subtype] N: +1/+1 counters on an Army, which may first have to be made.

Rule 701.47a: *If you don't control an Army creature, create a 0/0 black
[subtype] Army creature token. Choose an Army creature you control. Put N +1/+1
counters on that creature. If it isn't a [subtype], it becomes a [subtype] in
addition to its other types.* Dreadhorde Invasion ("amass Zombies 1" every
upkeep) is the shipped witness.

The ways to get it wrong, each a different card from the printed one:

- **Making an Army you did not need.** `create_token` then `add_counters` puts
  a fresh 0/0 beside the Army you control, so every amass would be a new body
  instead of a bigger one. The token is made only when you control no Army
  *creature* -- an opponent's does not count, and a nontoken one does.
- **Countering every Army.** The counters go on *an* Army. With two (a doubled
  creation), the player picks one, and the other is a 0/0 for 704.5f.
- **Letting 704.5f look too early.** The token is 0/0. Created and countered
  inside one effect, it is never seen by a state-based action at zero toughness
  unless nothing was put on it (amass 0 still makes it).
- **Forgetting the subtype.** The amassed Army becomes the named type: an Orc
  Army that amasses Zombies is a Zombie too, for good, and Dreadhorde
  Invasion's lifelink line counts Zombie tokens.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_counters import AMASS_TOKENS
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, add_subtypes, create_token
from tests.conftest import (
    attack_with,
    find_action,
    keywords,
    only_oid,
    pass_until,
    plus_one_counters,
    pt,
    settle,
)

ZOMBIE_ARMY = AMASS_TOKENS["Zombie"]
ORC_ARMY = AMASS_TOKENS["Orc"]
BEAR = "t_bear"


def board(builder, *, mine=(), theirs=()):
    """Player 0 in their precombat main; the Plains in hand keeps the builder's
    auto-pass from handing an empty board's turn to player 1."""
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


def amass(game, amount, subtype="Zombie", *, pick: int = 0, bind: str | None = None):
    """Run ``amass`` directly, answering any choice with option ``pick``.

    Returns ``(decisions raised, bindings)``.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    spec = {"op": "amass", "subtype": subtype, "amount": amount}
    if bind:
        spec["as"] = bind
    gen = execute(ctx, [spec])
    asked, send = [], None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked, ctx.bindings
        asked.append(decision)
        send = [pick]


def armies(game, pid: int = 0) -> list[int]:
    state = game.state
    return [
        oid
        for oid in state.battlefield
        if state.objects[oid].controller == pid and "Army" in chars(state, oid).subtypes
    ]


def subtypes(game, oid: int) -> set[str]:
    return set(chars(game.state, oid).subtypes)


class TestWithNoArmy:
    def test_it_creates_the_token_with_the_counters(self, builder):
        game = board(builder)
        amass(game, {"const": 2})
        [army] = armies(game)
        assert game.state.card(army).id == ZOMBIE_ARMY
        assert game.state.objects[army].is_token
        assert pt(game, army) == (2, 2)

    def test_the_subtype_picks_the_token(self, builder):
        game = board(builder)
        amass(game, {"const": 1}, "Orc")
        [army] = armies(game)
        assert game.state.card(army).id == ORC_ARMY
        assert subtypes(game, army) == {"Orc", "Army"}

    def test_it_survives_the_state_based_actions(self, builder):
        """A 0/0; the counters arrive in the same effect."""
        game = board(builder)
        amass(game, {"const": 1})
        settle(game)
        [army] = armies(game)
        assert pt(game, army) == (1, 1)

    def test_zero_makes_an_army_that_dies(self, builder):
        """Amass 0 still creates the token, and 704.5f takes it."""
        game = board(builder)
        amass(game, {"const": 0})
        assert len(armies(game)) == 1
        pass_until(game, lambda g: not armies(g))

    def test_a_negative_amount_is_zero(self, builder):
        """107.1b: a negative X is 0, never a removal."""
        game = board(builder)
        amass(game, {"const": -3})
        [army] = armies(game)
        assert plus_one_counters(game, army) == 0


class TestWithAnArmy:
    def test_it_grows_the_one_you_control(self, builder):
        game = board(builder)
        amass(game, {"const": 2})
        [army] = armies(game)
        amass(game, {"const": 3})
        assert armies(game) == [army], "no second Army"
        assert pt(game, army) == (5, 5)

    def test_an_opponents_army_is_not_yours(self, builder):
        game = board(builder)
        [theirs] = create_token(game.state, ZOMBIE_ARMY, 1)
        add_counters(game.state, theirs, "+1/+1", 3)
        amass(game, {"const": 2})
        [mine] = armies(game, 0)
        assert mine != theirs
        assert pt(game, mine) == (2, 2)
        assert pt(game, theirs) == (3, 3)

    def test_a_nontoken_army_creature_counts(self, builder):
        """"An Army creature you control" -- read off the characteristics."""
        game = board(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        add_subtypes(game.state, bear, ["Army"])
        before = pt(game, bear)
        amass(game, {"const": 2})
        assert armies(game) == [bear]
        assert pt(game, bear) == (before[0] + 2, before[1] + 2)
        assert "Zombie" in subtypes(game, bear)

    def test_with_two_it_asks_and_grows_only_one(self, builder):
        game = board(builder)
        first, second = create_token(game.state, ZOMBIE_ARMY, 0, 2)
        for oid in (first, second):
            add_counters(game.state, oid, "+1/+1", 1)
        asked, _ = amass(game, {"const": 2}, pick=1)
        assert [d.kind for d in asked] == [DecisionKind.CHOOSE_OBJECTS]
        assert asked[0].player == 0
        assert (pt(game, first), pt(game, second)) == ((1, 1), (3, 3))

    def test_as_records_the_amassed_army(self, builder):
        """"The amassed Army" -- the one chosen, for a later line."""
        game = board(builder)
        _, bindings = amass(game, {"const": 2}, bind="army")
        assert bindings["army"] == armies(game)


class TestTheSubtype:
    def test_an_orc_army_amassing_zombies_becomes_a_zombie(self, builder):
        game = board(builder)
        amass(game, {"const": 1}, "Orc")
        [army] = armies(game)
        amass(game, {"const": 1}, "Zombie")
        assert armies(game) == [army]
        assert subtypes(game, army) == {"Orc", "Zombie", "Army"}

    def test_it_stays_past_the_turn(self, builder):
        """No duration: the type is the Army's until it leaves (701.47a)."""
        game = board(builder)
        amass(game, {"const": 1}, "Orc")
        [army] = armies(game)
        amass(game, {"const": 1}, "Goblin")
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert "Goblin" in subtypes(game, army)

    def test_a_zombie_army_is_not_made_a_zombie_twice(self, builder):
        game = board(builder)
        amass(game, {"const": 1})
        [army] = armies(game)
        amass(game, {"const": 1})
        assert list(chars(game.state, army).subtypes).count("Zombie") == 1


class TestUnderDoublingSeason:
    def test_two_armies_one_amassed_and_the_counters_doubled(self, builder):
        """Doubling Season doubles the creation and the counters. One Army gets
        the doubled counters; the other is a 0/0 and dies."""
        game = board(builder, mine=["doubling_season"])
        asked, _ = amass(game, {"const": 2})
        assert len(asked) == 1, "two Armies, so the player chooses"
        assert sorted(plus_one_counters(game, oid) for oid in armies(game)) == [0, 4]
        pass_until(game, lambda g: len(armies(g)) == 1)
        [survivor] = armies(game)
        assert pt(game, survivor) == (4, 4)


class TestTheLoaderRefuses:
    @staticmethod
    def probe(effect):
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Amass Zombies 2.",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_an_amass_without_an_amount(self):
        with pytest.raises(DslError, match="amass needs an 'amount'"):
            compile_card(self.probe({"op": "amass", "subtype": "Zombie"}))

    def test_an_amass_without_a_subtype(self):
        with pytest.raises(DslError, match="amass needs a 'subtype'"):
            compile_card(self.probe({"op": "amass", "amount": {"const": 2}}))

    def test_the_printed_plural_is_not_a_subtype(self):
        """"Amass Zombies" names the subtype Zombie; the plural has no token."""
        effect = {"op": "amass", "subtype": "Zombies", "amount": {"const": 2}}
        with pytest.raises(DslError, match="amass needs a 'subtype'"):
            compile_card(self.probe(effect))


class TestDreadhordeInvasion:
    """The witness. The behaviour gate casts it in a main phase, so neither
    trigger is covered there: the upkeep amass and the lifelink grant are here."""

    def test_each_upkeep_costs_a_life_and_amasses_one(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["dreadhorde_invasion"])
            .library(0, ["island"] * 10)
            .active(0)
            .step(Step.UNTAP)
            .build()
        )
        pass_until(
            game,
            lambda g: g.state.step is Step.DRAW or g.state.step is Step.PRECOMBAT_MAIN,
        )
        [army] = armies(game)
        assert game.state.card(army).id == ZOMBIE_ARMY
        assert pt(game, army) == (1, 1)
        me = game.state.players[0]
        assert me.life == me.starting_life - 1

    def attack(self, builder, counters: int, *, token: bool = True):
        game = (
            builder(players=2)
            .battlefield(0, ["dreadhorde_invasion"])
            .battlefield(0, [ZOMBIE_ARMY], counters={"+1/+1": counters})
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        army = only_oid(game, ZOMBIE_ARMY, 0)
        game.state.objects[army].is_token = token
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        attack_with(game, army)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settle(game)
        return game, army

    def test_a_six_power_zombie_token_gains_lifelink(self, builder):
        game, army = self.attack(builder, 6)
        assert "lifelink" in keywords(game, army)

    def test_five_power_is_not_enough(self, builder):
        game, army = self.attack(builder, 5)
        assert "lifelink" not in keywords(game, army)

    def test_a_nontoken_zombie_does_not(self, builder):
        game, army = self.attack(builder, 6, token=False)
        assert "lifelink" not in keywords(game, army)
