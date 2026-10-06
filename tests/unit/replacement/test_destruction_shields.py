"""Regeneration and totem armor — one mechanism, replacing a destruction.

    Regeneration (701.15) — "The next time this permanent would be destroyed
    this turn, instead tap it, remove it from combat, and remove all damage
    from it."
    Totem armor (702.88a) — "If enchanted permanent would be destroyed, instead
    remove all damage from it and destroy this Aura."

Both were filed against the replacement whitelist, and both belong somewhere
else for the same reason wither does: that whitelist is about a permanent
**entering** the battlefield, and this is the moment one leaves. Every route to
a destruction — the lethal-damage state-based action, the `destroy` op,
deathtouch — already goes through `zones.destroy`, so one check there is the
whole implementation.

They are two mechanisms rather than one with a parameter, and the tests below
are mostly about where they differ:

|  | regeneration | totem armor |
|---|---|---|
| lives on | the permanent, as a spent-once shield | the **Aura**, as a keyword |
| also does | taps it, removes it from combat | destroys the Aura |
| lasts | until end of turn | as long as the Aura does |

Two orderings are load-bearing and neither is visible on a board:

- **Regeneration is checked first.** A regenerating creature never leaves the
  battlefield, so nothing has happened for the Aura to replace; the other way
  round, the Aura is eaten protecting a creature that was going to survive.
- **The shield expires at cleanup.** One that survived the turn would make every
  regenerator indestructible from the first time its ability was used, and the
  board would look identical.

Neither saves a creature from **0 toughness** or from sacrifice, which is not an
extra rule here but the absence of one: those do not destroy, so they never
reach this function.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader.effects import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError
from automtg.engine.objects import MINUS_ONE
from automtg.engine.primitives import add_counters, attach
from automtg.engine.zones import destroy, sacrifice
from tests.conftest import only_oid, pass_until

FOREST = "forest"
TROLL = "t_regenerator"
AURA = "t_totem_armor"
BEAR = "t_bear"


def board(builder, *cards: str):
    game = builder(players=2).battlefield(0, [FOREST] * 3).battlefield(0, list(cards)).build(
        advance=False
    )
    return game


def shield(game, oid: int, amount: int = 1) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    gen = OPS["regenerate"](
        ctx,
        {"op": "regenerate", "amount": {"const": amount},
         "objects": {"zone": "battlefield", "self_only": True}},
    )
    with contextlib.suppress(StopIteration):
        next(gen)


class TestRegeneration:
    def test_a_shield_stops_the_destruction(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)

        assert destroy(game.state, troll) is False
        assert game.state.objects[troll].zone is Zone.BATTLEFIELD

    def test_it_taps_the_creature(self, builder):
        """701.15a, and it is the cost of the save rather than decoration."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)
        destroy(game.state, troll)

        assert game.state.objects[troll].tapped

    def test_it_removes_the_damage(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        game.state.objects[troll].damage = 2
        game.state.objects[troll].deathtouched = True
        shield(game, troll)
        destroy(game.state, troll)

        assert game.state.objects[troll].damage == 0
        assert game.state.objects[troll].deathtouched is False

    def test_a_shield_is_spent_by_one_destruction(self, builder):
        """"The **next** time" — the second one gets through."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)

        destroy(game.state, troll)
        assert destroy(game.state, troll) is True
        assert game.state.objects[troll].zone is Zone.GRAVEYARD

    def test_two_shields_survive_two_destructions(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll, amount=2)

        destroy(game.state, troll)
        destroy(game.state, troll)

        assert game.state.objects[troll].zone is Zone.BATTLEFIELD

    def test_it_does_not_stop_a_sacrifice(self, builder):
        """Not an extra rule: sacrificing does not destroy, so it never asks."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)

        sacrifice(game.state, troll)

        assert game.state.objects[troll].zone is Zone.GRAVEYARD

    def test_the_shield_expires_at_cleanup(self, builder):
        """One that survived the turn would make every regenerator indestructible."""
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 3)
            .battlefield(0, [TROLL])
            .library(0, [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        troll = only_oid(game, TROLL)
        shield(game, troll)
        assert game.state.objects[troll].regeneration_shields == 1

        pass_until(game, lambda g: g.state.turn >= 2)

        assert game.state.objects[troll].regeneration_shields == 0


class TestTotemArmor:
    def _enchanted(self, builder):
        game = board(builder, BEAR, AURA)
        bear = only_oid(game, BEAR)
        aura = only_oid(game, AURA)
        attach(game.state, aura, bear)
        return game, bear, aura

    def test_the_aura_dies_instead(self, builder):
        game, bear, aura = self._enchanted(builder)

        assert destroy(game.state, bear) is False

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[aura].zone is Zone.GRAVEYARD

    def test_the_damage_is_removed(self, builder):
        game, bear, _ = self._enchanted(builder)
        game.state.objects[bear].damage = 3

        destroy(game.state, bear)

        assert game.state.objects[bear].damage == 0

    def test_it_does_not_tap_the_creature(self, builder):
        """The half that separates it from regeneration."""
        game, bear, _ = self._enchanted(builder)
        destroy(game.state, bear)
        assert not game.state.objects[bear].tapped

    def test_the_creature_is_unprotected_afterwards(self, builder):
        game, bear, _ = self._enchanted(builder)
        destroy(game.state, bear)

        assert destroy(game.state, bear) is True
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_an_unattached_aura_protects_nobody(self, builder):
        game = board(builder, BEAR, AURA)
        bear = only_oid(game, BEAR)

        assert destroy(game.state, bear) is True

    def test_it_does_not_save_a_creature_from_zero_toughness(self, builder):
        """-1/-1 counters are not a destruction, so nothing here is consulted.

        The state-based action for zero toughness *moves* the creature rather
        than destroying it (704.5f), so it never reaches `destroy` and the Aura
        is never offered the chance to replace anything -- it simply falls off
        and is binned as an Aura attached to nothing.
        """
        from automtg.engine import sba

        game, bear, aura = self._enchanted(builder)
        add_counters(game.state, bear, MINUS_ONE, 5)

        sba.run(game.state)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[aura].zone is Zone.GRAVEYARD, "it fell off, unspent"


class TestTheOrdering:
    def test_regeneration_is_spent_before_the_aura(self, builder):
        """A regenerating creature never leaves, so the Aura has nothing to replace."""
        game = board(builder, TROLL, AURA)
        troll = only_oid(game, TROLL)
        aura = only_oid(game, AURA)
        attach(game.state, aura, troll)
        shield(game, troll)

        destroy(game.state, troll)

        assert game.state.objects[troll].zone is Zone.BATTLEFIELD
        assert game.state.objects[aura].zone is Zone.BATTLEFIELD, "not spent"
        assert game.state.objects[troll].regeneration_shields == 0, "the shield was"


class TestIndestructibleStillWins:
    def test_neither_shield_is_spent_on_an_indestructible_permanent(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)
        game.state.objects[troll].granted_keywords.add("indestructible")
        game.state.bump_chars()

        assert destroy(game.state, troll) is False
        assert game.state.objects[troll].regeneration_shields == 1, "nothing to replace"


class TestTheLoaderGuard:
    def test_a_well_formed_regenerate_loads(self):
        _validate_effect(
            {"op": "regenerate", "objects": {"self_only": True}}, "test", {}
        )

    def test_omitting_objects_is_refused(self):
        with pytest.raises(DslError, match="regenerate needs 'objects'"):
            _validate_effect({"op": "regenerate"}, "test", {})
