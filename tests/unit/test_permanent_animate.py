"""An animation with no duration that *sets* what the permanent is.

"Target artifact or creature loses all abilities and becomes a green Elk
creature with base power and toughness 3/3." Oko, Thief of Crowns' +1.

`animate` was built for creature-lands, and two of its promises are exactly
wrong here:

- **It wore off at cleanup.** Oko prints no duration (611.2a: a continuous
  effect from a resolving ability with no stated duration lasts indefinitely).
  An Elk that turned back into a Wurm at end of turn is a strictly weaker card,
  and the one it is played for is the other direction -- Elking your own Food
  every turn into a permanent 3/3.
- **It added types.** "It's still a land" is every creature-land's sentence;
  Oko's is not. Per the card's rulings the target loses its other colours, card
  types and creature types (layers 4 and 5) and keeps its supertypes: an Oko'd
  Sol Ring is not an artifact (so artifact removal cannot find it), an Oko'd
  Goblin is not a Goblin, and an Oko'd legend is still legendary.

The base P/T half (layer 7b) is the part `animate` already had right: counters,
anthems and pumps land on top of the 3/3. And since two animations each set the
base size, the later one wins (613.7) -- which now has to be decided across the
timed list and the indefinite one, so each carries a timestamp.

`duration` takes the same two spellings `gain_control` does, and a misspelling
is a load error rather than the permanent animation it would otherwise read as.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.costs import mana_sources
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import (
    add_counters,
    animate,
    grant_ability,
    grant_keyword,
    granted_abilities,
    pump,
)
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import only_oid, pass_until

ELK = {
    "op": "animate",
    "power": {"const": 3},
    "toughness": {"const": 3},
    "types": ["Creature"],
    "subtypes": ["Elk"],
    "colors": ["G"],
    "duration": "permanent",
    "exact": True,
    "objects": {"target": "t1"},
}


def a_board(builder, *victims: str, mine: tuple[str, ...] = ()):
    """Player 0's permanents (``mine``) facing player 1's ``victims``."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest", *mine])
        .battlefield(1, list(victims))
        .build()
    )
    return game


def run(game, spec: dict, oid: int) -> None:
    """Resolve one op against ``oid`` as if it were target t1 of player 0's ability."""
    ctx = EffectContext(
        state=game.state, controller=0, targets={"t1": (TargetRef.obj(oid),)}
    )
    gen = OPS[spec["op"]](ctx, spec)
    try:
        decision = next(gen)
    except StopIteration:
        return
    raise AssertionError(f"{spec['op']} asked an unexpected question: {decision}")


def oko(game, oid: int) -> None:
    """The whole +1: loses all abilities, then becomes the Elk."""
    run(game, {"op": "lose_all_abilities", "objects": {"target": "t1"}}, oid)
    run(game, ELK, oid)


class TestWhatItBecomes:
    def test_an_artifact_stops_being_an_artifact(self, builder):
        game = a_board(builder, "sol_ring")
        ring = only_oid(game, "sol_ring")
        oko(game, ring)

        c = chars(game.state, ring)
        assert c.types == frozenset({"Creature"}), "'becomes a creature', not 'also'"
        assert c.subtypes == frozenset({"Elk"})
        assert c.colors == frozenset({"G"})
        assert (c.power, c.toughness) == (3, 3)

    def test_it_loses_its_abilities_and_so_its_mana(self, builder):
        game = a_board(builder, "sol_ring")
        ring = only_oid(game, "sol_ring")
        oko(game, ring)
        assert abilities_of(game.state, ring) == ()
        assert mana_sources(game.state, 1) == [], "an Elk'd Sol Ring taps for nothing"

    def test_a_goblin_stops_being_a_goblin(self, builder):
        game = a_board(builder, "t_goblin")
        goblin = only_oid(game, "t_goblin")
        oko(game, goblin)
        assert chars(game.state, goblin).subtypes == frozenset({"Elk"})
        assert chars(game.state, goblin).colors == frozenset({"G"}), "red is gone"

    def test_a_legend_stays_legendary(self, builder):
        """Supertypes are not a colour, card type or creature type."""
        game = a_board(builder, "t_legend")
        legend = only_oid(game, "t_legend")
        oko(game, legend)
        assert "Legendary" in chars(game.state, legend).supertypes

    def test_a_land_stops_being_a_land(self, builder):
        """The additive reading's opposite: this is not a creature-land."""
        game = a_board(builder, mine=())
        forest = only_oid(game, "forest")
        run(game, ELK, forest)
        c = chars(game.state, forest)
        assert "Land" not in c.types
        assert "Forest" not in c.subtypes, "a Forest subtype goes with the Land type"


class TestItIsABaseValue:
    def test_an_anthem_adds_to_it(self, builder):
        game = a_board(builder, mine=("t_anthem", "t_goblin"))
        goblin = only_oid(game, "t_goblin")
        run(game, ELK, goblin)
        c = chars(game.state, goblin)
        assert (c.power, c.toughness) == (4, 4)

    def test_counters_and_pumps_add_to_it(self, builder):
        game = a_board(builder, "t_goblin")
        goblin = only_oid(game, "t_goblin")
        add_counters(game.state, goblin, "+1/+1", 1)
        run(game, ELK, goblin)
        pump(game.state, goblin, 2, 0)
        c = chars(game.state, goblin)
        assert (c.power, c.toughness) == (6, 4)


class TestTheLaterAnimationSetsTheSize:
    def test_elked_after_a_timed_animation(self, builder):
        game = a_board(builder)
        forest = only_oid(game, "forest")
        animate(game.state, forest, 5, 5)
        run(game, ELK, forest)
        c = chars(game.state, forest)
        assert (c.power, c.toughness) == (3, 3)
        assert "Land" not in c.types, "the later, exact animation replaces the type line"

    def test_animated_after_being_elked(self, builder):
        game = a_board(builder)
        forest = only_oid(game, "forest")
        run(game, ELK, forest)
        animate(game.state, forest, 5, 5)
        assert (chars(game.state, forest).power, chars(game.state, forest).toughness) == (5, 5)

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        c = chars(game.state, forest)
        assert (c.power, c.toughness) == (3, 3), "the timed one ends; the Elk is left"


class TestItLasts:
    def test_cleanup_does_not_take_it_away(self, builder):
        game = a_board(builder, "sol_ring")
        ring = only_oid(game, "sol_ring")
        oko(game, ring)
        turn = game.state.turn

        pass_until(game, lambda g: g.state.turn > turn + 1)

        c = chars(game.state, ring)
        assert c.types == frozenset({"Creature"})
        assert (c.power, c.toughness) == (3, 3)

    def test_a_timed_animation_still_wears_off(self, builder):
        """The default did not move: no creature-land became permanent."""
        game = a_board(builder)
        forest = only_oid(game, "forest")
        run(game, {**ELK, "duration": "until_end_of_turn", "exact": False}, forest)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert "Creature" not in chars(game.state, forest).types

    def test_leaving_the_battlefield_ends_it(self, builder):
        """400.7: the card that comes back is a new object, printed as itself."""
        game = a_board(builder, "t_goblin")
        goblin = only_oid(game, "t_goblin")
        oko(game, goblin)
        move_object(game.state, goblin, Zone.HAND)
        move_object(game.state, goblin, Zone.BATTLEFIELD)
        c = chars(game.state, goblin)
        assert "Goblin" in c.subtypes
        assert "Elk" not in c.subtypes


class TestLosingAbilitiesGoesByTimestamp:
    """613.7: the loss removes what was granted before it, not what came after.

    A Bear given flying until end of turn and then Elked is a 3/3 with no
    flying; one Elked and then given flying flies. The same holds for a grant
    that lasts as long as the permanent does, and for suspend's haste.
    """

    def test_a_keyword_granted_earlier_this_turn_is_lost(self, builder):
        game = a_board(builder, "t_bear")
        bear = only_oid(game, "t_bear")
        grant_keyword(game.state, bear, "flying")
        oko(game, bear)
        assert "flying" not in chars(game.state, bear).keywords

    def test_a_keyword_granted_afterwards_survives(self, builder):
        game = a_board(builder, "t_bear")
        bear = only_oid(game, "t_bear")
        oko(game, bear)
        grant_keyword(game.state, bear, "flying")
        assert "flying" in chars(game.state, bear).keywords

    def test_a_permanent_keyword_granted_earlier_is_lost(self, builder):
        game = a_board(builder, "t_bear")
        bear = only_oid(game, "t_bear")
        grant_keyword(game.state, bear, "haste", permanent=True)
        oko(game, bear)
        assert "haste" not in chars(game.state, bear).keywords

    def test_a_granted_ability_earlier_is_lost(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_ghostform_source"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        bear = only_oid(game, "t_bear")
        grant_ability(game.state, bear, 0, only_oid(game, "t_ghostform_source"), permanent=True)
        assert len(list(granted_abilities(game.state, bear))) == 1
        oko(game, bear)
        assert list(granted_abilities(game.state, bear)) == []

    def test_suspend_haste_is_lost(self, builder):
        game = a_board(builder, "t_bear")
        bear = only_oid(game, "t_bear")
        game.state.objects[bear].hasted_by_suspend = True
        oko(game, bear)
        assert "haste" not in chars(game.state, bear).keywords


class TestTheLoaderGuards:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_elk_maker",
                "name": "Test Elk Maker",
                "mana_cost": "{1}{G}",
                "types": ["Sorcery"],
                "oracle_text": "Target creature becomes a green Elk creature with base "
                "power and toughness 3/3.",
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    def test_the_permanent_exact_form_loads(self):
        compile_card(self._card(ELK))

    def test_a_misspelt_duration_is_refused(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(self._card({**ELK, "duration": "forever"}))

    def test_a_your_turn_keyword_has_no_permanent_form(self):
        with pytest.raises(DslError, match="your_turn_keywords"):
            compile_card(self._card({**ELK, "your_turn_keywords": ["first_strike"]}))

    def test_exact_is_a_flag(self):
        with pytest.raises(DslError, match="exact"):
            compile_card(self._card({**ELK, "exact": "yes"}))
