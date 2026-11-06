"""Damage can't be prevented -- 615.12, 101.2.

Everlasting Torment is the witness: "Damage can't be prevented." A "can't"
over every prevention effect at once, so it outranks each of them however it
was made. Prevention here is not one system but a set of named hooks in
`primitives.damage_player` and `primitives.damage_permanent`, so the static
has to be read by every one of them -- one test per hook, because a static
wired into five of six is a Fog that still works.

Two things that look like prevention and are not, and must keep working:

* A shield counter (122.1c) is a replacement -- "instead remove a shield
  counter" -- and still answers the damage.
* A redirect (614.9) moves the damage rather than preventing it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE, SHIELD
from commanderblitz.engine.player_statics import damage_cant_be_prevented
from commanderblitz.engine.primitives import add_counters, attach, damage_permanent, damage_player
from commanderblitz.engine.temp_effects import fog_combat_damage, shield_permanent, shield_player
from tests.conftest import only_oid, static_probe

TORMENT = "t_no_prevention"  # Damage can't be prevented.
BEAR = "t_pc_bear"
OGRE = "t_pc_ogre"  # a red 3/3 source
WARDED = "t_pc_warded"  # protection from red
HABIT = "t_pc_habit"  # prevent damage to equipped creature, put +1/+1 counters instead
BLANKET = "t_blanket_shield"  # prevent all damage that would be dealt to creatures you control
HERB = "t_heart_herb"  # prevent 1 of damage an opponent's source would deal to you


def board(builder, mine=(), theirs=(OGRE,), *, torment: bool = True):
    extra = [TORMENT] if torment else []
    game = (
        builder(players=2)
        .battlefield(0, list(mine) + extra)
        .battlefield(1, list(theirs))
        .life(0, 40)
        .life(1, 40)
        .build(advance=False)
    )
    return game


def ogre(game) -> int:
    return only_oid(game, OGRE, 1)


class TestTheStatic:
    def test_it_is_on_while_the_permanent_is(self, builder):
        assert damage_cant_be_prevented(board(builder).state)
        assert not damage_cant_be_prevented(board(builder, torment=False).state)


class TestEveryPlayerHook:
    def test_a_shield_on_the_player(self, builder):
        game = board(builder)
        shield_player(game.state, 0)
        assert damage_player(game.state, 0, 3, ogre(game)) == 3
        assert game.state.players[0].life == 37

    def test_the_shield_still_works_without_it(self, builder):
        """The control: the same shield prevents everything."""
        game = board(builder, torment=False)
        shield_player(game.state, 0)
        assert damage_player(game.state, 0, 3, ogre(game)) == 0

    def test_absorb_over_the_player(self, builder):
        game = board(builder, mine=[HERB])
        assert damage_player(game.state, 0, 3, ogre(game)) == 3

    def test_a_fog(self, builder):
        game = board(builder)
        fog_combat_damage(game.state, 0)
        assert damage_player(game.state, 0, 3, ogre(game), is_combat=True) == 3

    def test_a_shield_on_the_dealer(self, builder):
        game = board(builder)
        shield_permanent(game.state, ogre(game), "by")
        assert damage_player(game.state, 0, 3, ogre(game)) == 3

    def test_no_prevented_event_fires(self, builder):
        game = board(builder)
        shield_player(game.state, 0)
        mark = len(game.state.events)
        damage_player(game.state, 0, 3, ogre(game))
        kinds = [e.type for e in game.state.events[mark:]]
        assert "damage_prevented" not in kinds
        assert "damage_dealt" in kinds


class TestEveryPermanentHook:
    def test_protection(self, builder):
        """702.16e: protection's damage half is a prevention like any other."""
        game = board(builder, mine=[WARDED])
        warded = only_oid(game, WARDED, 0)
        assert damage_permanent(game.state, warded, 2, ogre(game)) == 2

    def test_a_prevent_all_static(self, builder):
        game = board(builder, mine=[BLANKET, BEAR])
        bear = only_oid(game, BEAR, 0)
        assert damage_permanent(game.state, bear, 1, ogre(game)) == 1

    def test_a_shield_on_the_permanent(self, builder):
        game = board(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        shield_permanent(game.state, bear, "to")
        assert damage_permanent(game.state, bear, 1, ogre(game)) == 1

    def test_prevent_into_counters(self, builder):
        """Panther Habit prevents first: under Torment there are no counters."""
        game = board(builder, mine=[HABIT, BEAR])
        bear = only_oid(game, BEAR, 0)
        attach(game.state, only_oid(game, HABIT, 0), bear)
        assert damage_permanent(game.state, bear, 1, ogre(game)) == 1
        assert game.state.objects[bear].counter(PLUS_ONE) == 0


class TestWhatIsNotPrevention:
    def test_a_shield_counter_still_answers_the_damage(self, builder):
        game = board(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, SHIELD, 1)
        assert damage_permanent(game.state, bear, 1, ogre(game)) == 0
        assert game.state.objects[bear].counter(SHIELD) == 0


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "extra",
        [{"affects": {"types": ["Creature"]}}, {"affects_player": "you"}, {"amount": 1}],
    )
    def test_a_filter_nothing_reads(self, extra):
        with pytest.raises(DslError, match="reaches all damage"):
            compile_card(CardModel.model_validate(static_probe({"effect": "damage_cant_be_prevented", **extra})))
