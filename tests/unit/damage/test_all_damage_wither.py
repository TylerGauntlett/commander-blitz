"""All damage dealt as though its source had wither -- 702.80a, 702.80b.

Everlasting Torment is the witness: "All damage is dealt as though its source
had wither." Every source, not only permanents: a `grant_keyword` static would
reach the creatures its `affects` matches and leave a Lightning Bolt marking
damage as normal, and an ability whose source has already left the battlefield
would have no keyword to read at all. So the static is asked where wither
itself is read, `primitives.damage_permanent`.

It is still damage (702.80b only changes where it lands): `DAMAGE_DEALT`
fires with the amount, and damage to a player is life loss exactly as a wither
creature's is. A planeswalker still loses loyalty (306.8).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import MINUS_ONE
from commanderblitz.engine.player_statics import all_damage_withers
from commanderblitz.engine.primitives import damage_permanent, damage_player
from tests.conftest import only_oid, static_probe

TORMENT = "t_all_wither"  # All damage is dealt as though its source had wither.
BEAR = "t_pc_bear"
OGRE = "t_pc_ogre"  # a red 3/3 with no wither


def board(builder, *, torment: bool = True):
    return (
        builder(players=2)
        .battlefield(0, [BEAR] + ([TORMENT] if torment else []))
        .battlefield(1, [OGRE])
        .life(0, 40)
        .build(advance=False)
    )


class TestDamageToACreature:
    def test_it_is_minus_one_counters(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        damage_permanent(game.state, bear, 1, only_oid(game, OGRE, 1))
        obj = game.state.objects[bear]
        assert obj.counter(MINUS_ONE) == 1
        assert obj.damage == 0

    def test_a_source_off_the_battlefield_too(self, builder):
        """A spell, or an ability whose source has gone: no keyword to read."""
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        damage_permanent(game.state, bear, 1, None)
        assert game.state.objects[bear].counter(MINUS_ONE) == 1

    def test_it_is_still_damage(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        mark = len(game.state.events)
        damage_permanent(game.state, bear, 1, only_oid(game, OGRE, 1))
        dealt = [e for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert [e.data["amount"] for e in dealt] == [1]

    def test_without_it_damage_is_marked(self, builder):
        game = board(builder, torment=False)
        assert not all_damage_withers(game.state)
        bear = only_oid(game, BEAR, 0)
        damage_permanent(game.state, bear, 1, only_oid(game, OGRE, 1))
        obj = game.state.objects[bear]
        assert (obj.damage, obj.counter(MINUS_ONE)) == (1, 0)


class TestDamageToAPlayer:
    def test_is_life_loss_as_usual(self, builder):
        game = board(builder)
        damage_player(game.state, 0, 3, only_oid(game, OGRE, 1))
        assert game.state.players[0].life == 37
        assert game.state.players[0].poison == 0


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "extra",
        [{"affects": {"types": ["Creature"]}}, {"affects_player": "you"}, {"amount": 1}],
    )
    def test_a_filter_nothing_reads(self, extra):
        with pytest.raises(DslError, match="reaches all damage"):
            compile_card(CardModel.model_validate(static_probe({"effect": "all_damage_wither", **extra})))
