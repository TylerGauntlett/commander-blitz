"""Lands that become creatures for a turn.

"Becomes a 4/4 Elemental creature until end of turn. It's still a land." Two
halves matter and both are easy to get wrong:

- **Still a land.** An animation that *replaced* the printed types would take a
  Celestial Colonnade's mana ability away for the turn it was animated, which is
  the opposite of what the card does.
- **A base P/T, not a pump.** The existing `set_pt` op is a compensating pump
  over whatever the permanent's power happens to be at that moment; that is fine
  for the cards it was written for, and wrong here, because a manland is
  routinely animated and then given a counter or stood next to an anthem.

Summoning sickness needs no code of its own -- `GameObject.summoning_sick` is
`entered_turn >= turn`, so a land played this turn cannot attack after animating
and one that has been down since last turn can. That is asserted here anyway,
because it is the thing a player would notice first if it broke.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.costs import mana_sources
from automtg.engine.enums import ActionKind, Step
from automtg.engine.primitives import add_counters, animate, pump
from tests.conftest import pass_until


def a_forest(builder, *, sick: bool = False):
    """One Forest on the battlefield, and its oid.

    ``sick`` is applied after ``build`` rather than through the builder's own
    flag: the builder sets ``entered_turn`` relative to the turn it is
    *describing*, and building then auto-passes a turn forward, so the flag alone
    leaves the land un-sick.
    """
    game = builder(players=2).battlefield(0, ["forest"]).build()
    land = game.state.battlefield[0]
    if sick:
        game.state.objects[land].entered_turn = game.state.turn
    return game, land


class TestWhatItBecomes:
    def test_it_is_a_creature_and_still_a_land(self, builder):
        game, land = a_forest(builder)
        animate(game.state, land, 3, 3, subtypes=["Elemental"])

        c = chars(game.state, land)
        assert "Creature" in c.types
        assert "Land" in c.types, "'it's still a land' is the default, not an option"
        assert "Elemental" in c.subtypes
        assert "Forest" in c.subtypes, "the printed subtype survives too"
        assert (c.power, c.toughness) == (3, 3)

    def test_it_keeps_making_mana(self, builder):
        """The mana ability is why anybody plays a creature-land over a Grizzly Bears."""
        game, land = a_forest(builder)
        animate(game.state, land, 3, 3)
        assert len(mana_sources(game.state, 0)) == 1

    def test_a_freshly_played_animated_land_cannot_tap_for_mana(self, builder):
        """It is a creature now, so summoning sickness reaches its mana ability."""
        game, land = a_forest(builder, sick=True)
        assert len(mana_sources(game.state, 0)) == 1
        animate(game.state, land, 3, 3)
        assert mana_sources(game.state, 0) == []

    def test_it_can_be_given_colours_and_keywords_are_separate(self, builder):
        game, land = a_forest(builder)
        animate(game.state, land, 4, 4, colors=["W", "U"])
        assert chars(game.state, land).colors == frozenset({"W", "U"})

    def test_animating_twice_takes_the_later_size(self, builder):
        game, land = a_forest(builder)
        animate(game.state, land, 3, 3)
        animate(game.state, land, 1, 1)
        assert (chars(game.state, land).power, chars(game.state, land).toughness) == (1, 1)


class TestItIsABaseValue:
    """Everything that modifies P/T must layer on top, not be cancelled."""

    def test_a_counter_adds_to_the_animated_size(self, builder):
        game, land = a_forest(builder)
        animate(game.state, land, 3, 3)
        add_counters(game.state, land, "+1/+1", 1)

        c = chars(game.state, land)
        assert (c.power, c.toughness) == (4, 4)

    def test_a_counter_placed_before_the_animation_still_counts(self, builder):
        """Order of events must not change the answer: the animation is a base value."""
        game, land = a_forest(builder)
        add_counters(game.state, land, "+1/+1", 1)
        animate(game.state, land, 3, 3)

        c = chars(game.state, land)
        assert (c.power, c.toughness) == (4, 4)

    def test_a_pump_adds_to_the_animated_size(self, builder):
        game, land = a_forest(builder)
        animate(game.state, land, 3, 3)
        pump(game.state, land, 2, 0)

        c = chars(game.state, land)
        assert (c.power, c.toughness) == (5, 3)


class TestItWearsOff:
    def test_cleanup_takes_it_away(self, builder):
        game, land = a_forest(builder)
        animate(game.state, land, 3, 3, subtypes=["Elemental"])
        turn = game.state.turn

        pass_until(game, lambda g: g.state.turn > turn)

        c = chars(game.state, land)
        assert "Creature" not in c.types
        assert "Elemental" not in c.subtypes
        assert (c.power, c.toughness) == (0, 0)
        assert "Land" in c.types


class TestCombat:
    """Animated at our own declare-attackers step, which is when it happens.

    A manland is held up for the opponent's turn and animated the moment its
    controller is ready to swing, so that is the position to assert against.
    """

    def at_our_combat(self, builder):
        """A bear stands beside the land purely so the step happens at all.

        With nothing able to attack, the engine skips declare-attackers
        entirely and the game passes out to the turn cap -- so a test that
        animates *after* arriving would never arrive.
        """
        game = builder(players=2).battlefield(0, ["forest", "mardu_hateblade"]).build()
        pass_until(
            game,
            lambda g: g.state.step is Step.DECLARE_ATTACKERS and g.state.active_idx == 0,
        )
        assert game.pending() is not None, "the position should be a live decision"
        return game, game.state.battlefield[0]

    def attacks(self, game, oid: int) -> bool:
        return any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == oid
            for a in game.legal_actions()
        )

    def test_a_land_down_since_last_turn_can_attack_once_animated(self, builder):
        game, land = self.at_our_combat(builder)
        animate(game.state, land, 3, 3)
        assert self.attacks(game, land)

    def test_a_land_played_this_turn_cannot(self, builder):
        game, land = self.at_our_combat(builder)
        game.state.objects[land].entered_turn = game.state.turn
        animate(game.state, land, 3, 3)
        assert not self.attacks(game, land)

    def test_an_unanimated_land_is_not_offered_at_all(self, builder):
        game, land = self.at_our_combat(builder)
        assert not self.attacks(game, land)
