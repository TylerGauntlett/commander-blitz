"""`prevent_combat_damage` -- a Fog keyed to the damage's source.

    Arachnogenesis -- "Create X 1/2 green Spider creature tokens with reach,
    where X is the number of creatures attacking you. Prevent all combat damage
    that would be dealt this turn by non-Spider creatures."

615.1: a prevention applies to damage as it would be dealt, so "by non-Spider
creatures" is asked of the dealer then, on its current characteristics. The
near misses each answer a different question: `prevent_damage` shields a seat
and stops burn too; `prevent_damage_permanent` shields objects chosen at
resolution, so a creature entering later in the turn would hit for full.

What the card is for is the asymmetry: the attackers' damage is prevented and
the Spiders' is not, so they block and kill.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent, damage_player
from commanderblitz.engine.temp_effects import clear_combat_fogs
from commanderblitz.engine.zones import move_object

BEAR = "t_bear"
SPIDER = "spider_1_2_g_reach"
NON_SPIDER = {"types": ["Creature"], "not_subtypes": ["Spider"]}


def board(builder):
    game = (
        builder(players=2)
        .battlefield(0, ["forest", SPIDER])
        .battlefield(1, [BEAR, BEAR])
        .hand(1, [BEAR])
        .library(0, ["forest"] * 5)
        .library(1, ["forest"] * 5)
        .build(advance=False)
    )
    return game


def fog(game, by=NON_SPIDER) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    spec = {"op": "prevent_combat_damage", "duration": "this_turn"}
    if by is not None:
        spec["by"] = by
    for _ in execute_one(ctx, spec):  # pragma: no cover - it asks nothing
        raise AssertionError("prevent_combat_damage asked a decision")


def oids(game, pid: int, def_id: str) -> list[int]:
    return [o.oid for o in game.state.battlefield_objects(pid) if o.def_id == def_id]


class TestItIsKeyedToTheDealer:
    def test_a_non_spider_deals_no_combat_damage(self, builder):
        game = board(builder)
        fog(game)
        bear = oids(game, 1, BEAR)[0]

        assert damage_player(game.state, 0, 2, bear, is_combat=True) == 0

    def test_a_spider_still_deals_its_damage(self, builder):
        game = board(builder)
        fog(game)
        spider, bear = oids(game, 0, SPIDER)[0], oids(game, 1, BEAR)[0]

        damage_permanent(game.state, bear, 1, spider, is_combat=True)

        assert game.state.objects[bear].damage == 1

    def test_damage_to_a_spider_by_a_bear_is_prevented(self, builder):
        game = board(builder)
        fog(game)
        spider, bear = oids(game, 0, SPIDER)[0], oids(game, 1, BEAR)[0]

        damage_permanent(game.state, spider, 2, bear, is_combat=True)

        assert game.state.objects[spider].damage == 0


class TestOnlyCombatDamage:
    def test_noncombat_damage_is_not_prevented(self, builder):
        game = board(builder)
        fog(game)
        bear = oids(game, 1, BEAR)[0]
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, bear, is_combat=False)

        assert game.state.players[0].life == life - 2


class TestItIsAskedAsTheDamageIsDealt:
    def test_a_creature_that_arrives_later_is_covered(self, builder):
        game = board(builder)
        fog(game)
        late = game.state.players[1].hand[0]
        move_object(game.state, late, Zone.BATTLEFIELD, to_player=1)

        assert damage_player(game.state, 0, 2, late, is_combat=True) == 0

    def test_with_no_filter_every_source_is_fogged(self, builder):
        game = board(builder)
        fog(game, by=None)
        spider, bear = oids(game, 0, SPIDER)[0], oids(game, 1, BEAR)[0]

        damage_permanent(game.state, bear, 1, spider, is_combat=True)

        assert game.state.objects[bear].damage == 0


class TestItWearsOff:
    def test_cleanup_ends_it(self, builder):
        game = board(builder)
        fog(game)
        clear_combat_fogs(game.state, "this_turn")
        bear = oids(game, 1, BEAR)[0]
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, bear, is_combat=True)

        assert game.state.players[0].life == life - 2


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {"id": "t_fog_probe", "name": "Fog Probe", "mana_cost": "{G}",
             "types": ["Instant"], "spell_effects": [effect]}
        )

    def test_it_loads(self):
        compile_card(self._card({"op": "prevent_combat_damage", "duration": "this_turn",
                                 "by": NON_SPIDER}))

    def test_a_duration_is_required(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(self._card({"op": "prevent_combat_damage"}))

    def test_an_unknown_filter_key_is_refused(self):
        with pytest.raises(DslError, match="mean nothing there"):
            compile_card(self._card({"op": "prevent_combat_damage", "duration": "this_turn",
                                     "by": {"target": "t1"}}))
