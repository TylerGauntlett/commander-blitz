"""Phasing — "treated as though it does not exist", said by not being in a list.

    "Phasing (This phases in or out before you untap during each of your untap
    steps.)" (702.26)

Phasing was `refused` as changing "how the untap step works for *every*
permanent in the game". It changes it for one permanent, once, and the reason it
is cheap is the same reason the merged pile was: the engine already has a place
for an object that exists and is nowhere.

**702.26c is a list membership.** A phased-out permanent comes out of
`state.battlefield` and stays in `state.objects` — which is exactly where a card
on the stack and a card under a merged permanent already sit. Every walk of the
battlefield therefore misses it: targeting, the state-based actions, the
characteristics statics, the combat declarations and the serializer, none of
which needed a test of their own.

Three rules then come for free, and each would be work in a flag-based
implementation that left the permanent in the list:

| rule | why it holds |
|---|---|
| 702.26c — no zone change, so no leave/enter triggers | nothing moves |
| 702.26c — counters, auras and damage survive | `reset_permanent_state` never runs |
| 702.26f — no summoning sickness on phasing in | `entered_turn` is untouched |

The one thing that does need saying out loud is 702.26e: what is attached to a
phasing permanent phases out **with** it, and comes back with it rather than on
its own controller's schedule. Without that, an Aura would be left alone on the
battlefield and the state-based action would put it in the graveyard — the
permanent would phase back in naked, which is a different card.
"""

from __future__ import annotations

from automtg.engine.enums import Keyword, Zone
from automtg.engine.objects import PLUS_ONE
from automtg.engine.primitives import add_counters, attach
from automtg.engine.turn import _phase
from tests.conftest import only_oid

ISLAND = "island"
PHASER = "t_phaser"      # {2}{U} 3/3 with phasing
AURA = "t_big_aura"      # Enchant creature, +5/+0
BEAR = "t_bear"


def position(builder):
    game = (
        builder(players=2)
        .battlefield(0, [ISLAND] * 4)
        .battlefield(0, [PHASER, BEAR])
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build(advance=False)
    )
    return game, only_oid(game, PHASER)


class TestPhasingOut:
    def test_it_leaves_the_battlefield_list(self, builder):
        game, phaser = position(builder)
        _phase(game.state, 0)

        assert phaser not in game.state.battlefield
        assert game.state.objects[phaser].phased_out

    def test_but_it_is_still_an_object(self, builder):
        """"Treated as though it does not exist" is not "destroyed"."""
        game, phaser = position(builder)
        _phase(game.state, 0)

        assert phaser in game.state.objects
        assert game.state.objects[phaser].zone is Zone.BATTLEFIELD

    def test_nothing_else_phases(self, builder):
        game, _phaser = position(builder)
        bear = only_oid(game, BEAR)
        _phase(game.state, 0)

        assert bear in game.state.battlefield

    def test_an_opponents_untap_step_leaves_it_alone(self, builder):
        """"…during each of *your* untap steps"."""
        game, phaser = position(builder)
        _phase(game.state, 1)

        assert phaser in game.state.battlefield


class TestPhasingBackIn:
    def test_the_next_untap_step_brings_it_back(self, builder):
        game, phaser = position(builder)
        _phase(game.state, 0)
        _phase(game.state, 0)

        assert phaser in game.state.battlefield
        assert not game.state.objects[phaser].phased_out

    def test_it_does_not_come_straight_back_in_the_same_step(self, builder):
        """702.26b is a toggle, so both lists are read before anything moves."""
        game, phaser = position(builder)
        _phase(game.state, 0)

        assert phaser not in game.state.battlefield

    def test_counters_and_damage_survive(self, builder):
        """702.26c: nothing moved, so `reset_permanent_state` never ran."""
        game, phaser = position(builder)
        add_counters(game.state, phaser, PLUS_ONE, 2)
        game.state.objects[phaser].damage = 1

        _phase(game.state, 0)
        _phase(game.state, 0)

        assert game.state.objects[phaser].counter(PLUS_ONE) == 2
        assert game.state.objects[phaser].damage == 1

    def test_it_is_not_summoning_sick(self, builder):
        """702.26f: treated as having been continuously on the battlefield."""
        game, phaser = position(builder)
        entered = game.state.objects[phaser].entered_turn

        _phase(game.state, 0)
        _phase(game.state, 0)

        assert game.state.objects[phaser].entered_turn == entered

    def test_no_zone_change_is_logged_either_way(self, builder):
        game, _phaser = position(builder)
        before = len(game.state.events)

        _phase(game.state, 0)
        _phase(game.state, 0)

        kinds = {e.type for e in game.state.events[before:]}
        assert "zone_change" not in kinds
        assert {"phased_out", "phased_in"} <= kinds


class TestWhatIsAttachedGoesWithIt:
    def _enchanted(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [ISLAND] * 4)
            .battlefield(0, [PHASER, AURA])
            .library(0, [ISLAND] * 20)
            .library(1, [ISLAND] * 20)
            .build(advance=False)
        )
        phaser, aura = only_oid(game, PHASER), only_oid(game, AURA)
        attach(game.state, aura, phaser)
        return game, phaser, aura

    def test_the_aura_phases_out_too(self, builder):
        """702.26e -- and without it the state-based action would bin it."""
        game, _phaser, aura = self._enchanted(builder)
        _phase(game.state, 0)

        assert aura not in game.state.battlefield
        assert game.state.objects[aura].phased_out

    def test_it_is_marked_as_having_done_so_indirectly(self, builder):
        game, phaser, aura = self._enchanted(builder)
        _phase(game.state, 0)

        assert game.state.objects[aura].phased_out_indirectly
        assert not game.state.objects[phaser].phased_out_indirectly

    def test_the_aura_is_not_put_into_the_graveyard(self, builder):
        game, _phaser, aura = self._enchanted(builder)
        _phase(game.state, 0)

        assert game.state.objects[aura].zone is Zone.BATTLEFIELD

    def test_they_come_back_together_and_still_attached(self, builder):
        game, phaser, aura = self._enchanted(builder)
        _phase(game.state, 0)
        _phase(game.state, 0)

        assert phaser in game.state.battlefield
        assert aura in game.state.battlefield
        assert game.state.objects[aura].attached_to == phaser

    def test_the_buff_is_back_with_them(self, builder):
        from automtg.engine.characteristics import chars

        game, phaser, _ = self._enchanted(builder)
        _phase(game.state, 0)
        _phase(game.state, 0)

        assert chars(game.state, phaser).power == 8, "a 3/3 with +5/+0"


class TestTheKeywordIsReal:
    def test_it_is_on_the_card(self, builder):
        game, phaser = position(builder)
        assert Keyword.PHASING.value in game.state.card(phaser).keywords
